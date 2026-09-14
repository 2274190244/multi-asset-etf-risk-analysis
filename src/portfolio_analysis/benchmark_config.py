"""Explicit official benchmark identities and conservative comparability gate."""
import json
from pathlib import Path

def load_benchmark_config(path=None):
    """Load UTF-8 benchmark JSON; return mapping with five unique ETF identities.

    Official benchmark and optional research reference remain separate. Missing
    identity evidence or duplicate tickers raise ValueError.
    """
    path=Path(path) if path else Path(__file__).resolve().parents[2]/"config"/"benchmarks.json"
    result=json.loads(path.read_text(encoding="utf-8"))
    tickers=[x["ticker"] for x in result["etfs"]]
    if len(set(tickers))!=len(tickers):
        raise ValueError("Duplicate ETF benchmark mapping")
    for item in result["etfs"]:
        b=item["official_benchmark"]
        if b["definition_status"]=="confirmed" and not b.get("evidence"):
            raise ValueError("Confirmed benchmark requires evidence")
    return result

def assess_comparability(etf,benchmark):
    """Return status/reasons for persisted ETF and benchmark metadata dicts.

    Only verified NAV total return with identical known currency/valuation time
    and a confirmed equity total-return or matching gold-spot basis is eligible.
    Price/unverified market data never silently become NAV tracking analysis.
    Missing data takes precedence over a basis mismatch.
    """
    if etf.get("data_status")!="available" or benchmark.get("data_status")!="available":
        return dict(status="unavailable",reasons=["ETF or benchmark history unavailable"])
    reasons=[]
    if etf.get("value_type")!="nav_total_return":
        reasons.append("ETF series is not NAV total return")
    if etf.get("return_basis_verified") is not True or not etf.get("evidence"):
        reasons.append("ETF return basis or corporate actions not verified")
    if benchmark.get("definition_status")!="confirmed" or not benchmark.get("evidence"):
        reasons.append("Benchmark definition not confirmed")
    kind=benchmark.get("benchmark_type")
    if kind not in {"equity_total_return","gold_spot_close"}:
        reasons.append("Benchmark excludes or differs from total-return basis")
    if kind=="gold_spot_close" and (not etf.get("underlying_contract") or etf.get("underlying_contract")!=benchmark.get("underlying_contract")):
        reasons.append("Gold valuation contract mismatch")
    for field in ("currency","valuation_time"):
        if etf.get(field) in (None,"","unknown") or etf.get(field)!=benchmark.get(field):
            reasons.append(field+" differs or is unknown")
    return dict(status="basis_mismatch" if reasons else "comparable",reasons=reasons)
