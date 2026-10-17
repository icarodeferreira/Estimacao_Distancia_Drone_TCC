# Estimação de distância de drones em vídeo monocular

Código e evidências numéricas do TCC que compara o Depth Pro e regressões baseadas nas dimensões aparentes das caixas de um detector YOLO. O Farol da Ilha da Moela é o caso de desenvolvimento com referência nominal; um segundo voo examina localização, disponibilidade e integração temporal dos estimadores congelados.

**Estado:** reprodução analítica do Farol e integração temporal verificadas em CPU. A inferência completa com YOLO/Depth Pro em GPU e a execução ponta a ponta no Google Colab ainda precisam ser testadas. As distâncias não possuem validação física independente.

## Executar no Google Colab

| Objetivo | Notebook |
|---|---|
| Reproduzir resultados do Farol, sem redes nem vídeo | [Abrir notebook 01](https://colab.research.google.com/github/icarodeferreira/Estimacao_Distancia_Drone_TCC/blob/preparacao-tcc-2026-10-17/notebooks/01_Reproduzir_Farol_Colab.ipynb) |
| Preparar um novo experimento | [Abrir notebook 02](https://colab.research.google.com/github/icarodeferreira/Estimacao_Distancia_Drone_TCC/blob/preparacao-tcc-2026-10-17/notebooks/02_Novos_Experimentos_Colab.ipynb) |
| Refazer as inferências do Farol | [Abrir notebook 03](https://colab.research.google.com/github/icarodeferreira/Estimacao_Distancia_Drone_TCC/blob/preparacao-tcc-2026-10-17/notebooks/03_Farol_inferencia_Colab.ipynb) |

Os notebooks obtêm esta branch no ambiente temporário do Colab. Para as redes, selecione GPU, obtenha os pesos e vídeos descritos abaixo e comece pelo piloto. Copie as saídas para o Drive antes de encerrar a sessão.

## Reprodução local

```bash
git clone --branch preparacao-tcc-2026-10-17 https://github.com/icarodeferreira/Estimacao_Distancia_Drone_TCC.git
cd Estimacao_Distancia_Drone_TCC
python -m pip install -r requirements-analysis.lock.txt
python scripts/reproduzir_farol.py
python scripts/integrar_sincronismo_novo_voo.py --dados-dir results/archived/dossie/03_FONTES_CODIGO_INTEGRACAO/FONTES --saida outputs/integracao_reproduzida
python scripts/gerar_figuras_tabelas.py
python -m unittest discover -s tests -v
```

A análise foi verificada em Python 3.12. FFmpeg e ffprobe são dependências de sistema para auditoria e vídeo. Os CSVs maiores foram comprimidos com gzip; a reprodução do Farol os lê diretamente.

## Materiais externos

| Material | Situação |
|---|---|
| Detector `best.pt` | Hash e origem em `models/registry.json`; colocar o arquivo autorizado em `models/best.pt` |
| Depth Pro | `python scripts/instalar_depth_pro.py`; registra commit efetivo e SHA-256. Checkpoint histórico exato desconhecido |
| Vídeo Farol | Pacote suplementar do autor; colocar em `inputs/video/farol.mov` |
| Imagens próprias | Suplemento com 202 imagens; 274 imagens ausentes; anotações e manifestos incluídos |
| Vídeo do segundo voo | `IMG_5962_editado.mov` não localizado no acervo usado nesta preparação |

Não há URL pública de download para os suplementos neste repositório. Os campos nulos de `data/external_assets.json` indicam essa pendência. Imagens, vídeos, pesos e capítulos do TCC precisam de autorização de redistribuição antes de serem hospedados publicamente. A licença própria ainda não foi escolhida pelo titular; consulte `LICENSE.md`.

## Métodos e resultados

Farol: 113 de 118 segundos elegíveis, oito modelos e 904 predições com exclusão de blocos temporais de 20 s. Regressão pela largura: MAE nominal 1,57443 m e RMSE 2,39229 m; no subconjunto aceito pelo controle de qualidade, 109 segundos e MAE 1,42415 m. O menor erro do subconjunto deve ser interpretado junto à perda de cobertura.

Depth Pro com focal fixa de 1.440 pixels: discrepância absoluta média de 12,92516 m para saída bruta e 9,78892 m após transformação transferida do ensaio XR. A comparação envolve calibrações assimétricas e grandezas axial/radial, sem estabelecer superioridade metrológica.

Segundo voo: 5.142 quadros; suporte telemétrico para 5.015 quadros no cenário de 10,566666667 s e 4.996 no de 11,2 s. Esses números medem disponibilidade temporal. A telemetria publicada foi reduzida às cinco colunas necessárias, sem coordenadas geográficas; isso altera seu hash, preservando os valores usados na análise.

## Organização

- `notebooks/`, `src/`, `scripts/`, `tests/`: execução e verificações.
- `configs/`, `models/`: parâmetros e calibrações documentadas, sem pesos binários.
- `data/`: rótulos originais, revisão manual e inventários.
- `results/archived/`: CSVs e protocolos de origem necessários à análise.
- `legacy/`: código histórico dos módulos integrados e geradores.
- `provenance/`: recuperação do pacote, seleção pública, hashes e validação atual.
- `outputs/`: saídas locais, ignoradas pelo Git.

## Documentação

[Farol](docs/GUIA_FAROL.md) · [Novos experimentos](docs/GUIA_NOVOS_EXPERIMENTOS.md) · [Limitações](docs/LIMITACOES.md) · [Dados e revisão](docs/DADOS_E_REVISAO.md) · [Modelos e fontes](docs/MODELOS_E_FONTES.md) · [Validação atual](docs/VALIDACAO_GITHUB.md) · [Materiais](docs/STATUS_GITHUB.md) · [Licenças](docs/LICENCAS_E_PUBLICACAO.md) · [Rastreabilidade](provenance/PREPARACAO_GITHUB.md)

A referência nominal, a validação interna da regressão e a localização do alvo são avaliações distintas. O segundo voo demonstra integração computacional e falhas, sem comprovar exatidão física generalizável nem prontidão operacional.
