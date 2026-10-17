from pathlib import Path
import argparse,pandas as pd,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('outputs/figuras_tabelas'));a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
R=Path(__file__).resolve().parents[1];D=R/'outputs/farol_reproduzido'
if not (D/'box_distance_blocked_cv_summary.csv').exists():raise SystemExit('Execute scripts/reproduzir_farol.py primeiro.')
for name in ['box_distance_blocked_cv_summary','final_method_comparison','box_width_quality_comparison']:
 d=pd.read_csv(D/(name+'.csv'));d.to_csv(a.out/(name+'.csv'),index=False)
 def esc(v):return str(v).replace('&',r'\&').replace('%',r'\%').replace('_',r'\_')
 text='\n'.join(' & '.join(esc(v) for v in row)+r' \\' for row in [list(d.columns)]+d.values.tolist())
 (a.out/(name+'.tex')).write_text(r'\begin{tabular}{'+len(d.columns)*'l'+'}\n'+text+'\n'+r'\end{tabular}')
d=pd.read_csv(D/'box_distance_blocked_cv_summary.csv');fig,ax=plt.subplots(figsize=(10,5));ax.barh(d.model,d.mae_m,label='MAE');ax.scatter(d.rmse_m,d.model,color='darkred',label='RMSE');ax.set_xlabel('Erro em relação à referência nominal (m)');ax.legend();fig.tight_layout()
for ext in ['png','pdf']:fig.savefig(a.out/('modelos_oof.'+ext),dpi=200)
plt.close(fig)
d=pd.read_csv(D/'box_distance_blocked_cv_predictions.csv');d=d[d.model=='box_width_log'];fig,ax=plt.subplots(figsize=(9,4));ax.plot(d.video_time_s,d.reference_distance_nominal_m,label='Referência nominal',color='black');ax.plot(d.video_time_s,d.oof_estimate_m,label='Largura: OOF');ax.set(xlabel='Tempo (s)',ylabel='Distância (m)');ax.legend();fig.tight_layout()
for ext in ['png','pdf']:fig.savefig(a.out/('farol_largura_oof.'+ext),dpi=200)
print(a.out)
