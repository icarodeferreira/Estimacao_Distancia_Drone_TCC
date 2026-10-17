> Documento de origem do pacote privado. Para os arquivos efetivamente publicados nesta branch e a validação atual, veja [STATUS_GITHUB.md](STATUS_GITHUB.md) e [VALIDACAO_GITHUB.md](VALIDACAO_GITHUB.md). Pesos, imagens, vídeos, capítulos e telemetria bruta não acompanham esta branch.

# Modelos e fontes externas

## YOLO

`models/best.pt` foi recuperado e coincide em SHA-256 com o melhor peso do arquivo de treinamento. SHA-256: `2ca8f89b9d946a6a06a12177db471cb7419b69b4a25ce619cc608c55267a61d8`. A configuração e curvas recuperadas estão em `results/archived/detector`. O registro do modelo identifica YOLO26n e Ultralytics 8.4.124. Classes: 0 airplane, 1 bird, 2 drone, 3 helicopter. Não reutilizar rótulos drone=0 sem remapeamento.

## Depth Pro

Código oficial: https://github.com/apple-aiml-research/ml-depth-pro

O instalador `scripts/instalar_depth_pro.py` usa esse repositório e o checkpoint indicado pelo projeto. Ele salva commit efetivo e hash do peso baixado. A revisão `main` é móvel: fixe o commit registrado para repetir a nova execução. O commit e o SHA-256 exatos do checkpoint usado nos resultados históricos não foram recuperados. Não alegar equivalência binária entre checkpoint atual e histórico sem essa comprovação.

## Calibração

`box_width_model_provisional.json` é o original. `largura_transferencia.json` acrescenta experimento de origem e intervalos observados de largura e referência. A equação usa a mediana da largura de caixas confiáveis por segundo em 3840×2160; não é uma lei física universal. A calibração XR e o protocolo de profundidade estão em `configs/farol.json` e `results/archived/farol/temporal_protocol.json`.

## Conjuntos públicos

- AOD 4: https://data.mendeley.com/datasets/cd5z895tr2/1 — obtenha os arquivos na página dos autores, registre versão, formato, classes e hashes. Referência: https://doi.org/10.1016/j.dib.2024.110801.
- Anti-UAV: https://github.com/ZhaoJ9014/Anti-UAV — siga as instruções da variante efetivamente usada. AOD 4 inclui fontes derivadas; isso não demonstra que todas as variantes Anti-UAV foram usadas diretamente neste treinamento.
- Os notebooks de treinamento originais e manifestos recuperados devem prevalecer para partições e transformações locais. Não substituir uma divisão local por uma versão pública mais recente.

Fontes oficiais consultadas em 12/10/2026. Licenças: consultar os arquivos LICENSE de cada origem. A licença de código não deve ser presumida como licença de todos os dados ou pesos.
