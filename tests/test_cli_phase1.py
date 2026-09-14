from pathlib import Path
from portfolio_analysis.cli import main
from portfolio_analysis.pipeline import PipelineResult

def test_cli_quality_only_is_explicit(monkeypatch,capsys):
    monkeypatch.setattr("portfolio_analysis.cli.run_pipeline",lambda *a,**k:PipelineResult(Path("out"),{},{"status":"quality_only","reason":"No reliable window"}))
    assert main(["--output-dir","unused"],session=object())==2
    assert "quality" in capsys.readouterr().out.lower()
