> Documento de origem do pacote privado. Para os arquivos efetivamente publicados nesta branch e a validação atual, veja [STATUS_GITHUB.md](STATUS_GITHUB.md) e [VALIDACAO_GITHUB.md](VALIDACAO_GITHUB.md). Pesos, imagens, vídeos, capítulos e telemetria bruta não acompanham esta branch.

# Dados, partições e revisão manual

`data/annotations_original/` preserva as anotações da classe única original (drone=0). `data/manifests/dataset_inventory.csv` identifica cada arquivo, SHA-256, partição e presença da imagem. Não remapear esses arquivos no lugar. O detector final usa drone=2, em quatro classes; `scripts/preparar_dataset.py` cria cópia compatível.

| Partição | Anotações | Imagens recuperadas | Caixas válidas |
|---|---:|---:|---:|
| Treino | 317 | 99 | 298 |
| Validação | 84 | 28 | 78 |
| Teste | 75 | 75 | 67 |

Foram recuperadas 202 de 476 imagens. Faltam 218 de treino e 56 de validação. Anotações vazias são preservadas como negativos. Há 443 caixas sintaticamente válidas nos arquivos recuperados; uma auditoria histórica relatava 442 válidas e uma inválida. Esse desacordo entre versões não autoriza alterar silenciosamente o resultado histórico. Validade sintática não certifica precisão visual.

Extraia o suplemento de imagens e copie `inputs/dataset/` para a raiz do repositório. Execute `python scripts/preparar_dataset.py`. Para teste do detector, use `python scripts/avaliar_detector.py --data outputs/dataset_yolo/data.yaml --split test`. A partição de teste está completa; treino/validação são subconjuntos e não reproduzem o treinamento integral.

## Registro manual

T05/T07/T08/T09/T10 e T13–T16 preservam vínculos, critérios e análises primária/pós-hoc. Os exemplos visuais recuperados estão em `results/archived/consolidacao/FIGURAS_DO_DOSSIE`. Nem todo quadro de revisão foi recuperado como imagem individual. Use os identificadores para extraí-lo do vídeo correto; não use outro recorte com mesmo número de quadro.

Critérios de inspeção: classe e identidade do alvo, cobertura do drone pela caixa, inclusão de fundo, deslocamento, dimensões anômalas, oclusão, visibilidade e correspondência temporal. Registre também casos inconclusivos. O arquivo `review_template.csv` é um formulário vazio, não evidência de revisão realizada.

Mantenha lado a lado a anotação original, a correção e o motivo. Não reconstruímos retrospectivamente anotações corrigidas ausentes. Preserve a amostra primária congelada; resultados pós-hoc devem permanecer separados e nominalmente identificados.
