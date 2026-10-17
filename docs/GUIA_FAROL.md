> Documento de origem do pacote privado. Para os arquivos efetivamente publicados nesta branch e a validação atual, veja [STATUS_GITHUB.md](STATUS_GITHUB.md) e [VALIDACAO_GITHUB.md](VALIDACAO_GITHUB.md). Pesos, imagens, vídeos, capítulos e telemetria bruta não acompanham esta branch.

# Guia de reprodução do Farol da Ilha da Moela

## Reprodução analítica

Abra o notebook 01 ou execute `python scripts/reproduzir_farol.py`. A entrada é `results/archived/farol/depth_all_frames.csv`, acompanhada de `yolo_all_frames.csv`. O script é extraído das funções e etapas analíticas do notebook original, mantendo o protocolo. Saídas novas vão para `outputs/farol_reproduzido`, sem modificar os CSVs de origem.

O processamento seleciona caixas com confiança ≥0,25, largura ≥10 px e altura ≥5 px; calcula medianas por segundo e preserva o suporte comum dos oito modelos. As variáveis incluem largura, altura, área, razão de aspecto e percentil 25 de profundidade. Cada bloco de 20 segundos é excluído do ajuste que o prediz. Escalonamento logarítmico é ajustado apenas no treino; ridge α=1, sem penalizar intercepto. O modelo geométrico de área fixa expoente −0,5.

A auditoria de qualidade considera pelo menos cinco quadros confiáveis por segundo, IQR relativo da largura ≤0,35 e Hampel causal de cinco segundos, k=3, salto logarítmico mínimo 0,35. O resultado primário permanece OOF sem filtro; a filtragem é análise operacional com perda de cobertura.

Esperado: 113 segundos, oito modelos, 904 predições; erro máximo de comparação com o arquivo original menor que 1e-8 m. Veja `verificacao.json`, `final_method_comparison.csv`, `box_width_robustness_audit.csv` e figuras geradas. A transformação XR é exp(1,4600571394959514) × Z^0,5026751660343942, não uma correção universal.

## Reexecutar as redes

Use `03_Farol_inferencia_Colab.ipynb`. O vídeo recuperado tem SHA-256 `0cf939776f4a1410f3a6394f6b91b3daaf943ab40569991a7dd83865e157453b`, 3.537 quadros, 3840×2160 e duração nominal 117,9 s. Copie-o do suplemento para `inputs/video/farol.mov`. A telemetria está em `data/telemetry/farol_original.csv`; o detector em `models/best.pt`; obtenha Depth Pro pelo instalador.

A sincronização original do recorte usa 4,8 s na telemetria para t=0 no vídeo. A câmera tem altura nominal de 1,5 m e afastamento horizontal nominal de 1,5 m em relação ao ponto HOME. O ângulo horizontal é desconhecido; a referência nominal usa composição ortogonal, acompanhada de limites geométricos parciais. Esses valores são informações do protocolo, não medições certificadas.

O notebook inicia em piloto, com controles de inferência desligados. Siga a ordem descrita nele: auditoria, YOLO, Depth Pro, métricas, regressões e relatório. Primeiro ative apenas a etapa necessária. A inferência em GPU não foi executada nesta entrega; os CSVs arquivados foram recalculados em CPU.

## Vídeos

O gerador `legacy/GERADOR_DOIS_VIDEOS_FAROL_v1_0/gerar_dois_videos_farol.py` acompanha o guia original. Exemplo:

```bash
python legacy/GERADOR_DOIS_VIDEOS_FAROL_v1_0/gerar_dois_videos_farol.py --video inputs/video/farol.mov --saida outputs/videos_farol --teste-quadros 30
```

Remova `--teste-quadros 30` para o vídeo completo. Separe a apresentação científica OOF da demonstração com equação ajustada no conjunto inteiro. Não reporte o erro desta última como erro fora da amostra.
