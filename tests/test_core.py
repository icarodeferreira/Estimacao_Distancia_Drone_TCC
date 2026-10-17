from pathlib import Path
import sys,tempfile,unittest,subprocess,importlib.util
import numpy as np,pandas as pd
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from audit_core import interpolate,timecode,synchronize,default_config,reference
from experiment import roi,metrics
class CoreTests(unittest.TestCase):
 def test_interpolation(self):
  np.testing.assert_allclose(interpolate([-1,0,.5,1,2,3,4],[0,1,3],[1,2,4],1),[np.nan,1,1.5,2,np.nan,4,np.nan],equal_nan=True)
 def test_time(self):
  self.assertAlmostEqual(timecode('00:00:02:25'),85/30);c=default_config();c['sync']['events']=[{'video_s':2.,'telemetry_s':6.8}];self.assertAlmostEqual(synchronize(c)['b'],4.8)
 def test_roi(self):
  z=np.arange(100,dtype=float).reshape(10,10)+1;self.assertAlmostEqual(roi(z,[0,0,10,10],[20,20]),float(np.percentile(z[:5,:5],25)));self.assertTrue(np.isnan(roi(z,[0,0,0,0],[20,20])))
 def test_missing_metrics(self):self.assertEqual(metrics([np.nan],[10])['n'],0)
 def test_no_reference(self):
  c=default_config();c['geometry']['mode']='none';c['sync']['b']=0
  with tempfile.TemporaryDirectory() as d:
   out=Path(d);(out/'audit').mkdir();(out/'tables').mkdir();v=reference(pd.DataFrame({'t':[0.,.5,2.]}),pd.DataFrame({'t':[0.,1.],'height':[1.,2.]}),c,out);self.assertTrue(v.ref.isna().all());self.assertAlmostEqual(v.telemetry_height.iloc[1],1.5);self.assertTrue(np.isnan(v.telemetry_height.iloc[2]))
 def test_pts_render(self):
  spec=importlib.util.spec_from_file_location('render',R/'scripts/anotar_video.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);v=d/'in.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:r=10:d=0.4','-c:v','libx264','-y',str(v)],check=True);pd.DataFrame({'frame_idx':range(4),'x1':[20]*4,'y1':[20]*4,'x2':[50]*4,'y2':[50]*4,'depth_z_m':[5]*4}).to_csv(d/'pred.csv',index=False);self.assertEqual(m.render(v,d/'pred.csv',d/'out.mp4')['output_frames'],4)
if __name__=='__main__':unittest.main()
