from datetime import date
from pathlib import Path

import pytest

from portfolio_analysis.cli import main
from portfolio_analysis.pipeline import PipelineResult


def test_cli_help_requires_a_new_versioned_output_directory(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"], session=object())

    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "must not already exist" in help_text
    assert "output_20260812" in help_text


def test_cli_creates_retrying_session_when_session_is_omitted(
    tmp_path, capsys, monkeypatch
):
    configured_session = object()
    factory_calls = []
    received_sessions = []

    def fake_session_factory():
        factory_calls.append(True)
        return configured_session

    def fake_pipeline(start, end, output_dir, session=None):
        received_sessions.append(session)
        return PipelineResult(
            Path(output_dir),
            {},
            {
                "status": "complete",
                "price_rows": 1,
                "asset_count": 5,
                "portfolio_count": 2,
                "start_date": "2026-01-02",
                "end_date": "2026-01-02",
            },
        )

    monkeypatch.setattr(
        "portfolio_analysis.cli.create_market_session", fake_session_factory
    )
    monkeypatch.setattr("portfolio_analysis.cli.run_pipeline", fake_pipeline)

    exit_code = main(
        ["--output-dir", str(tmp_path / "results")]
    )

    assert exit_code == 0
    assert factory_calls == [True]
    assert received_sessions == [configured_session]
    assert "Complete: 1 price rows" in capsys.readouterr().out


def test_cli_passes_injected_session_and_prints_computed_summary(
    tmp_path, capsys, monkeypatch
):
    injected_session = object()
    calls = []

    def fake_pipeline(start, end, output_dir, session=None):
        calls.append((start, end, Path(output_dir), session))
        return PipelineResult(
            Path(output_dir),
            {},
            {
                "status": "complete",
                "price_rows": 321,
                "asset_count": 5,
                "portfolio_count": 2,
                "start_date": "2026-01-02",
                "end_date": "2026-02-13",
            },
        )

    monkeypatch.setattr("portfolio_analysis.cli.run_pipeline", fake_pipeline)

    exit_code = main(
        [
            "--start",
            "2026-01-01",
            "--end",
            "2026-02-14",
            "--output-dir",
            str(tmp_path / "results"),
        ],
        session=injected_session,
    )

    assert exit_code == 0
    assert calls == [
        (
            date(2026, 1, 1),
            date(2026, 2, 14),
            tmp_path / "results",
            injected_session,
        )
    ]
    assert capsys.readouterr().out.strip() == (
        "Complete: 321 price rows, 5 assets, 2 portfolios, "
        "2026-01-02 to 2026-02-13."
    )


def test_cli_returns_nonzero_and_lists_missing_assets(capsys, monkeypatch):
    def fake_pipeline(start, end, output_dir, session=None):
        return PipelineResult(
            Path(output_dir),
            {"510500.SS": "RuntimeError: unavailable"},
            {"status": "asset_fetch_failed"},
        )

    monkeypatch.setattr("portfolio_analysis.cli.run_pipeline", fake_pipeline)

    exit_code = main(
        ["--start", "2026-01-01", "--end", "2026-02-14"], session=object()
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() == (
        "Pipeline failed: missing 510500.SS (RuntimeError: unavailable)."
    )


def test_cli_removes_request_url_from_http_failure(capsys, monkeypatch):
    def fake_pipeline(start, end, output_dir, session=None):
        return PipelineResult(
            Path(output_dir),
            {
                "510300.SS": (
                    "HTTPError: 429 Client Error: Too Many Requests for url: "
                    "https://query1.finance.yahoo.com/example"
                )
            },
            {"status": "asset_fetch_failed"},
        )

    monkeypatch.setattr("portfolio_analysis.cli.run_pipeline", fake_pipeline)

    exit_code = main(
        ["--start", "2026-01-01", "--end", "2026-02-14"], session=object()
    )

    assert exit_code == 1
    assert capsys.readouterr().err.strip() == (
        "Pipeline failed: missing 510300.SS "
        "(HTTPError: 429 Client Error: Too Many Requests)."
    )
