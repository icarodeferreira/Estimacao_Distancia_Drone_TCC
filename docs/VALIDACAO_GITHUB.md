# Validação atual — 05/11/2026

Validação realizada em ambiente virtual novo, Python 3.12, instalado exclusivamente a partir de `requirements-analysis.lock.txt`:

- Seis testes unitários aprovados, incluindo vídeo CFR com PTS preservados.
- Reprodução Farol: 904 predições comparadas; diferença máxima 2,1316282072803006e-13 m (limite 1e-8 m).
- Integração do segundo voo concluída: 5.015 e 4.996 quadros com suporte telemétrico nos dois cenários.
- Geração de figuras e tabelas concluída.
- Sintaxe das células Python dos três notebooks verificada.

O log da execução GitHub Actions 41440110446 identificou `ModuleNotFoundError: No module named 'scipy'` no cálculo de Spearman. A dependência foi adicionada aos requisitos gerais e fixada em 1.17.0 no arquivo de análise. Os links e clones dos notebooks agora apontam para `Estimacao-de-distancia-de-drones`.

O estado da validação no servidor deve ser consultado na execução Actions do commit correspondente. A CI guarda resultados e ambiente no artefato `reproducao-cpu` por 30 dias.

A inferência completa YOLO/Depth Pro em GPU/Colab, o treinamento e a equivalência binária do checkpoint Depth Pro histórico continuam sem validação nesta revisão. A execução em ambiente virtual local não é apresentada como uma sessão Colab concluída. Consulte [FINALIZACAO.md](FINALIZACAO.md).

---

## Registro histórico

# Validação da preparação para GitHub — 17/10/2026

- Seis testes locais aprovados: interpolação sem extrapolação, sincronização/timecode, ROI, métricas ausentes, telemetria sem referência de alcance e anotação de vídeo CFR com PTS preservados.
- Reprodução do Farol: 904 predições nos oito modelos; erro absoluto máximo 2,1316282072803006e-13 m frente às predições históricas. Não foi realizada nova inferência das redes.
- Integração do segundo voo: os resultados numéricos coincidem com os arquivados. Os hashes diferem pela retirada de colunas de localização e pela compressão gzip de tabelas grandes, ambos documentados.
- Gerador de figuras/tabelas executado localmente.
- Sintaxe dos módulos e das células Python dos notebooks verificada.

Uma rotina GitHub Actions foi preparada para repetir essas verificações em CPU. A conclusão sobre o resultado no servidor dependerá da execução efetiva; o teste local não é apresentado como teste concluído no GitHub.

Não verificado nesta preparação: inferência completa YOLO/Depth Pro em GPU, sessão Colab completa, treinamento, VFR/HDR em todos os codecs e generalização métrica em voo independente. Os relatórios de 12/10 são registros históricos, não prova automática da montagem atual.
