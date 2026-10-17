# Guia para novos experimentos

1. Preserve o vídeo original e registre seu SHA-256. Trabalhe em cópia. Documente qualquer recorte, transcodificação, estabilização ou mudança de escala. Não substitua o tempo do arquivo por um FPS arbitrário.
2. Copie `configs/novo.json` e dê um `experiment_id` novo. Informe `video`, peso YOLO e, se usado, caminhos de Depth Pro. Execute `scripts/novo_experimento.py CONFIG --audit-only`. Veja resolução, rotação, PTS, duração, repetição e amostras em `outputs/ID/audit/`.
3. Preencha `field`: câmera, lente, zoom, drone, local/data, câmera fixa, zoom constante, iluminação, altura, posição, orientação, datum e incertezas disponíveis. Use null para desconhecido. Informe `measurement_resolution` e justifique limiares de caixa em pixels nessa resolução. Mude o identificador da execução após auditoria.
4. Configure `telemetry_columns` e `telemetry_units` (m ou ft). O leitor aceita BOM e linha `sep=,`, ordena tempos e mantém o último registro de tempos duplicados; a transformação é registrada. Em `geometry.mode=none`, a telemetria não é convertida em alcance. Para referência, escolha `nominal`, `angle` ou `enu`, com parâmetros efetivamente conhecidos.
5. Defina t_telemetria = a × t_vídeo + b. Um evento fornece offset com a=1; múltiplos eventos podem ajustar escala temporal. Dois eventos definem uma reta e não demonstram ausência de erro. Registre a incerteza e preserve cenários alternativos. A interpolação não extrapola e respeita `max_telemetry_gap_s`.
6. Instale dependências e Depth Pro; execute piloto de dez segundos e inspecione caixas, identificação da classe drone, fundo/oclusões e Z. O seletor escolhe a caixa drone de maior confiança e não garante identidade temporal do alvo.
7. Use outro ID para execução integral. Confira `predictions.csv`, `per_second.csv`, `metrics.json`, ambiente e hashes. O pipeline salva um CSV parcial durante processamento, mas não retoma automaticamente uma execução interrompida.

```bash
python scripts/novo_experimento.py configs/execucao.json --pilot-s 10
python scripts/novo_experimento.py configs/execucao_completa.json
python scripts/anotar_video.py inputs/video/novo.mov outputs/ID/tables/predictions.csv outputs/ID/video.mp4
```

## Geometria

Nominal: R_nom = sqrt(r² + b² + (h−h_c−desnível)²), com azimute desconhecido. Os limites sqrt((r−b)²+dz²) e sqrt((r+b)²+dz²) expressam apenas a incerteza geométrica horizontal, não toda a incerteza do sistema.

Angular: R = sqrt(r²+b²−2rb cos(phi)+dz²). phi é o ângulo horizontal entre os vetores pertinentes, não yaw/pitch substituído sem transformação.

ENU: informe câmera e drone no mesmo referencial métrico e use a norma da diferença. Confirme HOME fixo e datum vertical antes de calcular uma referência.

## Modelos e domínio

Depth Pro devolve profundidade axial Z. Focal fornecida deve estar em pixels e corresponder à resolução efetiva; null permite a estimativa interna. O campo `radial_extension` do núcleo de auditoria não implementa conversão automática. Nesta versão não há retificação/distorção nem conversão calibrada de Z em R.

A regressão fica desligada por padrão. Para transferência exploratória, informe `regression.frozen_model`, revise câmera/lente/zoom/resolução/aparência do drone e marque `domain_review=confirmed` somente após revisão documentada. O arquivo inclui faixa de largura; extrapolações são rejeitadas. O resultado continua provisório. O ajuste e a validação bloqueada novos exigem protocolo científico próprio; o script genérico não refaz automaticamente o treinamento da regressão nem promove o modelo Farol a um novo domínio.

Não use a altura do sensor como se fosse alcance câmera–drone. Sem referência adequada, publique disponibilidade, dispersão e saídas ausentes, sem alegar MAE/RMSE de alcance validado fisicamente.
