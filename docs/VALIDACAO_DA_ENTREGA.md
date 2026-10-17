> Documento de origem do pacote privado. Para os arquivos efetivamente publicados nesta branch e a validação atual, veja [STATUS_GITHUB.md](STATUS_GITHUB.md) e [VALIDACAO_GITHUB.md](VALIDACAO_GITHUB.md). Pesos, imagens, vídeos, capítulos e telemetria bruta não acompanham esta branch.

# Validação da entrega — 12/10/2026

Esta compilação foi reconstruída a partir dos materiais de origem após indisponibilidade dos arquivos intermediários anteriores. Os resultados abaixo foram verificados novamente nesta montagem; não dependem apenas de relato de uma execução anterior.

| Verificação | Resultado |
|---|---|
| Reprodução Farol a partir de inferências arquivadas | 904 predições dos oito modelos; erro absoluto máximo 2,1316282072803006e-13 m em relação ao arquivo original |
| Integração temporal do novo voo | JSON de resultados reproduzido idêntico ao arquivado |
| Geração de tabelas e figuras | Script executado; CSV/LaTeX/PNG/PDF em results/generated |
| best.pt | Hash igual ao peso no ZIP de treinamento |
| Imagens/anotações | 202 imagens; 476 rótulos; 443 caixas sintaticamente válidas; 274 imagens ausentes |
| Vídeo Farol | SHA-256 conferido e ffprobe preservado |
| Testes automatizados | Seis testes aprovados: interpolação sem extrapolar, ausência de referência, timecode/sincronização, ROI, métricas ausentes e vídeo com preservação de PTS |
| Sintaxe | Módulos/scripts/notebooks conferidos sem executar as redes |

O teste de vídeo usa sequência sintética CFR. Isso não certifica todos os codecs, VFR, HDR ou rotações possíveis. O anotador genérico rejeita rotação não normalizada; usa orientação codificada, preserva intervalos de apresentação e não copia áudio.

**Não executado aqui:** inferência YOLO/Depth Pro em GPU, treinamento, execução completa no Colab, validação externa da regressão e geração dos vídeos completos. Torch, Ultralytics e PyAV não estavam instalados no ambiente de análise. A versão histórica completa do ambiente não foi recuperada.

Os resultados de verificação estão em `provenance/` e os resultados numéricos em `results/reproduced/`. Os dados arquivados permanecem distinguíveis das saídas reproduzidas e dos modelos de configuração ainda a preencher.

Prévia real adicional: 30 quadros do Farol anotados em resolução nativa, com 30 quadros de saída e erro máximo de PTS igual a zero. Veja results/examples/farol_30_quadros.mp4 e o JSON correspondente. É uma prévia de aproximadamente um segundo, não o vídeo integral.
