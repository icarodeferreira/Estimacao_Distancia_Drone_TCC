"""Anota previsões quadro a quadro com os PTS nativos, sem áudio."""
from pathlib import Path
import argparse,json,subprocess,tempfile
import numpy as np,pandas as pd
from PIL import Image,ImageDraw

def run(a):return subprocess.check_output(list(map(str,a)))
def render(video,table,out,limit=None):
    meta=json.loads(run(['ffprobe','-v','error','-show_streams','-of','json',video]));stream=next(v for v in meta['streams'] if v['codec_type']=='video')
    angles=[float(stream.get('tags',{}).get('rotate',0))]+[float(v.get('rotation',0)) for v in stream.get('side_data_list',[])]
    if any(abs(v)%360>1e-6 for v in angles):raise ValueError('Normalize rotação antes de inferir e anotar.')
    cmd=['ffprobe','-v','error','-select_streams','v:0','-show_streams','-show_frames','-show_entries','stream=width,height:frame=best_effort_timestamp_time,pkt_duration_time,duration_time','-of','json']
    if limit is not None:cmd+=['-read_intervals',f'%+#{limit+16}']
    info=json.loads(run(cmd+[video]));fs=info['frames'];W,H=info['streams'][0]['width'],info['streams'][0]['height'];times=np.array([float(f['best_effort_timestamp_time']) for f in fs]);times-=times[0]
    if len(times)>1 and (np.diff(times)<=0).any():raise ValueError('PTS não monotônicos.')
    durations=np.r_[np.diff(times),float(fs[-1].get('duration_time',fs[-1].get('pkt_duration_time',np.median(np.diff(times)) if len(times)>1 else 1/30)))];d=pd.read_csv(table).set_index('frame_idx');n=len(fs) if limit is None else min(limit,len(fs));out=Path(out).resolve();out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='annotate_') as tmp:
        tmp=Path(tmp);proc=subprocess.Popen(['ffmpeg','-v','error','-noautorotate','-i',str(video),'-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL);lines=[]
        try:
            for i in range(n):
                raw=proc.stdout.read(W*H*3)
                if len(raw)!=W*H*3:raise RuntimeError('Decodificação incompleta.')
                im=Image.frombytes('RGB',(W,H),raw);draw=ImageDraw.Draw(im);label=f'Quadro {i} | t={times[i]:.3f}s | sem saida'
                if i in d.index:
                    r=d.loc[i];box=r[['x1','y1','x2','y2']].to_numpy(float)
                    if np.isfinite(box).all():draw.rectangle(tuple(box),outline='yellow',width=max(2,W//500))
                    label=f'Quadro {i} | t={times[i]:.3f}s | Z={r.get("depth_z_m",float("nan")):.2f} m (axial)'
                draw.rectangle((0,0,min(W,1000),36),fill='black');draw.text((8,8),label,fill='white');p=tmp/f'{i:08d}.png';im.save(p);lines+=['file '+p.as_posix(),'option framerate 1000000',f'duration {durations[i]:.9f}']
        finally:
            proc.stdout.close();proc.terminate();proc.wait()
        lines+=['file '+p.as_posix(),'option framerate 1000000'];listing=tmp/'frames.txt';listing.write_text('\n'.join(lines)+'\n');total=float(durations[:n].sum())
        run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',listing,'-t',total,'-fps_mode','vfr','-c:v','libx264','-bf','0','-preset','fast','-crf','20','-pix_fmt','yuv420p','-enc_time_base','1:1000000','-video_track_timescale','1000000','-bsf:v',f"setts=duration='if(eq(N,{n-1}),{durations[n-1]}/TB,DURATION)'",out])
    check=json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',out]));actual=np.array([float(f['best_effort_timestamp_time']) for f in check['frames']]);error=float(np.max(abs(actual-times[:n]))) if len(actual)==n else None
    report={'input_frames_used':n,'output_frames':len(actual),'max_pts_error_s':error,'audio':False};out.with_suffix('.json').write_text(json.dumps(report,indent=2))
    if len(actual)!=n or error>=2e-5:raise RuntimeError(report)
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('video');p.add_argument('table');p.add_argument('out');p.add_argument('--limit',type=int);a=p.parse_args();print(render(a.video,a.table,a.out,a.limit))
