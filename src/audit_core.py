"""Experimento monocular do TCC — rotinas compartilhadas, documentadas em português.

Não contém pesos, dados privados nem resultados experimentais pré-calculados.
As importações pesadas dos modelos ocorrem apenas quando a inferência é solicitada.
"""
from pathlib import Path
from fractions import Fraction
from dataclasses import replace
import copy, gc, hashlib, importlib.metadata, io, json, math, os, platform
import shutil, sqlite3, subprocess, sys, time, warnings
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

VERSION = '1.0.0'
SPECS = {'largura':['w'], 'altura':['h'], 'area':['area'],
         'largura_altura':['w','h'], 'area_aspecto':['area','aspect'],
         'profundidade':['z'], 'area_profundidade':['area','z'], 'area_fixa':['area']}

# %% Configuração, arquivos e rastreabilidade

def default_config(profile='novo'):
    """Ausências são None: nenhum dado de um novo voo é presumido como o do Farol."""
    farol = profile == 'farol'
    return {
      'profile':profile, 'experiment_id':'farol_reproducao' if farol else 'novo_voo_001',
      'video':None, 'telemetry':None, 'yolo_weights':None, 'depth_weights':None,
      'depth_repo':None, 'depth_revision':'main', 'device':'auto',
      'video_role':'recorte_final' if farol else 'novo_video',
      'farol_clip_confirmed':False, 'rotation_ccw':None, 'hdr_policy':'stop',
      'pixel_aspect_policy':'stop', 'persist_frames':False,
      'clock':'legacy_opencv' if farol else 'pts', 'legacy_fps':30.,
      'source_clip_start_s':85/30 if farol else 0.,
      'sync':{'a':1., 'b':4.8 if farol else None, 'events':[],
              'origin':'protocolo TCC' if farol else None, 'uncertainty_s':None},
      'telemetry_columns':{'t':'OSD.flyTime [s]', 'height':'OSD.height [ft]',
                          'radius':'HOME.distance [ft]', 'east':'east_m',
                          'north':'north_m', 'up':'up_m', 'phi':'phi_deg'},
      'telemetry_units':{'height':'ft','radius':'ft'},
      'max_telemetry_gap_s':None if farol else 1.,
      'geometry':{'mode':'nominal', 'camera_height_m':1.5 if farol else None,
                  'camera_takeoff_horizontal_m':1.5 if farol else None,
                  'camera_ground_above_takeoff_m':0. if farol else None,
                  'relative_phi_deg':None, 'camera_enu_m':None,
                  'vertical_reference_confirmed':farol, 'home_fixed_confirmed':farol,
                  'origin':'estimativas do TCC' if farol else None},
      'field':{'date':'2026-07-23' if farol else None,'timezone':None,
        'location':'Farol da Ilha da Moela' if farol else None,'operator':None,
        'drone':'DJI Mini 2' if farol else None,'drone_dimensions_m':None,
        'camera':'iPhone 17 Pro (identificação no TCC; conferir)' if farol else None,
        'lens':None,'zoom':1. if farol else None,'fixed_camera':True if farol else None,
        'constant_zoom':True if farol else None,'stabilization':None,'autofocus':None,
        'yaw_pitch_roll_deg':None,'camera_coordinates_datum':None,
        'takeoff_coordinates_datum':None,'angle_definition':None,'vertical_datum':None,
        'lighting':None,'background':None,'occlusions':None,'uncertainties':None,
        'notes':None,'provenance':{}},
      'intrinsics':None, # {fx,fy,cx,cy,width,height,dist,origin,reprojection_error_px}
      'radial_extension':False,
      'evaluation_windows_s':None, # lista [[inicio,fim[...]]; None = todo o vídeo
      'yolo':{'imgsz':1920,'record_conf':.001,'reliable_conf':.25,
              'min_width':10.,'min_height':5.,'drone_class_id':None,
              'confirmed_class_name':None,'iou_nms':.7},
      'depth':{'enabled':True,'focal_px':1440. if farol else None,
               'focal_resolution':[3840,2160] if farol else None,
               'percentile':25.,'min_pixels':6,'min_m':1.,'max_m':150.,
               'calibration':{'intercept':1.4600571394959514,'slope':.5026751660343942,
                              'origin':'ensaio anterior iPhone XR; transferência'} if farol else None},
      'regression':{'mode':'calibrate' if farol else 'independent',
                    'frozen_model':None,'domain_review':None,'block_s':20.,'ridge':1.,
                    'width_scale':1.,'width_scale_reason':None},
      'quality':{'min_frames':5,'max_iqr':.35,'history_s':5,'min_history':3,
                 'mad_factor':1.4826,'k':3.,'min_log_jump':.35},
      'distance_bins_m':[0,10,20,30,40,60,100,150,100000],
      'render':{'crf':20,'preset':'fast','preserve_audio':False,'preview_width':960},
    }

def clean_json(x):
    if isinstance(x, dict): return {str(k):clean_json(v) for k,v in x.items()}
    if isinstance(x, (list,tuple,np.ndarray)): return [clean_json(v) for v in x]
    if isinstance(x, Path): return str(x)
    if isinstance(x, np.generic): return clean_json(x.item())
    if isinstance(x, float) and not math.isfinite(x): return None
    return x

def save_json(value, path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(clean_json(value),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    os.replace(tmp,path)

def save_csv(df,path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp'); df.to_csv(tmp,index=False); os.replace(tmp,path)

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''): h.update(block)
    return h.hexdigest()

def fingerprint(obj):
    return hashlib.sha256(json.dumps(clean_json(obj),sort_keys=True).encode()).hexdigest()

def run(cmd):
    p=subprocess.run([str(x) for x in cmd],capture_output=True,text=True)
    if p.returncode: raise RuntimeError('Falhou: '+str(cmd[0])+'\n'+p.stderr[-5000:])
    return p.stdout

def project(root,experiment_id):
    """Cria a estrutura; nunca sobrescreve entradas fornecidas pelo pesquisador."""
    root=Path(root).expanduser().resolve()
    for folder in ['inputs/video','inputs/telemetry','inputs/weights/yolo',
        'inputs/weights/depth_pro','inputs/calibration','inputs/annotations',
        'inputs/legacy/farol','inputs/manifests','configs','vendor',
        f'outputs/{experiment_id}/tables',f'outputs/{experiment_id}/figures',
        f'outputs/{experiment_id}/videos',f'outputs/{experiment_id}/audit',
        f'outputs/{experiment_id}/frames',f'outputs/{experiment_id}/cache']:
        p=root/folder; p.mkdir(parents=True,exist_ok=True)
        note=p/'LEIA_ME.txt'
        if folder.startswith('inputs') and not note.exists():
            note.write_text('Coloque aqui as entradas correspondentes ao nome da pasta.\n'
                            'Também é possível apontar para outro caminho do Drive na configuração.\n',encoding='utf-8')
    return root, root/'outputs'/experiment_id

def choose_file(config,key,folder,patterns):
    """Um único candidato pode ser escolhido; ambiguidades nunca são resolvidas ao acaso."""
    if config[key]:
        p=Path(config[key]).expanduser()
        if not p.is_file(): raise FileNotFoundError(f'{key}: arquivo não encontrado: {p}')
        return str(p.resolve())
    found=sorted(set(p for pattern in patterns for p in Path(folder).glob(pattern)))
    if len(found)!=1:
        raise FileNotFoundError(f'{key}: informe o caminho na configuração. Candidatos em {folder}: '+str(found))
    config[key]=str(found[0].resolve()); return config[key]

def environment():
    versions={}
    for name in ['numpy','pandas','scipy','Pillow','av','torch','torchvision','ultralytics','timm','opencv-python']:
        try: versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: versions[name]=None
    return {'python':sys.version,'platform':platform.platform(),'versions':versions,
            'pipeline_version':VERSION,'pipeline_sha256':digest(__file__)}

# %% Auditoria nativa do vídeo

def probe(path):
    return json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',path]))

def video_info(path):
    info=probe(path); s=next(s for s in info['streams'] if s['codec_type']=='video')
    rotation=float(s.get('tags',{}).get('rotate',0))
    for side in s.get('side_data_list',[]):
        if 'rotation' in side: rotation=float(side['rotation'])
    return info,s,rotation

def frames(path,rotation_ccw=0):
    """Decodificação por PTS. Nenhum resize é aplicado à imagem usada nas medidas."""
    import av
    with av.open(str(path)) as container:
        stream=container.streams.video[0]
        for i,f in enumerate(container.decode(stream)):
            if f.pts is None: raise ValueError(f'Quadro {i} sem PTS; corrigir a entrada explicitamente.')
            rgb=f.to_ndarray(format='rgb24')
            if rotation_ccw: rgb=np.ascontiguousarray(np.rot90(rgb,int(rotation_ccw)//90))
            yield i,float(f.pts*f.time_base),rgb,f

def legacy_times(path,fps):
    import cv2
    cap=cv2.VideoCapture(str(path)); times=[]; sources=[]
    try:
        while True:
            ok,_=cap.read()
            if not ok: break
            fallback=len(times)/fps; value=cap.get(cv2.CAP_PROP_POS_MSEC)/1000
            good=np.isfinite(value) and value>=0 and abs(value-fallback)<=.25
            times.append(value if good else fallback); sources.append('opencv_msec' if good else 'index_fps')
    finally: cap.release()
    return times,sources

def audit_video(c,out):
    out=Path(out); info,s,rotation=video_info(c['video'])
    if c['rotation_ccw'] is None:
        # ffprobe expressa a rotação da matriz de exibição em sentido anti-horário.
        c['rotation_ccw']=int(round(rotation))%360
    if c['rotation_ccw'] not in (0,90,180,270): raise ValueError('Rotação deve ser 0, 90, 180 ou 270 graus.')
    transfer=s.get('color_transfer','unknown'); sar=s.get('sample_aspect_ratio','1:1')
    hdr=transfer in ['smpte2084','arib-std-b67']
    report={'ffprobe':info,'sha256':digest(c['video']),'size_bytes':Path(c['video']).stat().st_size,
            'free_bytes':shutil.disk_usage(out).free,'hdr':hdr,'rotation_ccw':c['rotation_ccw'],
            'color_policy':c['hdr_policy'],'pixel_aspect':sar}
    save_json(report,out/'audit/audit_video.json')
    if hdr and c['hdr_policy']!='sdr_acknowledged':
        raise ValueError('Vídeo HDR. Faça conversão SDR explícita na célula própria e use o novo arquivo; '
                         'não basta ignorar a transferência de cor.')
    if sar not in ('1:1','0:1','N/A') and c['pixel_aspect_policy']!='acknowledge':
        raise ValueError('Pixels não quadrados: normalizar explicitamente e conferir calibração.')
    rows=[]; hashes=[]; first=None; last_duration=None
    for i,pts,rgb,f in frames(c['video'],c['rotation_ccw']):
        first=pts if first is None else first
        dur=float(f.duration*f.time_base) if f.duration else np.nan
        last_duration=dur
        rows.append({'frame_idx':i,'pts':f.pts,'time_base':str(f.time_base),
          'pts_abs_s':pts,'t':pts-first,'duration_s':dur,'width':rgb.shape[1],
          'height':rgb.shape[0],'timestamp_source':'pts','pixel_sha1':hashlib.sha1(rgb.tobytes()).hexdigest()})
        if c['persist_frames']: Image.fromarray(rgb).save(out/'frames'/f'{i:08d}.png')
        if i%300==0: print(f'Auditoria: {i+1} quadros',flush=True)
    manifest=pd.DataFrame(rows)
    if manifest.empty: raise ValueError('Nenhum quadro decodificado.')
    if (np.diff(manifest.pts_abs_s)<=0).any(): raise ValueError('PTS repetidos ou fora de ordem: não alterar silenciosamente.')
    if manifest[['width','height']].drop_duplicates().shape[0]!=1: raise ValueError('Resolução variável: separar segmentos.')
    intervals=np.diff(manifest.pts_abs_s)
    nominal=float(Fraction(s.get('avg_frame_rate','30/1'))) if s.get('avg_frame_rate')!='0/0' else 30.
    if not np.isfinite(last_duration) or last_duration<=0:
        last_duration=float(np.median(intervals)) if len(intervals) else 1/nominal
        report['last_duration_source']='mediana dos intervalos; ausência no quadro final'
    else: report['last_duration_source']='duração do quadro'
    manifest.loc[manifest.index[-1],'duration_s']=last_duration
    if len(manifest)>1: manifest.loc[manifest.index[:-1],'duration_s']=intervals
    if c['clock']=='legacy_opencv':
        t,origins=legacy_times(c['video'],c['legacy_fps'])
        if len(t)!=len(manifest): raise ValueError('OpenCV e PyAV decodificaram contagens diferentes.')
        manifest['t']=t; manifest['timestamp_source']=origins
        if (np.diff(manifest.t)<0).any(): raise ValueError('Relógio legado não monotônico.')
    manifest['original_time_s']=manifest.t+c['source_clip_start_s']
    manifest['second']=np.floor(manifest.t).astype(int)
    report.update({'frames':len(manifest),'width':int(manifest.width.iloc[0]),
       'height':int(manifest.height.iloc[0]),'duration_s':float(manifest.pts_abs_s.iloc[-1]-first+last_duration),
       'first_pts_s':first,'nominal_fps':nominal,
       'variable_timing':bool(len(intervals)>1 and np.ptp(intervals)>1e-4),
       'exact_repeated_consecutive_frames':int((manifest.pixel_sha1==manifest.pixel_sha1.shift()).sum())})
    save_csv(manifest,out/'audit/frames_manifest.csv'); save_json(report,out/'audit/audit_video.json')
    selected={0,len(manifest)//2,len(manifest)-1}
    for i,_,rgb,_ in frames(c['video'],c['rotation_ccw']):
        if i in selected:
            im=Image.fromarray(rgb); im.thumbnail((960,540)); im.save(out/'audit'/f'amostra_{i:08d}.jpg')
    if c['profile']=='farol':
        report['historical_checks']={
          '3840x2160':(report['width'],report['height'])==(3840,2160),
          '3537_frames':len(manifest)==3537, '118_seconds':manifest.second.nunique()==118,
          '117_9_s':abs(report['duration_s']-117.9)<.08}
        save_json(report,out/'audit/audit_video.json')
        if not c['farol_clip_confirmed'] or not all(report['historical_checks'].values()):
            raise ValueError('Confira audit_video.json: reprodução exige o RECORTE correto, 3537 quadros '
                '3840×2160, 117,9 s, e farol_clip_confirmed=True. Use o outro notebook para material diferente.')
    return manifest,report

def convert_hdr(source,destination):
    """Conversão documentada HLG/PQ → SDR. A saída passa a ser uma NOVA entrada auditada."""
    if Path(destination).exists(): raise FileExistsError(destination)
    run(['ffmpeg','-v','error','-i',source,'-vf',
         'zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p',
         '-fps_mode','passthrough','-c:v','libx264','-crf','18','-c:a','copy',destination])

# %% Sincronização e referência geométrica

def timecode(value,fps=30):
    hh,mm,ss,ff=map(int,value.split(':'))
    if not (0<=mm<60 and 0<=ss<60 and 0<=ff<fps): raise ValueError('Timecode inválido.')
    return hh*3600+mm*60+ss+ff/fps

def synchronize(config):
    s=copy.deepcopy(config['sync']); events=s['events']
    if events:
        a=np.array([e['video_s'] for e in events],float); b=np.array([e['telemetry_s'] for e in events],float)
        if len(events)==1: s['a']=1.; s['b']=float(b[0]-a[0])
        else:
            if np.ptp(a)<=0: raise ValueError('Eventos devem ocorrer em tempos distintos.')
            s['a'],s['b']=map(float,np.linalg.lstsq(np.c_[a,np.ones(len(a))],b,rcond=None)[0])
        s['residuals_s']=(b-(s['a']*a+s['b'])).tolist()
        s['residual_note']='Dois eventos definem a reta; resíduos nulos não comprovam precisão.'
    if s['b'] is None: return s
    if not np.isfinite([s['a'],s['b']]).all() or s['a']<=0: raise ValueError('Sincronização inválida.')
    return s

def read_telemetry(c,out):
    if not c['telemetry']: return None
    raw=Path(c['telemetry']).read_text(encoding='utf-8-sig')
    first=raw.splitlines()[0]; sep=None
    if first.lower().startswith('sep='): sep=first[4:]; raw='\n'.join(raw.splitlines()[1:])
    source=pd.read_csv(io.StringIO(raw),sep=sep,engine='python')
    columns=c['telemetry_columns']; required=['t']+([] if c['geometry']['mode']=='none' else ['east','north','up'] if c['geometry']['mode']=='enu' else ['height','radius'])
    missing=[columns[k] for k in required if columns[k] not in source]
    if missing: raise ValueError(f'Colunas ausentes {missing}. Encontradas: {list(source)}')
    df=pd.DataFrame({k:pd.to_numeric(source[v],errors='coerce') for k,v in columns.items() if v in source})
    n=len(df); df=df[np.isfinite(df.t)].sort_values('t',kind='stable').drop_duplicates('t',keep='last')
    for k in ['height','radius']:
        if k in df:
            unit=c['telemetry_units'][k]
            if unit not in ('ft','m'): raise ValueError(f'Unidade de {k}: use ft ou m.')
            if unit=='ft': df[k]*=.3048
    if len(df)<2: raise ValueError('São necessários pelo menos dois instantes telemétricos.')
    save_csv(df,out/'audit/telemetry_normalized.csv')
    save_json({'original_rows':n,'kept_rows':len(df),'removed_time_or_duplicates':n-len(df),
               'gaps_s':np.diff(df.t),'columns':columns,'units':c['telemetry_units'],
               'sha256':digest(c['telemetry'])},out/'audit/audit_telemetry.json')
    return df

def interpolate(t,x,y,max_gap=None):
    """Não extrapola nem atravessa valores inválidos ou lacunas além do limite."""
    t=np.asarray(t,float); x=np.asarray(x,float); y=np.asarray(y,float)
    result=np.full(t.shape,np.nan); idx=np.searchsorted(x,t)
    exact=(idx<len(x)) & (x[np.clip(idx,0,len(x)-1)]==t)
    result[exact]=y[idx[exact]]
    inside=(idx>0)&(idx<len(x))&~exact
    j=idx[inside]; q=t[inside]; gap=x[j]-x[j-1]
    ok=np.isfinite(y[j])&np.isfinite(y[j-1])&(gap>0)
    if max_gap is not None: ok&=gap<=max_gap
    value=y[j-1]+(q-x[j-1])/gap*(y[j]-y[j-1]); value[~ok]=np.nan
    result[inside]=value
    return result

def reference(manifest,telemetry,c,out):
    df=manifest.copy(); sync=synchronize(c); save_json(sync,out/'audit/synchronization.json')
    df['telemetry_s']=np.nan if sync['b'] is None else sync['a']*df.t+sync['b']
    df['ref']=np.nan; df['ref_lower']=np.nan; df['ref_upper']=np.nan
    df['in_domain']=True
    if c['evaluation_windows_s'] is not None:
        df['in_domain']=False
        for lo,hi in c['evaluation_windows_s']: df.loc[(df.t>=lo)&(df.t<hi),'in_domain']=True
    g=c['geometry']; reason=None
    if telemetry is not None and sync['b'] is not None:
        for k in telemetry:
            if k!='t': df['telemetry_'+k]=interpolate(df.telemetry_s,telemetry.t,telemetry[k],c['max_telemetry_gap_s'])
    if g['mode']=='none': reason='Sem geometria: telemetria não convertida em alcance.'
    elif telemetry is None or sync['b'] is None: reason='Telemetria ou sincronização ausente: métricas indisponíveis.'
    elif not g['vertical_reference_confirmed'] or not g['home_fixed_confirmed']:
        reason='Confirmar datum vertical e HOME antes de calcular a referência.'
    else:
        values={k:interpolate(df.telemetry_s,telemetry.t,telemetry[k],c['max_telemetry_gap_s']) for k in telemetry if k!='t'}
        if g['mode']=='enu':
            camera=g['camera_enu_m']
            if camera is None: reason='Informar câmera em ENU, no mesmo referencial da telemetria.'
            else: df['ref']=np.linalg.norm(np.c_[values['east'],values['north'],values['up']]-np.asarray(camera),axis=1)
        else:
            pars=[g['camera_height_m'],g['camera_takeoff_horizontal_m'],g['camera_ground_above_takeoff_m']]
            if any(v is None for v in pars): reason='Altura, afastamento ou desnível da câmera ausente.'
            else:
                hc,bc,ground=pars
                if hc<0 or bc<0: raise ValueError('Altura e afastamento não podem ser negativos.')
                r=values['radius']; dz=values['height']-(hc+ground)
                r=np.where(r>=0,r,np.nan)
                df['ref_lower']=np.sqrt((r-bc)**2+dz**2); df['ref_upper']=np.sqrt((r+bc)**2+dz**2)
                if g['mode']=='nominal': df['ref']=np.sqrt(r*r+bc*bc+dz*dz)
                elif g['mode']=='angle':
                    phi=values.get('phi',g['relative_phi_deg'])
                    if phi is None: reason='Ângulo entre vetores no solo ausente; não usar yaw/pitch como substituto.'
                    else: df['ref']=np.sqrt(np.maximum(0,r*r+bc*bc-2*r*bc*np.cos(np.deg2rad(phi))+dz*dz))
                else: raise ValueError('Geometria deve ser nominal, angle ou enu.')
    df['eligible']=df.in_domain & np.isfinite(df.ref)
    df['reference_status']=np.where(df.eligible,'referencia_'+g['mode'],'sem_referencia_ou_fora_dominio')
    if reason: print(reason)
    save_csv(df,out/'tables/frame_reference.csv')
    return df

def audit_experiment(c,out,video):
    pending=[]
    for key,value in c['field'].items():
        if value is None: pending.append({'item':key,'impacto':'Documentação de aquisição incompleta','onde':'registro de campo/metadados','estado':'ausente'})
    for key in ['yolo_weights','depth_weights','telemetry']:
        if not c.get(key): pending.append({'item':key,'impacto':'Etapa correspondente indisponível','onde':'inputs/'+key,'estado':'ausente'})
    if c['sync']['uncertainty_s'] is None: pending.append({'item':'incerteza_sincronismo','impacto':'Não quantificada','onde':'eventos marcados no vídeo e telemetria','estado':'ausente'})
    if c['intrinsics'] is None: pending.append({'item':'intrinsecos','impacto':'Sem conversão calibrada Z→d','onde':'inputs/calibration','estado':'ausente'})
    rows=[]
    for group in ['field','geometry','sync','yolo','depth','quality']:
        for k,v in c[group].items(): rows.append({'parametro':group+'.'+k,'valor':json.dumps(clean_json(v),ensure_ascii=False),
          'origem':'TCC/código legado ou edição manual: consultar configuração' if c['profile']=='farol' else 'configuração manual do novo voo',
          'situacao':'ausente' if v is None else 'registrado; não é comprovação física'})
    for k in ['width','height','frames','duration_s']: rows.append({'parametro':k,'valor':video[k],'origem':'decodificação do vídeo','situacao':'medido'})
    save_csv(pd.DataFrame(rows),out/'audit/parameter_provenance.csv')
    save_csv(pd.DataFrame(pending,columns=['item','impacto','onde','estado']),out/'audit/pendencias.csv')
    save_json(c,out/'audit/audit_experiment.json'); save_json(environment(),out/'audit/environment.json')
    return pd.DataFrame(pending)
