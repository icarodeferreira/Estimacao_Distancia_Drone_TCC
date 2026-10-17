# -*- coding: utf-8 -*-
"""Videos demonstrativos do FAROL EDITADO (3537 quadros), sem nova inferencia.
Todos os dados exibidos sao de fontes historicas congeladas, inclusive o cenario
geometrico nominal da telemetria. Nao constitui validacao metrica independente.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

try:
    import cv2
    import numpy as np
except ImportError as e:
    raise SystemExit('Instale bibliotecas no .venv: python -m pip install opencv-python numpy') from e

DIR = Path(__file__).resolve().parent
FNT = DIR / 'FONTES'
N_EXPECTED, FPS, WIDTH, HEIGHT = 3537, 30., 3840, 2160
BGR = {'white': (240, 247, 252), 'muted': (178, 194, 208),
       'background': (14, 23, 36), 'panel': (23, 38, 57),
       'green': (107, 217, 128), 'yellow': (62, 223, 248),
       'blue': (255, 194, 88), 'orange': (48, 157, 250), 'red': (106, 112, 244)}


def rows_csv(p: Path):
    with p.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def number(x):
    if x is None or x == '': return None
    try:
        r = float(x)
        return r if math.isfinite(r) else None
    except (TypeError, ValueError): return None


def value(x, ndigits=2, suffix=' m'):
    return 'N/D' if x is None else f'{x:.{ndigits}f}{suffix}'


def delta_pct(x, ref):
    if x is None or ref is None or ref <= 0: return None
    return abs(x-ref)/ref*100.


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):h.update(b)
    return h.hexdigest()


def get_data():
    p = [FNT/x for x in ('yolo_all_frames.csv', 'depth_all_frames.csv','T04_pareamento_oof_113_segundos.csv')]
    if not all(x.is_file() for x in p):
        raise RuntimeError('Faltam fontes historicas em FONTES; extraia integralmente o ZIP.')
    y, d, o = (rows_csv(x) for x in p)
    if len(y)!=N_EXPECTED or len(d)!=N_EXPECTED or len(o)!=113:
        raise RuntimeError(f'Quantidade inconsistente: YOLO={len(y)}, DEPTH={len(d)}, OOF={len(o)}')
    yd=[]; by_second={}
    for r in o:
        s=int(r['second'])
        if s in by_second or s<0 or s>117:raise RuntimeError('Segundo OOF duplicado/invalido')
        by_second[s]=r
    for i,(a,b) in enumerate(zip(y,d)):
        if int(a['frame_idx'])!=i or int(b['frame_idx'])!=i:
            raise RuntimeError('Indices dos quadros inconsistentes YOLO/Depth no quadro '+str(i))
        t=number(a['video_time_s']); t2=number(b['video_time_s'])
        if t is None or t2 is None or abs(t-t2)>.001 or abs(t-i/FPS)>.01:
            raise RuntimeError(f'Timestamps divergentes no quadro {i}: {t}, {t2}')
        ref=number(a['reference_distance_nominal_m'])
        br=number(b['reference_distance_nominal_m'])
        if ref is None or br is None or abs(ref-br)>1e-7:
            raise RuntimeError('Referencias historicas nao coincidem no quadro '+str(i))
        s=i//30
        rr=by_second.get(s)
        reg=number(rr.get('oof_box_width_estimate_m')) if rr else None
        qual=(rr.get('quality_gate_emitted')=='True') if rr else False
        # OOF SEM FILTRO (primario) e OOF aprovado (sensibilidade operacional).
        # Nunca recalcule o OOF com a formula global calibrada em todos os dados.
        z=number(b['raw_s00_p25_m']) if b['abstained']=='False' else None
        dc=number(b['estimated_distance_m']) if b['abstained']=='False' else None
        c=number(a['confidence'])
        bbox=None
        xy=[number(a.get(k)) for k in ('x1','y1','x2','y2')]
        if all(x is not None for x in xy) and xy[2]>xy[0] and xy[3]>xy[1]: bbox=xy
        yd.append({'frame':i, 'time':t, 'original_time':number(a['original_video_time_s']),
            'telemetry_time':number(a['telemetry_time_s']),'ref':ref, 'reg':reg,
            'reg_filtered':reg if qual else None,'ref_oof':number(rr.get('reference_distance_nominal_m')) if rr else None,
            'oof_second':s if rr else None,'quality_pass':qual,
            'z':z,'depth_cal':dc,'depth_abstention':b['abstention_reason'],
            'conf':c,'class_id':a.get('class_id',''), 'detection_count':number(a['detection_count']),
            'bbox':bbox,'width_median':number(rr.get('yolo_median_width_4k_px')) if rr else None,
            'n_reliable':number(rr.get('yolo_reliable_boxes_per_second')) if rr else None})
    if sorted(by_second)!=sorted(set(range(118))-{39,40,51,52,53}):
        raise RuntimeError('O arquivo OOF nao apresenta os 113 segundos esperados; rever fonte.')
    return yd


def txt(c, x, y, msg, scale, col='white', thickness=1, maxlen=None):
    w=c.shape[1]
    if maxlen is not None:
        while cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)[0][0]>maxlen and scale>.25:
            scale-=.025
    cv2.putText(c, msg,(int(x),int(y)),cv2.FONT_HERSHEY_SIMPLEX,scale,BGR[col],thickness,cv2.LINE_AA)


def figure_data(data, frame_idx, width, height, kind):
    chart = np.full((height,width,3), BGR['background'], dtype=np.uint8)
    left=int(width*.05); right=width-int(width*.03); top=24; bottom=height-34
    vset=[v for r in data for v in (r['ref'],r['reg'],r['z']) if v is not None]
    ymax=max(5.,np.percentile(np.array(vset,dtype='float64'),98)*1.10)
    ymax=min(300., max(5.,ymax))
    for k in (0,.25,.5,.75,1):
        py=bottom-int(k*(bottom-top))
        cv2.line(chart,(left,py),(right,py),(56,66,78),1)
        txt(chart,left+2,py-3,f'{k*ymax:.0f}m',.36,'muted')
    def xy(i,v):
        return left+round(i/max(1,len(data)-1)*(right-left)),bottom-round(min(ymax,max(0,v))/ymax*(bottom-top))
    series=[('ref','yellow',5),(('reg' if kind=='cientifico' else 'reg_filtered'),'green',30),('z','blue',4)]
    for key,color,step in series:
        prev=None
        for i in range(0,min(frame_idx+1,len(data)),step):
            v=data[i].get(key)
            if v is None:prev=None; continue
            now=xy(i,v)
            if prev is not None: cv2.line(chart,prev,now,BGR[color],2,cv2.LINE_AA)
            prev=now
    txt(chart,left+4,18,'HISTORICO: amarelo R nominal | verde regressao OOF (1 Hz) | azul Depth Z',.47,'white',1,maxlen=right-left-10)
    txt(chart,left,bottom+24,f'{min(frame_idx/FPS,(len(data)-1)/FPS):.1f} s / 117.9 s  |  OOF bruto/filtrado conforme painel',.44,'muted')
    return chart


def draw_bbox(view,src_shape,row):
    xy=row['bbox']
    if not xy: return
    w0,h0=src_shape
    vx=view.shape[1]/w0;vy=view.shape[0]/h0
    pts=[round(xy[0]*vx),round(xy[1]*vy),round(xy[2]*vx),round(xy[3]*vy)]
    x1,y1,x2,y2=[int(max(0,a)) for a in pts]
    x1=min(view.shape[1]-1,x1); x2=min(view.shape[1]-1,x2)
    y1=min(view.shape[0]-1,y1); y2=min(view.shape[0]-1,y2)
    if x2<=x1 or y2<=y1:return
    good=row['conf'] is not None and row['conf']>=.25
    color=BGR['green'] if good else BGR['orange']
    cv2.rectangle(view,(x1,y1),(x2,y2),color,2)
    info=('ROI YOLO '+f'{row["conf"]:.2f}' if row['conf'] is not None else 'ROI YOLO')
    label_y=y1-9 if y1>20 else y2+22
    txt(view,x1,label_y,info,.5,'green' if good else 'orange',2)


def render(frame,row,data,idx,kind):
    W,H=(1920,1080) if kind=='cientifico' else (1280,720)
    view_w=round(W*.72/16)*16 if kind=='cientifico' else round(W*.70/16)*16
    view_h=round(view_w*frame.shape[0]/frame.shape[1])
    img=np.full((H,W,3),BGR['background'],dtype=np.uint8)
    view=cv2.resize(frame,(view_w,view_h),interpolation=cv2.INTER_AREA)
    draw_bbox(view,(frame.shape[1],frame.shape[0]),row)
    img[:view_h,:view_w]=view
    cv2.rectangle(img,(view_w,0),(W,view_h),BGR['panel'],-1)
    s=W/1920.; x=view_w+int(20*s);panel_w=W-x-int(12*s)
    def show(y,label,val,color='white',sub=''):
        txt(img,x,int(y*s),label, .49 if kind=='cientifico' else .46,'muted',1,maxlen=panel_w)
        txt(img,x,int((y+31)*s),val,.75 if kind=='cientifico' else .68,color,2,maxlen=panel_w)
        if sub:txt(img,x,int((y+53)*s),sub,.40,'muted',1,maxlen=panel_w)
    txt(img,x,int(53*s),'FAROL | TCC DRONE',.68,'white',2,maxlen=panel_w)
    txt(img,x,int(92*s),f'Quadro {idx:04d} | {row["time"]:7.3f} s',.49,'muted',1,maxlen=panel_w)
    show(141,'R NOMINAL | TELEMETRIA',value(row['ref']), 'yellow','Geometria historica hipotetica')
    reg_show=row['reg'] if kind=='cientifico' else row['reg_filtered']
    regdelta=delta_pct(reg_show,row['ref'])
    reg_note=('Filtro QC: absteve' if row['reg'] is not None else 'Sem predicao OOF neste segundo')
    show(251,('REGRESSAO OOF | BRUTA 1 Hz' if kind=='cientifico' else 'REGRESSAO OOF | FILTRADA'),value(reg_show),'green',
        ('Dif. %: '+value(regdelta,1,' %')) if reg_show is not None else reg_note)
    depthdelta=delta_pct(row['z'],row['ref'])
    show(361,'DEPTH PRO | Z BRUTO',value(row['z']),'blue',
         'Dif. Z/R*: '+value(depthdelta,1,' %') if row['z'] is not None else 'Abstencao / sem medicao aceita')
    if kind=='cientifico':
        show(478,'DEPTH PRO | CALIBRADO',value(row['depth_cal']), 'orange',
             'Exploratorio / calibrado no voo')
        y=593
        txt(img,x,int(y*s),'QC OOF: '+('APROVADO' if row['quality_pass'] else 'NAO EMITIDO'),.44,'green' if row['quality_pass'] else 'muted',1,maxlen=panel_w)
        txt(img,x,int((y+35)*s),'ROI: '+('SELECIONADA (NAO GT)' if row['bbox'] else 'AUSENTE'),.45,'white',1,maxlen=panel_w)
        txt(img,x,int((y+69)*s),'Tempo telem: '+value(row['telemetry_time'],2,' s'),.40,'muted',1,maxlen=panel_w)
        txt(img,x,int((y+97)*s),'Cenario: camera 1.5m H / 1.5m HOME',.36,'muted',1,maxlen=panel_w)
    else:
        txt(img,x,int(594*s),'OOF: '+('ACEITO' if row['quality_pass'] else 'NAO ACEITO'),.45,'muted',1,maxlen=panel_w)
        txt(img,x,int(625*s),'ROI: '+('PROPOSTA' if row['bbox'] else 'AUSENTE'),.46,'muted',1,maxlen=panel_w)
    chart_h=H-view_h
    chart=figure_data(data,idx,view_w,chart_h,kind)
    img[view_h:,:view_w]=chart
    # banner in bottom panel; in 720p the label must fit within narrower right panel
    txt(img,view_w+int(12*s),H-int(113*s),'LEGENDA',.54,'yellow',2,maxlen=W-view_w-int(24*s))
    txt(img,view_w+int(12*s),H-int(79*s),'*Z axial != R radial',.47,'red',1,maxlen=W-view_w-int(24*s))
    txt(img,view_w+int(12*s),H-int(50*s),'Desvios nao certificados',.45,'red',1,maxlen=W-view_w-int(24*s))
    txt(img,view_w+int(12*s),H-int(22*s),'Refer. nominal do farol',.42,'muted',1,maxlen=W-view_w-int(24*s))
    return img


class VideoEncoder:
    def __init__(self,target,size,fps,source):
        self.writer=None;self.proc=None;self.log=None
        if shutil.which('ffmpeg'):
            self.log=target.with_suffix('.ffmpeg.log').open('wb')
            w,h=size
            cmd=['ffmpeg','-hide_banner','-loglevel','warning','-y','-f','rawvideo','-pix_fmt','bgr24','-s',f'{w}x{h}',
                 '-r',f'{fps:g}','-i','pipe:0','-i',str(source),'-map','0:v:0','-map','1:a?',
                 '-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-c:a','aac',
                 '-b:a','128k','-shortest','-movflags','+faststart',str(target)]
            self.proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=self.log,stderr=self.log)
        else:
            self.writer=cv2.VideoWriter(str(target),cv2.VideoWriter_fourcc(*'mp4v'),fps,size)
            if not self.writer.isOpened():raise RuntimeError('Falha no OpenCV VideoWriter e FFmpeg indisponivel')
            print('AVISO: FFmpeg indisponivel; video sem audio.')
    def write(self,frame):
        if self.proc:
            if self.proc.poll() is not None:raise RuntimeError('FFmpeg encerrou: ver .ffmpeg.log')
            try:self.proc.stdin.write(frame.tobytes())
            except BrokenPipeError as e:raise RuntimeError('FFmpeg interrompido. Consulte .ffmpeg.log') from e
        else:self.writer.write(frame)
    def close(self):
        if self.proc:
            self.proc.stdin.close();code=self.proc.wait();self.log.close()
            if code:raise RuntimeError('FFmpeg retornou erro; consulte .ffmpeg.log')
        else:self.writer.release()


def write_audit(data,where):
    fields=['frame_idx','video_editado_t_s','video_original_t_s','telemetria_t_s','referencia_R_nominal_quadro_m',
        'regressao_OOF_segundo_m','referencia_OOF_mesmo_segundo_m','regressao_OOF_filtrada_m',
        'percentual_regressao_vs_ref_quadro','percentual_regressao_OOF_vs_ref_mesmo_segundo',
        'depth_pro_Z_bruto_aceito_m','depth_pro_calibrado_aceito_m','percentual_Z_vs_R_NAO_COMPARAVEL',
        'qualidade_OOF','roi_yolo_existe','conf_roi','motivo_abstencao_depth','comparacao_cientifica']
    with (where/'AUDITORIA_DADOS_EXIBIDOS_FAROL.csv').open('w',newline='',encoding='utf-8-sig') as fh:
        wr=csv.DictWriter(fh,fieldnames=fields);wr.writeheader()
        for row in data:
            wr.writerow(dict(zip(fields,[row['frame'],row['time'],row['original_time'],row['telemetry_time'],row['ref'],row['reg'],row['ref_oof'],row['reg_filtered'],
                  delta_pct(row['reg'],row['ref']),delta_pct(row['reg'],row['ref_oof']),row['z'],row['depth_cal'],delta_pct(row['z'],row['ref']),
                  row['quality_pass'],row['bbox'] is not None,row['conf'],row['depth_abstention'],
                  'EXPLORATORIA: telemetria/geometria nao certificada; Z != R'])))


def main():
    ap=argparse.ArgumentParser(description='Reproduzir videos cientifico e banca do FAROL EDITADO, sem retreino/novas inferencias.')
    ap.add_argument('--video',type=Path,help='video_final_farol.mov EDITADO; nao use _original.MOV (6702 quadros)')
    ap.add_argument('--saida',type=Path,default=DIR/'SAIDAS')
    ap.add_argument('--teste-quadros',type=int,help='Gerar videos de TESTE com apenas N quadros; nao confundir com videos completos')
    ap.add_argument('--so-diagnostico',action='store_true',help='Conferir dados historicos sem precisar do MOV')
    args=ap.parse_args()
    data=get_data();print(f'Fontes verificadas: {len(data)} quadros, {sum(r["reg"] is not None for r in data)} quadros com OOF por segundo, '
                          f'{sum(r["z"] is not None for r in data)} quadros Depth aceitos.')
    args.saida.mkdir(parents=True,exist_ok=True)
    write_audit(data,args.saida)
    with (args.saida/'RESUMO_PROVENIENCIA_FAROL.json').open('w',encoding='utf-8') as fh:
        json.dump({'papel':'VIDEO DEMONSTRATIVO, SEM VALIDACAO METRICA INDEPENDENTE',
            'video_alvo':'video_final_farol.mov','quadros_esperados':N_EXPECTED,'fps_esperado':FPS,
            'video_original_distinto':'video_final_farol_original.MOV (6702 quadros)',
            'offset_historico_video_editado_para_telemetria_s':4.8,
            'cenario_geometria_historico':'altura camera=1.5m; distancia horizontal camera-HOME=1.5m, hipoteticas',
            'avisos':['Fonte YOLO/Depth framewise congelada.','Regressao OOF por segundo, nao por quadro.',
                      'Comparacoes % sao descritivas contra referencia nominal inferida de telemetria, nao erros fisicos certificados.',
                      'Z Depth Pro e profundidade axial, enquanto a referencia e radial.','GT e correcoes humanas nao atestam todas as ROIs.',
                      'Valores de camera-HOME declarados em outros registros podem divergir do cenario historico; NAO recalibrado.'],
            'fontes_sha256':{x.name:sha(x) for x in FNT.iterdir() if x.is_file()},
            'contagens':{'quadros':len(data),'segundos_oof':len({r['oof_second'] for r in data if r['oof_second'] is not None}),
                        'segundos_oof_aceitos':len({r['oof_second'] for r in data if r['quality_pass']}),
                        'depth_aceitos':sum(r['z'] is not None for r in data),
                        'rois_propostas':sum(r['bbox'] is not None for r in data)},
            'teste_quadros':args.teste_quadros},fh,indent=2,ensure_ascii=False)
    if args.so_diagnostico:
        print('Diagnostico concluido:',args.saida)
        return
    if not args.video:ap.error('Informe --video ou use --so-diagnostico')
    if args.teste_quadros is not None and not 1<=args.teste_quadros<=N_EXPECTED:
        ap.error('A quantidade --teste-quadros deve estar entre 1 e 3537.')
    video=args.video.expanduser().resolve()
    if not video.is_file():ap.error(f'Video nao encontrado: {video}')
    cap=cv2.VideoCapture(str(video))
    if not cap.isOpened():raise RuntimeError('Nao foi possivel abrir MOV do farol.')
    n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));f=float(cap.get(cv2.CAP_PROP_FPS))
    w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if (n,w,h)!=(N_EXPECTED,WIDTH,HEIGHT) or abs(f-FPS)>.01:
        cap.release()
        raise RuntimeError(f'VIDEO INCOMPATIVEL: {n} quadros, {f}fps, {w}x{h}; esperado 3537/30/3840x2160. '
            'Provavelmente foi selecionado _original.MOV; NAO usar os mesmos indices.')
    limit=args.teste_quadros or N_EXPECTED
    prefix='TESTE_' if args.teste_quadros else ''
    p1=args.saida/(prefix+'01_VIDEO_CIENTIFICO_FAROL.mp4')
    p2=args.saida/(prefix+'02_VIDEO_APRESENTACAO_BANCA_FAROL.mp4')
    enc1=VideoEncoder(p1,(1920,1080),FPS,video)
    enc2=VideoEncoder(p2,(1280,720),FPS,video)
    done=0
    try:
        for i in range(limit):
            ok,frame=cap.read()
            if not ok:raise RuntimeError('Falha na decodificacao do quadro '+str(i))
            a=render(frame,data[i],data,i,'cientifico')
            b=render(frame,data[i],data,i,'banca')
            if i==0:
                cv2.imwrite(str(args.saida/(prefix+'PREVIA_CIENTIFICO.jpg')),a)
                cv2.imwrite(str(args.saida/(prefix+'PREVIA_BANCA.jpg')),b)
            enc1.write(a);enc2.write(b);done+=1
            if (i+1)%300==0:print(f'Processados {i+1}/{limit} quadros',flush=True)
    finally:
        cap.release()
        enc1.close();enc2.close()
    print(f'Concluido: {done}/{limit} quadros -> {p1} e {p2}')
    if args.teste_quadros: print('ATENCAO: VIDEOS DE TESTE TRUNCADOS, NAO SAO VIDEOS COMPLETOS!')

if __name__ == '__main__':
    main()
