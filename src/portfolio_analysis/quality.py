"""Calendar-aware quality reports and explicit contiguous-sample selection."""
import numpy as np
import pandas as pd

def china_sessions(start, end):
    """Return XSHG sessions for China cash ETFs; never approximate with weekdays.

    The current Shanghai/Shenzhen ETF universe shares this holiday schedule.
    Calendar coverage errors are explicit; callers must not silently fall back.
    """
    import exchange_calendars as xc
    start,end=pd.Timestamp(start).normalize(),pd.Timestamp(end).normalize()
    if start>end:
        raise ValueError("start must not be after end")
    calendar=xc.get_calendar("XSHG",start=f"{start.year}-01-01",end=f"{end.year}-12-31")
    sessions=calendar.sessions
    sessions=sessions[(sessions >= start) & (sessions <= end)]
    return sessions.tz_localize(None) if sessions.tz is not None else sessions

def assess_quality(prices, quality, start, end, *, sessions_by_symbol=None, status_by_key=None):
    """Return ticker report, event ledger and longest complete contiguous price block.

    Input: cleaned long prices, cleaning ledger, inclusive request dates, optional
    explicit per-asset calendars and evidence-backed status map (suspension/no_trade).
    Unknown missing observations remain source_missing_unverified, never inferred
    suspension. Nontrading dates are expected absences. Different calendars restrict
    joint analysis; excluded observations are audited. Ties choose earliest block.
    Output never fills prices or concatenates disconnected return intervals.
    """
    symbols=sorted(set(prices.symbol).union(quality.raw_counts))
    calendar_label = "XSHG" if sessions_by_symbol is None else "explicit"
    if sessions_by_symbol is None:
        dates=china_sessions(start,end)
        sessions_by_symbol={s:dates for s in symbols}
    if set(symbols)!=set(sessions_by_symbol):
        raise ValueError("Calendar symbols must match requested assets")
    calendars={s:pd.DatetimeIndex(v).normalize().sort_values().unique()
               for s,v in sessions_by_symbol.items()}
    common=calendars[symbols[0]]
    union=common
    for dates in calendars.values():
        common=common.intersection(dates); union=union.union(dates)
    common=common.sort_values()
    events=list(quality.events)
    status_by_key=status_by_key or {}
    rows=[]
    all_days=pd.date_range(start,end,freq="D")
    for s in symbols:
        g=prices.loc[prices.symbol.eq(s)]
        observed=pd.DatetimeIndex(g.date)
        expected=calendars[s]
        missing=expected.difference(observed)
        for d in missing:
            reason=status_by_key.get((s,d),"source_missing_unverified")
            if reason not in {"suspension","no_trade","source_missing_unverified"}:
                raise ValueError("Unsupported missing-observation status")
            events.append(dict(stage="calendar",ticker=s,date=d,reason=reason,
                               action="exclude_from_contiguous_analysis",affected_rows=1))
        for d in all_days.difference(expected):
            reason="different_asset_calendar" if d in union else "non_trading_day"
            events.append(dict(stage="calendar",ticker=s,date=d,reason=reason,
                               action="expected_absence",affected_rows=0))
        for d in observed.difference(expected):
            events.append(dict(stage="calendar",ticker=s,date=d,reason="unexpected_non_session_price",
                               action="exclude_from_analysis",affected_rows=1))
        # Threshold is only a screening flag; no winsorization or row removal.
        series=g.set_index("date").close.reindex(expected)
        ret=series.pct_change(fill_method=None)
        threshold=.02 if g.asset_class.eq("government_bond").any() else .10
        anomalies=ret.abs().ge(threshold)
        for d in ret.index[anomalies]:
            events.append(dict(stage="returns",ticker=s,date=d,reason="large_absolute_return",
                action="flag_retain",affected_rows=0,value=float(ret[d]),threshold=threshold))
        if "volume" in g:
            for row in g.loc[g.volume.eq(0)].itertuples():
                events.append(dict(stage="calendar",ticker=s,date=row.date,reason="no_trade",
                    action="retain_reported_close_flag_staleness",affected_rows=0))
        rows.append(dict(ticker=s,first_date=g.date.min(),last_date=g.date.max(),
            observation_count=len(g),expected_observation_count=len(expected),
            missing_count=len(missing),duplicate_count=int(quality.duplicate_counts.get(s,0)),
            coverage=len(expected.intersection(observed))/len(expected) if len(expected) else np.nan,
            anomaly_count=int(anomalies.sum()),anomaly_threshold=threshold,
            input_rows=int(quality.raw_counts.get(s,0)),removed_rows=int(quality.raw_counts.get(s,0))-len(g),
            calendar=calendar_label))
    wide=prices.pivot(index="date",columns="symbol",values="close").reindex(index=union.sort_values(),columns=symbols)
    complete=wide.notna().all(axis=1) & wide.index.isin(common)
    best=[]; current=[]
    for d,ok in complete.items():
        if ok:
            current.append(d)
            if len(current)>len(best): best=current.copy()
        else: current=[]
    selected=pd.DatetimeIndex(best)
    # Record exclusions for every asset, including unaffected assets losing valid rows.
    for row in prices.itertuples():
        if row.date not in selected:
            events.append(dict(stage="sample_selection",ticker=row.symbol,date=row.date,
                reason="outside_selected_contiguous_window",action="exclude_from_analysis",affected_rows=1))
    if len(selected):
        for s in symbols:
            events.append(dict(stage="returns",ticker=s,date=selected[0],reason="initial_price_no_previous",
                action="no_return",affected_rows=1))
    report=pd.DataFrame(rows)
    report["selected_price_count"]=len(selected)
    report["selected_return_count"]=max(0,len(selected)-1)
    report["selected_start"]=selected.min() if len(selected) else pd.NaT
    report["selected_end"]=selected.max() if len(selected) else pd.NaT
    report["coverage_basis"]="expected exchange sessions in requested interval"
    event_frame=pd.DataFrame(events,columns=["stage","row_id","ticker","date","reason","action","affected_rows","value","threshold"])
    return report,event_frame,wide.reindex(selected)
