from pathlib import Path
import argparse,shutil,json
p=argparse.ArgumentParser();p.add_argument('--images',type=Path,default=Path('inputs/dataset/images'));p.add_argument('--out',type=Path,default=Path('outputs/dataset_yolo'));a=p.parse_args();root=Path(__file__).resolve().parents[1];rows=[]
for split in ['train','val','test']:
 for label in (root/'data/annotations_original'/split).glob('*.txt'):
  im=a.images/split/(label.stem+'.jpg')
  if not im.exists():continue
  dst=a.out/'images'/split/im.name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy(im,dst);lines=[]
  for line in label.read_text().splitlines():
   fields=line.split()
   if not fields:continue
   if len(fields)!=5 or fields[0]!='0':raise ValueError(f'Rótulo inesperado: {label}')
   vals=list(map(float,fields[1:]))
   if not all(0<=v<=1 for v in vals) or min(vals[2:])<=0:raise ValueError(f'Caixa inválida: {label}')
   fields[0]='2';lines.append(' '.join(fields))
  dst=a.out/'labels'/split/label.name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text('\n'.join(lines)+ ('\n' if lines else ''));rows.append({'split':split,'image':im.name})
if not rows:raise SystemExit('Nenhuma imagem correspondente. Obtenha o suplemento e confira --images.')
(a.out/'data.yaml').write_text('path: '+json.dumps(str(a.out.resolve()))+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: airplane\n  1: bird\n  2: drone\n  3: helicopter\n');(a.out/'available.json').write_text(json.dumps(rows,indent=2));print(a.out/'data.yaml')
