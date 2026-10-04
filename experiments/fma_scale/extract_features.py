#!/usr/bin/env python3
from __future__ import annotations
import argparse, ctypes, ctypes.util, json, subprocess, tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
from remotezip import RemoteZip

FMA_URL="https://os.unil.cloud.switch.ch/fma/fma_small.zip"
SR=44100
WINDOW_STARTS=(0,5,10,20)
WINDOW_SEC=10
WORKER_RZ=None
LIB=None

def init_worker():
    global WORKER_RZ
    WORKER_RZ=RemoteZip(FMA_URL)

def load_chromaprint():
    global LIB
    if LIB is not None: return LIB
    name=ctypes.util.find_library("chromaprint") or "libchromaprint.so.1"
    lib=ctypes.CDLL(name)
    lib.chromaprint_new.argtypes=[ctypes.c_int]; lib.chromaprint_new.restype=ctypes.c_void_p
    lib.chromaprint_free.argtypes=[ctypes.c_void_p]
    lib.chromaprint_start.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int]; lib.chromaprint_start.restype=ctypes.c_int
    lib.chromaprint_feed.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_int16),ctypes.c_int]; lib.chromaprint_feed.restype=ctypes.c_int
    lib.chromaprint_finish.argtypes=[ctypes.c_void_p]; lib.chromaprint_finish.restype=ctypes.c_int
    lib.chromaprint_get_raw_fingerprint.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.POINTER(ctypes.c_uint32)),ctypes.POINTER(ctypes.c_int)]
    lib.chromaprint_get_raw_fingerprint.restype=ctypes.c_int
    lib.chromaprint_dealloc.argtypes=[ctypes.c_void_p]
    LIB=lib
    return lib

def chromaprint_raw(pcm):
    lib=load_chromaprint()
    pcm=np.ascontiguousarray(pcm,dtype=np.int16)
    ctx=lib.chromaprint_new(1)
    if not ctx: raise RuntimeError("chromaprint_new failed")
    try:
        if lib.chromaprint_start(ctx,SR,1)!=1: raise RuntimeError("chromaprint_start failed")
        ptr=pcm.ctypes.data_as(ctypes.POINTER(ctypes.c_int16))
        if lib.chromaprint_feed(ctx,ptr,int(pcm.size))!=1: raise RuntimeError("chromaprint_feed failed")
        if lib.chromaprint_finish(ctx)!=1: raise RuntimeError("chromaprint_finish failed")
        out_ptr=ctypes.POINTER(ctypes.c_uint32)(); out_size=ctypes.c_int()
        if lib.chromaprint_get_raw_fingerprint(ctx,ctypes.byref(out_ptr),ctypes.byref(out_size))!=1:
            raise RuntimeError("get_raw_fingerprint failed")
        try:
            return np.ctypeslib.as_array(out_ptr,shape=(out_size.value,)).copy().astype(np.uint32)
        finally:
            lib.chromaprint_dealloc(out_ptr)
    finally:
        lib.chromaprint_free(ctx)

def bit_pair_stats(fp):
    fp=np.asarray(fp,dtype=np.uint32)
    shifts=np.arange(32,dtype=np.uint32)
    bits=((fp[:,None]>>shifts)&1).astype(np.float32)
    bit_mean=bits.mean(axis=0) if len(fp) else np.zeros(32,np.float32)
    if len(fp)>=2:
        x=fp[1:]^fp[:-1]
        transitions=(((x[:,None]>>shifts)&1).astype(np.float32)).mean(axis=0)
    else:
        transitions=np.zeros(32,np.float32)
    return np.concatenate([bit_mean,transitions]).astype(np.float32)

def decode_mp3(data):
    with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
        f.write(data); f.flush()
        p=subprocess.run(["ffmpeg","-v","error","-i",f.name,"-f","s16le","-acodec","pcm_s16le","-ac","1","-ar",str(SR),"pipe:1"],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
    if p.returncode!=0: raise RuntimeError(p.stderr.decode("utf-8","replace")[-1000:])
    pcm=np.frombuffer(p.stdout,dtype="<i2").copy()
    if pcm.size<int(25*SR): raise RuntimeError(f"audio too short: {pcm.size/SR:.2f}s")
    return pcm

def process_one(name):
    global WORKER_RZ
    tid=int(Path(name).stem)
    try:
        pcm=decode_mp3(WORKER_RZ.read(name))
        full_fp=chromaprint_raw(pcm)
        feats=[]; fps=[]
        for start in WINDOW_STARTS:
            a=int(start*SR); b=min(pcm.size,int((start+WINDOW_SEC)*SR))
            if b-a<int(8*SR): raise RuntimeError(f"window {start}s too short")
            fp=chromaprint_raw(pcm[a:b]); fps.append(fp); feats.append(bit_pair_stats(fp))
        return True,tid,np.stack(feats[:3]),feats[3],full_fp,fps[3],None
    except Exception as e:
        return False,tid,None,None,None,None,repr(e)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--shard",type=int,required=True)
    ap.add_argument("--num-shards",type=int,default=8)
    ap.add_argument("--workers",type=int,default=2)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()
    with RemoteZip(FMA_URL) as rz:
        names=sorted(i.filename for i in rz.infolist() if not i.is_dir() and i.filename.lower().endswith(".mp3"))
    total=len(names); lo=total*args.shard//args.num_shards; hi=total*(args.shard+1)//args.num_shards
    selected=names[lo:hi]
    print(json.dumps({"total_mp3":total,"shard":args.shard,"lo":lo,"hi":hi,"count":len(selected)}),flush=True)
    ok=[]; errors=[]
    with ProcessPoolExecutor(max_workers=args.workers,initializer=init_worker) as ex:
        futs=[ex.submit(process_one,n) for n in selected]
        for done,fut in enumerate(as_completed(futs),1):
            good,tid,tr,te,full,q,err=fut.result()
            if good: ok.append((tid,tr,te,full,q))
            else: errors.append({"track_id":tid,"error":err})
            if done%50==0 or done==len(selected):
                print(f"progress {done}/{len(selected)} ok={len(ok)} err={len(errors)}",flush=True)
    ok.sort(key=lambda x:x[0])
    ids=np.array([x[0] for x in ok],dtype=np.int32)
    tr=np.stack([x[1] for x in ok]).astype(np.float32)
    te=np.stack([x[2] for x in ok]).astype(np.float32)
    full=np.empty(len(ok),dtype=object); q=np.empty(len(ok),dtype=object)
    for i,x in enumerate(ok): full[i]=x[3]; q[i]=x[4]
    out=Path(args.out)
    np.savez_compressed(out,track_ids=ids,train_features=tr,test_features=te,full_fp=full,test_fp=q)
    out.with_suffix(".errors.json").write_text(json.dumps(errors,indent=2),encoding="utf-8")
    print(json.dumps({"saved":str(out),"valid":len(ok),"errors":len(errors)}),flush=True)
if __name__=="__main__": main()
