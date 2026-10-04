#!/usr/bin/env python3
from __future__ import annotations
import argparse, glob, json
from pathlib import Path
import numpy as np

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--glob",dest="pattern",required=True)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()
    fs=sorted(glob.glob(a.pattern))
    if not fs: raise SystemExit("no shard files")
    ids=[]; tr=[]; te=[]; full=[]; q=[]
    for f in fs:
        z=np.load(f,allow_pickle=True)
        ids.append(z["track_ids"]); tr.append(z["train_features"]); te.append(z["test_features"])
        full.extend(list(z["full_fp"])); q.extend(list(z["test_fp"]))
        print(f,len(z["track_ids"]))
    ids=np.concatenate(ids); tr=np.concatenate(tr); te=np.concatenate(te)
    order=np.argsort(ids)
    ids=ids[order]; tr=tr[order]; te=te[order]
    full=np.asarray(full,dtype=object)[order]; q=np.asarray(q,dtype=object)[order]
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out,track_ids=ids,train_features=tr,test_features=te,full_fp=full,test_fp=q)
    print(json.dumps({"out":str(out),"valid_tracks":int(len(ids))}))
if __name__=="__main__": main()
