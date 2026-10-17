# TCC Drone — Pipeline completo no novo vídeo | etapa 1.9.8

## O que o módulo faz

Este módulo **não treina** nenhuma rede nem altera os datasets. Processa todo o `IMG_5962_editado.mov` (5.142 quadros, 3840×2160, 30 fps) reutilizando a **seleção YOLO previamente congelada**; opcionalmente, permite inferir novamente com o checkpoint `best.pt` de SHA256 fixado. Combina:

- YOLO: caixa **selecionada**, que pode estar incorreta; **não** é uma detecção validada pelo GT;
- regressão por largura, com parâmetros congelados do FAROL, largura **mediana de quadros confiáveis por segundo** e filtro de qualidade;
- Depth Pro no quadro RGB completo (quando solicitado), registrando **Z axial** nos quadros amostrados; os demais quadros ficam marcados como não amostrados;
- renderização integral com **caixa**, `conf`, **distância exploratória**, `Z axial` e razões da abstenção;
- resultados por quadro e segundo, indicadores de **cobertura**, parâmetros e hashes.

O objetivo da etapa é **demonstrar transferência e disponibilidade operacional**, não certificar metros reais. O ajuste por largura foi treinado/calibrado no FAROL, não é predição OOF no novo vídeo, e a compatibilidade de câmera/zoom NÃO foi demonstrada. O modelo de largura não distingue falsos positivos: uma caixa sobre vegetação pode gerar uma distância sem significado para o drone. Depth Pro pode medir céu/árvores se a ROI estiver errada. **Nenhum MAE físico é computado.**

## Preparação

1. Extraia o ZIP dentro de `C:\Users\Icaro Lima\Downloads\TCC_Drone_VSCode`. Não substitua arquivos anteriores.
2. Certifique-se de que `data\video\IMG_5962_editado.mov` continua presente, sem modificação.
3. No VS Code, abra o terminal PowerShell na raiz do projeto, com `.venv` previamente instalado. Requisitos básicos: `numpy`, `pandas`, `opencv-python`, `pytest` (opcional para testes). Para Depth Pro, também `torch`, `Pillow`, código oficial `ml-depth-pro` e checkpoint original.
4. Execute `01_AUDITAR.bat`; depois `02_PILOTO_REGRESSAO.bat`. O piloto rende os primeiros **120 quadros** como vídeo de 4 segundos.
5. Confirme se a renderização está visualmente correta. Execute `03_VIDEO_INTEGRAL_REGRESSAO.bat` para gerar o vídeo **integral de 5.142 quadros**.
6. Para executar Depth Pro, instale sua implementação oficial no `.venv` e confirme os pesos em `data\weights\depth_pro\depth_pro.pt` e o código em `vendor\ml-depth-pro\src`. Execute `04_VIDEO_INTEGRAL_DEPTH_1HZ.bat`, preferencialmente em GPU com VRAM adequada (a RTX 2060 Max-Q de 6 GB pode não comportar o mapa 4K). **Se der OOM, não haverá downscale oculto**; prefira Google Colab T4 ou outra GPU. O programa persiste quadros Depth concluídos e retoma execução compatível.

**AVISO:** o script Depth do `.bat` usa `--depth-every 30` (≈1 profundidade por segundo, caso haja caixa confiável nesse quadro). Assim, o **vídeo é integral** e a **regressão utiliza todos os quadros**, mas o Depth Pro é explicitamente amostrado. Para inferir Depth Pro em cada quadro elegível, use `--depth-every 1` com recursos computacionais adequados, em pasta de saída separada. Não preencha automaticamente quadros sem Depth Pro.

## Execução manual equivalente

```powershell
cd "C:\Users\Icaro Lima\Downloads\TCC_Drone_VSCode"

.\.venv\Scripts\python.exe -u .\ETAPA_PIPELINE_INTEGRADO_NOVO_VOO_v1_9_8\pipeline_integrado.py auditar

.\.venv\Scripts\python.exe -u .\ETAPA_PIPELINE_INTEGRADO_NOVO_VOO_v1_9_8\pipeline_integrado.py piloto --saida .\outputs\pipeline_integrado_novo_voo_v1_9_8\PILOTO_120

.\.venv\Scripts\python.exe -u .\ETAPA_PIPELINE_INTEGRADO_NOVO_VOO_v1_9_8\pipeline_integrado.py executar --saida .\outputs\pipeline_integrado_novo_voo_v1_9_8\INTEGRAL_REGRESSAO

.\.venv\Scripts\python.exe -u .\ETAPA_PIPELINE_INTEGRADO_NOVO_VOO_v1_9_8\pipeline_integrado.py executar --saida .\outputs\pipeline_integrado_novo_voo_v1_9_8\INTEGRAL_DEPTH_1HZ --depth-every 30
```

Para estimativas de **referência meramente hipotética**, adicione `--usar-referencia-hipotetica` e mantenha a proveniência geométrica e o `--offset-telemetria-s` registrados. Essa referência **não** habilita MAE/RMSE de erro físico certificado.

## Arquivos de saída

- `VIDEO_FINAL_EXPLORATORIO_SEM_AUDIO.mp4` — vídeo anotado, sem áudio.
- `RESULTADOS_POR_QUADRO.csv` — todas as caixas, seus status, referências por segundo e Z quando calculado.
- `RESULTADOS_POR_SEGUNDO.csv` — largura mediana, IQR, filtros, estimativa provisória e justificativa da abstenção.
- `RESUMO_EXECUCAO_v1_9_8.json` — cobertura, quantidade de quadros e segundos processados.
- `PROVENIENCIA_v1_9_8.json` — vídeo, fonte de caixa, hashes e protocolo.
- `RELATORIO_INTEGRACAO_v1_9_8.md` — interpretação e limitações.
- `profundidade_amostrada.jsonl` e `profundidade_proveniencia.json` — somente se executar Depth Pro.

Para enviar à análise, compacte **o JSON de proveniência, o resumo, o relatório e as duas tabelas**. O vídeo final (potencialmente grande) permanece local; poderá ser enviado em separado, se necessário.

## Métodos e advertências

- O **cache** corresponde apenas ao vídeo `IMG_5962_editado.mov`. SHA-256 do vídeo e das seleções é validado antes da utilização.
- `--fonte novo-yolo` é uma alternativa para novos vídeos e usa sempre o peso congelado, sem treinamento. Sua política de seleção (maior confiança >=0,25) é documentada e pode ser diferente daquela dos arquivos arquivados.
- `--seletor temporal --aceitar-supervisao` usa a associação histórica que recebeu **seis sementes supervisionadas**: não é autonomia plena.
- O vídeo deve ser **CFR 4K** sob o protocolo histórico. `ffprobe` audita PTS de todos os quadros; VFR/PTS irregular interrompe o processamento. Para VFR use pipeline PTS/PyAV separado; não trate `frame_idx/fps` como tempo físico automaticamente.
- `--depth-every 0` (padrão) desativa o Depth Pro. Nunca rotule a execução somente-regressão como execução Depth Pro completa.
- O status `qc_aprovado` é uma **regra de emissão por segundo**, não prova de que as caixas correspondem ao drone.
- Os filtros (mínimo 5 caixas, IQR relativo <=0,35 e Hampel causal sobre larguras) derivam do experimento original. Seu emprego nesta nova aquisição é **transferência exploratória**, sem ajuste dos parâmetros.
- O modelo provisório é `d = 4442.5484604804715 * mediana_largura_px**(-1.2771511434180072)`, na resolução original 3840×2160. Não aplique diretamente a caixas isoladas nem confunda com as predições OOF da avaliação histórica.
- Nenhuma nova anotação GT foi usada para seleção de caixas. A revisão v1.9.6 e sua pós-hoc v1.9.7 permanecem **avaliações separadas**.
- Não combine resultados de `IMG_5962_editado.mov` com telemetria do FAROL: trata-se de voos distintos.

## Google Colab

Use o notebook `EXECUTAR_NO_COLAB_v1_9_8.ipynb` incluído no ZIP. Ele instala dependências básicas, monta Drive, extrai este pacote do Drive e executa a mesma implementação Python. Ajuste explicitamente os caminhos para vídeo e checkpoints **copiados para o Drive**. Não há download automático de pesos protegidos.

## Testes internos

```powershell
.\.venv\Scripts\python.exe -m pytest -q .\ETAPA_PIPELINE_INTEGRADO_NOVO_VOO_v1_9_8\tests
```

Os testes incluem reprodução dos 5.142 estados congelados, abstenção por qualidade, rejeição de índices inválidos e renderização de vídeo sintético. **Eles não substituem a primeira execução real na sua máquina.**
