"""Validated offline adapters for saved vendor/official responses; never eval JS."""
import json
import re
import numpy as np
import pandas as pd
from .tracking import _levels

def _series(dates,values):
    result=pd.Series(values,index=pd.DatetimeIndex(dates),name="level",dtype=float)
    _levels(result,"parsed")
    if result.isna().any() or result.empty:
        raise ValueError("Parsed history must contain finite positive observations")
    return result

def parse_csi(text,code):
    """Parse CSI official index-perf JSON to dated closing levels; verify code."""
    payload=json.loads(text)
    if str(payload.get("code"))!="200" or not payload.get("data"):
        raise ValueError("CSI history unavailable")
    rows=payload["data"]
    if any(str(row.get("indexCode"))!=code for row in rows):
        raise ValueError("CSI response identity mismatch")
    return _series(pd.to_datetime([r["tradeDate"] for r in rows],format="%Y%m%d"),
                   [r["close"] for r in rows])

def parse_eastmoney_index(text,code):
    """Parse unadjusted Eastmoney index kline JSON; verify response identity."""
    p=json.loads(text)
    d=p.get("data")
    if p.get("rc")!=0 or not d or d.get("code")!=code or not d.get("klines"):
        raise ValueError("Index unavailable or identity mismatch")
    rows=[r.split(",") for r in d["klines"]]
    return _series(pd.to_datetime([r[0] for r in rows]),[float(r[2]) for r in rows])

def parse_efunds(text,code):
    """Parse official cumulative NAV growth history into 1+growth wealth levels.

    Header field 1 is EnumSourceTypeAccIncomeRatio (NOT cumulative NAV field 3);
    official chart computes (1+growth_end)/(1+growth_start)-1. Return a Series.
    """
    m=re.fullmatch(r'\s*mk_'+re.escape(code)+r'_(?:all|1y)\s*=\s*"([^"]*)"\s*;?\s*',text)
    if not m:
        raise ValueError("Official fund identity/format mismatch")
    lines=m.group(1).split(";")
    header=lines[0].split("_")
    if "0" not in header or "1" not in header:
        raise ValueError("Official cumulative-return field unavailable")
    rows=[r.split("_") for r in lines[1:] if r]
    return _series(pd.to_datetime([r[header.index("0")] for r in rows],format="%Y%m%d"),
                   [1+float(r[header.index("1")]) for r in rows])

def parse_eastmoney_nav(text,code,start=None,end=None):
    """Reconstruct ex-date cash-reinvested NAV wealth from unit NAV and events.

    Return (level Series, cash-event DataFrame). Chinese-midnight milliseconds
    are converted via Asia/Shanghai. Optional inclusive dates limit action
    validation to the study interval. Unknown actions/splits raise, not guess.
    Source event completeness still needs independent verification in metadata.
    No use of rounded equityReturn or additive cumulative NAV.
    """
    identity=re.search(r'var\s+fS_code\s*=\s*["\']([^"\']+)["\']',text)
    match=re.search(r'var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);',text,re.S)
    if not identity or identity.group(1)!=code or not match:
        raise ValueError("NAV identity/format mismatch")
    rows=json.loads(match.group(1))
    dates=pd.to_datetime([r["x"] for r in rows],unit="ms",utc=True).tz_convert("Asia/Shanghai").tz_localize(None).normalize()
    nav=_series(dates,[r["y"] for r in rows])
    mask=np.ones(len(nav),dtype=bool)
    if start is not None:mask &= nav.index>=pd.Timestamp(start)
    if end is not None:mask &= nav.index<=pd.Timestamp(end)
    selected=np.flatnonzero(mask); nav=nav.iloc[selected]
    cash=np.zeros(len(nav));events=[]
    for j,i in enumerate(selected):
        event=rows[i].get("unitMoney","")
        if not event:continue
        m=re.fullmatch(r"分红：每份派现金([0-9]+(?:\.[0-9]+)?)元",event)
        if not m:raise ValueError("Unverified corporate action: "+str(event))
        cash[j]=float(m.group(1))
        events.append(dict(date=dates[i],cash_per_share=cash[j],source_text=event))
    if nav.empty:raise ValueError("NAV history unavailable for requested dates")
    factors=(nav.to_numpy()[1:]+cash[1:])/nav.to_numpy()[:-1]
    wealth=np.r_[1.,np.cumprod(factors)]
    return _series(nav.index,wealth),pd.DataFrame(events,columns=["date","cash_per_share","source_text"])

def merge_levels(series_list):
    """Merge overlapping official snapshots; count identical duplicates, reject conflicts.

    Returns (sorted level Series, audit dict). No inconsistent duplicate wins
    silently; individual inputs must already be sorted and unique.
    """
    for s in series_list:
        _levels(s,"snapshot")
        if s.isna().any():raise ValueError("Missing snapshot levels require explicit alignment, not merging")
    joined=pd.concat(series_list)
    counts=joined.groupby(level=0).nunique(dropna=False)
    if (counts>1).any():raise ValueError("Conflicting snapshot duplicates")
    merged=joined.groupby(level=0).first().sort_index()
    _levels(merged,"merged")
    return merged,dict(identical_duplicates_removed=len(joined)-len(merged))

def parse_sge(text,old_date=None):
    """Parse exact Au99.99 closing levels from official new/old HTML tables.

    Optional old_date must match the dated article heading. Remove commented
    cells before indexing. Return a sorted unique Series, never weighted average.
    """
    import html
    text=re.sub(r"<!--.*?-->","",text,flags=re.S)
    if old_date is not None:
        date=pd.Timestamp(old_date)
        heading=re.search(r"<h1[^>]*>(.*?)</h1>",text,re.S)
        if not heading or f"{date.year}年{date.month}月{date.day}日" not in heading.group(1):
            raise ValueError("SGE article date mismatch")
    rows=[]
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>",text,re.S):
        cells=[html.unescape(re.sub(r"<[^>]+>","",c)).strip() for c in re.findall(r"<td\b[^>]*>(.*?)</td>",row,re.S)]
        if old_date is None and len(cells)>5 and cells[1]=="Au99.99":
            rows.append((pd.Timestamp(cells[0]),float(cells[5].replace(",",""))))
        elif old_date is not None and len(cells)>4 and cells[0]=="Au99.99":
            rows.append((date,float(cells[4].replace(",",""))))
    rows.sort()
    return _series([r[0] for r in rows],[r[1] for r in rows])
