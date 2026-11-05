# Finalização e critérios de aceite

## Reprodução numérica (CPU)

Use Python 3.12 e instale `requirements-analysis.lock.txt`. Instale FFmpeg (inclui ffprobe) no sistema. Execute os quatro comandos de reprodução e testes indicados no README. A execução GitHub Actions deve concluir todas as etapas e disponibilizar o artefato `reproducao-cpu`, com resultados, ambiente e commit.

Aceite do Farol: 904 predições comparadas, diferença máxima inferior a 1e-8 m. Os resultados esperados são MAE 1,57443 m (113 segundos) e MAE 1,42415 m com controle de qualidade (109 segundos). Isso verifica o processamento das inferências arquivadas, não uma nova inferência das redes.

## Materiais que o autor precisa disponibilizar

| Material | Ação necessária |
|---|---|
| `best.pt` | Hospedar o peso autorizado e informar URL; conferir SHA-256 em `models/registry.json`. |
| `farol.mov` | Hospedar o vídeo autorizado; preencher URL em `data/external_assets.json`. |
| `IMG_5962_editado.mov` | Recuperar o arquivo original, conferir hash e fornecer URL. |
| Imagens próprias | Disponibilizar as 202 recuperadas com licença/permissão; conferir o manifesto e as 274 apontadas como ausentes. Não afirmar reprodução integral do treinamento enquanto o conjunto não estiver completo. |
| Vídeos anotados finais | Disponibilizar links dos dois vídeos e identificar execução/configuração de origem. |
| TCC aprovado | Informar título definitivo, nome completo, instituição e ano; fornecer PDF e autorização de publicação, se desejada. |
| Licença do código | O titular deve escolher os termos; a licença do código não abrange automaticamente dados e pesos. |
| Depth Pro histórico | Recuperar commit e hash do checkpoint, se possível; manter a limitação explícita se não forem recuperados. |

Não é necessário publicar coordenadas pessoais ou telemetria bruta para repetir a análise já arquivada. Use a versão reduzida disponibilizada e documente qualquer alteração adicional.

## Teste completo no Colab

1. Abra o notebook 01 pelo README em uma sessão limpa. Execute todas as células e confira `outputs/farol_reproduzido/verificacao.json`.
2. Abra o notebook 03 em uma nova sessão com GPU. Obtenha os arquivos indicados no próprio notebook e confira seus hashes antes de iniciar.
3. Execute primeiro o piloto, verificando caixas, classe drone (índice 2), focal, sincronização e saídas de distância. Depois execute o processamento completo.
4. Salve notebook executado, configuração, commit do repositório, versões instaladas, identificação da GPU, hash dos pesos, tempo de execução e mensagens de erro, se houver.
5. Confira o vídeo anotado e as tabelas. Compare as métricas com as arquivadas, explicando diferenças de ambiente/checkpoint; não substitua resultados históricos silenciosamente.
6. Execute o notebook 02 com o segundo voo quando seu vídeo estiver disponível. Disponibilidade temporal não comprova acurácia métrica em voo independente.
7. Atualize `docs/VALIDACAO_GITHUB.md` com evidências e links. Só marque inferência completa como validada após o término dessas etapas.

## Versão final

Após CI aprovada, links verificados e pendências bibliográficas/licenças resolvidas, publique uma release com tag, notas, hashes e links dos suplementos. O campo de autoria atual de `CITATION.cff` identifica a conta mantenedora; substitua-o pela autoria bibliográfica confirmada. Não apresente a versão como reprodução integral do treinamento se persistirem imagens ausentes.
