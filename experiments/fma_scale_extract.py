from __future__ import annotations
import argparse, ctypes, hashlib, json, os, subprocess, sys, time, zipfile
from pathlib import Path
import numpy as np

SR=44100
WIN_S=10.0
HOP_S=5.0
QUERY_OFFSET_S=7.3
WIN_N=int(SR*WIN_S)

def load_chromaprint():
    lib=None
    for name in ("libchromaprint.so.1","libchromaprint.so"):
        try:
            lib=ctypes.CDLL(name); break
        except OSError:
            pass
    if lib is None: raise RuntimeError("libchromaprint not found")
    lib.chromaprint_new.argtypes=[ctypes.c_int]; lib.chromaprint_new.restype=ctypes.c_void_p
    lib.chromaprint_free.argtypes=[ctypes.c_void_p]
    lib.chromaprint_start.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int]; lib.chromaprint_start.restype=ctypes.c_int
    lib.chromaprint_feed.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_int16),ctypes.c_int]; lib.chromaprint_feed.restype=ctypes.c_int
    lib.chromaprint_finish.argtypes=[ctypes.c_void_p]; lib.chromaprint_finish.restype=ctypes.c_int
    lib.chromaprint_get_raw_fingerprint.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.POINTER(ctypes.c_uint32)),ctypes.POINTER(ctypes.c_int)]
    lib.chromaprint_get_raw_fingerprint.restype=ctypes.c_int
    lib.chromaprint_dealloc.argtypes=[ctypes.c_void_p]
    return lib

CP=load_chromaprint()

def raw_fp(pcm: np.ndarray) -> np.ndarray:
    pcm=np.ascontiguousarray(pcm,dtype=np.int16)
    ctx=CP.chromaprint_new(1)
    if not ctx: raise RuntimeError("chromaprint_new failed")
    try:
        if CP.chromaprint_start(ctx,SR,1)!=1: raise RuntimeError("chromaprint_start failed")
        ptr=pcm.ctypes.data_as(ctypes.POINTER(ctypes.c_int16))
        if CP.chromaprint_feed(ctx,ptr,int(pcm.size))!=1: raise RuntimeError("chromaprint_feed failed")
        if CP.chromaprint_finish(ctx)!=1: raise RuntimeError("chromaprint_finish failed")
        out=ctypes.POINTER(ctypes.c_uint32)()
        n=ctypes.c_int()
        if CP.chromaprint_get_raw_fingerprint(ctx,ctypes.byref(out),ctypes.byref(n))!=1:
            raise RuntimeError("chromaprint_get_raw_fingerprint failed")
        arr=np.ctypeslib.as_array(out,shape=(n.value,)).copy()
        CP.chromaprint_dealloc(out)
        return arr.astype(np.uint32,copy=False)
    finally:
        CP.chromaprint_free(ctx)

def feat64(fp: np.ndarray) -> np.ndarray:
    if fp.size==0: return np.zeros(64,dtype=np.float32)
    shifts=np.arange(32,dtype=np.uint32)
    bits=((fp[:,None]>>shifts)&1).astype(np.float32)
    means=bits.mean(axis=0)
    if fp.size<2:
        trans=np.zeros(32,dtype=np.float32)
    else:
        x=np.bitwise_xor(fp[:-1],fp[1:])
        trans=(((x[:,None]>>shifts)&1).astype(np.float32)).mean(axis=0)
    return np.concatenate([means,trans]).astype(np.float32)

def decode_mp3(blob: bytes) -> np.ndarray:
    p=subprocess.run(
        ["ffmpeg","-v","error","-i","pipe:0","-f","s16le","-acodec","pcm_s16le","-ac","1","-ar",str(SR),"pipe:1"],
        input=blob,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    if p.returncode!=0:
        raise RuntimeError(p.stderr.decode("utf-8","ignore")[-1000:])
    return np.frombuffer(p.stdout,dtype="<i2").copy()

def one_track(pcm: np.ndarray):
    need=int(SR*(QUERY_OFFSET_S+WIN_S))
    if pcm.size<need: raise RuntimeError(f"too short: {pcm.size/SR:.2f}s")
    refs=[]
    for s in (0.,5.,10.,15.,20.):
        a=int(s*SR); b=a+WIN_N
        if b>pcm.size: raise RuntimeError("reference window out of range")
        refs.append(feat64(raw_fp(pcm[a:b])))
    qa=int(QUERY_OFFSET_S*SR)
    q=feat64(raw_fp(pcm[qa:qa+WIN_N]))
    return np.stack(refs),q

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--zip",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--limit",type=int,default=8000)
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    zpath=Path(args.zip)
    sha1=hashlib.sha1()
    with zpath.open("rb") as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b""): sha1.update(chunk)
    got=sha1.hexdigest()
    expected="ade154f733639d52e35e32f5593efe5be76c6d70"
    print("sha1",got,flush=True)
    if got!=expected: raise SystemExit(f"SHA1 mismatch: {got}")

    refs=[]; queries=[]; ids=[]; errors=[]
    t0=time.perf_counter()
    with zipfile.ZipFile(zpath) as z:
        names=sorted([n for n in z.namelist() if n.lower().endswith(".mp3")])
        print("mp3_entries",len(names),flush=True)
        for i,n in enumerate(names[:args.limit],1):
            try:
                blob=z.read(n)
                pcm=decode_mp3(blob)
                r,q=one_track(pcm)
                refs.append(r); queries.append(q)
                tid=Path(n).stem
                ids.append(tid)
            except Exception as e:
                errors.append({"path":n,"error":str(e)})
            if i%100==0:
                elapsed=time.perf_counter()-t0
                print(json.dumps({"seen":i,"ok":len(ids),"errors":len(errors),"elapsed_s":round(elapsed,1)}),flush=True)
                if len(ids)%500==0:
                    np.savez_compressed(out/"features_checkpoint.npz",
                        refs=np.asarray(refs,dtype=np.float32),
                        queries=np.asarray(queries,dtype=np.float32),
                        track_ids=np.asarray(ids,dtype="U32"))
    refs=np.asarray(refs,dtype=np.float32)
    queries=np.asarray(queries,dtype=np.float32)
    np.savez_compressed(out/"fma_small_chromaprint64.npz",refs=refs,queries=queries,track_ids=np.asarray(ids,dtype="U32"))
    (out/"extract_errors.json").write_text(json.dumps(errors,indent=2))
    meta={"tracks_ok":len(ids),"errors":len(errors),"refs_shape":list(refs.shape),"queries_shape":list(queries.shape),
          "sample_rate":SR,"window_s":WIN_S,"hop_s":HOP_S,"query_offset_s":QUERY_OFFSET_S,
          "elapsed_s":time.perf_counter()-t0,"fma_small_sha1":got}
    (out/"extract_meta.json").write_text(json.dumps(meta,indent=2))
    print(json.dumps(meta,indent=2),flush=True)
if __name__=="__main__": main()
