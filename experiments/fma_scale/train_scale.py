#!/usr/bin/env python3
from __future__ import annotations
import argparse,gc,json,os,threading,time,traceback
from pathlib import Path
import numpy as np, psutil
from sklearn.ensemble import RandomForestClassifier

ALIGN_BITS=12
ALIGN_MASK=np.uint32(((1<<ALIGN_BITS)-1)<<(32-ALIGN_BITS))
POPCOUNT8=np.array([bin(i).count("1") for i in range(256)],dtype=np.uint8)

def akey(x): return int((np.uint32(x)&ALIGN_MASK)>>np.uint32(32-ALIGN_BITS))

def compare_fp(ref,query,top_offsets=3,min_overlap_items=12):
    ref=np.asarray(ref,dtype=np.uint32); query=np.asarray(query,dtype=np.uint32)
    if len(ref)==0 or len(query)==0: return (0.0,0.0,0)
    ri={}; qi={}
    for i,v in enumerate(ref): ri.setdefault(akey(v),[]).append(i)
    for j,v in enumerate(query): qi.setdefault(akey(v),[]).append(j)
    hist={}
    for k in ri.keys()&qi.keys():
        for i in ri[k]:
            for j in qi[k]:
                o=i-j; hist[o]=hist.get(o,0)+1
    if not hist: return (0.0,0.0,0)
    hyp=sorted(hist.items(),key=lambda kv:(kv[1],-abs(kv[0])),reverse=True)[:top_offsets]
    best=(0.0,0.0,0)
    for off,support in hyp:
        q0=max(0,-off); q1=min(len(query),len(ref)-off); overlap=q1-q0
        if overlap<min_overlap_items: continue
        rs=ref[q0+off:q0+off+overlap]; qs=query[q0:q0+overlap]
        biterr=int(POPCOUNT8[(rs^qs).view(np.uint8)].sum())
        score=max(0.0,1.0-2.0*biterr/(32.0*overlap))
        cand=(score,overlap/len(query),support)
        if cand>best: best=cand
    return best

class PeakSampler:
    def __init__(self): self.peak=0; self.stop_evt=threading.Event()
    def start(self):
        p=psutil.Process(os.getpid())
        def run():
            while not self.stop_evt.is_set():
                try:self.peak=max(self.peak,p.memory_info().rss)
                except:pass
                time.sleep(.05)
        self.t=threading.Thread(target=run,daemon=True); self.t.start()
    def stop(self):
        self.stop_evt.set(); self.t.join(timeout=1); return self.peak

def tree_bytes(rf):
    total=0; nodes=0
    attrs=["children_left","children_right","feature","threshold","impurity","n_node_samples","weighted_n_node_samples","value"]
    for est in rf.estimators_:
        t=est.tree_; nodes+=t.node_count
        for a in attrs:
            x=getattr(t,a,None)
            if x is not None: total+=x.nbytes
    return total,nodes

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",required=True); ap.add_argument("--n",type=int,required=True)
    ap.add_argument("--trees",type=int,default=100); ap.add_argument("--out",required=True)
    ap.add_argument("--seed",type=int,default=20261004)
    a=ap.parse_args(); out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    result={"requested_tracks":a.n,"trees":a.trees,"seed":a.seed,"status":"started"}
    try:
        z=np.load(a.data,allow_pickle=True)
        rng=np.random.default_rng(a.seed); order=rng.permutation(len(z["track_ids"]))
        n=min(a.n,len(order)); idx=order[:n]
        tr=z["train_features"][idx]; te=z["test_features"][idx]
        full=z["full_fp"][idx]; qfp=z["test_fp"][idx]
        X=tr.reshape(n*3,64).astype(np.float32); y=np.repeat(np.arange(n,dtype=np.int32),3)
        Xq=te.astype(np.float32)

        s=PeakSampler(); s.start(); t0=time.perf_counter()
        rf=RandomForestClassifier(n_estimators=a.trees,random_state=a.seed,n_jobs=-1,max_features="sqrt")
        rf.fit(X,y); fit_s=time.perf_counter()-t0; peak=s.stop()
        tb,nodes=tree_bytes(rf)

        ranks=np.empty(n,dtype=np.int32); kk=min(5,n); top5=np.empty((n,kk),dtype=np.int32)
        t0=time.perf_counter()
        for lo in range(0,n,128):
            hi=min(n,lo+128); p=rf.predict_proba(Xq[lo:hi])
            truth=np.arange(lo,hi,dtype=np.int32); tp=p[np.arange(hi-lo),truth]
            ranks[lo:hi]=1+(p>tp[:,None]).sum(axis=1)
            top=np.argpartition(-p,kth=kk-1,axis=1)[:,:kk]
            vals=np.take_along_axis(p,top,axis=1); oo=np.argsort(-vals,axis=1)
            top5[lo:hi]=np.take_along_axis(top,oo,axis=1)
        pred_total=time.perf_counter()-t0

        lat=[]
        for i in np.linspace(0,n-1,min(200,n),dtype=int):
            t=time.perf_counter(); rf.predict_proba(Xq[i:i+1]); lat.append((time.perf_counter()-t)*1000)

        correct=unknown=falsem=0; cmp_ms=[]
        for i in range(n):
            t=time.perf_counter(); eligible=[]
            for c in top5[i]:
                sc,ov,sup=compare_fp(full[int(c)],qfp[i])
                if sc>=0.60 and ov>=0.50: eligible.append((sc,ov,sup,int(c)))
            if not eligible: unknown+=1
            elif max(eligible)[3]==i: correct+=1
            else: falsem+=1
            cmp_ms.append((time.perf_counter()-t)*1000)

        result.update({
          "status":"completed","effective_tracks":int(n),"valid_tracks_total":int(len(z["track_ids"])),
          "train_samples":int(len(X)),"test_queries":int(n),"fit_seconds":fit_s,
          "peak_rss_mb":peak/1048576,"tree_arrays_mb":tb/1048576,"tree_nodes_total":int(nodes),
          "rf_predict_total_seconds":pred_total,"rf_query_ms_p50":float(np.percentile(lat,50)),
          "rf_query_ms_p95":float(np.percentile(lat,95)),
          "recall_at_1":float(np.mean(ranks<=1)),"recall_at_3":float(np.mean(ranks<=3)),
          "recall_at_5":float(np.mean(ranks<=5)),"recall_at_10":float(np.mean(ranks<=10)),
          "median_true_rank":float(np.median(ranks)),
          "e2e_correct_rate_top5_verify":correct/n,"e2e_unknown_rate_top5_verify":unknown/n,
          "e2e_false_match_rate_top5_verify":falsem/n,
          "comparator_top5_ms_p50":float(np.percentile(cmp_ms,50)),
          "comparator_top5_ms_p95":float(np.percentile(cmp_ms,95))
        })
        np.save(out.with_suffix(".ranks.npy"),ranks); del rf; gc.collect()
    except Exception as e:
        result.update({"status":"failed","error":repr(e),"traceback":traceback.format_exc()[-8000:]})
    out.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
