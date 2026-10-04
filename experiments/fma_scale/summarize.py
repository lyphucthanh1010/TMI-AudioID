#!/usr/bin/env python3
from pathlib import Path
import csv,glob,json
rows=[]
for f in glob.glob("results/**/result*.json",recursive=True):
    try:
        r=json.loads(Path(f).read_text()); r["source"]=f; rows.append(r)
    except Exception as e: print("skip",f,e)
rows.sort(key=lambda r:(int(r.get("trees",0)),int(r.get("requested_tracks",0))))
keys=["requested_tracks","effective_tracks","trees","status","valid_tracks_total","train_samples","test_queries",
"fit_seconds","peak_rss_mb","tree_arrays_mb","tree_nodes_total","recall_at_1","recall_at_3","recall_at_5","recall_at_10",
"median_true_rank","e2e_correct_rate_top5_verify","e2e_unknown_rate_top5_verify","e2e_false_match_rate_top5_verify",
"rf_query_ms_p50","rf_query_ms_p95","comparator_top5_ms_p50","comparator_top5_ms_p95","error","source"]
Path("summary").mkdir(exist_ok=True)
with open("summary/fma_scale_summary.csv","w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=keys); w.writeheader()
    for r in rows:w.writerow({k:r.get(k,"") for k in keys})
md=["# FMA Small catalog-scale experiment","",
"Each FMA track is one AudioID identity/class. Genre labels are not used.",
"Train windows: 0-10s, 5-15s, 10-20s. Test query: 20-30s.","",
"| Tracks | Trees | Status | R@1 | R@5 | E2E correct | Train s | Peak MB | Tree MB | RF P95 ms | Verify P95 ms |",
"|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
for r in rows:
    pct=lambda k:"" if r.get(k) is None else f"{100*float(r[k]):.2f}%"
    num=lambda k,d=2:"" if r.get(k) is None else f"{float(r[k]):.{d}f}"
    md.append(f"| {r.get('effective_tracks',r.get('requested_tracks',''))} | {r.get('trees','')} | {r.get('status','')} | {pct('recall_at_1')} | {pct('recall_at_5')} | {pct('e2e_correct_rate_top5_verify')} | {num('fit_seconds')} | {num('peak_rss_mb',1)} | {num('tree_arrays_mb',1)} | {num('rf_query_ms_p95')} | {num('comparator_top5_ms_p95')} |")
Path("summary/README.md").write_text("\n".join(md),encoding="utf-8")
print("\n".join(md))
