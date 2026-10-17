# Relatório final — estimação de distância do drone

## Resultado selecionado

- Método científico principal: largura da bounding box YOLO com validação OOF por blocos de 20 segundos.
- Equação provisória de implantação: `distância_m = 4442.5485 × largura_px ^ (-1.277151)`.
- MAE OOF primário: `1.574 m`.
- RMSE OOF primário: `2.392 m`.
- R² OOF primário: `0.952`.
- Cobertura primária: `95.763%`.

## Variante operacional

- MAE com controle de qualidade: `1.424 m`.
- RMSE com controle de qualidade: `1.808 m`.
- R² com controle de qualidade: `0.973`.
- Cobertura com controle de qualidade: `92.373%`.

## Interpretação

O Depth Pro foi preservado como comparador experimental, mas não manteve desempenho métrico suficiente. A largura da caixa YOLO apresentou o melhor resultado interno. A versão sem filtro constitui o resultado científico principal; a versão com abstenção é uma análise operacional secundária.

## Limitações

- Único voo e ausência de validação externa.
- Necessidade de zoom fixo e resolução de 3840 × 2160.
- Dependência da aparência e orientação do mesmo modelo de drone.
- Apenas dois segundos válidos acima de 40 m.
- Quadros adjacentes e telemetria interpolada não são observações independentes.
- A equação ajustada em todos os dados serve para implantação provisória; seu desempenho é estimado pelas predições OOF.
