# Validação da preparação para GitHub — 17/10/2026

- Seis testes locais aprovados: interpolação sem extrapolação, sincronização/timecode, ROI, métricas ausentes, telemetria sem referência de alcance e anotação de vídeo CFR com PTS preservados.
- Reprodução do Farol: 904 predições nos oito modelos; erro absoluto máximo 2,1316282072803006e-13 m frente às predições históricas. Não foi realizada nova inferência das redes.
- Integração do segundo voo: os resultados numéricos coincidem com os arquivados. Os hashes diferem pela retirada de colunas de localização e pela compressão gzip de tabelas grandes, ambos documentados.
- Gerador de figuras/tabelas executado localmente.
- Sintaxe dos módulos e das células Python dos notebooks verificada.

Uma rotina GitHub Actions foi preparada para repetir essas verificações em CPU. A conclusão sobre o resultado no servidor dependerá da execução efetiva; o teste local não é apresentado como teste concluído no GitHub.

Não verificado nesta preparação: inferência completa YOLO/Depth Pro em GPU, sessão Colab completa, treinamento, VFR/HDR em todos os codecs e generalização métrica em voo independente. Os relatórios de 12/10 são registros históricos, não prova automática da montagem atual.
