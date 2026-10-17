import importlib.util
import math
from pathlib import Path
import cv2
import numpy as np
import pandas as pd

SCRIPT=Path(__file__).resolve().parents[1]/'pipeline_integrado.py'
spec=importlib.util.spec_from_file_location('pipe',SCRIPT)
pipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipe)


def test_replay_arquivado():
    md=dict(frames=5142,width=3840,height=2160,fps=30)
    orig,_=pipe.archived_yolo(md,5142,'original')
    temporal,_=pipe.archived_yolo(md,5142,'temporal')
    assert int(orig.detectado.sum())==3764
    assert int(temporal.detectado.sum())==1853
    frames=pipe.normalize_frames(orig,md,5142)
    sec=pipe.per_second(frames)
    assert len(sec)==172
    assert sec['distancia_regressao_exploratoria_m'].notna().sum()<=172
    assert math.isclose(pipe.MODEL_A*100**pipe.MODEL_B,12.415617,rel_tol=.01)


def test_per_second_n_few_abstains():
    r=[]
    for i in range(90):
        r.append(dict(frame_idx=i,t_video_s=i/30,second=i//30,detectado=True,
                      x1=10.,y1=10.,x2=110.,y2=50.,confianca=.9,
                      box_width_px=100.,box_height_px=40.,
                      caixa_confiavel_para_largura=(i//30!=1 or i%30<3)))
    frames=pd.DataFrame(r)
    sec=pipe.per_second(frames)
    assert len(sec)==3 and sec.iloc[0].qc_aprovado and not sec.iloc[1].qc_aprovado
    assert math.isnan(sec.iloc[1].distancia_regressao_exploratoria_m)
    assert sec.iloc[2].qc_aprovado


def test_input_validation_rejects_mismatch():
    md=dict(frames=4,width=3840,height=2160,fps=30)
    df=pd.DataFrame(dict(frame_idx=[0,1,2,4],t_video_s=[0,1/30,2/30,4/30],
       detectado=[True]*4,x1=[10]*4,y1=[10]*4,x2=[20]*4,y2=[20]*4,confianca=[.9]*4))
    import pytest
    with pytest.raises(ValueError):pipe.validate_cache_df(df,md,4,'invalido')


def test_video_render_sintetico(tmp_path):
    v=tmp_path/'input.mp4';w=cv2.VideoWriter(str(v),cv2.VideoWriter_fourcc(*'mp4v'),30,(640,360))
    assert w.isOpened()
    for i in range(60):
        img=np.zeros((360,640,3),np.uint8)
        cv2.rectangle(img,(50+i//3,30),(90+i//3,55),(120,120,220),-1)
        w.write(img)
    w.release()
    md=pipe.check_video(v)
    assert md['frames']==60 and md['fps']==30
    pt=pipe.audit_pts(v,md,permit_unverified=False)
    assert pt['status']=='CFR_VERIFICADO'
    arr=[]
    for i in range(60):
        arr.append(dict(frame_idx=i,t_video_s=i/30,second=i//30,detectado=True,
                        x1=50,y1=30,x2=90,y2=55,confianca=.85,
                        caixa_confiavel_para_largura=True,box_width_px=40.,box_height_px=25.))
    f=pd.DataFrame(arr);sec=pipe.per_second(f)
    x=pipe.add_meta_to_frame_table(f,sec,None)
    from types import SimpleNamespace
    out=pipe.render(SimpleNamespace(video=v,video_scale=2),md,x,sec,tmp_path)
    assert out.exists()
    cap=cv2.VideoCapture(str(out))
    assert cap.get(cv2.CAP_PROP_FRAME_COUNT)==60
    cap.release()
