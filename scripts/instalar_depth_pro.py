from pathlib import Path
import argparse,subprocess,sys,urllib.request,hashlib,json
p=argparse.ArgumentParser();p.add_argument('--revision',default='main');p.add_argument('--directory',type=Path,default=Path('external/ml-depth-pro'));a=p.parse_args()
def run(*args):return subprocess.check_output(list(map(str,args)),text=True).strip()
if not a.directory.exists():run('git','clone','https://github.com/apple-aiml-research/ml-depth-pro.git',a.directory)
run('git','-C',a.directory,'checkout',a.revision);run(sys.executable,'-m','pip','install','-e',a.directory.resolve())
f=a.directory/'checkpoints/depth_pro.pt';f.parent.mkdir(parents=True,exist_ok=True)
if not f.exists():
 tmp=f.with_suffix('.download');urllib.request.urlretrieve('https://ml-site.cdn-apple.com/models/depth-pro/depth_pro.pt',tmp);tmp.replace(f)
h=hashlib.sha256()
with f.open('rb') as fd:
 for b in iter(lambda:fd.read(8*1024*1024),b''):h.update(b)
(a.directory/'registro_local.json').write_text(json.dumps({'requested_revision':a.revision,'commit':run('git','-C',a.directory,'rev-parse','HEAD'),'weights_sha256':h.hexdigest(),'historical_version_confirmed':False},indent=2));print(f)
