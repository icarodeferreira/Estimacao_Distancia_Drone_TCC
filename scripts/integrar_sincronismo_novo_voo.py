#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integra temporalmente PTS, telemetria e resultados JÁ existentes do novo voo.

Nao treina modelos, nao realiza inferencia, nao valida distancias metricas.
Uso:
    python integrar_sincronismo_novo_voo.py --dados-dir FONTES --saida RESULTADOS
A auditoria usa apenas os arquivos identificados na pasta de entrada.
"""
from __future__ import annotations

import gzip
import argparse
import bisect
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

CENARIOS = {
    "candidato_10_5667s": 21.4 - 325 / 30.0,
    "historico_11_2s": 11.2,
}
EVENTOS = (
    ("decolagem", 137, 15.3, "primeira velocidade vertical registrada; nao e contato certificado"),
    ("segunda_subida", 325, 21.4, "primeira velocidade vertical negativa; marco visual 324→325"),
    ("subida_intermediaria", 2173, 82.9, "primeira velocidade vertical negativa; marco visual 2172→2173"),
    ("pouso", 4987, 176.8, "parada da velocidade vertical registrada; nao e contato certificado"),
)
TELEM_FIELDS = ("height_m", "vps_height_m", "velocity_z_ms")
EXPECTED_ROWS = 5142


def read_csv(p):
    with (gzip.open(p,"rt",encoding="utf-8-sig",newline="") if p.suffix==".gz" else p.open(encoding="utf-8-sig",newline="")) as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, keys=None):
    rows = list(rows)
    if keys is None:
        if not rows:
            raise ValueError(f"Sem dados para escrever: {path}")
        keys = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for part in iter(lambda: fh.read(2**20), b""):
            h.update(part)
    return h.hexdigest()


def number(s):
    if s is None or str(s).strip() == "":
        return None
    v = float(s)
    if not math.isfinite(v):
        return None
    return v


def interp_at(t, series, times):
    """Interpola SOMENTE campos continuos quando duas amostras distam <=0,15s.

    Nunca interpola flight_mode. Nao extrapola apos as amostras.
    Retorna status proprio da disponibilidade de amostragem, que nao e qualidade metrica.
    """
    eps = 1e-6
    res = {"status_telemetria": "", "intervalo_amostras_s": "", "amostra_inferior_s": "", "amostra_superior_s": "",
           "flight_mode_amostra_anterior": ""}
    for col in TELEM_FIELDS:
        res[f"{col}_interpolado"] = ""
    if t < times[0] - eps or t > times[-1] + eps:
        res["status_telemetria"] = "fora_da_janela_temporal"
        return res
    i = bisect.bisect_left(times, t)
    if i < len(times) and abs(times[i] - t) < eps:
        a = b = i
        status = "amostra_exata"
    elif i > 0 and abs(times[i-1] - t) < eps:
        a = b = i - 1
        status = "amostra_exata"
    elif i == 0 or i == len(times):
        res["status_telemetria"] = "fora_da_janela_temporal"
        return res
    else:
        a, b = i-1, i
        if (times[b] - times[a]) > 0.150000001:
            res["status_telemetria"] = "lacuna_amostral_sem_interpolacao"
            res["intervalo_amostras_s"] = round(times[b] - times[a], 9)
            res["amostra_inferior_s"] = round(times[a], 9)
            res["amostra_superior_s"] = round(times[b], 9)
            return res
        status = "interpolacao_linear_local"
    res["status_telemetria"] = status
    res["intervalo_amostras_s"] = round(times[b] - times[a], 9)
    res["amostra_inferior_s"] = round(times[a], 9)
    res["amostra_superior_s"] = round(times[b], 9)
    res["flight_mode_amostra_anterior"] = series[a].get("flight_mode", "")
    u = 0.0 if a == b else (t - times[a]) / (times[b] - times[a])
    for col in TELEM_FIELDS:
        va, vb = number(series[a].get(col)), number(series[b].get(col))
        if va is not None and vb is not None:
            res[f"{col}_interpolado"] = round(va + u * (vb - va), 8)
    return res


def check_inputs(folder):
    files = {
        "pts": folder/"PTS_TODOS_QUADROS.csv",
        "telem": folder/"FlightRecord_2026-09-24_14-12-36_corrigido.csv",
        "pipeline": folder/"T17_pipeline_5142_quadros.csv",
        "pts_auditoria": folder/"AUDITORIA_PTS_VIDEO.json",
    }
    files = {k: (p if p.exists() else p.with_suffix(p.suffix+".gz")) for k,p in files.items()}
    missing = [p.name for p in files.values() if not p.exists()]
    if missing:
        raise SystemExit("Faltam arquivos em FONTES: " + ", ".join(missing))
    pts, telem, pipeline = (read_csv(files[k]) for k in ("pts", "telem", "pipeline"))
    audit = json.loads(files["pts_auditoria"].read_text(encoding="utf-8-sig"))
    if len(pts) != EXPECTED_ROWS or len(pipeline) != EXPECTED_ROWS:
        raise ValueError("PTS e T17 devem ter exatamente 5142 quadros; confira o vídeo e versão do pipeline")
    if audit.get("total_quadros_pts") != EXPECTED_ROWS or audit.get("arquivo_video") != "IMG_5962_editado.mov":
        raise ValueError("Auditoria de PTS não se refere ao vídeo IMG_5962_editado.mov de 5142 quadros")
    for i, (p, row) in enumerate(zip(pts, pipeline)):
        if int(p["frame_idx_0_based"]) != i or int(row["frame_idx"]) != i:
            raise ValueError(f"Divergencia na sequencia PTS/pipeline: linha {i}")
        t_pts = float(p["pts_relativo_primeiro_s"])
        t_pipeline = float(row["t_video_s"])
        if abs(t_pts - t_pipeline) > 1e-4:
            raise ValueError(f"PTS e pipeline com tempos divergentes no quadro {i}: {t_pts}, {t_pipeline}")
    pts_times = [float(p["pts_relativo_primeiro_s"]) for p in pts]
    if any(t1 <= t0 for t0,t1 in zip(pts_times,pts_times[1:])):
        raise ValueError("PTS não são estritamente crescentes")
    times = [float(r["time_s"]) for r in telem]
    if any(t1 <= t0 for t0,t1 in zip(times,times[1:])):
        raise ValueError("Tempos da telemetria nao sao estritamente crescentes")
    if abs(times[0])>0.01 or abs(times[-1]-177.7)>0.01:
        raise ValueError("Inicio/fim de telemetria inesperados: confira o arquivo")
    return files, pts, telem, pipeline, pts_times, times


def status_roi(row):
    return row["detectado"].strip().lower() == "true"


def qtile(values, q):
    if not values:
        return None
    s=sorted(values)
    p=(len(s)-1)*q
    a=int(math.floor(p)); b=int(math.ceil(p))
    return s[a] if a==b else s[a]+(s[b]-s[a])*(p-a)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dados-dir", type=Path, default=Path(__file__).resolve().parent/"FONTES")
    ap.add_argument("--saida", type=Path, default=Path(__file__).resolve().parent/"RESULTADOS")
    args = ap.parse_args()
    args.saida.mkdir(parents=True,exist_ok=True)
    files, pts, telem, pipeline, pts_times, times = check_inputs(args.dados_dir)

    obs = []
    sensitivity = []
    by_scenario = {}
    compact_rows = {}
    for label, offset in CENARIOS.items():
        allrows = []
        per10 = defaultdict(list)
        for i,(t, m) in enumerate(zip(pts_times, pipeline)):
            target = t+offset
            tel = interp_at(target, telem, times)
            reg = m["distancia_regressao_exploratoria_m"]
            dep = m["depth_pro_Z_axial_p25_m"]
            row={
              "cenario": label,"frame_idx":i,"pts_video_s":round(t,9),"offset_hipotese_s":round(offset,9),
              "t_telemetria_hipotetico_s":round(target,9),
              **tel,
              "roi_emitida_nao_validada":str(status_roi(m)).lower(),
              "classe_id_original":m["classe_id"],
              "confianca_roi":m["confianca"],
              "largura_roi_px":m["box_width_px"],
              "qc_agregado_segundo_aprovado":m["qc_aprovado"],
              "motivo_abstencao_agregado":m["motivo_abstencao"],
              "regressao_exploratoria_repetida_no_segundo_m":reg,
              "depth_pro_Z_axial_roi_nao_validada_m":dep,
              "depth_status_original":m["depth_status"],
              "referencia_distancia_camera_drone_m":"",
              "erro_metrico_avaliavel":"false",
            }
            allrows.append(row)
            per10[int(t//10)*10].append(row)
        outfile = args.saida/f"INTEGRACAO_{label}.csv"
        write_csv(outfile,allrows)
        ok = [x for x in allrows if x["status_telemetria"] in ("amostra_exata","interpolacao_linear_local")]
        roi_ok = [x for x in ok if x["roi_emitida_nao_validada"] == "true"]
        reg_ok = [x for x in ok if x["regressao_exploratoria_repetida_no_segundo_m"] != ""]
        depth_ok = [x for x in ok if x["depth_pro_Z_axial_roi_nao_validada_m"] != ""]
        counter = Counter(x["status_telemetria"] for x in allrows)
        data = {
          "cenario":label,"offset_s":round(offset,9),"total_quadros":len(allrows),
          "quadros_com_suporte_telemetrico":len(ok),
          "pct_quadros_com_suporte_telemetrico":round(100*len(ok)/len(allrows),4),
          "quadros_fora_cobertura":counter.get("fora_da_janela_temporal",0),
          "quadros_sem_interpolacao_por_lacuna":counter.get("lacuna_amostral_sem_interpolacao",0),
          "ultimo_frame_com_suporte":max(int(x["frame_idx"]) for x in ok) if ok else "",
          "quadros_roi_total":sum(x["roi_emitida_nao_validada"]=="true" for x in allrows),
          "quadros_roi_com_telemetria":len(roi_ok),
          "quadros_com_regressao_repetida_e_telemetria":len(reg_ok),
          "segundos_com_regressao_e_telemetria":len({int(float(x["pts_video_s"])) for x in reg_ok}),
          "quadros_com_depth_Z_e_telemetria":len(depth_ok),
          "referencia_metrica_independente":"nao_disponivel",
          "avaliacao_mae_rmse_permitida":"nao",
        }
        obs.append(data)
        by_scenario[label]=allrows
        compact_rows[label]=per10
    write_csv(args.saida/"RESUMO_CENARIOS.csv",obs)

    blocos=[]
    for label in CENARIOS:
        for bloco,group in sorted(compact_rows[label].items()):
            valid = [x for x in group if x["status_telemetria"] in ("amostra_exata","interpolacao_linear_local")]
            roi = [x for x in valid if x["roi_emitida_nao_validada"]=="true"]
            blocos.append({"cenario":label,"inicio_intervalo_video_s":bloco,"fim_intervalo_video_s_exclusivo":bloco+10,
                "quadros_no_intervalo":len(group),"quadros_com_suporte_telemetrico":len(valid),
                "quadros_com_roi_e_telemetria":len(roi),
                "quadros_com_Z_depth_e_telemetria":sum(x["depth_pro_Z_axial_roi_nao_validada_m"] != "" for x in valid),
                "pct_temporal_no_intervalo":round(100*len(valid)/len(group),4)})
    write_csv(args.saida/"COBERTURA_BLOCOS_10_SEGUNDOS.csv",blocos)

    eventos=[]
    for nome, frame, t_sensor, nota in EVENTOS:
        t_video=pts_times[frame]
        row={"evento":nome,"frame_visual":frame,"pts_visual_s":round(t_video,9),
             "indicador_instrumental_s":t_sensor,"tipo_indicador":nota,
             "offset_nominal_indicador_menos_video_s":round(t_sensor-t_video,9)}
        for key,offset in CENARIOS.items():
            row[f"tempo_telem_previsto_{key}_s"]=round(t_video+offset,9)
            row[f"residuo_instrumental_{key}_s"]=round(t_sensor-t_video-offset,9)
        eventos.append(row)
    write_csv(args.saida/"EVENTOS_E_RESIDUOS_EXPLORATORIOS.csv",eventos)

    base=by_scenario["candidato_10_5667s"]
    hist=by_scenario["historico_11_2s"]
    for x,y in zip(base,hist):
        valid=x["status_telemetria"] in ("amostra_exata","interpolacao_linear_local") and y["status_telemetria"] in ("amostra_exata","interpolacao_linear_local")
        xa=number(x["height_m_interpolado"]); ya=number(y["height_m_interpolado"])
        sensitivity.append({"frame_idx":x["frame_idx"],"pts_video_s":x["pts_video_s"],
         "suporte_nos_dois_cenarios":str(valid).lower(),
         "altura_sensor_candidato_m":round(xa,8) if valid and xa is not None else "",
         "altura_sensor_historico_m":round(ya,8) if valid and ya is not None else "",
         "diferenca_altura_sensor_historico_menos_candidato_m":round(ya-xa,8) if valid and xa is not None and ya is not None else ""})
    write_csv(args.saida/"SENSIBILIDADE_ALTURA_SENSOR_DOIS_CENARIOS.csv",sensitivity)
    deltas = [abs(float(x["diferenca_altura_sensor_historico_menos_candidato_m"])) for x in sensitivity if x["diferenca_altura_sensor_historico_menos_candidato_m"] != ""]
    diff_summary = {"n_quadros_com_altura_nos_dois_cenarios":len(deltas),
         "abs_diferenca_altura_sensor_mediana_m":round(median(deltas),5),
         "abs_diferenca_altura_sensor_p95_m":round(qtile(deltas,0.95),5),
         "abs_diferenca_altura_sensor_max_m":round(max(deltas),5),
         "aviso":"Esta diferenca e entre leituras de altura em tempos distintos, NAO e erro de alcance camera-drone."}

    hashes={str(p.name):sha256(p) for p in files.values()}
    checks={"fonte_video_declarada": "IMG_5962_editado.mov", "pts_quadros":len(pts), "pipeline_quadros":len(pipeline),
       "telemetria_registros":len(telem),"telemetria_inicio_s":times[0],"telemetria_fim_s":times[-1],
       "pts_primeiro_s":pts_times[0],"pts_ultimo_s":pts_times[-1],
       "pipeline_roi_total":sum(status_roi(x) for x in pipeline),
       "segundos_qc_regressao_distintos":len({int(float(row["t_video_s"])) for row in pipeline if row["distancia_regressao_exploratoria_m"] != ""}),
       "quadros_regressao_repetida":sum(row["distancia_regressao_exploratoria_m"] != "" for row in pipeline),
       "quadros_depth_Z_com_valor":sum(row["depth_pro_Z_axial_p25_m"] != "" for row in pipeline),
       "cenarios":list(CENARIOS),"resumos":obs,"sensibilidade_altura":diff_summary,"hashes_SHA256_fontes":hashes,
       "regra_interpolacao":"somente numéricos de amostras vizinhas com distancia <=0,15s; sem extrapolacao",
       "controle_qualidade":"quadros com ROI nao provam TP; regressao por segundo repetida nao equivale a preditoes independentes; Depth Pro Z nao equivale a R",
       "status_sincronizacao":"hipoteses exploratorias; sem referencia absoluta certificada; deriva nao identificada"}
    (args.saida/"RESULTADOS_INTEGRACAO.json").write_text(json.dumps(checks,indent=2,ensure_ascii=False),encoding="utf-8")

    try:
        # Gráficos de apoio, não indispensáveis à reprodução dos CSVs.
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(12,4.7))
        for label, offset in CENARIOS.items():
            x = [v-offset for v in times]
            y = [number(r["height_m"]) for r in telem]
            ax.plot(x,y,label=label,linewidth=1.25)
        for nome,frame,_,_ in EVENTOS:
            ax.axvline(pts_times[frame],alpha=.35,linewidth=.9,linestyle="--")
        ax.set_xlabel("Tempo do vídeo (s; PTS relativo)")
        ax.set_ylabel("height_m do sensor (m; não equivale a alcance)")
        ax.set_title("Posicionamento temporal hipotético da altura telemétrica")
        ax.grid(alpha=.2)
        ax.legend()
        fig.tight_layout()
        fig.savefig(args.saida/"FIGURA_SENSIBILIDADE_ALINHAMENTO.png",dpi=160)
        plt.close(fig)
    except ImportError:
        pass
    print(json.dumps({"status":"OK", "resumos":obs,"sensibilidade":diff_summary,"saida":str(args.saida)},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
