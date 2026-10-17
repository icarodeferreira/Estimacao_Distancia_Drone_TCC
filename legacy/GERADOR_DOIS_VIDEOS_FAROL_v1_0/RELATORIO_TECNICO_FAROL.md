# TCC Drone — Base para visualização do vídeo antigo do farol

## Identidade do experimento

- `video_final_farol_original.MOV`: gravação original, 6702 quadros e 223,46 s.
- `video_final_farol.mov`: vídeo **editado**, 3537 quadros e 117,90 s. **É este o arquivo associado aos arquivos quadro a quadro do pipeline.**
- Vínculo histórico da edição: início do recorte no original em 00:00:02:25 (2,833333 s), telemetria em 4,8 s no quadro inicial. Trata-se da **hipótese histórica do farol**, não da hipótese +10,5667 s do novo voo.
- Detecção histórica: resultados cacheados de YOLO na resolução 1920 de inferência, vídeo nativo 3840×2160, hipótese de câmera/zoom fixos. As caixas mantêm coordenadas nativas.

## Disponibilidade documental

| Série | Cobertura e status |
|---|---|
| Quadros com telemetria e R nominal histórico | 3537/3537, sem medição física independente |
| ROI selecionada em arquivo YOLO | 3502/3537 (não é taxa de acerto) |
| Profundidades Depth Pro **aceitas** | 3143/3537; 359 rejeições por baixa confiança e 35 sem detecção |
| Regressão OOF por segundo | 113 de 118 segundos |
| Variante com controle de qualidade OOF | 109 de 118 segundos |

**Resultados primários históricos:** regressão por largura com validação cruzada bloqueada (113 instantes), MAE `1,5744 m` e RMSE `2,3923 m` **somente contra referência nominal**. Variante filtrada (109 instantes), MAE `1,4241 m` e RMSE `1,8077 m`, com redução de cobertura. Não utilizar essas métricas como aferição absoluta da distância física; havia apenas dois segundos acima de 40 m e a aquisição usada para seleção de métodos foi a mesma.

## Compatibilidade métrica

A referência `reference_distance_nominal_m` dos arquivos de 3537 quadros foi calculada por uma geometria presumida (altura 1,5 m; separação horizontal câmera–HOME 1,5 m, azimute não determinado). Registros do projeto também indicam estimativa de aproximadamente 5 m de separação horizontal para o farol; essa divergência impede declarar a referência hipotética como verdade-terreno. A visualização preserva o cenário histórico e rotula percentuais como discrepâncias exploratórias.

Além disso, a saída principal Depth Pro bruto `raw_s00_p25_m` é **Z axial**, enquanto a referência histórica é **R radial**. O percentual `|Z-R|/R×100` é apresentado apenas sob o nome de diferença Z/R; não mede erro de alcance radial fisicamente comparável. A série histórica Depth calibrada é adicional e não representa teste externo independente.

## Garantias do renderizador

O arquivo `gerar_dois_videos_farol.py` só aceita vídeo com `3537` quadros, `3840×2160` e `30 FPS`, confere índice a índice e mantém as lacunas OOF e as abstenções Depth. Calcula, em separado, a diferença percentual da regressão contra referência **do quadro** e contra referência **do segundo OOF**. Gera CSV auditável e JSON com hashes. Não modifica nenhum arquivo fonte.

**Estado:** fontes integradas e verificadas, renderizador pronto para execução local com o MOV editado. MP4s completos ainda não renderizados, pois o MOV não está disponível no ambiente de execução atual.
