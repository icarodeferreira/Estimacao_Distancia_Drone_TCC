# -*- coding: utf-8 -*-
"""TCC Drone — dois vídeos auditáveis, com dados congelados (sem inferência de IA).

PRINCÍPIO: HOME corrigido é distância horizontal drone-HOME, não alcance
câmera-drone. No modo padrão, porcentagens são DIFERENÇAS EXPLORATÓRIAS
em relação ao HOME, jamais erros métricos certificados.
"""
from __future__ import annotations
import argparse
import bisect
import csv
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError as exc:
    raise SystemExit('Instale no .venv: python -m pip install opencv-python numpy') from exc

BASE = Path(__file__).resolve().parent
FONTES = BASE / 'FONTES'
EXPECTED_FRAMES = 5142
EXPECTED_FPS = 30.0
OFFSET_DEFAULT = 10.566666667
MIN_DENOMINATOR_M = 2.0
MAX_GAP_TELEM_S = 0.15
# BGR: azul, verde, laranja, amarelo, branco
WHITE = (245, 248, 251)
MUTED = (178, 194, 211)
BG = (15, 24, 38)
PANEL = (23, 36, 54)
GREEN = (94, 214, 129)
BLUE = (247, 185, 74)
YELLOW = (77, 211, 247)
RED = (108, 116, 245)


def read_csv(name):
    p = FONTES / name
    if not p.exists():
        raise SystemExit(f'Fonte obrigatoria ausente: {p}')
    with p.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def num(x):
    if x is None or x == '':
        return None
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def fmt(v, decimals=1, suffix=' m'):
    return 'N/D' if v is None else f'{v:.{decimals}f}{suffix}'


def finite_positive(x):
    return x is not None and math.isfinite(x) and x > 0


def pct(est, ref):
    if est is None or ref is None or ref < MIN_DENOMINATOR_M:
        return None
    return 100.0 * abs(est - ref) / ref


def haversine(lat1, lon1, lat2, lon2):
    r = 6371008.8
    a1, a2 = math.radians(lat1), math.radians(lat2)
    da, db = a2-a1, math.radians(lon2-lon1)
    h = math.sin(da/2)**2 + math.cos(a1)*math.cos(a2)*math.sin(db/2)**2
    return 2*r*math.asin(math.sqrt(max(0., min(1., h))))


class Telemetry:
    def __init__(self, records):
        self.rows = sorted(records, key=lambda r: float(r['time_s']))
        self.times = [float(r['time_s']) for r in self.rows]

    def get(self, t, cols):
        if t < self.times[0] or t > self.times[-1]:
            return None
        j = bisect.bisect_left(self.times, t)
        if j < len(self.times) and abs(self.times[j]-t) < 1e-5:
            i = j
            if any(num(self.rows[i].get(x)) is None for x in cols):
                return None
            return {x: num(self.rows[i][x]) for x in cols}
        if j == 0 or j == len(self.times):
            return None
        i = j-1
        gap = self.times[j]-self.times[i]
        if gap <= 0 or gap > MAX_GAP_TELEM_S + 1e-9:
            return None
        f = (t-self.times[i])/gap
        out = {}
        for col in cols:
            lo, hi = num(self.rows[i].get(col)), num(self.rows[j].get(col))
            if lo is None or hi is None:
                return None
            out[col] = lo + (hi-lo)*f
        return out


def parse_data(args):
    roi_data = read_csv('T17_pipeline_5142_quadros.csv')
    pts_data = read_csv('PTS_TODOS_QUADROS.csv')
    depth_data = read_csv('T19_depth_pro_126_medidas_Z_exploratorias.csv')
    telem = Telemetry(read_csv('FlightRecord_2026-09-24_14-12-36_corrigido.csv'))
    if len(roi_data) != EXPECTED_FRAMES or len(pts_data) != EXPECTED_FRAMES:
        raise SystemExit('Inconsistencia: T17 e/ou PTS nao possuem 5142 linhas.')
    rois = {}
    pts = {}
    for row in roi_data:
        n = int(row['frame_idx'])
        if n in rois: raise SystemExit('Frame duplicado em T17')
        rois[n] = row
    for row in pts_data:
        n = int(row['frame_idx_0_based'])
        if n in pts: raise SystemExit('Frame duplicado em PTS')
        pts[n] = float(row['pts_relativo_primeiro_s'])
    if set(rois) != set(range(EXPECTED_FRAMES)) or set(pts) != set(range(EXPECTED_FRAMES)):
        raise SystemExit('Indices de quadros nao consecutivos ou diferentes entre PTS/T17.')
    measured_depth = {}
    for row in depth_data:
        n = int(row['frame_idx'])
        v = num(row['Z_axial_p25_m']) if row.get('status') == 'ok' else None
        if v is not None:
            if n in measured_depth: raise SystemExit('Depth duplicado no frame '+str(n))
            measured_depth[n] = v
    # Análise temporal determinística: método disponível no quadro sem extrapolar.
    output = []
    for i in range(EXPECTED_FRAMES):
        row = rois[i]
        t = pts[i]
        if abs((i/EXPECTED_FPS)-t) > .005:
            raise SystemExit(f'PTS anomalo no quadro {i}: {t}')
        tm = t + args.offset
        if args.referencia == 'home':
            tel = telem.get(tm, ['distance_home_corrigida_m'])
            ref = tel['distance_home_corrigida_m'] if tel else None
        else:
            tel = telem.get(tm, ['lat','lng','height_m'])
            if tel and (tel['lat'] == 0 or tel['lng'] == 0): tel = None
            if tel:
                h = haversine(args.camera_lat, args.camera_lon, tel['lat'], tel['lng'])
                ref = math.hypot(h, tel['height_m']-args.camera_altura_m)
            else: ref = None
        regression = num(row['distancia_regressao_exploratoria_m'])
        if row.get('qc_aprovado', '').lower() != 'true': regression = None
        depth_z = measured_depth.get(i)
        valid_box = all(num(row.get(c)) is not None for c in ['x1','y1','x2','y2'])
        box = [float(row[c]) for c in ['x1','y1','x2','y2']] if valid_box else None
        # Depth Pro e profundidade AXIAL Z; somente igual ao radial apos conversao
        # por intrinsecos e posicao da ROI. No modo HOME as porcentagens sao
        # deliberadamente EXPLORATORIAS (comparacao de grandezas distintas).
        if depth_z is not None and args.referencia == 'camera':
            if args.fx is not None and args.fy is not None and box is not None:
                u = (box[0]+box[2])/2.0
                v = (box[1]+box[3])/2.0
                depth_radial = depth_z * math.sqrt(1. + ((u-args.cx)/args.fx)**2 + ((v-args.cy)/args.fy)**2)
            else:
                depth_radial = None
        else:
            depth_radial = depth_z
        regression_pct = pct(regression, ref)
        depth_pct = pct(depth_radial, ref)
        output.append(dict(frame_idx=i, pts_video_s=t, t_telemetria_s=tm, referencia_m=ref,
                           regressao_m=regression, depth_z_m=depth_z, depth_comparavel_m=depth_radial,
                           delta_regressao_pct=regression_pct, delta_depth_pct=depth_pct,
                           bbox=box, confianca=num(row.get('confianca')),
                           motivo_abstencao=row.get('motivo_abstencao') or '',
                           depth_status=row.get('depth_status') or '',
                           telemetria_valida=ref is not None, depth_observado=depth_z is not None,
                           roi_emitida=valid_box))
    return output, measured_depth


def pt(img, text, x, y, size=.7, color=WHITE, thick=1, max_width=None):
    if max_width is not None:
        # fit ascii labels without clipping
        while size > .23 and cv2.getTextSize(str(text), cv2.FONT_HERSHEY_SIMPLEX,size,thick)[0][0] > max_width:
            size *= .92
    cv2.putText(img,str(text),(int(x),int(y)),cv2.FONT_HERSHEY_SIMPLEX,size,color,thick,cv2.LINE_AA)


def rect(img, x0, y0, x1, y1, color, thickness=-1):
    cv2.rectangle(img, (int(x0),int(y0)),(int(x1),int(y1)),color,thickness)


def plot_background(data, width, height, plot_tag):
    canvas = np.full((height,width,3), BG,dtype=np.uint8)
    top,left,right,bottom=32,69,width-26,height-30
    values=[]
    for row in data:
        for key in ['referencia_m','regressao_m','depth_z_m']:
            v=row[key]
            if finite_positive(v): values.append(v)
    ymax=math.ceil(max(10, np.percentile(values,99)*1.10) / 10)*10 if values else 100
    for fraction in [0,.25,.5,.75,1.]:
        y=int(bottom-(bottom-top)*fraction)
        cv2.line(canvas,(left,y),(right,y),(54,65,84),1,cv2.LINE_AA)
        pt(canvas,f'{fraction*ymax:.0f}',6,y+5,.40,MUTED,1)
    for fraction in [0,.25,.5,.75,1.]:
        x=int(left+(right-left)*fraction)
        pt(canvas,f'{171.4*fraction:.0f}s',max(0,x-15),height-8,.40,MUTED,1)
    def xp(row): return int(left+(right-left)*row['pts_video_s']/171.4)
    def yp(v): return int(bottom-(bottom-top)*min(ymax,max(0,v))/ymax)
    for col,color in [('referencia_m',YELLOW),('regressao_m',GREEN)]:
        last=None
        for row in data:
            v=row[col]
            if finite_positive(v):
                pos=(xp(row),yp(v))
                if last is not None and row['frame_idx']-last[0] <= 31:
                    cv2.line(canvas,last[1],pos,color,2,cv2.LINE_AA)
                last=(row['frame_idx'],pos)
            else: last=None
    for row in data:
        v=row['depth_z_m']
        if finite_positive(v): cv2.circle(canvas,(xp(row),yp(v)),3,BLUE,-1,cv2.LINE_AA)
    pt(canvas,plot_tag,18,20,.49,WHITE,1,max_width=width-24)
    return canvas,left,right


def blit_plot(base, plot, upto_x, xleft, xright, x0, y0):
    part=plot.copy()
    if upto_x < xright: rect(part,max(xleft,upto_x+1),0,part.shape[1],part.shape[0],(13,20,32))
    cv2.line(part,(int(upto_x),29),(int(upto_x),part.shape[0]-30),WHITE,2,cv2.LINE_AA)
    base[y0:y0+part.shape[0],x0:x0+part.shape[1]]=part


def inset_roi(view, src, row, srcw, srch):
    """Amostra visual ampliada da ROI proposta, sempre com aviso NAO GT."""
    b=row['bbox']
    if b is None: return
    h,w=view.shape[:2]
    bw=max(0.0,b[2]-b[0]); bh=max(0.0,b[3]-b[1])
    if bw<2 or bh<2: return
    u,v=(b[0]+b[2])/2,(b[1]+b[3])/2
    cw=max(110,min(srcw*.45,bw*2.4))
    ch=cw*.70
    # evitar recorte vazio perto das bordas do vídeo
    x0=max(0,int(u-cw/2));y0=max(0,int(v-ch/2))
    x1=min(srcw,int(u+cw/2));y1=min(srch,int(v+ch/2))
    if x1-x0<20 or y1-y0<20: return
    thumbw=min(290,int(w*.25)); thumbh=int(thumbw*.65)
    x=int(w-thumbw-15); y=16
    thumb=cv2.resize(src[y0:y1,x0:x1],(thumbw,thumbh),interpolation=cv2.INTER_AREA)
    view[y:y+thumbh,x:x+thumbw]=thumb
    cv2.rectangle(view,(x-2,y-2),(x+thumbw+2,y+thumbh+2),YELLOW,2)
    rect(view,x,y+thumbh-24,x+thumbw,y+thumbh,(9,14,22))
    pt(view,'ROI AMPLIADA (NAO GT)',x+7,y+thumbh-7,.47,WHITE,2,max_width=thumbw-12)


def draw_video_box(view, row, srcw, srch):
    b=row['bbox']
    if b is None: return
    h,w=view.shape[:2]
    x0=int(max(0,min(w-1,b[0]*w/srcw)))
    y0=int(max(0,min(h-1,b[1]*h/srch)))
    x1=int(max(0,min(w-1,b[2]*w/srcw)))
    y1=int(max(0,min(h-1,b[3]*h/srch)))
    if x1 <= x0 or y1 <= y0: return
    cv2.rectangle(view,(x0,y0),(x1,y1),YELLOW,2,cv2.LINE_AA)
    conf=row['confianca']
    text='ROI NAO VALIDADA' + (f'  conf={conf:.2f}' if conf is not None else '')
    ylab=max(20,y0-9)
    pt(view,text,max(6,min(w-260,x0)),ylab,.53,WHITE,2,max_width=w-12)


def make_canvas(src, meta, idx, rows, measured_idx, plot_data, args, style, srcw, srch):
    sw, sh=(1920,1080) if style=='cientifico' else (1280,720)
    vieww=int(sw*.75) if style=='cientifico' else int(sw*.76)
    vieww=(vieww//16)*16
    viewh=int(vieww*srch/srcw)
    panelw=sw-vieww
    ploth=sh-viewh
    canvas=np.full((sh,sw,3),BG,dtype=np.uint8)
    view=cv2.resize(src,(vieww,viewh),interpolation=cv2.INTER_AREA)
    draw_video_box(view,meta,srcw,srch)
    inset_roi(view,src,meta,srcw,srch)
    canvas[:viewh,:vieww]=view
    rect(canvas,vieww,0,sw,viewh,PANEL)
    sc=sw/1920.
    x=vieww+int(25*sc); iw=panelw-int(44*sc)
    header=.75 if style=='cientifico' else .58
    title_size=header
    pt(canvas,'TCC DRONE | NOVO VOO',x,int(52*sc),title_size,WHITE,2,max_width=iw)
    pt(canvas,f'FRAME {idx:04d}  |  {meta["pts_video_s"]:07.3f}s',x,int(92*sc),.60 if style=='cientifico' else .44,MUTED,1,max_width=iw)
    def labeled(y, label, value, color=WHITE, labelinfo=''):
        # y in full HD logical units
        py=int(y*sc)
        pt(canvas,label,x,py,.52 if style=='cientifico' else .46,MUTED,1,max_width=iw)
        pt(canvas,value,x,py+int(35*sc),.83 if style=='cientifico' else .72,color,2,max_width=iw)
        if labelinfo:
            pt(canvas,labelinfo,x,py+int(58*sc),.39 if style=='cientifico' else .36,MUTED,1,max_width=iw)
    if args.referencia == 'home':
        rtitle='TELEMETRIA | DIST. HOME'
        comment='Horizontal, NAO camera-drone'
    else:
        rtitle='TELEM. | R CAM-DRONE'
        comment='Geometria derivada; provisoria'
    labeled(143,rtitle,fmt(meta['referencia_m'],2),YELLOW,comment)
    if args.referencia == 'home': err_label='DIF. % vs HOME*'
    else: err_label='DIF. % vs REF. CAM*'
    rg=fmt(meta['regressao_m'],2)
    dlt=fmt(meta['delta_regressao_pct'],1,' %')
    labeled(266,'REGRESSAO | largura',rg,GREEN,err_label+': '+dlt)
    # nearest preceding Depth sample - explicitly label it as historical when held
    j=bisect.bisect_right(measured_idx,idx)-1
    selected=rows[measured_idx[j]] if j>=0 else None
    dt=meta['pts_video_s']-selected['pts_video_s'] if selected else None
    if selected and dt >= -1e-6 and dt <= args.profundidade_exibir_ate_s:
        dep=selected['depth_z_m']
        dep_comp=selected['depth_comparavel_m']
        dperc=selected['delta_depth_pct']
        subj=f'Amostra anterior, idade {dt:.2f}s' if dt>0.017 else 'Medicao neste quadro'
        if args.referencia=='camera' and dep_comp is None:
            dep_text=fmt(dep,2)+' (Z)'; dlabel='SEM %: falta intrinseca validada'
        else:
            dep_text=fmt(dep,2)+' (Z)' if args.referencia=='home' else fmt(dep_comp,2)+' (R derivado)'
            dlabel=err_label+': '+fmt(dperc,1,' %')
        labeled(407,'DEPTH PRO | axial Z',dep_text,BLUE,subj)
        pt(canvas,dlabel,x,int(504*sc),.43,MUTED,1,max_width=iw)
    else:
        labeled(407,'DEPTH PRO | axial Z','N/D',MUTED,'Nao amostrado / sem dado valido')
        pt(canvas,err_label+': N/D',x,int(504*sc),.43,MUTED,1,max_width=iw)
    # explicit classification / support
    y=int(580*sc)
    if meta['roi_emitida']:
        status='ROI: SELECIONADA, NAO GT'
        c=YELLOW
    else:
        status='ROI: AUSENTE'
        c=MUTED
    pt(canvas,status,x,y,.49,c,1,max_width=iw)
    y+=int(31*sc)
    pt(canvas,'Sync: +%.4fs (hipotese)'%args.offset,x,y,.46,MUTED,1,max_width=iw)
    y+=int(31*sc)
    pt(canvas, 'Sem extrapolar telemetria',x,y,.45,MUTED,1,max_width=iw)
    # chart below video; precomputed points are revealed progressively
    chart,xleft,xright=plot_data
    cur_x=int(xleft+(xright-xleft)*meta['pts_video_s']/171.4)
    blit_plot(canvas,chart,cur_x,xleft,xright,0,viewh)
    # footer mandatory visible in both formats
    py=sh-int(16*sc)
    if style == 'cientifico':
        pt(canvas,'*COMPARACAO EXPLORATORIA: dist. HOME != distancia camera-drone; Depth Pro fornece Z.',int(78*sc),py,.48,RED,2,max_width=sw-int(90*sc))
    else:
        pt(canvas,'*DESVIOS ILUSTRATIVOS, NAO ERROS METRICOS CERTIFICADOS.',int(60*sc),py,.46,RED,1,max_width=sw-int(70*sc))
    return canvas


class Encoder:
    def __init__(self,path, size, fps, video_source, use_ffmpeg=True):
        self.path=path
        self.writer=None
        self.process=None
        self.log=None
        if use_ffmpeg and shutil.which('ffmpeg'):
            self.log=path.with_suffix('.ffmpeg.log').open('wb')
            w,h=size
            cmd=['ffmpeg','-hide_banner','-loglevel','warning','-y','-f','rawvideo','-pix_fmt','bgr24','-s',f'{w}x{h}', '-r', f'{fps:g}', '-i','pipe:0', '-i',str(video_source),
                 '-map','0:v:0','-map','1:a?', '-c:v','libx264','-preset','veryfast','-crf','22','-pix_fmt','yuv420p',
                 '-c:a','aac','-b:a','128k','-movflags','+faststart',str(path)]
            self.process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=self.log,stderr=self.log)
        else:
            fourcc=cv2.VideoWriter_fourcc(*'mp4v')
            self.writer=cv2.VideoWriter(str(path),fourcc,fps,size)
            if not self.writer.isOpened():
                raise SystemExit('OpenCV nao conseguiu abrir encoder MP4. Instale FFmpeg.')
            print(f'[AVISO] FFmpeg ausente: {path.name} sera salvo sem audio (OpenCV).')

    def write(self,image):
        if self.process:
            if self.process.poll() is not None:
                raise RuntimeError('FFmpeg terminou prematuramente; consulte .ffmpeg.log')
            try: self.process.stdin.write(image.tobytes())
            except BrokenPipeError as e: raise RuntimeError('Erro de codificacao FFmpeg; veja .ffmpeg.log') from e
        else:
            self.writer.write(image)

    def close(self):
        if self.process:
            self.process.stdin.close()
            code=self.process.wait()
            self.log.close()
            if code: raise RuntimeError(f'FFmpeg falhou ({code}) ao gerar {self.path}. Leia {self.path.with_suffix(".ffmpeg.log")}')
        else: self.writer.release()


def main():
    ap=argparse.ArgumentParser(description='Gerar videos cientifico/apresentacao com dados existentes; sem inferencia de IA.')
    ap.add_argument('--video',type=Path,required=True,help='Arquivo local IMG_5962_editado.mov')
    ap.add_argument('--saida',type=Path,default=BASE/'SAIDAS')
    ap.add_argument('--offset',type=float,default=OFFSET_DEFAULT)
    ap.add_argument('--referencia',choices=['home','camera'],default='home',help='home=proxy horizontal; camera=exige geodesia exata')
    ap.add_argument('--camera-lat',type=float,default=None)
    ap.add_argument('--camera-lon',type=float,default=None)
    ap.add_argument('--camera-altura-m',type=float,default=None,help='Altura da camera acima do nivel HOME em metros')
    ap.add_argument('--fx',type=float,default=None,help='Focal horizontal em px NA RESOLUCAO ORIGINAL, calibrada')
    ap.add_argument('--fy',type=float,default=None,help='Focal vertical em px NA RESOLUCAO ORIGINAL, calibrada')
    ap.add_argument('--cx',type=float,default=None,help='Ponto principal x em px')
    ap.add_argument('--cy',type=float,default=None,help='Ponto principal y em px')
    ap.add_argument('--profundidade-exibir-ate-s',type=float,default=1.0,help='Tempo maximo que mostra a ultima amostra, com idade explicita; nunca nova inferencia')
    ap.add_argument('--limite-quadros',type=int,default=None,help='Somente testes; videos truncados')
    ap.add_argument('--permitir-video-teste',action='store_true',help=argparse.SUPPRESS)
    ap.add_argument('--sem-ffmpeg',action='store_true')
    args=ap.parse_args()
    if args.referencia == 'camera':
        if any(a is None for a in (args.camera_lat,args.camera_lon,args.camera_altura_m)):
            ap.error('Referencia camera requer --camera-lat --camera-lon --camera-altura-m verificadas')
        if not (-90<=args.camera_lat<=90 and -180<=args.camera_lon<=180):
            ap.error('Coordenadas da camera invalidas')
        intr=[args.fx,args.fy,args.cx,args.cy]
        if any(x is not None for x in intr) and not all(x is not None for x in intr):
            ap.error('Informe fx,fy,cx,cy em conjunto ou nenhum')
        if args.fx is not None and (args.fx<=0 or args.fy<=0): ap.error('fx/fy invalidas')
    if args.profundidade_exibir_ate_s<0: ap.error('limite de amostra anterior invalido')
    args.video=args.video.expanduser().resolve()
    if not args.video.is_file(): ap.error(f'Video nao encontrado: {args.video}')
    args.saida.mkdir(parents=True,exist_ok=True)
    data, depth_map=parse_data(args)
    cap=cv2.VideoCapture(str(args.video))
    if not cap.isOpened(): raise SystemExit('OpenCV nao conseguiu abrir o arquivo MOV')
    nsrc=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=float(cap.get(cv2.CAP_PROP_FPS))
    srcw=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));srch=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not args.permitir_video_teste and (nsrc!=EXPECTED_FRAMES or abs(fps-30)>0.005 or (srcw,srch)!=(3840,2160)):
        raise SystemExit(f'VIDEO ERRADO: ({nsrc},{fps},{srcw}x{srch}) esperado (5142,30,3840x2160)')
    print(f'Usando {len(data)} linhas, {len(depth_map)} amostras Depth. MOV: {nsrc} quadros, {fps:.3f}fps, {srcw}x{srch}')
    if args.referencia=='home':
        print('AVISO CIENTIFICO: HOME!=CAMERA; porcentagens sao DIFERENCAS EXPLORATORIAS, NAO ERROS CERTIFICADOS.')
    num_frames=min(nsrc, EXPECTED_FRAMES, args.limite_quadros or EXPECTED_FRAMES)
    scenario='home_exploratorio' if args.referencia=='home' else 'camera_geometrico_provisorio'
    audit_path=args.saida/'AUDITORIA_NUMEROS_EXIBIDOS.csv'
    fields=['frame_idx','pts_video_s','t_telemetria_s','referencia_m','regressao_m','depth_z_m','depth_comparavel_m',
            'delta_regressao_pct','delta_depth_pct','telemetria_valida','depth_observado','roi_emitida','confianca','motivo_abstencao','depth_status','referencia_tipo','comparacao_status']
    with audit_path.open('w',newline='',encoding='utf-8-sig') as fh:
        wr=csv.DictWriter(fh,fieldnames=fields)
        wr.writeheader()
        for row in data[:num_frames]:
            d={k:row.get(k) for k in fields}
            d['referencia_tipo']=scenario
            d['comparacao_status']='EXPLORATORIO_NAO_ERRO_METRICO' if args.referencia=='home' else 'PROVISORIO_GEODESIA_NAO_CERTIFICADA'
            wr.writerow(d)
    plotw_c,h_c=1920,1080
    vieww_c=(int(plotw_c*.75)//16)*16
    viewh_c=round(vieww_c*srch/srcw)
    chart_c=plot_background(data,plotw_c,h_c-viewh_c,'DISTANCIAS EM METROS | amarelo: HOME; verde: regressao; azul: amostras Z')
    plotw_b,h_b=1280,720
    vieww_b=(int(plotw_b*.76)//16)*16
    viewh_b=round(vieww_b*srch/srcw)
    chart_b=plot_background(data,plotw_b,h_b-viewh_b,'CURVAS DE COMPARACAO | amostras Depth Pro em pontos')
    sorted_depth=sorted(depth_map)
    sci=args.saida/'01_VIDEO_CIENTIFICO_NOVO_VOO.mp4'
    banca=args.saida/'02_VIDEO_APRESENTACAO_BANCA.mp4'
    e1=Encoder(sci,(1920,1080),EXPECTED_FPS,args.video,not args.sem_ffmpeg)
    e2=Encoder(banca,(1280,720),EXPECTED_FPS,args.video,not args.sem_ffmpeg)
    frameidx=0
    try:
        while frameidx<num_frames:
            ok,frm=cap.read()
            if not ok: raise RuntimeError(f'Falha de leitura em quadro {frameidx} de {num_frames}')
            m=data[frameidx]
            c=make_canvas(frm,m,frameidx,data,sorted_depth,chart_c,args,'cientifico',srcw,srch)
            b=make_canvas(frm,m,frameidx,data,sorted_depth,chart_b,args,'banca',srcw,srch)
            e1.write(c);e2.write(b)
            frameidx+=1
            if frameidx%300==0:print(f'{frameidx}/{num_frames} quadros renderizados...',flush=True)
    finally:
        cap.release()
        e1.close();e2.close()
    result=dict(status='ok',arquivos_video=[str(sci),str(banca)],quadros_processados=frameidx,fps=EXPECTED_FPS,
                referencia=scenario,offset_s=args.offset,depth_amostras_disponiveis=len(depth_map),
                audio_preservado_quando_ffmpeg_suporta=True,
                aviso='Porcentagens HOME sao diferencas exploratorias entre grandezas potencialmente distintas, nao MAE, MAPE nem erro certificado. ROI nao confirmada como drone.',
                dados_auditoria=str(audit_path))
    (args.saida/'RELATORIO_EXECUCAO_VIDEO.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print('CONCLUIDO:',sci,'\n',banca,'\n',audit_path)

if __name__=='__main__': main()
