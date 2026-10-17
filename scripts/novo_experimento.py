from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from experiment import execute
p=argparse.ArgumentParser();p.add_argument('config',type=Path);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--pilot-s',type=float);p.add_argument('--audit-only',action='store_true')
a=p.parse_args();print(execute(json.loads(a.config.read_text()),a.root,a.pilot_s,a.audit_only))
