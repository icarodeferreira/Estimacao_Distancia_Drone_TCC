"""Execução exploratória; não certifica a distância física câmera–drone."""
from pathlib import Path
import copy,gc,json,sys,random
import numpy as np
import pandas as pd
from PIL import Image
from audit_core import *

def roi(depth,box,wh,percentile=25,min_pixels=6):
    h,w=depth.shape;W,H=wh
    x1,y1,x2,y2=box
    x1,x2=np.clip([np.floor(x1*w/W),np.ceil(x2*w/W)],0,w).astype(int)
    y1,y2=np.clip([np.floor(y1*h/H),np.ceil(y2*h/H)],0,h).astype(int)
    v=depth[y1:y2,x1:x2];v=v[np.isfinite(v)&(v>0)]
    return float(np.percentile(v,percentile)) if len(v)>=min_pixels else np.nan

def metrics(ref,pred):
    r=np.asarray(ref,float);p=np.asarray(pred,float);m=np.isfinite(r)&np.isfinite(p);r,p=r[m],p[m]
    if not len(r):return {'n':0,'mae_m':None,'rmse_m':None,'bias_m':None}
    e=p-r
    return {'n':len(r),'mae_m':float(abs(e).mean()),'rmse_m':float(np.sqrt((e*e).mean())),'bias_m':float(e.mean())}

def summarize(df,c):
    rows=[]
    for s,g in df[df.box_reliable].groupby('second'):
        w=g.box_width_px;med=w.median()
        rows.append({'second':s,'reliable_frames':len(g),'width_px':med,'relative_iqr':(w.quantile(.75)-w.quantile(.25))/med,'depth_z_m':g.depth_z_m.median(),'reference_m':g.ref.median()})
    sec=pd.DataFrame({'second':np.sort(df.second.unique())}).merge(pd.DataFrame(rows,columns=['second','reliable_frames','width_px','relative_iqr','depth_z_m','reference_m']),how='left')
    sec['reliable_frames']=sec.reliable_frames.fillna(0).astype(int)
    sec['quality_ok']=(sec.reliable_frames>=c['quality']['min_frames'])&(sec.relative_iqr<=c['quality']['max_iqr']);sec['temporal_reject']=False
    for i,r in sec.iterrows():
        if not np.isfinite(r.width_px) or r.width_px<=0:continue
        hist=sec[(sec.second<r.second)&(sec.second>=r.second-c['quality']['history_s'])].width_px
        hist=np.log(hist[hist>0].dropna())
        if len(hist)>=c['quality']['min_history']:
            center=hist.median();mad=np.median(abs(hist-center));threshold=max(c['quality']['min_log_jump'],c['quality']['k']*c['quality']['mad_factor']*mad)
            sec.loc[i,'temporal_reject']=abs(np.log(r.width_px)-center)>threshold
    sec['quality_ok'] &= ~sec.temporal_reject;sec['width_estimate_m']=np.nan
    if c['regression'].get('frozen_model'):
        model=json.loads(Path(c['regression']['frozen_model']).read_text())
        if model['input_resolution_px']!=c['measurement_resolution']:raise ValueError('Resolução incompatível com calibração.')
        if c['regression'].get('domain_review')!='confirmed':raise ValueError('Confirme domínio da calibração.')
        if model.get('origin_experiment')==c['experiment_id']:raise ValueError('Teste independente exige outro experimento.')
        lo,hi=model['width_domain_px'];valid=sec.quality_ok&sec.width_px.between(lo,hi)
        sec.loc[valid,'width_estimate_m']=model['coefficient']*sec.loc[valid,'width_px']**model['exponent']
    return sec

def execute(c,root,pilot_s=None,audit_only=False):
    if not c.get('video'):raise ValueError('Informe video no JSON.')
    root,out=project(root,c['experiment_id'])
    if (out/'audit/config.json').exists():raise FileExistsError('Use novo experiment_id para preservar a execução anterior.')
    save_json(c,out/'audit/config.json');save_json(environment(),out/'audit/environment.json')
    manifest,report=audit_video(c,out)
    if audit_only:return out
    if any(c['field'].get(k) is None for k in ['camera','lens','zoom','fixed_camera','constant_zoom']):raise ValueError('Preencha câmera, lente, zoom, câmera fixa e zoom constante.')
    if not c['field']['constant_zoom']:raise ValueError('Separe segmentos com zoom constante.')
    expected=c.get('measurement_resolution')
    if expected!=[report['width'],report['height']]:raise ValueError('Confirme measurement_resolution e limiares de caixa.')
    telem=read_telemetry(c,out);ref=reference(manifest,telem,c,out)
    import torch
    from ultralytics import YOLO
    random.seed(42);np.random.seed(42);torch.manual_seed(42)
    device=('cuda' if torch.cuda.is_available() else 'cpu') if c['device']=='auto' else c['device']
    weight=Path(c['yolo_weights']);save_json({'yolo_sha256':digest(weight),'seed':42,'device':device},out/'audit/models.json')
    model=YOLO(str(weight));cid=c['yolo']['drone_class_id']
    if cid is None or str(model.names[cid]).lower()!=c['yolo']['confirmed_class_name']:raise ValueError(f'Confirme classe drone: {model.names}')
    rows=[]
    for i,pts,rgb,f in frames(c['video'],c['rotation_ccw']):
        record=ref.iloc[i].to_dict()
        if pilot_s is not None and record['t']>=pilot_s:break
        pred=model.predict(Image.fromarray(rgb),imgsz=c['yolo']['imgsz'],conf=c['yolo']['record_conf'],iou=c['yolo']['iou_nms'],device=device,verbose=False)[0]
        boxes=pred.boxes;pick=[j for j,v in enumerate(boxes.cls.tolist()) if int(v)==cid]
        record.update({'confidence':np.nan,'x1':np.nan,'y1':np.nan,'x2':np.nan,'y2':np.nan,'box_reliable':False,'box_width_px':np.nan,'depth_z_m':np.nan,'depth_status':'not_run'})
        if pick:
            j=max(pick,key=lambda k:float(boxes.conf[k]));box=boxes.xyxy[j].cpu().numpy();conf=float(boxes.conf[j]);x1,y1,x2,y2=box
            record.update(dict(zip(['x1','y1','x2','y2'],box)));record.update(confidence=conf,box_width_px=x2-x1,box_reliable=bool(conf>=c['yolo']['reliable_conf'] and x2-x1>=c['yolo']['min_width'] and y2-y1>=c['yolo']['min_height']))
        rows.append(record)
        if i%25==0:save_csv(pd.DataFrame(rows),out/'tables/predictions.partial.csv')
    del model;gc.collect()
    if torch.cuda.is_available():torch.cuda.empty_cache()
    df=pd.DataFrame(rows)
    if df.empty:raise ValueError('Nenhum quadro selecionado.')
    if c['depth']['enabled']:
        sys.path.insert(0,str(Path(c['depth_repo'])/'src'))
        import depth_pro
        from depth_pro.depth_pro import DEFAULT_MONODEPTH_CONFIG_DICT
        cfg=copy.deepcopy(DEFAULT_MONODEPTH_CONFIG_DICT);cfg.checkpoint_uri=str(c['depth_weights']);precision=torch.float16 if device.startswith('cuda') else torch.float32
        model,transform=depth_pro.create_model_and_transforms(config=cfg,device=torch.device(device),precision=precision);model.eval();focal=c['depth']['focal_px']
        if focal is not None and c['depth']['focal_resolution']!=expected:raise ValueError('Focal incompatível com resolução.')
        for i,pts,rgb,f in frames(c['video'],c['rotation_ccw']):
            if i>=len(df):break
            if not df.loc[i,'box_reliable']:df.loc[i,'depth_status']='no_reliable_box';continue
            with torch.inference_mode():
                image=transform(Image.fromarray(rgb)).to(device=device,dtype=precision);fpx=None if focal is None else torch.tensor(float(focal),device=device,dtype=precision)
                z=model.infer(image,f_px=fpx)['depth'].squeeze().detach().float().cpu().numpy()
            val=roi(z,df.loc[i,['x1','y1','x2','y2']].to_numpy(float),expected,c['depth']['percentile'],c['depth']['min_pixels']);ok=np.isfinite(val) and c['depth']['min_m']<=val<=c['depth']['max_m']
            df.loc[i,'depth_z_m']=val if ok else np.nan;df.loc[i,'depth_status']='ok_axial' if ok else 'rejected_depth'
            if i%5==0:save_csv(df,out/'tables/predictions.partial.csv')
        del model;gc.collect();save_json({'sha256':digest(c['depth_weights']),'git_revision':run(['git','-C',c['depth_repo'],'rev-parse','HEAD']).strip()},out/'audit/depth_model.json')
    sec=summarize(df,c);save_csv(df,out/'tables/predictions.csv');save_csv(sec,out/'tables/per_second.csv')
    save_json({'frames':len(df),'reliable_boxes':int(df.box_reliable.sum()),'depth_outputs':int(df.depth_z_m.notna().sum()),'seconds':len(sec),'quality_seconds':int(sec.quality_ok.sum()),'width_outputs':int(sec.width_estimate_m.notna().sum()),'width_vs_reference':metrics(sec.reference_m,sec.width_estimate_m),'depth_Z_vs_reference_R_exploratory':metrics(sec.reference_m,sec.depth_z_m),'reference_status':'nominal; no independent physical validation'},out/'tables/metrics.json')
    save_json(environment(),out/'audit/environment_final.json');return out
