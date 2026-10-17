# Farol — dois vídeos experimentais (v1.0)

## Escopo e status

Este pacote **não contém o vídeo**; contém os seis arquivos de evidência histórica e o renderizador para produzir localmente dois vídeos anotados do **arquivo editado** `video_final_farol.mov`. As predições YOLO e Depth Pro foram reaproveitadas: **nenhum modelo é treinado ou executado novamente**. A regressão exibida provém da série OOF **validada por blocos**, um valor para cada segundo elegível. Não se substitui silenciosamente a regressão OOF pela equação global do voo.

Arquivo alvo: `video_final_farol.mov` — **3537 quadros, 30 FPS, 3840×2160, 117,90 segundos**.

**NÃO usar** `video_final_farol_original.MOV` — **6702 quadros, 223,46 segundos**. O arquivo original possui recortes/exclusões e os índices não correspondem aos arquivos históricos do editado. O script aborta quando recebe metadados distintos.

## Principais saídas

- `01_VIDEO_CIENTIFICO_FAROL.mp4` — 1920×1080. Mostra quadro, ROI proposta, R de referência nominal, estimativa OOF por largura (não filtrada), Z bruto Depth Pro, Depth histórico calibrado, diferenças relativas, QC, telemetria e gráfico temporal.
- `02_VIDEO_APRESENTACAO_BANCA_FAROL.mp4` — 1280×720. Versão mais simples, com regressão **filtrada** (rejeita os quatro segundos de QC) e avisos.
- `AUDITORIA_DADOS_EXIBIDOS_FAROL.csv` — alinhamento de dados de 3537 quadros, registros da referência nominal, OOF e Depth, e diferenças relativas calculadas; tem valores distintos de percentual para OOF contra referência por segundo e contra referência por quadro.
- `RESUMO_PROVENIENCIA_FAROL.json` — fontes, hashes, protocolo e avisos.
- `PREVIA_CIENTIFICO.jpg`, `PREVIA_BANCA.jpg` — primeiros quadros reais quando o vídeo é disponibilizado localmente.

## Executar pelo PowerShell do VS Code (sem arquivos .bat)

Extraia a pasta `GERADOR_DOIS_VIDEOS_FAROL_v1_0` na raiz do projeto. Execute:

```powershell
$projeto = 'C:\Users\Icaro Lima\Downloads\TCC_Drone_VSCode'
$dir = Join-Path $projeto 'GERADOR_DOIS_VIDEOS_FAROL_v1_0'
$python = Join-Path $projeto '.venv\Scripts\python.exe'

if (!(Test-Path $python)) { throw 'Python virtual nao encontrado' }
if (!(Test-Path (Join-Path $dir 'gerar_dois_videos_farol.py'))) { throw 'Extraia o ZIP por completo' }

# Primeiro: conferir 3537 linhas e os resultados, sem usar vídeo
& $python (Join-Path $dir 'gerar_dois_videos_farol.py') --so-diagnostico

# Buscar o vídeo EDITADO, não o original, dentro do projeto
$video = Get-ChildItem -LiteralPath $projeto -Filter 'video_final_farol.mov' -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
if (!$video) { throw 'Nao encontrei video_final_farol.mov. Atribua $video ao caminho exato do editado (3537 quadros).' }
Write-Host "Usando vídeo: $video"

# Teste rápido de 90 quadros (3 segundos); não é o vídeo final
& $python (Join-Path $dir 'gerar_dois_videos_farol.py') --video $video --saida (Join-Path $dir 'SAIDAS') --teste-quadros 90

# Se o teste estiver correto, renderizar os DOIS vídeos completos
& $python (Join-Path $dir 'gerar_dois_videos_farol.py') --video $video --saida (Join-Path $dir 'SAIDAS')
```

O relatório histórico aponta também um possível caminho `C:\TCC_Drone_local\video_final_farol_original\video_final_farol.mov`. Se o arquivo editado estiver lá, você pode atribuir diretamente seu caminho a `$video` antes de executar o teste. Não confunda o nome da pasta `video_final_farol_original` com o nome do arquivo efetivo.

Pré-requisitos: Python `.venv` com `opencv-python` e `numpy`. FFmpeg no PATH é **opcional**, mas recomendado para copiar o áudio original; sem ele, OpenCV tenta salvar MP4 sem áudio.

## Fontes e rastreabilidade

Os seguintes cinco arquivos vieram da cópia histórica `resultados_pipeline_farol_30fps(1)` preservada em `CONSOLIDACAO_CIENTIFICA_TCC_v1_9_9.zip`; a cópia `(2)` possui conteúdo byte a byte idêntico para esses arquivos:

- `yolo_all_frames.csv` — 3537 linhas de caixas propostas, tempos, sincronismo e referência nominal por quadro.
- `depth_all_frames.csv` — 3537 linhas com Depth Pro bruto Z, Depth calibrado, status e abstenção.
- `synchronization_correction.json` — correspondência histórica: início recortado no original em 2,833333 s e telemetria em 4,8 s.
- `temporal_protocol.json` — metadados do experimento e os pressupostos geométricos.
- `box_width_model_provisional.json` — equação global histórica **somente para proveniência, não utilizada na substituição dos valores OOF**.

O sexto arquivo, `T04_pareamento_oof_113_segundos.csv`, provém de `PACOTE_EVIDENCIAS_CONSOLIDADAS_PARA_WORK_v1_9_9(2).zip` (113 pares OOF). Manifestações de proveniência e SHA-256 das cópias estão no arquivo `MANIFESTO_FONTES_SHA256.csv`.

## Política de exibição e limites científicos

- **R referência nominal** é radial câmera–drone **hipotético**, derivado historicamente da telemetria e da geometria presumida. Não é medição independente ou certificada. Esse R nominal foi calculado no experimento histórico assumindo câmera a **1,5 m de altura e 1,5 m de distância horizontal do HOME**, com azimute desconhecido. Outros registros do farol mencionam aproximadamente **5 m horizontais**; **há divergência documental**. Não corrigimos silenciosamente a referência; as comparações atuais são apenas **do cenário histórico preservado**.
- **Regressão OOF** tem 113 instantes (segundos), não 3537 predições independentes. Na versão científica mostramos o OOF não filtrado de cada segundo disponível; na versão banca a variante com QC tem 109 segundos. Os segundos 39, 40, 51, 52, 53 são N/D. Cada valor da série de um segundo é **mantido visualmente nos quadros daquele segundo**, sem inferir que existiram novas regressões individuais em todos os quadros.
- **Depth Pro** bruto é profundidade **axial Z**. A referência R é **radial**. A expressão percentual `Dif. Z/R*` é uma comparação numérica entre grandezas diferentes, **não um erro percentual de alcance físico**. O painel não chama essas diferenças de MAE/MAPE certificados. O valor calibrado histórico é distinguido do bruto; essa calibração não é avaliação externa independente.
- Se o Depth Pro `abstained=True`, mesmo que o CSV contenha alguma medida bruta calculada, a exibição é **N/D**: não reaproveitamos um valor rejeitado como válido.
- As ROIs do YOLO são **candidatas selecionadas**, não localização automaticamente correta segundo o GT. Baixa confiança é exibida em laranja. A presença de uma caixa não equivale a verdadeiro positivo.
- O percentual da regressão no vídeo é calculado contra o R nominal exibido **naquele quadro**, de forma clara para demonstração. O valor oficial OOF contra referência **do próprio segundo** é preservado separadamente na auditoria; não comparar diretamente médias aritméticas por quadro com os resultados OOF originais.
- Caso haja FPS variável/alterações de ordem dos quadros no arquivo local, metadados idênticos por si só não asseguram identidade do vídeo. Para uma validação definitiva, auditar os PTS e a identidade do arquivo **editado** antes de divulgar os percentuais como resultados de pesquisa.

## Testes feitos

- Leitura e conferência da correspondência dos 3537 quadros, índices, tempos e referências: concluída.
- Pareamento dos 113 segundos OOF sem duplicações; confirmados MAE nominal OOF `1,5744298 m` (113) e com QC `1,4241446 m` (109): concluído.
- Verificação de 3143 registros aceitos do Depth e 394 abstenções: concluída.
- Testes unitários de composição dos painéis com quadros **sintéticos** em 1920×1080 e 1280×720: concluídos.
- Teste do codificador FFmpeg com quadros **sintéticos**: concluído.
- Execução dos 3537 quadros com o **MOV real**: **não executada nesta sessão** (vídeo não foi fornecido).

Os resultados históricos permanecem congelados, e este pacote não adiciona inferências nem retreinamentos.
