# Materiais desta branch

Código, notebooks, configurações, rótulos, decisões de revisão e dados numéricos de reprodução estão incluídos. Os arquivos grandes de inferência estão comprimidos com gzip. A análise de CPU pode ser reproduzida sem baixar pesos ou vídeos.

Os três pacotes originais continuam sendo a compilação privada de origem; não foram publicados como releases. O ZIP principal disponível estava truncado e foi parcialmente recuperado com CRC. CSVs do Farol e rotinas faltantes foram reconstruídos a partir das fontes e submetidos a nova verificação. Veja provenance/PREPARACAO_GITHUB.md.

Ficam externos: best.pt (hash registrado), pesos Depth Pro, vídeo Farol, 202 imagens, telemetria bruta e capítulos do TCC. Os suplementos agora estão vinculados em [SUPLEMENTOS_DRIVE.md](SUPLEMENTOS_DRIVE.md), incluindo o vídeo do segundo voo, pesos e dataset. O best.pt teve hash confirmado. A recuperação das 274 imagens antes ausentes, a equivalência dos vídeos e a identificação binária do checkpoint histórico Depth Pro ainda precisam ser verificadas. A licença própria continua pendente.

Os relatórios de validação de 12/10 são históricos; a validação atual é docs/VALIDACAO_GITHUB.md. A inferência completa em GPU/Colab permanece não testada.

Em 05/11/2026, os links e comandos foram ajustados à branch principal e a dependência SciPy foi incluída após diagnóstico dos logs de CI. Consulte `FINALIZACAO.md` para as ações restantes e a execução de Actions do commit correspondente para o estado no servidor.
