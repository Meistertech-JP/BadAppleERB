"""Freeze a deterministic full-range grayscale reference from the supplied PV."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path
import numpy as np

FILTER = "scale=79:24:flags=area:in_range=tv:out_range=full,format=gray"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("video",type=Path)
    p.add_argument("output",type=Path)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
    probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_format","-show_streams","-of","json",str(a.video)]))
    frames_meta=json.loads(subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-show_frames","-show_entries","frame=pts,best_effort_timestamp,pkt_duration","-of","json",str(a.video)]))["frames"]
    argv=["ffmpeg","-v","error","-threads","1","-i",str(a.video),"-map","0:v:0","-vf",FILTER,"-fps_mode","passthrough","-f","rawvideo","-pix_fmt","gray","-"]
    raw=subprocess.check_output(argv)
    gray=np.frombuffer(raw,dtype=np.uint8).reshape(-1,24,79).copy()
    pts=np.array([x.get("pts",x.get("best_effort_timestamp")) for x in frames_meta],dtype=np.int64)
    assert len(gray)==len(pts)
    binary=(gray>=128).astype(np.uint8)
    np.savez_compressed(a.output/"reference_frames.npz",gray=gray,frames=binary,pts=pts)
    metadata={"source_name":a.video.name,"source_sha256":hashlib.sha256(a.video.read_bytes()).hexdigest(),"source_bytes":a.video.stat().st_size,"ffmpeg_version":subprocess.check_output(["ffmpeg","-version"],text=True).splitlines()[0],"filter":FILTER,"shape":list(gray.shape),"gray_sha256":hashlib.sha256(gray.tobytes()).hexdigest(),"binary_sha256":hashlib.sha256(binary.tobytes()).hexdigest(),"binary_threshold":128,"pts":pts.tolist(),"probe":probe,"mapping":"Full source rectangle mapped to79columns24rows, no crop or letterbox.4:3 optical aspect needs character width/height32/79.","timeline":"Video PTS normalized by first video frame, final frame retained for1/30s."}
    (a.output/"reference_metadata.json").write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+"\n")
    stats={}
    for levels in (2,4,8,16,256):
        values=np.minimum((gray.astype(np.uint16)*levels)//256,levels-1)
        runs=1+(values[:,:,1:]!=values[:,:,:-1]).sum(axis=2)
        stats[str(levels)]={"mean_runs_per_row":float(runs.mean()),"max_runs":int(runs.max()),"total_runs":int(runs.sum()),"distinct_frames":len(set(hashlib.blake2b(f.tobytes(),digest_size=8).digest() for f in values))}
    print(json.dumps({"shape":list(gray.shape),"gray_range":[int(gray.min()),int(gray.max())],"source_sha256":metadata["source_sha256"],"run_statistics":stats},indent=2))

if __name__=="__main__":main()
