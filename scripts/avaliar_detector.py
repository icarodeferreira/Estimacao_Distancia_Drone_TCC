import argparse
p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--weights',default='models/best.pt');p.add_argument('--imgsz',type=int,default=1920);p.add_argument('--split',choices=['val','test'],default='test');p.add_argument('--out',default='outputs/detector');a=p.parse_args()
from ultralytics import YOLO
result=YOLO(a.weights).val(data=a.data,imgsz=a.imgsz,split=a.split,conf=.001,seed=42,project=a.out,name='avaliacao',exist_ok=False)
print(result.results_dict)
