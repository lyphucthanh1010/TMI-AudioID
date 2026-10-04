from __future__ import annotations
import argparse,csv,json,os,resource,time
from pathlib import Path
import numpy as np
from sklearn.ensemble import RandomForestClassifier

def tree_bytes(model):
    total=0
    for est in model.estimators_:
        t=est.tree_
        for name in ("children_left","children_right","feature","threshold","impurity","n_node_samples","weighted_n_node_samples","value"):
            a=getattr(t,name,None)
            if hasattr(a,"nbytes"): total+=a.nbytes
    return total

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--features",required=True)
    ap.add_argument("--scale",type=int,required=True)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()
    d=np.load(args.features,allow_pickle=False)
    refs=d["refs"]; queries=d["queries"]; ids=d["track_ids"]
    n=min(args.scale,len(ids))
    rng=np.random.default_rng(20260929)
    perm=rng.permutation(len(ids))[:n]
    X=refs[perm].reshape(n*refs.shape[1],refs.shape[2])
    y=np.repeat(np.arange(n,dtype=np.int32),refs.shape[1])
    Q=queries[perm]
    print(json.dumps({"scale":n,"X":list(X.shape),"Q":list(Q.shape)}),flush=True)

    model=RandomForestClassifier(n_estimators=100,random_state=42,n_jobs=-1)
    t0=time.perf_counter(); model.fit(X,y); fit_s=time.perf_counter()-t0

    recalls={1:0,3:0,5:0,10:0}
    ranks=[]
    batch=64
    tpred0=time.perf_counter()
    for st in range(0,n,batch):
        pr=model.predict_proba(Q[st:st+batch])
        for bi,row in enumerate(pr):
            true=st+bi
            top=np.argpartition(row,-min(10,n))[-min(10,n):]
            top=top[np.argsort(row[top])[::-1]]
            where=np.where(top==true)[0]
            rank=int(where[0]+1) if len(where) else 999999
            ranks.append(rank)
            for k in recalls:
                if rank<=k: recalls[k]+=1
    pred_total_s=time.perf_counter()-tpred0
    recalls={f"recall_at_{k}":v/n for k,v in recalls.items()}

    timings=[]
    for i in range(min(300,n)):
        a=time.perf_counter(); model.predict_proba(Q[i:i+1]); timings.append((time.perf_counter()-a)*1000)
    rss_kb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result={
      "scale_tracks":n,"train_samples":int(X.shape[0]),"query_count":n,"trees":100,
      **recalls,"fit_s":fit_s,"predict_total_s":pred_total_s,
      "query_p50_ms":float(np.percentile(timings,50)),"query_p95_ms":float(np.percentile(timings,95)),
      "peak_rss_mb":rss_kb/1024.0,"tree_arrays_mb":tree_bytes(model)/(1024**2),
      "mean_rank_top10_capped":float(np.mean(np.minimum(np.asarray(ranks),11))),
      "status":"ok"
    }
    Path(args.out).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)
if __name__=="__main__": main()
