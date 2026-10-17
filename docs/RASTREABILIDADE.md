> Documento de origem do pacote privado. Para os arquivos efetivamente publicados nesta branch e a validação atual, veja [STATUS_GITHUB.md](STATUS_GITHUB.md) e [VALIDACAO_GITHUB.md](VALIDACAO_GITHUB.md). Pesos, imagens, vídeos, capítulos e telemetria bruta não acompanham esta branch.

# Rastreabilidade científica

`provenance/MANIFEST_SHA256.csv` cobre os arquivos desta entrega, exceto o próprio manifesto. `environment.json` registra a análise realizada. Os diretórios arquivados preservam protocolos, datas e caminhos de origem; caminhos Windows antigos são evidência histórica, não instruções operacionais para Colab.

Cada novo experimento salva configuração, versão do Python/pacotes, hashes do vídeo/peso, PTS, auditoria da telemetria, semente 42 e métricas. Um identificador já usado não é sobrescrito pelo pipeline de novos voos. O paralelismo/GPU pode impedir igualdade bit a bit; a semente não garante determinismo universal.

As principais mudanças desta compilação são organização de caminhos, adaptação Colab, exportação do pós-processamento original para script, acréscimo de auditorias e fluxo genérico de novos voos. Os resultados arquivados não foram alterados. O script analítico do Farol reaplica os critérios originais; o fluxo genérico possui saídas próprias e não é substituto silencioso da análise histórica.

O CSV corrigido do novo voo foi recebido como fonte, não corrigido novamente nesta montagem. Compare com o original e consulte as justificativas nos relatórios do dossiê; não inferir significado de colunas apenas por semelhança de nomes.

Distinguir no texto: inspeção humana, concordância com referência nominal, validação temporal interna e validação física independente. O termo inglês *checkpoint* pode ser apresentado como arquivo de pesos do modelo (checkpoint). FFmpeg é nome de software; descreva sua função e versão usada, sem forçar sua inclusão como sigla científica.
