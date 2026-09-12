import pandas as pd
import pytest
from portfolio_analysis.dashboard_data import portfolio_cumulative_returns,portfolio_drawdowns

def test_display_includes_first_evaluation_return_and_initial_peak():
    frame=pd.DataFrame({"date":pd.to_datetime(["2026-01-05","2026-01-06"]),
        "portfolio":["minimum_volatility"]*2,"daily_return":[-.1,-.1]})
    curve=portfolio_cumulative_returns(frame)
    assert curve.cumulative_return.tolist()==pytest.approx([-.1,-.19])
    assert portfolio_drawdowns(curve).drawdown.tolist()==pytest.approx([-.1,-.19])
