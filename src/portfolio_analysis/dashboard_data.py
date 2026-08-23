from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd


class DashboardDataError(ValueError):
    """Raised when the verified dashboard package cannot be used safely."""


@dataclass(frozen=True)
class CsvSpec:
    relative_path: str
    required_columns: tuple[str, ...]
    date_columns: tuple[str, ...] = ()
    numeric_columns: tuple[str, ...] = ()
    nullable_numeric_columns: tuple[str, ...] = ()


CSV_SPECS = {
    "prices": CsvSpec(
        "powerbi/prices.csv",
        ("date", "symbol", "asset_name", "asset_class", "close"),
        date_columns=("date",),
        numeric_columns=("close",),
    ),
    "asset_metrics": CsvSpec(
        "powerbi/asset_metrics.csv",
        (
            "symbol",
            "asset_name",
            "asset_class",
            "annualized_return",
            "annualized_volatility",
            "sharpe_ratio",
            "maximum_drawdown",
            "historical_var",
        ),
        numeric_columns=(
            "annualized_return",
            "annualized_volatility",
            "sharpe_ratio",
            "maximum_drawdown",
            "historical_var",
        ),
    ),
    "portfolio_timeseries": CsvSpec(
        "powerbi/portfolio_timeseries.csv",
        (
            "date",
            "portfolio",
            "daily_return",
            "cumulative_return",
            "rolling_volatility_20d",
        ),
        date_columns=("date",),
        numeric_columns=("daily_return", "cumulative_return", "rolling_volatility_20d"),
        nullable_numeric_columns=("rolling_volatility_20d",),
    ),
    "portfolio_metrics": CsvSpec(
        "powerbi/portfolio_metrics.csv",
        (
            "portfolio",
            "annualized_return",
            "annualized_volatility",
            "sharpe_ratio",
            "maximum_drawdown",
            "historical_var",
        ),
        numeric_columns=(
            "annualized_return",
            "annualized_volatility",
            "sharpe_ratio",
            "maximum_drawdown",
            "historical_var",
        ),
    ),
    "correlation_matrix": CsvSpec(
        "powerbi/correlation_matrix.csv",
        ("symbol", "correlated_symbol", "correlation"),
        numeric_columns=("correlation",),
    ),
    "portfolio_weights": CsvSpec(
        "powerbi/portfolio_weights.csv",
        ("portfolio", "symbol", "weight"),
        numeric_columns=("weight",),
    ),
    "data_quality": CsvSpec(
        "powerbi/data_quality.csv",
        (
            "input_rows",
            "output_rows",
            "duplicates_removed",
            "invalid_prices_removed",
            "missing_close_removed",
            "start_date",
            "end_date",
            "shared_window_rows",
            "shared_window_start",
            "shared_window_end",
        ),
        date_columns=("start_date", "end_date", "shared_window_start", "shared_window_end"),
        numeric_columns=(
            "input_rows",
            "output_rows",
            "duplicates_removed",
            "invalid_prices_removed",
            "missing_close_removed",
            "shared_window_rows",
        ),
    ),
}


@dataclass(frozen=True)
class DashboardData:
    prices: pd.DataFrame
    asset_metrics: pd.DataFrame
    portfolio_timeseries: pd.DataFrame
    portfolio_metrics: pd.DataFrame
    correlation_matrix: pd.DataFrame
    portfolio_weights: pd.DataFrame
    data_quality: pd.DataFrame
    resume_facts: dict

    @property
    def asset_names(self) -> dict[str, str]:
        assets = self.asset_metrics[["symbol", "asset_name"]].drop_duplicates("symbol")
        return dict(zip(assets["symbol"], assets["asset_name"], strict=True))


def _load_csv(package_root: Path, spec: CsvSpec) -> pd.DataFrame:
    path = package_root / spec.relative_path
    if not path.is_file():
        raise DashboardDataError(f"缺少看板数据文件：{spec.relative_path}")

    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as exc:
        raise DashboardDataError(f"无法读取 {spec.relative_path}：{exc}") from exc

    missing = [column for column in spec.required_columns if column not in frame.columns]
    if missing:
        raise DashboardDataError(
            f"{spec.relative_path} 缺少必需字段：{', '.join(missing)}"
        )

    if frame.empty:
        raise DashboardDataError(f"{spec.relative_path} 没有可用数据")

    for column in spec.date_columns:
        parsed = pd.to_datetime(frame[column], errors="coerce", format="mixed")
        if parsed.isna().any():
            raise DashboardDataError(
                f"{spec.relative_path} 的 {column} 字段包含无法解析的日期"
            )
        frame[column] = parsed

    for column in spec.numeric_columns:
        converted = pd.to_numeric(frame[column], errors="coerce")
        if column not in spec.nullable_numeric_columns and converted.isna().any():
            raise DashboardDataError(
                f"{spec.relative_path} 的 {column} 字段包含缺失或非数值内容"
            )
        finite_values = converted.dropna().to_numpy(dtype=float)
        if not np.isfinite(finite_values).all():
            raise DashboardDataError(
                f"{spec.relative_path} 的 {column} 字段包含非有限数值"
            )
        frame[column] = converted

    parsed_columns = set(spec.date_columns) | set(spec.numeric_columns)
    for column in set(spec.required_columns).difference(parsed_columns):
        values = frame[column]
        if values.isna().any() or values.astype(str).str.strip().eq("").any():
            raise DashboardDataError(
                f"{spec.relative_path} 的 {column} 字段包含缺失或空白内容"
            )

    return frame


def _load_resume_facts(package_root: Path) -> dict:
    path = package_root / "resume_facts.json"
    if not path.is_file():
        raise DashboardDataError("缺少看板数据文件：resume_facts.json")

    try:
        facts = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardDataError(f"无法读取 resume_facts.json：{exc}") from exc

    required = {
        "price_rows",
        "asset_count",
        "risk_metric_count",
        "start_date",
        "end_date",
        "portfolio_count",
    }
    missing = sorted(required.difference(facts))
    if missing:
        raise DashboardDataError(
            f"resume_facts.json 缺少必需字段：{', '.join(missing)}"
        )

    for field in ("price_rows", "asset_count", "risk_metric_count", "portfolio_count"):
        value = facts[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise DashboardDataError(f"resume_facts.json 的 {field} 必须是非负整数")

    for field in ("start_date", "end_date"):
        if pd.isna(pd.to_datetime(facts[field], errors="coerce")):
            raise DashboardDataError(f"resume_facts.json 的 {field} 不是有效日期")

    return facts


def load_dashboard_data(project_root: str | Path) -> DashboardData:
    package_root = Path(project_root) / "output_verified"
    frames = {
        name: _load_csv(package_root, spec) for name, spec in CSV_SPECS.items()
    }
    facts = _load_resume_facts(package_root)
    observed = {
        "price_rows": len(frames["prices"]),
        "asset_count": frames["asset_metrics"]["symbol"].nunique(),
        "risk_metric_count": 5,
        "portfolio_count": frames["portfolio_metrics"]["portfolio"].nunique(),
        "start_date": frames["prices"]["date"].min().date().isoformat(),
        "end_date": frames["prices"]["date"].max().date().isoformat(),
    }
    for field, observed_value in observed.items():
        if facts[field] != observed_value:
            raise DashboardDataError(
                f"resume_facts.json 的 {field} 与验证 CSV 不一致："
                f"{facts[field]} != {observed_value}"
            )

    return DashboardData(
        **frames,
        resume_facts=facts,
    )


def asset_cumulative_returns(
    prices: pd.DataFrame,
    symbols: list[str] | tuple[str, ...] | None = None,
    start_date=None,
    end_date=None,
) -> pd.DataFrame:
    selected = list(prices["symbol"].drop_duplicates()) if symbols is None else list(symbols)
    if not selected:
        raise DashboardDataError("筛选条件没有选择任何 ETF")

    start = prices["date"].min() if start_date is None else pd.Timestamp(start_date)
    end = prices["date"].max() if end_date is None else pd.Timestamp(end_date)
    if start > end:
        raise DashboardDataError("筛选条件的开始日期不能晚于结束日期")

    filtered = prices.loc[
        prices["symbol"].isin(selected) & prices["date"].between(start, end)
    ].copy()
    if filtered.empty:
        raise DashboardDataError("筛选条件下没有可用价格数据")

    filtered = filtered.sort_values(["symbol", "date"])
    first_close = filtered.groupby("symbol")["close"].transform("first")
    filtered["cumulative_return"] = filtered["close"] / first_close - 1.0
    return filtered[
        ["date", "symbol", "asset_name", "asset_class", "cumulative_return"]
    ].reset_index(drop=True)


def portfolio_cumulative_returns(
    portfolio_timeseries: pd.DataFrame,
    start_date=None,
    end_date=None,
) -> pd.DataFrame:
    required = {"date", "portfolio", "daily_return"}
    missing = sorted(required.difference(portfolio_timeseries.columns))
    if missing:
        raise DashboardDataError(f"组合时间序列缺少字段：{', '.join(missing)}")

    start = (
        portfolio_timeseries["date"].min()
        if start_date is None
        else pd.Timestamp(start_date)
    )
    end = (
        portfolio_timeseries["date"].max()
        if end_date is None
        else pd.Timestamp(end_date)
    )
    if start > end:
        raise DashboardDataError("筛选条件的开始日期不能晚于结束日期")

    result = portfolio_timeseries.loc[
        portfolio_timeseries["date"].between(start, end),
        ["date", "portfolio", "daily_return"],
    ].copy()
    if result.empty:
        raise DashboardDataError("所选日期范围内没有组合日收益记录")
    if (result["daily_return"] <= -1.0).any() or not np.isfinite(
        result["daily_return"]
    ).all():
        raise DashboardDataError("组合日收益包含无法复利的数值")

    result = result.sort_values(["portfolio", "date"])
    growth = (1.0 + result["daily_return"]).groupby(result["portfolio"]).cumprod()
    start_growth = growth.groupby(result["portfolio"]).transform("first")
    result["cumulative_return"] = growth / start_growth - 1.0
    return result.reset_index(drop=True)


def portfolio_drawdowns(portfolio_timeseries: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "portfolio", "cumulative_return"}
    missing = sorted(required.difference(portfolio_timeseries.columns))
    if missing:
        raise DashboardDataError(f"组合时间序列缺少字段：{', '.join(missing)}")

    result = portfolio_timeseries[["date", "portfolio", "cumulative_return"]].copy()
    result = result.sort_values(["portfolio", "date"])
    result["wealth"] = 1.0 + result["cumulative_return"]
    if (result["wealth"] <= 0).any() or not np.isfinite(result["wealth"]).all():
        raise DashboardDataError("组合累计收益无法转换为有效累计财富")

    running_peak = result.groupby("portfolio")["wealth"].cummax()
    result["drawdown"] = (result["wealth"] / running_peak - 1.0).clip(upper=0.0)
    return result[["date", "portfolio", "drawdown"]].reset_index(drop=True)


def correlation_wide(
    correlations: pd.DataFrame, asset_names: dict[str, str]
) -> pd.DataFrame:
    matrix = correlations.pivot(
        index="symbol", columns="correlated_symbol", values="correlation"
    )
    symbols = list(asset_names)
    expected = set(symbols)
    observed_rows = set(matrix.index)
    observed_columns = set(matrix.columns)
    if observed_rows != expected or observed_columns != expected:
        missing = expected.difference(observed_rows.intersection(observed_columns))
        unexpected = observed_rows.union(observed_columns).difference(expected)
        details = []
        if missing:
            details.append(
                "缺少资产："
                + "、".join(asset_names[symbol] for symbol in symbols if symbol in missing)
            )
        if unexpected:
            details.append("包含未知资产：" + "、".join(sorted(unexpected)))
        raise DashboardDataError("相关性矩阵资产集合不完整；" + "；".join(details))

    matrix = matrix.reindex(index=symbols, columns=symbols)
    if matrix.isna().any().any():
        raise DashboardDataError("相关性数据不能构成完整方阵")
    if not np.allclose(matrix.to_numpy(), matrix.to_numpy().T):
        raise DashboardDataError("相关性矩阵不是对称矩阵")
    if not np.allclose(np.diag(matrix), 1.0):
        raise DashboardDataError("相关性矩阵对角线必须为 1")

    labels = [asset_names[symbol] for symbol in symbols]
    matrix.index = labels
    matrix.columns = labels
    return matrix
