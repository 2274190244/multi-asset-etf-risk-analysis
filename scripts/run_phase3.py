"""Reproduce Phase 3 from archived responses; no network and no prior output overwrite."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import pandas as pd
from portfolio_analysis.benchmark_config import load_benchmark_config
from portfolio_analysis.benchmark_data import (parse_csi,parse_eastmoney_index,parse_efunds,
    parse_eastmoney_nav,merge_levels,parse_sge)
from portfolio_analysis.quality import china_sessions
from portfolio_analysis.tracking_reporting import analyze_pair,export_tracking

START,END="2023-08-14","2026-08-12"

def main(argv=None):
    """Validate saved source hashes, analyze eight pairs, create an independent report."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=Path("output_phase3"))
    parser.add_argument("--evidence-dir",type=Path,default=Path("docs/audit/phase3"))
    args=parser.parse_args(argv)
    if args.output_dir.exists():parser.error("Output exists; supply a new --output-dir")
    evidence=args.evidence_dir
    records=[]
    for folder in ("discovery","csi_discovery","gold_discovery"):
        for p in sorted((evidence/folder).glob("*.json")):
            if not (p.name.startswith("requests") or p.name.startswith("manifest")):continue
            payload=json.loads(p.read_text(encoding="utf-8"))
            if isinstance(payload,list):
                for r in payload:
                    if not r.get("sha256"):continue
                    filename=Path(r.get("file",r.get("name","")+".raw")).name
                    records.append(dict(r,local_path=str(p.parent/filename)))
    used=[]
    def read(path,basis,source):
        data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
        matches=[r for r in records if Path(r["local_path"]).resolve()==path.resolve() and r["sha256"]==digest]
        if not matches:raise ValueError("No matching source hash manifest: "+str(path))
        rec=matches[-1]
        meta=dict(source=source,price_basis=basis,retrieval_timestamp=rec.get("retrieved_at",rec.get("retrieved_utc",rec.get("utc"))),
                  requested_start=START,requested_end=END,request_url=rec["url"],
                  raw_file=str(path),sha256=digest,
                  date_request_note="Analysis bounds; some provider endpoints return full history. Exact URL retained.")
        if not meta["retrieval_timestamp"]:raise ValueError("Missing retrieval timestamp")
        used.append(meta)
        return data.decode("utf-8"),meta
    config=load_benchmark_config()
    calendar=china_sessions(START,END)
    nav={};nav_meta={};actions=[];nav_audits=[]
    dividends=json.loads((evidence/"csi_discovery/dividend_audit.json").read_text(encoding="utf-8"))
    for item in config["etfs"]:
        ticker=item["ticker"];code=ticker[:6]
        text,origin=read(evidence/"discovery"/("nav"+code+".raw"),"unit_nav_with_cash_action_records","Eastmoney")
        levels,events=parse_eastmoney_nav(text,code,START,END)
        events["ticker"]=ticker
        actions.extend(json.loads(events.to_json(orient="records",date_format="iso")))
        # A known listed cash event must agree with the corroborating announcement.
        corroborated=[r for r in dividends["events"] if r["code"]==code]
        for event in events.itertuples():
            if code in {"510300","510500"} and not any(
                r["ex_date"]==str(event.date.date()) and abs(r["cash_per_unit"]-event.cash_per_share)<1e-12
                for r in corroborated):
                raise ValueError("Cash action not corroborated for "+ticker)
        nav[ticker]=levels
        nav_meta[ticker]=dict(origin,data_status="available",value_type="nav_total_return",
            currency="CNY",valuation_time="equity_close" if code in {"510300","510500","159915"} else "unknown",
            return_basis_verified=code in {"510300","510500","159915"},
            evidence=[origin["request_url"]]+[r["url"] for r in corroborated],
            corporate_action_completeness="Vendor event completeness assumed; listed equity cash events corroborated, absence of unlisted actions not independently certified.",
            reinvestment_convention="Theoretical ex-date cash reinvestment: (NAV_t + cash_t) / NAV_previous; not actual cash payment-date execution.")
        if code=="518880":nav_meta[ticker]["underlying_contract"]="Au99.99"
        nav_audits.append(dict(ticker=ticker,source="Eastmoney unit NAV",observations=len(levels),
            first_date=str(levels.index[0].date()),last_date=str(levels.index[-1].date()),
            non_session_dates=[str(d.date()) for d in levels.index.difference(calendar)],
            missing_sessions=len(calendar.difference(levels.index)),cash_event_count=len(events)))
    # Prefer the fund manager's explicit cumulative-return field to reconstructing unit NAV.
    official=[];official_sources=[]
    for filename in ("efunds_nav.raw","efunds_1y.raw"):
        text,origin=read(evidence/"discovery"/filename,"official_cumulative_nav_growth","E Fund")
        official.append(parse_efunds(text,"159915"));official_sources.append(origin)
    official,merge_audit=merge_levels(official)
    nav["159915.SZ"]=official.loc[START:END]
    nav_meta["159915.SZ"]=dict(official_sources[-1],data_status="available",value_type="nav_total_return",
        currency="CNY",valuation_time="equity_close",return_basis_verified=True,
        evidence=[s["request_url"] for s in official_sources]+["https://www.efunds.com.cn/js/fund_details/product-detail-overview.js?7905e4a6"],
        field="1 + EnumSourceTypeAccIncomeRatio; not additive cumulative NAV",merge_audit=merge_audit)
    indices={};index_meta={}
    for code,filename in {"000300":"probe_3.raw","H00300":"probe_10.raw","000905":"probe_11.raw",
                           "H00905":"probe_12.raw","000140":"probe_13.raw"}.items():
        text,origin=read(evidence/"csi_discovery"/filename,"index_close_"+code,"CSI official")
        indices[code]=parse_csi(text,code);index_meta[code]=origin
    for code,filename in {"399006":"chinext_price.raw","399606":"chinexttr.raw"}.items():
        text,origin=read(evidence/"discovery"/filename,"unadjusted_index_close_"+code,"Eastmoney index history")
        indices[code]=parse_eastmoney_index(text,code);index_meta[code]=origin
    gold=[];gold_meta=[]
    folder=evidence/"gold_discovery"
    for path in sorted(list(folder.glob("sge_202*.raw"))+list(folder.glob("sge_old_202*.raw"))):
        text,origin=read(path,"Au99.99_spot_close_not_weighted_average","Shanghai Gold Exchange official")
        gold.append(parse_sge(text,path.stem[-10:] if path.name.startswith("sge_old_") else None))
        gold_meta.append(origin)
    indices["Au99.99"],gold_merge=merge_levels(gold)
    indices["Au99.99"]=indices["Au99.99"].loc[START:END]
    index_meta["Au99.99"]=dict(source="Shanghai Gold Exchange official",price_basis="Au99.99_spot_close",
        retrieval_timestamp=sorted(s["retrieval_timestamp"] for s in gold_meta)[-1],
        requested_start=START,requested_end=END,evidence_files=[s["raw_file"] for s in gold_meta],
        merge_audit=gold_merge)
    # Calendar union includes actual SGE sessions beyond the equity calendar.
    # XSHG supplies a conservative missing-session reference, not an asserted SGE holiday calendar.
    gold_calendar=calendar.union(indices["Au99.99"].index)
    results=[]
    for item in config["etfs"]:
        ticker=item["ticker"]
        for role,key in (("official","official_benchmark"),("total_return_reference","research_reference")):
            definition=item.get(key)
            if definition is None:continue
            code=definition["code"]
            bm=dict(definition,**index_meta[code],data_status="available",comparison_role=role)
            if code=="Au99.99":
                bm["calendar_status"]="Observed SGE dates union XSHG; independent SGE holiday calendar not verified"
            r=analyze_pair(ticker+"__"+role,nav[ticker],indices[code],nav_meta[ticker],bm,
                           calendar,gold_calendar if code=="Au99.99" else calendar,window=config["rolling_window"])
            r["summary"].update(ticker=ticker,benchmark_code=code,comparison_role=role,
                etf_value_type=nav_meta[ticker]["value_type"],benchmark_type=definition["benchmark_type"])
            results.append(r)
    market_path=Path("output_phase1/powerbi/prices.csv")
    market=pd.read_csv(market_path,parse_dates=["date"])
    market_audit=[]
    for ticker,g in market.groupby("symbol"):
        market_audit.append(dict(ticker=ticker,first_date=str(g.date.min().date()),last_date=str(g.date.max().date()),
             observation_count=len(g),missing_count=int(g.close.isna().sum()),
             duplicate_count=int(g.duplicated(["date","symbol"]).sum()),
             coverage=float(g.date.nunique()/len(calendar)),source=";".join(g.source.unique()),
             price_basis=";".join(g.price_basis.unique()),value_type="market_price_NOT_NAV",
             retrieval_timestamp=";".join(g.retrieval_timestamp.unique()),
             requested_start=str(g.requested_start.iloc[0]),requested_end=str(g.requested_end.iloc[0])))
    metadata=dict(generated_at=datetime.now(timezone.utc).isoformat(),requested_start=START,requested_end=END,
        benchmark_configuration=config,annualization_days=252,ddof=1,rolling_window=63,
        source_manifest=used,corporate_actions=actions,nav_data_quality=nav_audits,
        original_etf_data_audit=market_audit,
        original_market_sha256=hashlib.sha256(market_path.read_bytes()).hexdigest(),
        limitations=dividends["limits"]+[
          "Official mapping history before cited documents not independently exhaustively certified.",
          "510300/510500 NAV total return assumes vendor event completeness; known cash events corroborated.",
          "Gold NAV valuation time unverified; all strict tracking fields suppressed.",
          "Bond clean-price official benchmark differs from reinvested NAV; all strict tracking fields suppressed.",
          "Pairwise longest complete block may differ across ETFs; no common five-ETF ranking sample.",
          "Retrospective research, not point-in-time investable returns; no index construction or trading model."])
    export_tracking(results,args.output_dir,metadata)
    print(pd.DataFrame([r["summary"] for r in results]).to_string(index=False))
    return 0

if __name__=="__main__":raise SystemExit(main())
