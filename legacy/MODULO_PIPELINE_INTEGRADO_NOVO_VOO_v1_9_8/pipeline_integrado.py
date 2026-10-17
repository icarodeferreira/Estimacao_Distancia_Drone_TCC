# -*- coding: utf-8 -*-
"""TCC Drone v1.9.8 — avaliação exploratória ponta a ponta, sem treinamento.

Reproduz a seleção YOLO previamente arquivada OU faz inferência YOLO com checkpoint fixo,
calcula a regressão provisória por LARGURA MEDIANA POR SEGUNDO, pode executar Depth Pro
em quadros explicitamente amostrados, e produz CSVs, vídeo e relatório.

NÃO converte profundidade Z em alcance R sem calibração; NÃO produz erro físico em metros
sem referência independente; NÃO usa caixas GT para escolher uma predição operacional.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import math
import os
import shutil
import platform
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_VIDEO = ROOT / 'data' / 'video' / 'IMG_5962_editado.mov'
DEFAULT_WEIGHT = ROOT / 'data' / 'weights' / 'yolo' / 'best.pt'
DEFAULT_DEPTH = ROOT / 'data' / 'weights' / 'depth_pro' / 'depth_pro.pt'
DEFAULT_DEPTH_REPO = ROOT / 'vendor' / 'ml-depth-pro' / 'src'
DEFAULT_TELEMETRY = ROOT / 'data' / 'telemetry' / 'FlightRecord_2026-09-24_14-12-36_corrigido.csv'
DEFAULT_OUTPUT = ROOT / 'outputs' / 'pipeline_integrado_novo_voo_v1_9_8'
EXPECTED_VIDEO_SHA = '3bc510982efea93d18734d39d670e7661edc250f55e9e28e85ade35b67779221'
EXPECTED_YOLO_SHA = '2ca8f89b9d946a6a06a12177db471cb7419b69b4a25ce619cc608c55267a61d8'
MODEL_A = 4442.5484604804715
MODEL_B = -1.2771511434180072
EXPECTED_SOURCE_ROWS = 5142


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(obj, path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False, default=str), encoding='utf-8')
    os.replace(temp, path)


def write_csv(df, path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    df.to_csv(temp, index=False)
    os.replace(temp, path)


def is_true(v):
    if isinstance(v, (bool, np.bool_)): return bool(v)
    if v is None or (isinstance(v, float) and math.isnan(v)): return False
    return str(v).strip().lower() in ('1', 'true', 'sim', 'yes')


def value_number(x):
    try:
        n = float(x)
        return n if math.isfinite(n) else math.nan
    except (TypeError, ValueError):
        return math.nan


def check_video(path, max_frames=None):
    path = Path(path)
    if not path.exists(): raise FileNotFoundError(f'Vídeo inexistente: {path}')
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened(): raise RuntimeError(f'OpenCV não abre o vídeo: {path}')
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if n <= 0 or fps <= 0 or w <= 0 or h <= 0: raise RuntimeError('Metadados inválidos.')
        ok, frame = cap.read()
        if not ok or frame.shape[:2] != (h,w): raise RuntimeError('Primeiro quadro ilegível.')
        return dict(frames=n, fps=fps, width=w, height=h, duration_s=n/fps,
                    inspected_frames=min(n, max_frames) if max_frames else n)
    finally:
        cap.release()



def audit_pts(path, md, permit_unverified=False):
    """Prova que index/fps pode representar o relógio do vídeo; recusa VFR silencioso."""
    exe=shutil.which('ffprobe')
    if not exe:
        if not permit_unverified: raise RuntimeError('ffprobe ausente: não posso confirmar timestamps. Instale FFmpeg ou informe --permitir-pts-nao-verificados (exploratório).')
        return dict(status='NAO_VERIFICADO',motivo='ffprobe ausente; tempos usam index/fps')
    cmd=[exe,'-v','error','-select_streams','v:0','-show_entries',
         'frame=best_effort_timestamp_time','-of','default=noprint_wrappers=1:nokey=1',str(path)]
    ret=subprocess.run(cmd,capture_output=True,text=True,timeout=240)
    if ret.returncode:
        if not permit_unverified: raise RuntimeError('ffprobe falhou: '+ret.stderr[:1000])
        return dict(status='NAO_VERIFICADO',motivo=ret.stderr[:1000])
    ts=[]
    for line in ret.stdout.splitlines():
        try:ts.append(float(line.strip()))
        except ValueError:pass
    if len(ts)!=md['frames']:
        if not permit_unverified: raise RuntimeError(f'Timestamps PTS: {len(ts)} != {md["frames"]}; não há vínculo garantido por índice.')
        return dict(status='NAO_VERIFICADO',motivo=f'PTS {len(ts)} != número de quadros {md["frames"]}')
    t=np.asarray(ts,float); dt=np.diff(t);exp=1/md['fps']
    maxerr=float(np.max(np.abs(dt-exp))) if len(dt) else 0
    ok=(np.isfinite(dt).all() and np.all(dt>0) and maxerr<=max(.0025,.12*exp))
    if not ok and not permit_unverified:
        raise RuntimeError(f'Vídeo VFR ou PTS irregular: delta esperado {exp:.6f}s, maior desvio {maxerr:.6f}s. Use pipeline PyAV por PTS.')
    return dict(status='CFR_VERIFICADO' if ok else 'NAO_VERIFICADO',
                n_pts=len(ts),pts_inicial_s=float(t[0]),
                delta_medio_s=float(np.mean(dt)),desvio_max_vs_1fps_s=maxerr,
                aviso=None if ok else 'Relógio index/fps não validado; evitar métricas temporais conclusivas')

def validate_cache_df(df, md, limit, source):
    required = {'frame_idx','detectado','t_video_s','x1','y1','x2','y2','confianca'}
    missing=required-set(df.columns)
    if missing: raise ValueError(f'{source}: colunas ausentes: {sorted(missing)}')
    idx = pd.to_numeric(df['frame_idx'], errors='raise').to_numpy(dtype=int)
    if len(df) != md['frames'] or not np.array_equal(idx, np.arange(md['frames'])):
        raise ValueError(f'{source}: seleção arquivada não cobre exatamente {md["frames"]} quadros na ordem esperada')
    times = pd.to_numeric(df['t_video_s'], errors='coerce').to_numpy(dtype=float)
    err = np.abs(times - idx/md['fps'])
    if not np.isfinite(err).all() or err.max() > max(0.04, 1.5/md['fps']):
        raise ValueError(f'{source}: relógio incompatível com fps; erro máximo={np.nanmax(err):.6f}s')
    for c in ('x1','y1','x2','y2','confianca'):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['detectado'] = df['detectado'].map(is_true)
    if 'classe_id' in df.columns:
        cls = pd.to_numeric(df['classe_id'], errors='coerce')
        badcls = df['detectado'] & cls.notna() & (cls != 2)
        if badcls.any(): raise ValueError(f'{source}: classe não drone para linhas detectadas.')
    positive = df['detectado'].to_numpy()
    valid = np.isfinite(df[['x1','y1','x2','y2','confianca']].to_numpy(dtype=float)).all(axis=1)
    xy = df[['x1','y1','x2','y2']].to_numpy(dtype=float)
    in_bounds = (xy[:,0]>=0)&(xy[:,1]>=0)&(xy[:,2]>xy[:,0])&(xy[:,3]>xy[:,1])&(
        xy[:,2]<=md['width']+.5)&(xy[:,3]<=md['height']+.5)
    if (positive & ~(valid & in_bounds)).any():
        bad = idx[positive & ~(valid & in_bounds)][:8]
        raise ValueError(f'{source}: caixas inválidas nos frames {bad.tolist()}')
    return df.iloc[:limit].copy()


def archived_yolo(md, limit, selector):
    filename = 'original_selected.csv' if selector == 'original' else 'temporal_selected.csv'
    inp = HERE / 'dados' / filename
    expected = json.loads((HERE/'dados'/'SHA256_FONTES.json').read_text(encoding='utf-8'))[filename]
    digest = sha256(inp)
    if digest != expected: raise RuntimeError(f'SHA-256 divergente no cache {filename}!\n{digest} != {expected}')
    if md['frames'] != EXPECTED_SOURCE_ROWS or (md['width'],md['height']) != (3840,2160) or abs(md['fps']-30)>.03:
        raise ValueError('Caches v1.9.5 são específicos do vídeo IMG_5962 3840x2160/30fps/5142 frames. Para novo vídeo use --fonte novo-yolo.')
    df=pd.read_csv(inp)
    return validate_cache_df(df,md,limit,filename), {"arquivo":filename, "sha256": digest, 'origem':'arquivo_congelado_v1.9.5'}


def predict_yolo(video, weights, md, limit, conf_candidates=0.001, valid_conf=0.25):
    from ultralytics import YOLO
    digest=sha256(weights)
    if digest != EXPECTED_YOLO_SHA:
        raise RuntimeError('Checkpoint diferente do best.pt congelado; execução bloqueada para evitar confusão de modelos.')
    model=YOLO(str(weights))
    if not hasattr(model,'names') or str(model.names.get(2,'')).lower()!='drone':
        raise RuntimeError(f'Classe 2 não é drone: {getattr(model,"names",None)}')
    cap=cv2.VideoCapture(str(video)); rows=[]
    try:
        for i in range(limit):
            ok,img=cap.read()
            if not ok: raise RuntimeError(f'Falha de leitura no quadro {i} durante YOLO')
            res=model.predict(img,classes=[2],imgsz=1920,conf=conf_candidates,iou=0.7,
                              device=0 if __import__('torch').cuda.is_available() else 'cpu',verbose=False)[0]
            boxes=res.boxes
            opts=[]
            if boxes is not None:
                for xy,score in zip(boxes.xyxy.cpu().numpy(),boxes.conf.cpu().numpy()):
                    x1,y1,x2,y2 = [float(x) for x in xy]
                    if (x2-x1)>=10 and (y2-y1)>=5 and float(score)>=valid_conf:
                        opts.append((float(score),x1,y1,x2,y2))
            opt=max(opts,default=None)
            record={'frame_idx':i,'t_video_s':i/md['fps'], 'detectado':opt is not None,
                    'x1':math.nan,'y1':math.nan,'x2':math.nan,'y2':math.nan,'confianca':math.nan,
                    'classe_id':2 if opt is not None else math.nan}
            if opt is not None:
                c,x1,y1,x2,y2=opt
                record.update(confianca=c,x1=x1,y1=y1,x2=x2,y2=y2)
            rows.append(record)
            if i%100==0: print(f'YOLO: {i+1}/{limit} quadros',flush=True)
    finally: cap.release()
    df=pd.DataFrame(rows)
    return validate_cache_df(df, dict(md,frames=limit),limit,'inferencia_yolo'),dict(
        checkpoint=str(weights),checkpoint_sha256=digest, img_size=1920,conf_candidates=conf_candidates,
        conf_selection=valid_conf, iou_nms=.7, classe_id=2, modelo='YOLO26n_finetune_congelado',
        advertencia='Política de seleção exploratória: maior confiança entre candidatos válidos; pode diferir da seleção histórica v1.6.')


def normalize_frames(df, md, limit):
    x=df.iloc[:limit].copy()
    x['second']=np.floor(x['t_video_s'].astype(float)).astype(int)
    x['box_width_px']=x['x2']-x['x1']
    x['box_height_px']=x['y2']-x['y1']
    x['caixa_confiavel_para_largura']=(x['detectado'].map(is_true)&(x['confianca']>=.25)&
        (x['box_width_px']>=10)&(x['box_height_px']>=5))
    return x


def per_second(df, min_frames=5, max_iqr=.35):
    # Causal Hampel sobre log-largura: histórico de deltas anteriores, sem usar GT nem erros de referência.
    rows=[]; history={}; previous=None
    for sec in range(int(df['second'].min()),int(df['second'].max())+1):
        sub=df[df['second']==sec]
        reliable=sub.loc[sub['caixa_confiavel_para_largura'],'box_width_px'].to_numpy(float)
        n=len(reliable)
        median=float(np.median(reliable)) if n else math.nan
        iq=float(np.subtract(*np.percentile(reliable,[75,25]))) if n else math.nan
        ratio=iq/median if n and median>0 else math.nan
        logw=float(math.log(median)) if n and median>0 else math.nan
        delta=logw-previous[1] if previous and sec==previous[0]+1 and math.isfinite(logw) else math.nan
        reason=[]
        if n<min_frames:reason.append('menos_de_5_caixas')
        if n and ratio>max_iqr:reason.append('largura_IQR_instavel')
        prev_deltas=[history[t] for t in range(sec-5,sec) if t in history and math.isfinite(history[t])]
        if math.isfinite(delta) and len(prev_deltas)>=3:
            mid=float(np.median(prev_deltas))
            mad=float(np.median(np.abs(np.array(prev_deltas)-mid)))
            threshold=max(3*1.4826*mad,.35)
            if abs(delta-mid)>threshold:reason.append('salto_hampel_causal')
        history[sec]=delta
        previous=(sec,logw) if math.isfinite(logw) else None
        passed=(n>0 and not reason)
        estimate=float(MODEL_A*(median**MODEL_B)) if passed else math.nan
        rows.append(dict(second=sec,quadros_no_segundo=len(sub),caixas_confiaveis=n,
                         largura_mediana_px=median,iqr_rel_largura=ratio,delta_logw=delta,
                         qc_aprovado=bool(passed),motivo_abstencao=';'.join(reason) if reason else '',
                         distancia_regressao_exploratoria_m=estimate,
                         natureza='modelo_global_farol_transferido; NAO OOF; NAO validado nesta camera'))
    return pd.DataFrame(rows)


def validate_metadata(md, args):
    if args.fonte=='cache':
        if args.seletor=='temporal' and not args.aceitar_supervisao:
            raise ValueError('Associação temporal contém seis sementes supervisionadas; informe --aceitar-supervisao para uso descritivo.')
    if args.depth_every<0:raise ValueError('--depth-every deve ser >=0')
    if args.video_scale<1:raise ValueError('--video-scale deve ser >=1')
    if md['width']!=3840 or md['height']!=2160:
        raise RuntimeError('Equação e limiares v1.9.8 congelados para 3840x2160. Novo formato requer auditoria explícita de escala/câmera antes do uso.')
    if args.fonte=='novo-yolo' and not args.yolo_weights.exists():raise FileNotFoundError(args.yolo_weights)
    if args.depth_every and not args.depth_weights.exists():raise FileNotFoundError(f'Depth Pro solicitado, mas pesos indisponíveis: {args.depth_weights}')
    if args.depth_every and not args.depth_repo.exists():raise FileNotFoundError(f'Repositório Depth Pro não encontrado: {args.depth_repo}')


def telemetry_nominal(sec, args):
    if not args.usar_referencia_hipotetica: return None
    if not args.telemetry.exists(): raise FileNotFoundError(f'Telemetria indisponível: {args.telemetry}')
    tel=pd.read_csv(args.telemetry)
    cols=['time_s','height_m','distance_home_corrigida_m']
    if not set(cols).issubset(tel.columns): raise ValueError('Telemetria não possui colunas esperadas: '+','.join(cols))
    tel=tel[cols].apply(pd.to_numeric,errors='coerce').dropna().sort_values('time_s').drop_duplicates('time_s')
    t=tel.time_s.to_numpy(float);height=tel.height_m.to_numpy(float);dist=tel.distance_home_corrigida_m.to_numpy(float)
    out=[]
    for s in sec.second:
        t0=float(s)+.5+args.offset_telemetria_s
        j=np.searchsorted(t,t0,'left')
        ok=0<j<len(t) and t[j]-t[j-1]<=2.0
        if ok:
            h=float(np.interp(t0,t[j-1:j+1],height[j-1:j+1]))
            d=float(np.interp(t0,t[j-1:j+1],dist[j-1:j+1]))
            R=math.sqrt(d*d+args.baseline_m**2+(h-args.camera_height_m)**2)
        else:R=math.nan
        out.append(R)
    return np.array(out,float)


def load_depth(args):
    # Código público Apple ml-depth-pro. Sem download automático nem calibração escondida.
    import torch
    from PIL import Image
    sys.path.insert(0,str(args.depth_repo))
    try:
        import depth_pro
        from depth_pro.depth_pro import DEFAULT_MONODEPTH_CONFIG_DICT
    except ImportError as e:
        raise RuntimeError('Dependências do Depth Pro ausentes. Instale o ml-depth-pro no ambiente e verifique --depth-repo.') from e
    cfg=dataclasses.replace(DEFAULT_MONODEPTH_CONFIG_DICT,checkpoint_uri=str(args.depth_weights))
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    precision=torch.float16 if device.type=='cuda' else torch.float32
    model,transform=depth_pro.create_model_and_transforms(config=cfg,device=device,precision=precision)
    model.eval()
    return model,transform,torch,Image,device


def depth_samples(args, df, md, limit, out, meta):
    if not args.depth_every:return None
    ck=sha256(args.depth_weights)
    video_id=sha256(args.video) if args.hash_video else f'{args.video.stat().st_size}:{args.video.stat().st_mtime_ns}'
    fingerprint=hashlib.sha256(json.dumps(dict(depth_checkpoint=ck,video=video_id,source=meta,
         every=args.depth_every,limit=limit,focal=args.focal_px),sort_keys=True).encode()).hexdigest()
    path=out/'profundidade_amostrada.jsonl';tag=out/'profundidade_proveniencia.json'
    old={}
    if path.exists() or tag.exists():
        if not tag.exists():raise RuntimeError('Cache Depth sem proveniência; separe a pasta de saída.')
        doc=json.loads(tag.read_text(encoding='utf-8'))
        if doc['fingerprint']!=fingerprint:raise RuntimeError('Proveniência Depth divergente. Escolha outra --saida.')
        if path.exists():
            with path.open(encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d=json.loads(line);old[int(d['frame_idx'])]=d
    else: write_json(dict(fingerprint=fingerprint,video=video_id,checkpoint=ck,every=args.depth_every,
                          estrategia='Depth Pro em quadro COMPLETO, amostragem explícita; sem preenchimento entre quadros'),tag)
    needed=[int(i) for i in range(0,limit,args.depth_every) if is_true(df.iloc[i]['caixa_confiavel_para_largura'])]
    todo=[i for i in needed if i not in old]
    if not todo:return old
    print(f'Depth Pro: {len(todo)} quadros ainda pendentes; {len(old)} já persistidos.',flush=True)
    model,transform,torch,Image,device=load_depth(args)
    cap=cv2.VideoCapture(str(args.video));
    todo_set=set(todo);done_count=0
    try:
        with path.open('a',encoding='utf-8') as f:
            # Decodificação SEQUENCIAL garante a identificação ordinal dos frames,
            # sem confiar em seek aleatório potencialmente impreciso em H.264/H.265.
            for i in range(limit):
                ok=cap.grab()
                if not ok:raise RuntimeError(f'Leitura Depth falhou no frame {i}')
                if i not in todo_set:continue
                ok,img=cap.retrieve()
                if not ok:raise RuntimeError(f'Falha ao recuperar o quadro {i} para Depth Pro.')
                row=df.iloc[i];start=time.perf_counter()
                try:
                    with torch.inference_mode():
                        rgb=cv2.cvtColor(img,cv2.COLOR_BGR2RGB)
                        model_input=transform(Image.fromarray(rgb))
                        pred=model.infer(model_input, f_px=args.focal_px)
                        depth=np.asarray(pred['depth'].detach().float().cpu().numpy()).squeeze()
                        if depth.shape != rgb.shape[:2]:
                            raise RuntimeError(f'Depth map {depth.shape} != frame {rgb.shape[:2]}; downscale não permitido silenciosamente')
                        x1,y1,x2,y2= [float(row[x]) for x in ('x1','y1','x2','y2')]
                        coords=(max(0,int(math.floor(x1))),max(0,int(math.floor(y1))),
                                min(md['width'],int(math.ceil(x2))),min(md['height'],int(math.ceil(y2))))
                        a,b,c,d=coords
                        roi=depth[b:d,a:c]
                        good=roi[np.isfinite(roi)&(roi>0)]
                        z=float(np.percentile(good,25)) if len(good)>=6 else math.nan
                        fo=value_number(pred.get('focallength_px'))
                        result=dict(frame_idx=i,second=int(row['second']),depth_pro_Z_axial_p25_m=z,
                                    n_pixels_depth_validos=int(len(good)),focal_utilizada_px=fo,
                                    elapsed_s=time.perf_counter()-start,depth_status='ok' if math.isfinite(z) else 'pixels_insuficientes',
                                    roi_status='caixa_nao_confirmada_como_drone',fisicamente_validado=False)
                except torch.cuda.OutOfMemoryError as e:
                    torch.cuda.empty_cache()
                    raise RuntimeError('GPU sem VRAM para Depth Pro em quadro completo 4K. Execute no Colab/CPU; não alterei resolução automaticamente.') from e
                f.write(json.dumps(result,ensure_ascii=False,allow_nan=True)+'\n'); f.flush();os.fsync(f.fileno())
                old[i]=result;done_count+=1
                print(f'Depth {done_count}/{len(todo)}: frame={i}, Z={result["depth_pro_Z_axial_p25_m"]:.2f}, {result["elapsed_s"]:.1f}s',flush=True)
    finally:cap.release()
    return old


def add_meta_to_frame_table(x, secs, depth):
    s=secs.set_index('second')
    x=x.merge(s[['qc_aprovado','motivo_abstencao','distancia_regressao_exploratoria_m']],
              left_on='second',right_index=True,how='left',validate='many_to_one')
    x['depth_pro_Z_axial_p25_m']=np.nan
    x['depth_status']='nao_processado' if depth is None else 'nao_amostrado'
    if depth is not None:
        for i,r in depth.items():
            idx=x.index[x['frame_idx']==int(i)]
            if len(idx):
                x.loc[idx,'depth_pro_Z_axial_p25_m']=r['depth_pro_Z_axial_p25_m']
                x.loc[idx,'depth_status']=r['depth_status']
    return x


def label(frame, lines, box=None, width=1920, height=1080, native_width=3840, native_height=2160):
    frame=cv2.resize(frame,(width,height),interpolation=cv2.INTER_AREA)
    if box is not None and all(math.isfinite(v) for v in box):
        xx=width/native_width; yy=height/native_height
        x1,y1,x2,y2=[int(v*(xx if j%2==0 else yy)) for j,v in enumerate(box)]
        cv2.rectangle(frame,(x1,y1),(x2,y2),(28,220,90),2)
    scale=max(.6,width/1920)
    top=min(height-1,int(24+len(lines)*32*scale))
    cv2.rectangle(frame,(0,0),(min(width,1120),top),(16,18,18),-1)
    for i,t in enumerate(lines):
        cv2.putText(frame,t[:105],(18,int(34+i*32*scale)),cv2.FONT_HERSHEY_SIMPLEX,
                    .85*scale,(245,245,245),max(1,int(2*scale)),cv2.LINE_AA)
    return frame


def render(args, md, all_df, secs, out):
    dest=out/'VIDEO_FINAL_EXPLORATORIO_SEM_AUDIO.mp4';tmp=out/'VIDEO_EM_CONSTRUCAO.mp4'
    w=md['width']//args.video_scale;h=md['height']//args.video_scale
    w-=w%2;h-=h%2
    if w<100 or h<100: raise ValueError('Escala de saída excessiva.')
    cap=cv2.VideoCapture(str(args.video))
    encoder=cv2.VideoWriter(str(tmp),cv2.VideoWriter_fourcc(*'mp4v'),md['fps'],(w,h))
    if not encoder.isOpened():cap.release();raise RuntimeError('Não foi possível criar mp4v. Instale codec MPEG4/FFmpeg.')
    secmap=secs.set_index('second').to_dict('index')
    try:
        for i,row in enumerate(all_df.itertuples(index=False)):
            ok,img=cap.read()
            if not ok:raise RuntimeError(f'Vídeo terminou inesperadamente no quadro {i}')
            ss=secmap[int(row.second)]
            box=None
            if is_true(row.detectado):box=[value_number(getattr(row,k)) for k in ('x1','y1','x2','y2')]
            d=value_number(ss['distancia_regressao_exploratoria_m'])
            dz=value_number(getattr(row,'depth_pro_Z_axial_p25_m'))
            reason=ss['motivo_abstencao'] or 'caixa insuficiente ou ausência de alvo'
            line_width=(f'REGRESSAO [PROVISORIA, calib. farol]: {d:.1f} m / agregado do segundo' if math.isfinite(d)
                else f'REGRESSAO: ABSTENCAO - {reason}')
            line_depth=(f'Depth Pro Z AXIAL [nao validado]: {dz:.1f} m (frame amostrado)' if math.isfinite(dz)
                else f'Depth Pro Z: {getattr(row,"depth_status")}')
            lines=[f'TCC Drone v1.9.8  |  t={row.t_video_s:.2f}s  |  frame {i}',
                   'YOLO: CAIXA CANDIDATA (alvo nao validado)' if box is not None else 'YOLO: sem caixa selecionada',
                   line_width,line_depth,'TRANSFERENCIA EXPLORATORIA. NAO E MEDICAO FISICA CERTIFICADA.']
            encoder.write(label(img,lines,box,width=w,height=h, native_width=md["width"],native_height=md["height"]))
            if (i+1)%300==0:print(f'Vídeo: {i+1}/{len(all_df)} quadros',flush=True)
    finally:cap.release();encoder.release()
    os.replace(tmp,dest)
    return dest


def main(argv=None):
    p=argparse.ArgumentParser(description='Pipeline completo YOLO + regressão + Depth Pro; sem treinamento.')
    p.add_argument('acao',choices=['auditar','piloto','executar'])
    p.add_argument('--video',type=Path,default=DEFAULT_VIDEO)
    p.add_argument('--saida',type=Path,default=DEFAULT_OUTPUT)
    p.add_argument('--fonte',choices=['cache','novo-yolo'],default='cache',
                   help='cache: inferência YOLO congelada do IMG_5962; novo-yolo: inferir com best.pt fixo')
    p.add_argument('--seletor',choices=['original','temporal'],default='original')
    p.add_argument('--aceitar-supervisao',action='store_true',help='reconhece 6 sementes humanas do rastreador temporal')
    p.add_argument('--yolo-weights',type=Path,default=DEFAULT_WEIGHT)
    p.add_argument('--depth-weights',type=Path,default=DEFAULT_DEPTH)
    p.add_argument('--depth-repo',type=Path,default=DEFAULT_DEPTH_REPO)
    p.add_argument('--depth-every',type=int,default=0,
                   help='0 desabilitado; 30 = 1 quadro/s a 30 FPS; 1 = todos os quadros elegíveis')
    p.add_argument('--focal-px',type=float,default=None,help='somente se calibrada para a entrada exata (pixels)')
    p.add_argument('--max-frames',type=int,default=None,help='usar para piloto; default = 120 no piloto')
    p.add_argument('--video-scale',type=int,default=2,help='2 -> vídeo final 1920x1080, coords das caixas convertidas')
    p.add_argument('--sem-video',action='store_true')
    p.add_argument('--hash-video',action='store_true',help='verificar SHA256 íntegro do MOV (automático no modo cache)')
    p.add_argument('--permitir-pts-nao-verificados',action='store_true',help='somente exploração com ffprobe indisponível/VFR: tempo por idx/fps não demonstrado')
    p.add_argument('--telemetry',type=Path,default=DEFAULT_TELEMETRY)
    p.add_argument('--usar-referencia-hipotetica',action='store_true',help='telemetria + geometria presumida; não é GT físico')
    p.add_argument('--offset-telemetria-s',type=float,default=11.2)
    p.add_argument('--baseline-m',type=float,default=.9)
    p.add_argument('--camera-height-m',type=float,default=.15)
    args=p.parse_args(argv)
    if args.acao=='piloto' and args.max_frames is None:args.max_frames=120
    if args.max_frames is not None and args.max_frames<1:p.error('--max-frames deve ser positivo')
    args.video=args.video.expanduser().resolve();args.saida=args.saida.expanduser().resolve()
    md=check_video(args.video,args.max_frames)
    limit=md['inspected_frames']
    validate_metadata(md,args)
    pts=audit_pts(args.video,md,args.permitir_pts_nao_verificados)
    provenance=dict(version='1.9.8', video=str(args.video),video_metadata=md, auditoria_temporal_pts=pts,fonte=args.fonte,
        seletor=args.seletor,regressao=dict(a=MODEL_A,b=MODEL_B,unidade_entrada='largura_px_no_video_nativo',
        agregacao='mediana_por_segundo_das_caixas_confiaveis',
        origem='farol, ajuste global posterior; NÃO OOF e NÃO calibrado neste novo voo'),
        camera_compativel_com_farol='NAO_VERIFICADO',
        alcance_metrico_independente_validado=False,
        depth_pro=dict(amostragem_um_em_cada=args.depth_every,origem_focal='informada' if args.focal_px else 'estimada',
                       observacao='somente Z axial, ROI sem confirmação independente'),
        selector_temporal_supervisionado=args.seletor=='temporal',
        observacao='Resultados no NOVO VOO exploratórios; o modelo foi congelado e não foi recalibrado.',
        versions=dict(python=sys.version,opencv=cv2.__version__,pandas=pd.__version__,numpy=np.__version__))
    if args.hash_video or args.fonte=='cache':
        dig=sha256(args.video);provenance['video_sha256']=dig
        if args.fonte=='cache' and dig!=EXPECTED_VIDEO_SHA:
            raise RuntimeError(f'SHA256 do vídeo diferente do original registrado: {dig}; cache NÃO reutilizado.')
    if args.fonte=='cache':df,source=archived_yolo(md,limit,args.seletor)
    else:
        if args.acao=='auditar':
            if sha256(args.yolo_weights)!=EXPECTED_YOLO_SHA:raise RuntimeError('Pesos diferentes do congelado.')
            df=None;source=dict(checkpoint=str(args.yolo_weights),sha256=EXPECTED_YOLO_SHA)
        else:df,source=predict_yolo(args.video,args.yolo_weights,md,limit)
    provenance['fonte_deteccao']=source
    if args.acao=='auditar':
        args.saida.mkdir(parents=True,exist_ok=True)
        write_json(provenance,args.saida/'AUDITORIA_ENTRADAS_v1_9_8.json')
        print('AUDITORIA APROVADA: vídeo, seleção e parâmetros. NÃO houve inferência/treinamento.\n'
              f'Quadros: {md["frames"]}; FPS: {md["fps"]}; resolução: {md["width"]}x{md["height"]}.')
        if args.fonte!='cache' and not args.hash_video:print('Nota: sha256 do vídeo NÃO foi conferido no modo novo-yolo. Use --hash-video.')
        return 0
    if args.acao=='piloto' and args.saida==DEFAULT_OUTPUT:args.saida=DEFAULT_OUTPUT/'PILOTO_120'
    args.saida.mkdir(parents=True,exist_ok=True)
    saved=args.saida/'PROVENIENCIA_v1_9_8.json'
    if saved.exists():
        prev=json.loads(saved.read_text(encoding='utf-8'))
        keys=('video','fonte','seletor')
        if any(prev.get(k)!=provenance.get(k) for k in keys) or prev['video_metadata'].get('inspected_frames')!=limit:
            raise RuntimeError('Saída existente pertence a outra execução/protocolo. Use outra pasta --saida; os resultados antigos permanecem intactos.')
    write_json(provenance,saved)
    df=normalize_frames(df,md,limit)
    sec=per_second(df)
    if args.usar_referencia_hipotetica:
        sec['R_referencia_nominal_HIPOTETICA_m']=telemetry_nominal(sec,args)
        sec['status_referencia']='nao_certificada_geometria_sincronismo_provisorios'
    depth=depth_samples(args,df,md,limit,args.saida,source)
    annotated=add_meta_to_frame_table(df,sec,depth)
    write_csv(annotated,args.saida/'RESULTADOS_POR_QUADRO.csv')
    write_csv(sec,args.saida/'RESULTADOS_POR_SEGUNDO.csv')
    n_emit=int(annotated['detectado'].sum());n_seconds_valid=int(sec['qc_aprovado'].sum())
    summary=dict(etapa='1.9.8',natureza='exploratoria_sem_validacao_fisica',
        video_frames=int(md['frames']),processed_frames=limit,seconds_total=len(sec),
        caixas_yolo_selecionadas=n_emit,cobertura_caixas_pct=100*n_emit/limit,
        segundos_estimativa_regressao=n_seconds_valid,
        cobertura_regressao_por_segundo_pct=100*n_seconds_valid/len(sec),
        segundos_sem_estimativa=len(sec)-n_seconds_valid,
        depth_quadros_com_Z=int(annotated['depth_pro_Z_axial_p25_m'].notna().sum()),
        depth_quadros_amostrados_programados=len(range(0,limit,args.depth_every)) if args.depth_every else 0,
        nenhum_mae_reportado_sem_referencia_certificada=True,
        seletor_supervisionado=(args.seletor=='temporal'),
        anotacao='Caixa selecionada não significa detecção correta; estimador global de outro voo: extrapolação exploratória')
    video_path = None
    if not args.sem_video:video_path=render(args,md,annotated,sec,args.saida)
    summary['video_sem_audio']=str(video_path) if video_path else None
    write_json(summary,args.saida/'RESUMO_EXECUCAO_v1_9_8.json')
    report=f'''# Relatório da execução — TCC Drone v1.9.8\n\n- Vídeo: `{args.video}`.\n- Quadros analisados: **{limit}/{md['frames']}** ({md['fps']:.3f} FPS).\n- Fonte das caixas: **{args.fonte} / {args.seletor}**.{' ASSOCIAÇÃO TEMPORAL SUPERVISIONADA.' if args.seletor=='temporal' else ''}\n- Caixas selecionadas: **{n_emit}/{limit}** ({100*n_emit/limit:.2f}%). Não representa recall/precision.\n- Segundos com estimativa de regressão emitida: **{n_seconds_valid}/{len(sec)}** ({100*n_seconds_valid/len(sec):.2f}%).\n- Profundidades Depth Pro Z emitidas: **{summary['depth_quadros_com_Z']} quadros** (amostragem a cada {args.depth_every} frames; zero=desligado).\n- Modelo de largura: `d_hat = {MODEL_A:.5f} * w**({MODEL_B:.6f})`, largura mediana de caixas confiáveis por segundo, no quadro original.\n- **ATENÇÃO:** a regressão foi calibrada no farol e NÃO validada para a câmera, zoom e domínio do novo voo. Qualquer distância exibida é uma **transferência exploratória**, não uma medição física comprovada.\n- **ATENÇÃO:** Depth Pro entrega **Z axial** no pixel/ROI selecionada, que pode não conter drone. NÃO interpretar como alcance radial R.\n- **ATENÇÃO:** nenhuma MAE/RMSE de distância física foi calculada. A referência de telemetria, se solicitada, é hipotética e depende de parâmetros não certificados.\n- Estimativas por segundo usam todo o segundo, não são predições causais instantâneas dentro dele. A vídeo exibido não é demonstração em tempo real.\n- Saída audiovisual, quando gerada, é **sem áudio**; vídeo integral só está completo quando o total de quadros analisados == {md['frames']}.\n\n## Arquivos\n\n`RESULTADOS_POR_QUADRO.csv`, `RESULTADOS_POR_SEGUNDO.csv`, `PROVENIENCIA_v1_9_8.json`, `RESUMO_EXECUCAO_v1_9_8.json` e vídeo anotado quando habilitado.\n'''
    (args.saida/'RELATORIO_INTEGRACAO_v1_9_8.md').write_text(report,encoding='utf-8')
    print('\nCONCLUÍDO — resultados em',args.saida)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:
        print('\nFALHA SEGURA: '+str(e),file=sys.stderr)
        raise
