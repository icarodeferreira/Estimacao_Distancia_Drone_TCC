from __future__ import annotations
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
import os, json, math, argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def display(x):
    pass
def atomic_csv(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)

def interp_finite(t: float, x: np.ndarray, y: np.ndarray) -> float:
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 2 or t < x[valid].min() or t > x[valid].max():
        return np.nan
    return float(np.interp(t, x[valid], y[valid]))

def telemetry_record_at(telemetry_time_s: float) -> dict:
    height_m = interp_finite(telemetry_time_s, telemetry_t, telemetry_height_m)
    home_m = interp_finite(telemetry_time_s, telemetry_t, telemetry_home_m)
    latitude = interp_finite(telemetry_time_s, telemetry_t, telemetry_lat)
    longitude = interp_finite(telemetry_time_s, telemetry_t, telemetry_lon)
    if not np.isfinite(height_m) or not np.isfinite(home_m):
        return {'drone_height_m': height_m, 'home_distance_m': home_m, 'latitude': latitude, 'longitude': longitude, 'reference_distance_nominal_m': np.nan, 'reference_distance_min_partial_m': np.nan, 'reference_distance_max_partial_m': np.nan}
    dz = height_m - CAMERA_HEIGHT_M
    horizontal_min = abs(home_m - CAMERA_TO_HOME_HORIZONTAL_M)
    horizontal_max = home_m + CAMERA_TO_HOME_HORIZONTAL_M
    nominal = math.sqrt(home_m ** 2 + CAMERA_TO_HOME_HORIZONTAL_M ** 2 + dz ** 2)
    lower = math.sqrt(horizontal_min ** 2 + dz ** 2)
    upper = math.sqrt(horizontal_max ** 2 + dz ** 2)
    return {'drone_height_m': height_m, 'home_distance_m': home_m, 'latitude': latitude, 'longitude': longitude, 'reference_distance_nominal_m': nominal, 'reference_distance_min_partial_m': lower, 'reference_distance_max_partial_m': upper}

def frame_timestamp_s(cap: cv2.VideoCapture, frame_idx: int) -> tuple[float, str]:
    nominal = frame_idx / NATIVE_FPS
    pos_msec = float(cap.get(cv2.CAP_PROP_POS_MSEC))
    measured = pos_msec / 1000.0
    if np.isfinite(measured) and measured >= 0 and (abs(measured - nominal) <= 0.25):
        return (measured, 'pos_msec')
    return (nominal, 'frame_index_fallback')

def distance_zone(distance_m: float) -> str:
    if not np.isfinite(distance_m):
        return 'outside_telemetry'
    if distance_m < 20:
        return 'critical_0_20m'
    if distance_m < 40:
        return 'attention_20_40m'
    if distance_m < 80:
        return 'distant_40_80m'
    return 'very_distant_80m_plus'

def calibrate(raw_m: float) -> float:
    if not np.isfinite(raw_m) or raw_m <= 0:
        return np.nan
    return float(np.exp(CAL_INTERCEPT + CAL_SLOPE * np.log(raw_m)))

def acceptable(estimate: float, reference: float) -> bool:
    return bool(np.isfinite(estimate) and np.isfinite(reference) and (abs(estimate - reference) <= max(ACCEPT_ABS_M, ACCEPT_REL * reference)))

def partial_interval_error(estimate: float, lower: float, upper: float) -> float:
    if not all(np.isfinite([estimate, lower, upper])):
        return np.nan
    if lower <= estimate <= upper:
        return 0.0
    return float(min(abs(estimate - lower), abs(estimate - upper)))

def parse_box(row) -> Optional[list[float]]:
    values = [row.get(k, np.nan) for k in ['x1', 'y1', 'x2', 'y2']]
    return list(map(float, values)) if np.all(np.isfinite(values)) else None

def roi_p25(depth: np.ndarray, box, source_wh) -> tuple[float, int]:
    if box is None:
        return (np.nan, 0)
    sw, sh = source_wh
    dh, dw = depth.shape
    x1, y1, x2, y2 = map(float, box)
    ix1 = int(np.floor(np.clip(x1 * dw / sw, 0, dw - 1)))
    ix2 = int(np.ceil(np.clip(x2 * dw / sw, ix1 + 1, dw)))
    iy1 = int(np.floor(np.clip(y1 * dh / sh, 0, dh - 1)))
    iy2 = int(np.ceil(np.clip(y2 * dh / sh, iy1 + 1, dh)))
    values = depth[iy1:iy2, ix1:ix2].reshape(-1)
    values = values[np.isfinite(values) & (values > 0)]
    return (float(np.percentile(values, 25)), int(values.size)) if values.size else (np.nan, 0)

def abstention_reason(conf, box, valid_pixels, estimate) -> str:
    if box is None:
        return 'no_detection'
    x1, y1, x2, y2 = box
    if not np.isfinite(conf) or conf < YOLO_RELIABLE_CONF:
        return 'low_confidence'
    if x2 - x1 < MIN_BOX_WIDTH_PX or y2 - y1 < MIN_BOX_HEIGHT_PX:
        return 'box_too_small'
    if valid_pixels < MIN_VALID_DEPTH_PIXELS:
        return 'insufficient_depth_pixels'
    if not np.isfinite(estimate) or not MIN_ESTIMATE_M <= estimate <= MAX_ESTIMATE_M:
        return 'invalid_distance'
    return ''

def metric_dict(reference, estimate) -> dict:
    ref = np.asarray(reference, float)
    est = np.asarray(estimate, float)
    valid = np.isfinite(ref) & np.isfinite(est)
    ref, est = (ref[valid], est[valid])
    if not len(ref):
        return {'n': 0}
    err = est - ref
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((ref - np.mean(ref)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if len(ref) > 1 and ss_tot > 0 else np.nan
    return {'n': int(len(ref)), 'mae_m': float(np.mean(np.abs(err))), 'rmse_m': float(np.sqrt(np.mean(err ** 2))), 'median_ae_m': float(np.median(np.abs(err))), 'mape_pct': float(np.mean(np.abs(err) / np.maximum(np.abs(ref), 1e-09)) * 100), 'bias_m': float(np.mean(err)), 'r2': float(r2), 'spearman': float(pd.Series(ref).corr(pd.Series(est), method='spearman')) if len(ref) > 1 else np.nan}

def longest_true_run(values) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if bool(value) else 0
        best = max(best, current)
    return best

def acceptance_dict(reference, estimate, all_labeled_count=None):
    reference = np.asarray(reference, float)
    estimate = np.asarray(estimate, float)
    finite = np.isfinite(reference) & np.isfinite(estimate)
    reference, estimate = (reference[finite], estimate[finite])
    absolute = np.abs(estimate - reference)
    relative = absolute / np.maximum(np.abs(reference), 1e-09)
    within_1m = absolute <= 1.0
    within_20pct = relative <= 0.2
    legacy = absolute <= np.maximum(5.0, 0.2 * np.abs(reference))
    result = {'within_1m_pct_emitted': float(within_1m.mean() * 100) if len(absolute) else np.nan, 'within_20pct_pct_emitted': float(within_20pct.mean() * 100) if len(absolute) else np.nan, 'legacy_5m_or_20pct_pct_emitted': float(legacy.mean() * 100) if len(absolute) else np.nan}
    if all_labeled_count is not None:
        denominator = max(1, int(all_labeled_count))
        result.update({'within_1m_pct_all_labeled': float(within_1m.sum() / denominator * 100), 'within_20pct_pct_all_labeled': float(within_20pct.sum() / denominator * 100), 'legacy_5m_or_20pct_pct_all_labeled': float(legacy.sum() / denominator * 100)})
    return result

p=argparse.ArgumentParser()
p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]/'results/archived/farol')
p.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1]/'outputs/farol_reproduzido')
a=p.parse_args(); OUTPUT_DIR=a.out.resolve(); OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
RUN_MODE='full'; NATIVE_FPS=30.; WIDTH=3840; HEIGHT=2160
YOLO_RELIABLE_CONF=.25; MIN_BOX_WIDTH_PX=10.; MIN_BOX_HEIGHT_PX=5.
MIN_VALID_DEPTH_PIXELS=6; MIN_ESTIMATE_M=1.; MAX_ESTIMATE_M=150.
ACCEPT_ABS_M=5.; ACCEPT_REL=.2
FIXED_FOCAL_PX=1440.; CAL_INTERCEPT=1.4600571394959514; CAL_SLOPE=.5026751660343942
RUN_TEMPORAL_METRICS=True; RUN_FULL_BOX_CALIBRATION_CV=True
RUN_BOX_ROBUSTNESS_AUDIT=True; RUN_FINAL_REPORT=True
BOX_AUDIT_MIN_FRAMES_PER_SECOND=5; BOX_AUDIT_MAX_RELATIVE_IQR=.35
BOX_AUDIT_HAMPEL_HISTORY_SECONDS=5; BOX_AUDIT_HAMPEL_K=3.
BOX_AUDIT_MAX_LOG_WIDTH_JUMP=.35
PER_SECOND_CSV=OUTPUT_DIR/'metrics_per_second.csv'
ZONE_CSV=OUTPUT_DIR/'metrics_by_zone.csv'; METRICS_JSON=OUTPUT_DIR/'temporal_metrics.json'
FINAL_REPORT_MD=OUTPUT_DIR/'relatorio_final_metodos.md'; FINAL_SUMMARY_JSON=OUTPUT_DIR/'resumo_final_metodos.json'
depth_frames=pd.read_csv(a.source/('depth_all_frames.csv' if (a.source/'depth_all_frames.csv').exists() else 'depth_all_frames.csv.gz'))
yolo_frames=pd.read_csv(a.source/('yolo_all_frames.csv' if (a.source/'yolo_all_frames.csv').exists() else 'yolo_all_frames.csv.gz'))


if RUN_TEMPORAL_METRICS:
    if not len(depth_frames):
        raise RuntimeError('Execute o Depth Pro antes das métricas.')
    df = depth_frames.copy()
    estimate_values = pd.to_numeric(df['estimated_distance_m'], errors='coerce').to_numpy(float)
    reference_values = pd.to_numeric(df['reference_distance_nominal_m'], errors='coerce').to_numpy(float)
    lower_values = pd.to_numeric(df['reference_distance_min_partial_m'], errors='coerce').to_numpy(float)
    upper_values = pd.to_numeric(df['reference_distance_max_partial_m'], errors='coerce').to_numpy(float)
    abstained_values = df['abstained'].fillna(True).astype(bool).to_numpy()
    df['signed_error_m'] = estimate_values - reference_values
    df['absolute_error_m'] = np.abs(estimate_values - reference_values)
    df['interval_error_partial_m'] = [partial_interval_error(estimate, lower, upper) for estimate, lower, upper in zip(estimate_values, lower_values, upper_values)]
    df['acceptable'] = [acceptable(estimate, reference) if not abstained else False for estimate, reference, abstained in zip(estimate_values, reference_values, abstained_values)]
    in_scope = df['reference_distance_nominal_m'].notna()
    emitted = in_scope & ~df['abstained'].astype(bool)
    valid = df.loc[emitted].copy()
    valid['second'] = np.floor(valid['video_time_s']).astype(int)
    per_second = valid.groupby('second', as_index=False).agg(video_time_s=('video_time_s', 'median'), telemetry_time_s=('telemetry_time_s', 'median'), reference_distance_nominal_m=('reference_distance_nominal_m', 'median'), reference_distance_min_partial_m=('reference_distance_min_partial_m', 'median'), reference_distance_max_partial_m=('reference_distance_max_partial_m', 'median'), estimated_distance_m=('estimated_distance_m', 'median'), frames=('frame_idx', 'size'), confidence=('confidence', 'median'))
    atomic_csv(per_second, PER_SECOND_CSV)
    zone_rows = []
    for zone, part in df.loc[in_scope].groupby('distance_zone'):
        part_emitted = part.loc[~part['abstained'].astype(bool)]
        zone_rows.append({'distance_zone': zone, 'frames': int(len(part)), 'emission_coverage_pct': float(len(part_emitted) / max(1, len(part)) * 100), 'acceptable_pct_all_frames': float(part['acceptable'].astype(bool).mean() * 100), 'mean_interval_error_partial_m': float(part_emitted['interval_error_partial_m'].mean()), **metric_dict(part_emitted.reference_distance_nominal_m, part_emitted.estimated_distance_m)})
    zones = pd.DataFrame(zone_rows)
    atomic_csv(zones, ZONE_CSV)
    estimate_series = valid['estimated_distance_m'].to_numpy(float)
    longest_abstention = longest_true_run(df.loc[in_scope, 'abstained'])
    metrics = {'created_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'mode': RUN_MODE, 'frames_processed': int(len(df)), 'telemetry_labeled_frames': int(in_scope.sum()), 'emitted_frames': int(emitted.sum()), 'emission_coverage_pct': float(emitted.sum() / max(1, in_scope.sum()) * 100), 'acceptable_pct_all_labeled_frames': float((df['acceptable'].astype(bool) & in_scope).sum() / max(1, in_scope.sum()) * 100), 'per_frame_descriptive': metric_dict(valid.reference_distance_nominal_m, valid.estimated_distance_m), 'per_second_primary_temporal': metric_dict(per_second.reference_distance_nominal_m, per_second.estimated_distance_m), 'mean_partial_interval_error_m': float(valid['interval_error_partial_m'].mean()), 'median_frame_to_frame_jitter_m': float(np.median(np.abs(np.diff(estimate_series)))) if len(estimate_series) > 1 else np.nan, 'longest_abstention_run_frames': longest_abstention, 'longest_abstention_run_s': longest_abstention / NATIVE_FPS, 'mean_yolo_time_s': float(df['yolo_time_s'].mean()), 'mean_depth_time_s': float(df['depth_time_s'].mean()), 'offline_real_time_factor': float((df['yolo_time_s'].sum() + df['depth_time_s'].sum()) / (len(df) / NATIVE_FPS)), 'abstention_reasons': df.loc[df['abstained'].astype(bool), 'abstention_reason'].value_counts().to_dict(), 'scientific_note': 'Quadros adjacentes e rótulos interpolados são temporalmente dependentes; o resumo por segundo é primário.'}
    with METRICS_JSON.open('w', encoding='utf-8') as handle:
        json.dump(metrics, handle, indent=2, ensure_ascii=False, allow_nan=True)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    display(zones.round(3))
    display(per_second.head())
else:
    print('Métricas bloqueadas.')

if RUN_TEMPORAL_METRICS:
    import matplotlib.pyplot as plt
    required = ['frame_idx', 'video_time_s', 'reference_distance_nominal_m', 'raw_s00_p25_m', 'estimated_distance_m', 'distance_zone', 'abstained']
    missing = [column for column in required if column not in depth_frames.columns]
    if missing:
        raise KeyError(f'Colunas ausentes no Depth CSV: {missing}')
    comparison = depth_frames.copy()
    for column in ['reference_distance_nominal_m', 'raw_s00_p25_m', 'estimated_distance_m', 'video_time_s']:
        comparison[column] = pd.to_numeric(comparison[column], errors='coerce')
    labeled = comparison['reference_distance_nominal_m'].notna()
    emitted = labeled & ~comparison['abstained'].fillna(True).astype(bool)
    finite_methods = np.isfinite(comparison['raw_s00_p25_m']) & np.isfinite(comparison['estimated_distance_m'])
    valid_comparison = comparison.loc[emitted & finite_methods].copy()
    valid_comparison['second'] = np.floor(valid_comparison['video_time_s']).astype(int)
    method_columns = {'Depth bruto — focal 1440 px': 'raw_s00_p25_m', 'Depth calibrado — calibração antiga': 'estimated_distance_m'}

    def acceptance_dict(reference, estimate, all_labeled_count=None):
        reference = np.asarray(reference, float)
        estimate = np.asarray(estimate, float)
        finite = np.isfinite(reference) & np.isfinite(estimate)
        reference, estimate = (reference[finite], estimate[finite])
        absolute = np.abs(estimate - reference)
        relative = absolute / np.maximum(np.abs(reference), 1e-09)
        within_1m = absolute <= 1.0
        within_20pct = relative <= 0.2
        legacy = absolute <= np.maximum(5.0, 0.2 * np.abs(reference))
        result = {'within_1m_pct_emitted': float(within_1m.mean() * 100) if len(absolute) else np.nan, 'within_20pct_pct_emitted': float(within_20pct.mean() * 100) if len(absolute) else np.nan, 'legacy_5m_or_20pct_pct_emitted': float(legacy.mean() * 100) if len(absolute) else np.nan}
        if all_labeled_count is not None:
            denominator = max(1, int(all_labeled_count))
            result.update({'within_1m_pct_all_labeled': float(within_1m.sum() / denominator * 100), 'within_20pct_pct_all_labeled': float(within_20pct.sum() / denominator * 100), 'legacy_5m_or_20pct_pct_all_labeled': float(legacy.sum() / denominator * 100)})
        return result
    comparison_per_second = valid_comparison.groupby('second', as_index=False).agg(video_time_s=('video_time_s', 'median'), reference_distance_nominal_m=('reference_distance_nominal_m', 'median'), raw_s00_p25_m=('raw_s00_p25_m', 'median'), estimated_distance_m=('estimated_distance_m', 'median'), frames=('frame_idx', 'size'), confidence=('confidence', 'median'))
    comparison_per_second['raw_absolute_error_m'] = np.abs(comparison_per_second['raw_s00_p25_m'] - comparison_per_second['reference_distance_nominal_m'])
    comparison_per_second['calibrated_absolute_error_m'] = np.abs(comparison_per_second['estimated_distance_m'] - comparison_per_second['reference_distance_nominal_m'])
    summary_rows = []
    for method, estimate_column in method_columns.items():
        frame_reference = valid_comparison['reference_distance_nominal_m']
        frame_estimate = valid_comparison[estimate_column]
        summary_rows.append({'level': 'per_frame_descriptive', 'method': method, 'emission_coverage_pct': float(len(valid_comparison) / max(1, labeled.sum()) * 100), 'mean_estimate_m': float(frame_estimate.mean()), 'median_estimate_m': float(frame_estimate.median()), **metric_dict(frame_reference, frame_estimate), **acceptance_dict(frame_reference, frame_estimate, labeled.sum())})
        second_reference = comparison_per_second['reference_distance_nominal_m']
        second_estimate = comparison_per_second[estimate_column]
        summary_rows.append({'level': 'per_second_primary', 'method': method, 'emission_coverage_pct': np.nan, 'mean_estimate_m': float(second_estimate.mean()), 'median_estimate_m': float(second_estimate.median()), **metric_dict(second_reference, second_estimate), **acceptance_dict(second_reference, second_estimate)})
    method_summary = pd.DataFrame(summary_rows)
    zone_rows = []
    for zone, zone_all in comparison.loc[labeled].groupby('distance_zone'):
        zone_valid = valid_comparison.loc[valid_comparison['distance_zone'] == zone]
        for method, estimate_column in method_columns.items():
            reference = zone_valid['reference_distance_nominal_m']
            estimate = zone_valid[estimate_column]
            zone_rows.append({'distance_zone': zone, 'method': method, 'frames_labeled': int(len(zone_all)), 'frames_emitted': int(len(zone_valid)), 'emission_coverage_pct': float(len(zone_valid) / max(1, len(zone_all)) * 100), 'mean_estimate_m': float(estimate.mean()), 'median_estimate_m': float(estimate.median()), **metric_dict(reference, estimate), **acceptance_dict(reference, estimate, len(zone_all))})
    method_by_zone = pd.DataFrame(zone_rows)
    METHOD_SUMMARY_CSV = OUTPUT_DIR / 'method_comparison_summary.csv'
    METHOD_PER_SECOND_CSV = OUTPUT_DIR / 'method_comparison_per_second.csv'
    METHOD_BY_ZONE_CSV = OUTPUT_DIR / 'method_comparison_by_zone.csv'
    METHOD_PLOT = OUTPUT_DIR / 'method_comparison_diagnostic.png'
    atomic_csv(method_summary, METHOD_SUMMARY_CSV)
    atomic_csv(comparison_per_second, METHOD_PER_SECOND_CSV)
    atomic_csv(method_by_zone, METHOD_BY_ZONE_CSV)
    fig, axes = plt.subplots(3, 1, figsize=(14, 16), constrained_layout=True)
    axes[0].plot(comparison_per_second['video_time_s'], comparison_per_second['reference_distance_nominal_m'], color='black', linewidth=2.2, label='Referência')
    axes[0].plot(comparison_per_second['video_time_s'], comparison_per_second['raw_s00_p25_m'], alpha=0.85, label='Depth bruto')
    axes[0].plot(comparison_per_second['video_time_s'], comparison_per_second['estimated_distance_m'], alpha=0.85, label='Depth calibrado')
    axes[0].set(title='Distância por segundo', xlabel='Tempo no vídeo (s)', ylabel='Distância (m)')
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    scatter_reference = valid_comparison['reference_distance_nominal_m']
    axes[1].scatter(scatter_reference, valid_comparison['raw_s00_p25_m'], s=8, alpha=0.22, label='Bruto')
    axes[1].scatter(scatter_reference, valid_comparison['estimated_distance_m'], s=8, alpha=0.22, label='Calibrado')
    diagonal_max = float(np.nanmax([scatter_reference.max(), valid_comparison['raw_s00_p25_m'].max(), valid_comparison['estimated_distance_m'].max()]))
    axes[1].plot([0, diagonal_max], [0, diagonal_max], 'k--', linewidth=1.5, label='Ideal')
    axes[1].set(title='Estimativa versus referência', xlabel='Referência (m)', ylabel='Estimativa (m)')
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    zone_order = [zone for zone in ['critical_0_20m', 'attention_20_40m', 'distant_40_80m'] if zone in set(method_by_zone['distance_zone'])]
    x = np.arange(len(zone_order))
    width = 0.36
    for index, (method, _) in enumerate(method_columns.items()):
        values = method_by_zone.loc[method_by_zone['method'] == method].set_index('distance_zone').reindex(zone_order)['mae_m']
        axes[2].bar(x + (index - 0.5) * width, values, width, label=method)
    axes[2].set_xticks(x, zone_order)
    axes[2].set(title='MAE por faixa de distância', xlabel='Faixa', ylabel='MAE (m)')
    axes[2].grid(axis='y', alpha=0.25)
    axes[2].legend()
    fig.savefig(METHOD_PLOT, dpi=180, bbox_inches='tight')
    plt.show()
    print('Resumo bruto versus calibrado:')
    display(method_summary.round(3))
    print('Comparação por zona:')
    display(method_by_zone.round(3))
    print('Arquivos salvos em:', OUTPUT_DIR)
else:
    print('Comparação de métodos bloqueada junto com as métricas.')

if RUN_TEMPORAL_METRICS:
    if 'valid_comparison' not in globals() or 'comparison_per_second' not in globals():
        raise RuntimeError('Execute primeiro as seções 8 e 8.1.')
    AUTO_FOCAL_MEDIAN_PX = 2985.761
    focal_grid = np.linspace(800.0, 12000.0, 225)
    second_reference = comparison_per_second['reference_distance_nominal_m'].to_numpy(float)
    second_raw = comparison_per_second['raw_s00_p25_m'].to_numpy(float)
    focal_rows = []
    for focal_px in focal_grid:
        estimate = second_raw * (focal_px / FIXED_FOCAL_PX)
        scores = metric_dict(second_reference, estimate)
        focal_rows.append({'focal_px': float(focal_px), **scores, **acceptance_dict(second_reference, estimate)})
    focal_sensitivity = pd.DataFrame(focal_rows)
    best_mae_row = focal_sensitivity.loc[focal_sensitivity['mae_m'].idxmin()]
    best_rmse_row = focal_sensitivity.loc[focal_sensitivity['rmse_m'].idxmin()]
    BEST_MAE_FOCAL_DIAGNOSTIC_PX = float(best_mae_row['focal_px'])
    BEST_RMSE_FOCAL_DIAGNOSTIC_PX = float(best_rmse_row['focal_px'])
    focal_candidates = {'Focal fixa original — 1440 px': FIXED_FOCAL_PX, 'Focal automática mediana — 2985,761 px': AUTO_FOCAL_MEDIAN_PX, 'Melhor focal por MAE — diagnóstico interno': BEST_MAE_FOCAL_DIAGNOSTIC_PX, 'Melhor focal por RMSE — diagnóstico interno': BEST_RMSE_FOCAL_DIAGNOSTIC_PX}
    focal_candidate_rows = []
    for method, focal_px in focal_candidates.items():
        estimate = second_raw * (focal_px / FIXED_FOCAL_PX)
        focal_candidate_rows.append({'method': method, 'focal_px': float(focal_px), 'mean_estimate_m': float(np.mean(estimate)), 'median_estimate_m': float(np.median(estimate)), **metric_dict(second_reference, estimate), **acceptance_dict(second_reference, estimate)})
    old_calibrated_second = comparison_per_second['estimated_distance_m'].to_numpy(float)
    focal_candidate_rows.append({'method': 'Calibração log-linear antiga', 'focal_px': np.nan, 'mean_estimate_m': float(np.mean(old_calibrated_second)), 'median_estimate_m': float(np.median(old_calibrated_second)), **metric_dict(second_reference, old_calibrated_second), **acceptance_dict(second_reference, old_calibrated_second)})
    focal_candidate_summary = pd.DataFrame(focal_candidate_rows)
    required_focal = valid_comparison.loc[np.isfinite(valid_comparison['raw_s00_p25_m']) & (valid_comparison['raw_s00_p25_m'] > 0)].copy()
    required_focal['required_focal_px'] = FIXED_FOCAL_PX * required_focal['reference_distance_nominal_m'] / required_focal['raw_s00_p25_m']
    required_focal_by_zone = required_focal.groupby('distance_zone', as_index=False).agg(n=('required_focal_px', 'size'), reference_mean_m=('reference_distance_nominal_m', 'mean'), required_focal_p25_px=('required_focal_px', lambda values: float(np.percentile(values, 25))), required_focal_median_px=('required_focal_px', 'median'), required_focal_p75_px=('required_focal_px', lambda values: float(np.percentile(values, 75))))
    required_focal_spearman = float(required_focal['reference_distance_nominal_m'].corr(required_focal['required_focal_px'], method='spearman'))
    FOCAL_SENSITIVITY_CSV = OUTPUT_DIR / 'focal_sensitivity_per_second.csv'
    FOCAL_CANDIDATES_CSV = OUTPUT_DIR / 'focal_candidate_summary.csv'
    REQUIRED_FOCAL_BY_ZONE_CSV = OUTPUT_DIR / 'required_focal_by_zone.csv'
    FOCAL_DIAGNOSTIC_PLOT = OUTPUT_DIR / 'focal_sensitivity_diagnostic.png'
    atomic_csv(focal_sensitivity, FOCAL_SENSITIVITY_CSV)
    atomic_csv(focal_candidate_summary, FOCAL_CANDIDATES_CSV)
    atomic_csv(required_focal_by_zone, REQUIRED_FOCAL_BY_ZONE_CSV)
    fig, axes = plt.subplots(3, 1, figsize=(14, 17), constrained_layout=True)
    axes[0].plot(focal_sensitivity['focal_px'], focal_sensitivity['mae_m'], label='MAE')
    axes[0].plot(focal_sensitivity['focal_px'], focal_sensitivity['rmse_m'], label='RMSE')
    axes[0].axvline(FIXED_FOCAL_PX, color='tab:blue', linestyle='--', label='Fixa 1440 px')
    axes[0].axvline(AUTO_FOCAL_MEDIAN_PX, color='tab:green', linestyle='--', label='Auto mediana 2985,761 px')
    axes[0].axvline(BEST_MAE_FOCAL_DIAGNOSTIC_PX, color='tab:red', linestyle=':', label='Mínimo MAE interno')
    axes[0].set(title='Sensibilidade do erro à focal — resumo por segundo', xlabel='Focal (px)', ylabel='Erro (m)')
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    axes[1].plot(comparison_per_second['video_time_s'], second_reference, color='black', linewidth=2.2, label='Referência')
    axes[1].plot(comparison_per_second['video_time_s'], second_raw, alpha=0.75, label='Fixa 1440 px')
    axes[1].plot(comparison_per_second['video_time_s'], second_raw * (AUTO_FOCAL_MEDIAN_PX / FIXED_FOCAL_PX), alpha=0.8, label='Auto mediana')
    axes[1].plot(comparison_per_second['video_time_s'], second_raw * (BEST_MAE_FOCAL_DIAGNOSTIC_PX / FIXED_FOCAL_PX), alpha=0.8, label='Melhor MAE interno')
    axes[1].plot(comparison_per_second['video_time_s'], old_calibrated_second, alpha=0.75, label='Calibração antiga')
    axes[1].set(title='Efeito da focal na série temporal', xlabel='Tempo no vídeo (s)', ylabel='Distância (m)')
    axes[1].grid(alpha=0.25)
    axes[1].legend(ncol=2)
    axes[2].scatter(required_focal['reference_distance_nominal_m'], required_focal['required_focal_px'], s=8, alpha=0.2)
    axes[2].axhline(AUTO_FOCAL_MEDIAN_PX, color='tab:green', linestyle='--', label='Auto mediana')
    axes[2].set(title=f'Focal exigida por quadro (Spearman com distância = {required_focal_spearman:.3f})', xlabel='Referência (m)', ylabel='Focal necessária (px)')
    axes[2].grid(alpha=0.25)
    axes[2].legend()
    fig.savefig(FOCAL_DIAGNOSTIC_PLOT, dpi=180, bbox_inches='tight')
    plt.show()
    print('Comparação das focais candidatas — valores otimizados são apenas diagnósticos internos:')
    display(focal_candidate_summary.round(3))
    print('Focal necessária por faixa:')
    display(required_focal_by_zone.round(3))
    print(f'Spearman entre referência e focal necessária: {required_focal_spearman:.3f}')
    print('Arquivos salvos em:', OUTPUT_DIR)
else:
    print('Diagnóstico de focal bloqueado junto com as métricas.')

if RUN_FULL_BOX_CALIBRATION_CV:
    if not len(depth_frames):
        raise RuntimeError('Carregue depth_all_frames.csv antes da seção 8.6.')
    full_box = depth_frames.copy()
    required_columns = ['frame_idx', 'video_time_s', 'reference_distance_nominal_m', 'confidence', 'x1', 'y1', 'x2', 'y2', 'raw_s00_p25_m']
    missing = [column for column in required_columns if column not in full_box.columns]
    if missing:
        raise KeyError(f'Colunas ausentes para a validação integral: {missing}')
    for column in required_columns:
        full_box[column] = pd.to_numeric(full_box[column], errors='coerce')
    full_box['box_width_px'] = full_box['x2'] - full_box['x1']
    full_box['box_height_px'] = full_box['y2'] - full_box['y1']
    full_box['box_area_px2'] = full_box['box_width_px'] * full_box['box_height_px']
    full_box['box_aspect_ratio'] = full_box['box_width_px'] / full_box['box_height_px']
    full_box['second'] = np.floor(full_box['video_time_s']).astype('Int64')
    labeled_frame = np.isfinite(full_box['reference_distance_nominal_m'])
    reliable_box = labeled_frame & np.isfinite(full_box['confidence']) & (full_box['confidence'] >= YOLO_RELIABLE_CONF) & np.isfinite(full_box[['box_width_px', 'box_height_px', 'box_area_px2']]).all(axis=1) & (full_box['box_width_px'] >= MIN_BOX_WIDTH_PX) & (full_box['box_height_px'] >= MIN_BOX_HEIGHT_PX) & (full_box['box_area_px2'] > 0)
    reliable = full_box.loc[reliable_box].copy()
    total_labeled_seconds = int(full_box.loc[labeled_frame, 'second'].nunique())
    second_data = reliable.groupby('second', as_index=False).agg(video_time_s=('video_time_s', 'median'), reference_distance_nominal_m=('reference_distance_nominal_m', 'median'), box_width_px=('box_width_px', 'median'), box_height_px=('box_height_px', 'median'), box_area_px2=('box_area_px2', 'median'), box_aspect_ratio=('box_aspect_ratio', 'median'), confidence=('confidence', 'median'), raw_s00_p25_m=('raw_s00_p25_m', 'median'), reliable_frames=('frame_idx', 'size'))
    second_data['distance_zone'] = second_data['reference_distance_nominal_m'].map(distance_zone)
    second_data['time_block_20s'] = np.floor(second_data['video_time_s'] / 20).astype(int)
    feature_columns = ['box_width_px', 'box_height_px', 'box_area_px2', 'box_aspect_ratio', 'confidence', 'raw_s00_p25_m']
    valid_seconds = np.ones(len(second_data), dtype=bool)
    for column in feature_columns + ['reference_distance_nominal_m']:
        valid_seconds &= np.isfinite(second_data[column]) & (second_data[column] > 0)
    second_data = second_data.loc[valid_seconds].copy().reset_index(drop=True)
    if len(second_data) < 20 or second_data['time_block_20s'].nunique() < 3:
        raise RuntimeError('Segundos válidos insuficientes para validação temporal integral.')
    model_specs = {'box_width_log': {'features': ['box_width_px']}, 'box_height_log': {'features': ['box_height_px']}, 'box_area_log': {'features': ['box_area_px2']}, 'box_width_height_log': {'features': ['box_width_px', 'box_height_px']}, 'box_area_aspect_log': {'features': ['box_area_px2', 'box_aspect_ratio']}, 'depth_p25_log': {'features': ['raw_s00_p25_m']}, 'box_area_depth_log': {'features': ['box_area_px2', 'raw_s00_p25_m']}, 'geometry_area_power_-0.5': {'features': ['box_area_px2'], 'fixed_slopes': [-0.5]}}

    def fit_full_log_model(train, specification, alpha=1.0):
        features = specification['features']
        x_log = np.log(np.maximum(train[features].to_numpy(float), 1e-09))
        y_log = np.log(np.maximum(train['reference_distance_nominal_m'].to_numpy(float), 1e-09))
        if 'fixed_slopes' in specification:
            slopes = np.asarray(specification['fixed_slopes'], float)
            intercept = float(np.mean(y_log - x_log @ slopes))
            return {'kind': 'fixed', 'intercept': intercept, 'slopes': slopes}
        center = x_log.mean(axis=0)
        scale = x_log.std(axis=0, ddof=0)
        scale[~np.isfinite(scale) | (scale < 1e-09)] = 1.0
        z = (x_log - center) / scale
        design = np.column_stack([np.ones(len(z)), z])
        penalty = np.eye(design.shape[1])
        penalty[0, 0] = 0.0
        beta = np.linalg.pinv(design.T @ design + alpha * penalty) @ (design.T @ y_log)
        return {'kind': 'ridge', 'center': center, 'scale': scale, 'beta': beta}

    def predict_full_log_model(data, specification, fitted):
        features = specification['features']
        x_log = np.log(np.maximum(data[features].to_numpy(float), 1e-09))
        if fitted['kind'] == 'fixed':
            prediction_log = fitted['intercept'] + x_log @ fitted['slopes']
        else:
            z = (x_log - fitted['center']) / fitted['scale']
            prediction_log = np.column_stack([np.ones(len(z)), z]) @ fitted['beta']
        return np.exp(np.clip(prediction_log, -20, 20))
    groups = sorted(second_data['time_block_20s'].unique())
    prediction_rows = []
    for model_name, specification in model_specs.items():
        oof = np.full(len(second_data), np.nan)
        for held_out in groups:
            train_mask = second_data['time_block_20s'] != held_out
            test_mask = ~train_mask
            if train_mask.sum() <= len(specification['features']) + 2:
                continue
            fitted = fit_full_log_model(second_data.loc[train_mask], specification)
            oof[test_mask] = predict_full_log_model(second_data.loc[test_mask], specification, fitted)
        for index, prediction in enumerate(oof):
            prediction_rows.append({'second': int(second_data.loc[index, 'second']), 'video_time_s': float(second_data.loc[index, 'video_time_s']), 'time_block_20s': int(second_data.loc[index, 'time_block_20s']), 'distance_zone': second_data.loc[index, 'distance_zone'], 'reference_distance_nominal_m': float(second_data.loc[index, 'reference_distance_nominal_m']), 'reliable_frames': int(second_data.loc[index, 'reliable_frames']), 'model': model_name, 'oof_estimate_m': float(prediction)})
    full_cv_predictions = pd.DataFrame(prediction_rows)
    summary_rows = []
    second_coverage = float(len(second_data) / max(1, total_labeled_seconds) * 100)
    frame_coverage = float(reliable_box.sum() / max(1, labeled_frame.sum()) * 100)
    for model_name, part in full_cv_predictions.groupby('model', sort=False):
        summary_rows.append({'model': model_name, 'validation': 'leave_one_20s_block_out', 'features': ', '.join(model_specs[model_name]['features']), 'seconds': int(len(part)), 'second_coverage_pct': second_coverage, 'reliable_frame_coverage_pct': frame_coverage, **metric_dict(part['reference_distance_nominal_m'], part['oof_estimate_m']), **acceptance_dict(part['reference_distance_nominal_m'], part['oof_estimate_m'])})
    full_cv_summary = pd.DataFrame(summary_rows).sort_values(['rmse_m', 'mae_m'])
    zone_rows = []
    for (model_name, zone), part in full_cv_predictions.groupby(['model', 'distance_zone']):
        zone_rows.append({'model': model_name, 'distance_zone': zone, 'seconds': int(len(part)), **metric_dict(part['reference_distance_nominal_m'], part['oof_estimate_m']), **acceptance_dict(part['reference_distance_nominal_m'], part['oof_estimate_m'])})
    full_cv_zones = pd.DataFrame(zone_rows)
    coefficient_rows = []
    for model_name, specification in model_specs.items():
        fitted = fit_full_log_model(second_data, specification)
        if fitted['kind'] == 'fixed':
            coefficient_rows.append({'model': model_name, 'term': 'intercept_log_m', 'coefficient': fitted['intercept']})
            for feature, coefficient in zip(specification['features'], fitted['slopes']):
                coefficient_rows.append({'model': model_name, 'term': feature, 'coefficient': float(coefficient)})
        else:
            beta = fitted['beta']
            slopes_original = beta[1:] / fitted['scale']
            intercept_original = beta[0] - np.sum(slopes_original * fitted['center'])
            coefficient_rows.append({'model': model_name, 'term': 'intercept_log_m', 'coefficient': float(intercept_original)})
            for feature, coefficient in zip(specification['features'], slopes_original):
                coefficient_rows.append({'model': model_name, 'term': feature, 'coefficient': float(coefficient)})
    full_cv_coefficients = pd.DataFrame(coefficient_rows)
    FULL_BOX_SECOND_CSV = OUTPUT_DIR / 'box_distance_per_second_inputs.csv'
    FULL_BOX_PREDICTIONS_CSV = OUTPUT_DIR / 'box_distance_blocked_cv_predictions.csv'
    FULL_BOX_SUMMARY_CSV = OUTPUT_DIR / 'box_distance_blocked_cv_summary.csv'
    FULL_BOX_ZONES_CSV = OUTPUT_DIR / 'box_distance_blocked_cv_zones.csv'
    FULL_BOX_COEFFICIENTS_CSV = OUTPUT_DIR / 'box_distance_provisional_coefficients.csv'
    FULL_BOX_PLOT = OUTPUT_DIR / 'box_distance_blocked_cv.png'
    atomic_csv(second_data, FULL_BOX_SECOND_CSV)
    atomic_csv(full_cv_predictions, FULL_BOX_PREDICTIONS_CSV)
    atomic_csv(full_cv_summary, FULL_BOX_SUMMARY_CSV)
    atomic_csv(full_cv_zones, FULL_BOX_ZONES_CSV)
    atomic_csv(full_cv_coefficients, FULL_BOX_COEFFICIENTS_CSV)
    best_model = str(full_cv_summary.iloc[0]['model'])
    best_predictions = full_cv_predictions.loc[full_cv_predictions['model'] == best_model].sort_values('video_time_s')
    best_zones = full_cv_zones.loc[full_cv_zones['model'] == best_model]
    fig, axes = plt.subplots(3, 1, figsize=(14, 16), constrained_layout=True)
    axes[0].bar(full_cv_summary['model'], full_cv_summary['mae_m'], label='MAE')
    axes[0].scatter(full_cv_summary['model'], full_cv_summary['rmse_m'], color='tab:red', label='RMSE', zorder=3)
    axes[0].set(title='Sequência completa: erro por segundo fora da amostra', ylabel='Erro (m)')
    axes[0].tick_params(axis='x', rotation=30)
    axes[0].grid(axis='y', alpha=0.25)
    axes[0].legend()
    reference = best_predictions['reference_distance_nominal_m']
    estimate = best_predictions['oof_estimate_m']
    axis_max = float(max(reference.max(), estimate.max()))
    axes[1].scatter(reference, estimate, c=best_predictions['video_time_s'], cmap='viridis', s=40)
    axes[1].plot([0, axis_max], [0, axis_max], 'k--', label='Ideal')
    axes[1].set(title=f'Melhor RMSE integral: {best_model}', xlabel='Referência (m)', ylabel='Predição OOF (m)')
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    axes[2].plot(best_predictions['video_time_s'], reference, color='black', linewidth=2, label='Referência')
    axes[2].plot(best_predictions['video_time_s'], estimate, color='tab:blue', marker='o', markersize=3, label='Predição OOF')
    axes[2].set(title='Sequência integral agregada por segundo', xlabel='Tempo no vídeo (s)', ylabel='Distância (m)')
    axes[2].grid(alpha=0.25)
    axes[2].legend()
    fig.savefig(FULL_BOX_PLOT, dpi=180, bbox_inches='tight')
    plt.show()
    print(f'Segundos rotulados/válidos: {total_labeled_seconds}/{len(second_data)}')
    print(f'Cobertura de caixas confiáveis por quadro: {frame_coverage:.3f}%')
    print(f'Blocos temporais de 20 s: {len(groups)}')
    print(f'Melhor RMSE integral bloqueado: {best_model}')
    print('Coeficientes permanecem provisórios até validação em outro vídeo.')
    display(full_cv_summary.round(3))
    display(best_zones.round(3))
    print('Arquivos salvos em:', OUTPUT_DIR)
else:
    print('Validação integral pela caixa YOLO bloqueada.')

if RUN_BOX_ROBUSTNESS_AUDIT:
    SECOND_INPUT_CSV = OUTPUT_DIR / 'box_distance_per_second_inputs.csv'
    BLOCKED_PREDICTIONS_CSV = OUTPUT_DIR / 'box_distance_blocked_cv_predictions.csv'
    COEFFICIENTS_CSV = OUTPUT_DIR / 'box_distance_provisional_coefficients.csv'
    for required_path in [SECOND_INPUT_CSV, BLOCKED_PREDICTIONS_CSV, COEFFICIENTS_CSV]:
        if not required_path.exists():
            raise FileNotFoundError(f'Arquivo ausente: {required_path}. Execute primeiro a seção 8.6.')
    audit_frames = depth_frames.copy()
    numeric = ['frame_idx', 'video_time_s', 'reference_distance_nominal_m', 'confidence', 'x1', 'y1', 'x2', 'y2']
    for column in numeric:
        audit_frames[column] = pd.to_numeric(audit_frames[column], errors='coerce')
    audit_frames['box_width_px'] = audit_frames['x2'] - audit_frames['x1']
    audit_frames['box_height_px'] = audit_frames['y2'] - audit_frames['y1']
    audit_frames['second'] = np.floor(audit_frames['video_time_s']).astype('Int64')
    labeled = np.isfinite(audit_frames['reference_distance_nominal_m'])
    reliable = labeled & np.isfinite(audit_frames['confidence']) & (audit_frames['confidence'] >= YOLO_RELIABLE_CONF) & np.isfinite(audit_frames[['box_width_px', 'box_height_px']]).all(axis=1) & (audit_frames['box_width_px'] >= MIN_BOX_WIDTH_PX) & (audit_frames['box_height_px'] >= MIN_BOX_HEIGHT_PX)
    reliable_frames = audit_frames.loc[reliable].copy()

    def percentile_25(values):
        return float(np.percentile(values, 25))

    def percentile_75(values):
        return float(np.percentile(values, 75))

    def median_absolute_deviation(values):
        values = np.asarray(values, float)
        median = np.median(values)
        return float(np.median(np.abs(values - median)))
    second_quality = reliable_frames.groupby('second', as_index=False).agg(video_time_s=('video_time_s', 'median'), reference_distance_nominal_m=('reference_distance_nominal_m', 'median'), width_median_px=('box_width_px', 'median'), width_q25_px=('box_width_px', percentile_25), width_q75_px=('box_width_px', percentile_75), width_mad_px=('box_width_px', median_absolute_deviation), confidence_median=('confidence', 'median'), reliable_frames=('frame_idx', 'size'))
    second_quality['width_relative_iqr'] = (second_quality['width_q75_px'] - second_quality['width_q25_px']) / second_quality['width_median_px'].clip(lower=1e-09)
    second_quality['distance_zone'] = second_quality['reference_distance_nominal_m'].map(distance_zone)
    predictions = pd.read_csv(BLOCKED_PREDICTIONS_CSV)
    predictions = predictions.loc[predictions['model'] == 'box_width_log'].copy()
    predictions['second'] = pd.to_numeric(predictions['second'], errors='coerce').astype('Int64')
    audit = second_quality.merge(predictions[['second', 'time_block_20s', 'oof_estimate_m']], on='second', how='inner').sort_values('second').reset_index(drop=True)
    audit['absolute_error_m'] = np.abs(audit['oof_estimate_m'] - audit['reference_distance_nominal_m'])
    audit['signed_error_m'] = audit['oof_estimate_m'] - audit['reference_distance_nominal_m']
    log_width = np.log(audit['width_median_px'].clip(lower=1e-09).to_numpy(float))
    seconds_array = audit['second'].to_numpy(float)
    log_delta = np.full(len(audit), np.nan)
    consecutive = np.diff(seconds_array) == 1
    log_delta[1:][consecutive] = np.diff(log_width)[consecutive]
    temporal_outlier = np.zeros(len(audit), dtype=bool)
    temporal_score = np.full(len(audit), np.nan)
    history_size = int(BOX_AUDIT_HAMPEL_HISTORY_SECONDS)
    for index in range(len(audit)):
        if not np.isfinite(log_delta[index]):
            continue
        current_second = int(audit.loc[index, 'second'])
        history_mask = (seconds_array < current_second) & (seconds_array >= current_second - history_size) & np.isfinite(log_delta)
        history = log_delta[history_mask]
        if len(history) < 3:
            continue
        center = float(np.median(history))
        mad = float(np.median(np.abs(history - center)))
        robust_scale = 1.4826 * mad
        residual = abs(log_delta[index] - center)
        threshold = max(BOX_AUDIT_HAMPEL_K * robust_scale, float(BOX_AUDIT_MAX_LOG_WIDTH_JUMP))
        temporal_score[index] = residual / max(robust_scale, 1e-09)
        temporal_outlier[index] = residual > threshold
    audit['log_width_change'] = log_delta
    audit['temporal_hampel_score'] = temporal_score
    audit['temporal_width_outlier'] = temporal_outlier
    audit['low_support'] = audit['reliable_frames'] < BOX_AUDIT_MIN_FRAMES_PER_SECOND
    audit['unstable_within_second'] = audit['width_relative_iqr'] > BOX_AUDIT_MAX_RELATIVE_IQR
    audit['quality_abstained'] = audit['low_support'] | audit['unstable_within_second'] | audit['temporal_width_outlier']

    def quality_reason(row):
        reasons = []
        if bool(row['low_support']):
            reasons.append('few_reliable_frames')
        if bool(row['unstable_within_second']):
            reasons.append('unstable_width_iqr')
        if bool(row['temporal_width_outlier']):
            reasons.append('causal_hampel_outlier')
        return ';'.join(reasons)
    audit['quality_reason'] = audit.apply(quality_reason, axis=1)
    total_labeled_seconds = int(audit_frames.loc[labeled, 'second'].nunique())
    emitted_quality = audit.loc[~audit['quality_abstained']].copy()
    comparison_rows = []
    for label, part in [('box_width_log_oof_primary', audit), ('box_width_log_oof_quality_gated', emitted_quality)]:
        comparison_rows.append({'variant': label, 'seconds_emitted': int(len(part)), 'coverage_all_labeled_seconds_pct': float(len(part) / max(1, total_labeled_seconds) * 100), 'coverage_box_valid_seconds_pct': float(len(part) / max(1, len(audit)) * 100), **metric_dict(part['reference_distance_nominal_m'], part['oof_estimate_m']), **acceptance_dict(part['reference_distance_nominal_m'], part['oof_estimate_m'])})
    quality_comparison = pd.DataFrame(comparison_rows)
    block_rows = []
    for block, block_all in audit.groupby('time_block_20s'):
        for label, part in [('primary', block_all), ('quality_gated', block_all.loc[~block_all['quality_abstained']])]:
            block_rows.append({'time_block_20s': int(block), 'variant': label, 'seconds_available': int(len(block_all)), 'seconds_emitted': int(len(part)), **metric_dict(part['reference_distance_nominal_m'], part['oof_estimate_m'])})
    block_metrics = pd.DataFrame(block_rows)
    coefficients = pd.read_csv(COEFFICIENTS_CSV)
    width_coefficients = coefficients.loc[coefficients['model'] == 'box_width_log'].copy()
    intercept = float(width_coefficients.loc[width_coefficients['term'] == 'intercept_log_m', 'coefficient'].iloc[0])
    exponent = float(width_coefficients.loc[width_coefficients['term'] == 'box_width_px', 'coefficient'].iloc[0])
    constant = float(np.exp(intercept))
    model_specification = {'status': 'provisional_internal_validation_only', 'model': 'box_width_log', 'equation': 'distance_m = constant * median_box_width_px ** exponent', 'constant': constant, 'exponent': exponent, 'intercept_log_m': intercept, 'input_resolution_px': [int(WIDTH), int(HEIGHT)], 'aggregation': 'median width of reliable YOLO boxes per second', 'yolo_reliable_confidence': float(YOLO_RELIABLE_CONF), 'minimum_box_width_px': float(MIN_BOX_WIDTH_PX), 'minimum_box_height_px': float(MIN_BOX_HEIGHT_PX), 'quality_gate': {'minimum_reliable_frames_per_second': int(BOX_AUDIT_MIN_FRAMES_PER_SECOND), 'maximum_relative_width_iqr': float(BOX_AUDIT_MAX_RELATIVE_IQR), 'causal_hampel_history_seconds': int(BOX_AUDIT_HAMPEL_HISTORY_SECONDS), 'causal_hampel_k': float(BOX_AUDIT_HAMPEL_K), 'minimum_log_width_jump': float(BOX_AUDIT_MAX_LOG_WIDTH_JUMP)}, 'limitations': ['single flight internal temporal validation', 'fixed zoom required', 'same drone appearance required', 'only two valid seconds above 40 m']}
    AUDIT_CSV = OUTPUT_DIR / 'box_width_robustness_audit.csv'
    QUALITY_COMPARISON_CSV = OUTPUT_DIR / 'box_width_quality_comparison.csv'
    BLOCK_METRICS_CSV = OUTPUT_DIR / 'box_width_block_metrics.csv'
    MODEL_JSON = OUTPUT_DIR / 'box_width_model_provisional.json'
    AUDIT_PLOT = OUTPUT_DIR / 'box_width_robustness_audit.png'
    atomic_csv(audit, AUDIT_CSV)
    atomic_csv(quality_comparison, QUALITY_COMPARISON_CSV)
    atomic_csv(block_metrics, BLOCK_METRICS_CSV)
    with MODEL_JSON.open('w', encoding='utf-8') as handle:
        json.dump(model_specification, handle, indent=2, ensure_ascii=False)
    top_errors = audit.sort_values('absolute_error_m', ascending=False).head(12)
    fig, axes = plt.subplots(3, 1, figsize=(14, 16), constrained_layout=True)
    axes[0].plot(audit['video_time_s'], audit['reference_distance_nominal_m'], color='black', linewidth=2, label='Referência')
    axes[0].plot(audit['video_time_s'], audit['oof_estimate_m'], color='tab:blue', marker='o', markersize=3, label='Predição OOF')
    rejected = audit.loc[audit['quality_abstained']]
    axes[0].scatter(rejected['video_time_s'], rejected['oof_estimate_m'], color='tab:red', marker='x', s=80, label='Abstenção proposta', zorder=5)
    axes[0].set(title='Auditoria temporal e abstenções propostas', xlabel='Tempo no vídeo (s)', ylabel='Distância (m)')
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    axes[1].scatter(audit['width_relative_iqr'], audit['absolute_error_m'], c=audit['reliable_frames'], cmap='viridis', s=45)
    axes[1].axvline(BOX_AUDIT_MAX_RELATIVE_IQR, color='tab:red', linestyle='--', label='Limite IQR relativo')
    axes[1].set(title='Dispersão da largura versus erro', xlabel='IQR da largura / mediana', ylabel='Erro absoluto (m)')
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    axes[2].bar(quality_comparison['variant'], quality_comparison['mae_m'], label='MAE')
    axes[2].scatter(quality_comparison['variant'], quality_comparison['rmse_m'], color='tab:red', label='RMSE', zorder=3)
    for index, row in quality_comparison.reset_index(drop=True).iterrows():
        axes[2].text(index, row['mae_m'] + 0.15, f"cobertura={row['coverage_all_labeled_seconds_pct']:.1f}%", ha='center', fontsize=9)
    axes[2].set(title='Erro e cobertura antes/depois do controle de qualidade', ylabel='Erro (m)')
    axes[2].tick_params(axis='x', rotation=15)
    axes[2].grid(axis='y', alpha=0.25)
    axes[2].legend()
    fig.savefig(AUDIT_PLOT, dpi=180, bbox_inches='tight')
    plt.show()
    print(f'Equação provisória: distância_m = {constant:.8g} × largura_px ^ ({exponent:.6f})')
    print(f"Segundos rejeitados pela regra operacional: {int(audit['quality_abstained'].sum())}/{len(audit)}")
    print('Resultado científico primário continua sendo a versão OOF sem filtro.')
    display(quality_comparison.round(3))
    print('Maiores erros para auditoria:')
    display(top_errors[['second', 'video_time_s', 'reference_distance_nominal_m', 'oof_estimate_m', 'absolute_error_m', 'reliable_frames', 'width_median_px', 'width_relative_iqr', 'temporal_hampel_score', 'quality_reason']].round(3))
    print('Métricas por bloco:')
    display(block_metrics.round(3))
    print('Arquivos salvos em:', OUTPUT_DIR)
else:
    print('Auditoria de robustez do modelo de largura bloqueada.')

if RUN_FINAL_REPORT:
    required_files = {'depth_summary': OUTPUT_DIR / 'method_comparison_summary.csv', 'depth_second': OUTPUT_DIR / 'method_comparison_per_second.csv', 'box_predictions': OUTPUT_DIR / 'box_distance_blocked_cv_predictions.csv', 'quality': OUTPUT_DIR / 'box_width_quality_comparison.csv', 'audit': OUTPUT_DIR / 'box_width_robustness_audit.csv', 'model': OUTPUT_DIR / 'box_width_model_provisional.json'}
    missing = [str(file) for file in required_files.values() if not file.exists()]
    if missing:
        raise FileNotFoundError('Arquivos ausentes; execute as seções 8.1, 8.6 e 8.7:\n' + '\n'.join(missing))
    depth_summary = pd.read_csv(required_files['depth_summary'])
    depth_second = pd.read_csv(required_files['depth_second'])
    box_predictions = pd.read_csv(required_files['box_predictions'])
    quality_summary = pd.read_csv(required_files['quality'])
    robustness_audit = pd.read_csv(required_files['audit'])
    with required_files['model'].open('r', encoding='utf-8') as handle:
        selected_model = json.load(handle)
    with METRICS_JSON.open('r', encoding='utf-8') as handle:
        temporal_metrics_saved = json.load(handle)
    final_rows = []
    labeled_seconds = max(1, int(math.ceil(float(temporal_metrics_saved['telemetry_labeled_frames']) / NATIVE_FPS)))
    depth_second_coverage_pct = 100.0 * depth_second['second'].nunique() / labeled_seconds
    depth_per_second = depth_summary.loc[depth_summary['level'] == 'per_second_primary']
    for _, row in depth_per_second.iterrows():
        final_rows.append({'method': row['method'], 'role': 'baseline_comparator', 'evaluation': 'full_sequence_per_second_descriptive', 'coverage_pct': float(depth_second_coverage_pct), 'n_seconds': int(row['n']), 'mae_m': float(row['mae_m']), 'rmse_m': float(row['rmse_m']), 'median_ae_m': float(row['median_ae_m']), 'mape_pct': float(row['mape_pct']), 'bias_m': float(row['bias_m']), 'r2': float(row['r2']), 'spearman': float(row['spearman']), 'within_1m_pct': float(row['within_1m_pct_emitted']), 'within_20pct_pct': float(row['within_20pct_pct_emitted']), 'legacy_5m_or_20pct_pct': float(row['legacy_5m_or_20pct_pct_emitted'])})
    for _, row in quality_summary.iterrows():
        is_gated = row['variant'] == 'box_width_log_oof_quality_gated'
        final_rows.append({'method': 'Largura YOLO — OOF com abstenção' if is_gated else 'Largura YOLO — OOF primário', 'role': 'operational_secondary' if is_gated else 'selected_primary', 'evaluation': 'leave_one_20s_block_out', 'coverage_pct': float(row['coverage_all_labeled_seconds_pct']), 'n_seconds': int(row['n']), 'mae_m': float(row['mae_m']), 'rmse_m': float(row['rmse_m']), 'median_ae_m': float(row['median_ae_m']), 'mape_pct': float(row['mape_pct']), 'bias_m': float(row['bias_m']), 'r2': float(row['r2']), 'spearman': float(row['spearman']), 'within_1m_pct': float(row['within_1m_pct_emitted']), 'within_20pct_pct': float(row['within_20pct_pct_emitted']), 'legacy_5m_or_20pct_pct': float(row['legacy_5m_or_20pct_pct_emitted'])})
    final_comparison = pd.DataFrame(final_rows)
    FINAL_COMPARISON_CSV = OUTPUT_DIR / 'final_method_comparison.csv'
    FINAL_PLOT = OUTPUT_DIR / 'final_method_comparison.png'
    atomic_csv(final_comparison, FINAL_COMPARISON_CSV)
    primary_box = final_comparison.loc[final_comparison['role'] == 'selected_primary'].iloc[0]
    gated_box = final_comparison.loc[final_comparison['role'] == 'operational_secondary'].iloc[0]
    summary_payload = {'created_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'scientific_primary': primary_box.to_dict(), 'operational_secondary': gated_box.to_dict(), 'provisional_equation': selected_model, 'interpretation': {'depth_pro': 'Evaluated comparator; insufficient metric performance in this sequence.', 'box_width': 'Selected estimator under internal temporally blocked validation.', 'external_validation': 'Not available; coefficients remain provisional.'}, 'limitations': selected_model.get('limitations', [])}
    with FINAL_SUMMARY_JSON.open('w', encoding='utf-8') as handle:
        json.dump(summary_payload, handle, indent=2, ensure_ascii=False, allow_nan=True)
    primary_predictions = box_predictions.loc[box_predictions['model'] == 'box_width_log'].sort_values('video_time_s')
    fig, axes = plt.subplots(3, 1, figsize=(14, 16), constrained_layout=True)
    axes[0].plot(depth_second['video_time_s'], depth_second['reference_distance_nominal_m'], color='black', linewidth=2.2, label='Referência')
    axes[0].plot(depth_second['video_time_s'], depth_second['estimated_distance_m'], color='tab:orange', alpha=0.8, label='Depth calibrado')
    axes[0].plot(primary_predictions['video_time_s'], primary_predictions['oof_estimate_m'], color='tab:blue', label='Largura YOLO — OOF')
    abstained_flag = robustness_audit['quality_abstained']
    if abstained_flag.dtype != bool:
        abstained_flag = abstained_flag.astype(str).str.strip().str.lower().isin({'true', '1', 'yes'})
    rejected = robustness_audit.loc[abstained_flag]
    axes[0].scatter(rejected['video_time_s'], rejected['oof_estimate_m'], color='tab:red', marker='x', s=75, label='Abstenção proposta')
    axes[0].set(title='Comparação temporal final', xlabel='Tempo no vídeo (s)', ylabel='Distância (m)')
    axes[0].grid(alpha=0.25)
    axes[0].legend()
    axes[1].bar(final_comparison['method'], final_comparison['mae_m'], label='MAE')
    axes[1].scatter(final_comparison['method'], final_comparison['rmse_m'], color='tab:red', label='RMSE', zorder=3)
    axes[1].set(title='Erro por método', ylabel='Erro (m)')
    axes[1].tick_params(axis='x', rotation=20)
    axes[1].grid(axis='y', alpha=0.25)
    axes[1].legend()
    axes[2].scatter(final_comparison['coverage_pct'], final_comparison['mae_m'], s=90)
    for _, row in final_comparison.iterrows():
        axes[2].annotate(row['method'], (row['coverage_pct'], row['mae_m']), xytext=(5, 5), textcoords='offset points', fontsize=9)
    axes[2].set(title='Cobertura versus MAE', xlabel='Cobertura (%)', ylabel='MAE (m)')
    axes[2].grid(alpha=0.25)
    fig.savefig(FINAL_PLOT, dpi=180, bbox_inches='tight')
    plt.show()
    equation = selected_model['equation']
    constant = selected_model['constant']
    exponent = selected_model['exponent']
    report_text = f"# Relatório final — estimação de distância do drone\n\n## Resultado selecionado\n\n- Método científico principal: largura da bounding box YOLO com validação OOF por blocos de 20 segundos.\n- Equação provisória de implantação: `distância_m = {constant:.8g} × largura_px ^ ({exponent:.6f})`.\n- MAE OOF primário: `{primary_box['mae_m']:.3f} m`.\n- RMSE OOF primário: `{primary_box['rmse_m']:.3f} m`.\n- R² OOF primário: `{primary_box['r2']:.3f}`.\n- Cobertura primária: `{primary_box['coverage_pct']:.3f}%`.\n\n## Variante operacional\n\n- MAE com controle de qualidade: `{gated_box['mae_m']:.3f} m`.\n- RMSE com controle de qualidade: `{gated_box['rmse_m']:.3f} m`.\n- R² com controle de qualidade: `{gated_box['r2']:.3f}`.\n- Cobertura com controle de qualidade: `{gated_box['coverage_pct']:.3f}%`.\n\n## Interpretação\n\nO Depth Pro foi preservado como comparador experimental, mas não manteve desempenho métrico suficiente. A largura da caixa YOLO apresentou o melhor resultado interno. A versão sem filtro constitui o resultado científico principal; a versão com abstenção é uma análise operacional secundária.\n\n## Limitações\n\n- Único voo e ausência de validação externa.\n- Necessidade de zoom fixo e resolução de 3840 × 2160.\n- Dependência da aparência e orientação do mesmo modelo de drone.\n- Apenas dois segundos válidos acima de 40 m.\n- Quadros adjacentes e telemetria interpolada não são observações independentes.\n- A equação ajustada em todos os dados serve para implantação provisória; seu desempenho é estimado pelas predições OOF.\n"
    FINAL_REPORT_MD.write_text(report_text, encoding='utf-8')
    print('Comparação consolidada:')
    display(final_comparison.round(3))
    print('Relatório:', FINAL_REPORT_MD)
    print('Resumo JSON:', FINAL_SUMMARY_JSON)
else:
    print('Consolidação final bloqueada.')

expected=pd.read_csv(a.source/'box_distance_blocked_cv_predictions.csv')
actual=pd.read_csv(OUTPUT_DIR/'box_distance_blocked_cv_predictions.csv')
joined=expected.merge(actual,on=['second','model'],validate='one_to_one',suffixes=('_original','_reproduzido'))
error=float(np.abs(joined.oof_estimate_m_original-joined.oof_estimate_m_reproduzido).max())
assert len(joined)==len(expected)==len(actual) and error<1e-8
report={'predicoes_comparadas':len(joined),'erro_maximo_absoluto_m':error,'reproducao_inferencia':False}
(OUTPUT_DIR/'verificacao.json').write_text(json.dumps(report,indent=2))
print(report)
