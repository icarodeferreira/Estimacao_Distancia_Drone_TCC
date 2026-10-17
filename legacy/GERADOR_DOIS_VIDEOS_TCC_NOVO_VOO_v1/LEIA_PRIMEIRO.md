# Gerador de dois vídeos — novo voo do TCC Drone (versão 1.0)

**Entregável desta pasta:** programa local para renderizar, no Windows/PowerShell do VS Code, dois vídeos MP4 completos a partir do `IMG_5962_editado.mov` do usuário. **O MOV original não integra este pacote**, por isso os MP4 completos ainda não estão gerados aqui. O pacote contém fontes numéricas congeladas, script e prévias estáticas do layout feitas com o quadro 137 exportado; nenhuma prévia é o vídeo completo.

## Arquivos que serão gerados

- `SAIDAS/01_VIDEO_CIENTIFICO_NOVO_VOO.mp4`: 1920 × 1080, 30 FPS; timeline com distâncias, ROI proposta, lupa, indicadores e diferenças relativas.
- `SAIDAS/02_VIDEO_APRESENTACAO_BANCA.mp4`: 1280 × 720, 30 FPS; apresentação simplificada com dados idênticos.
- `SAIDAS/AUDITORIA_NUMEROS_EXIBIDOS.csv`: tabela por quadro que registra todas as distâncias, diferenças e disponibilidade dos dados; esta tabela permite rastreabilidade.
- `SAIDAS/RELATORIO_EXECUCAO_VIDEO.json`: parâmetros efetivamente utilizados.

**Os dois MP4 recebem o vídeo inteiro de 5142 quadros / 171,4 s**, salvo falha de execução. O programa lê o arquivo MOV original, sem reexecutar YOLO ou Depth Pro. Para validar sem processar tudo, use `--limite-quadros 90`, lembrando-se de remover a opção na execução definitiva.

## PowerShell do VS Code — execução direta, SEM arquivos BAT

Extraia a pasta `GERADOR_DOIS_VIDEOS_TCC_NOVO_VOO_v1` no diretório principal do projeto.

```powershell
$projeto = 'C:\Users\Icaro Lima\Downloads\TCC_Drone_VSCode'
$dir = Join-Path $projeto 'GERADOR_DOIS_VIDEOS_TCC_NOVO_VOO_v1'
$python = Join-Path $projeto '.venv\Scripts\python.exe'
$video = Join-Path $projeto 'data\video\IMG_5962_editado.mov'

if (-not (Test-Path $python)) { throw "Python não encontrado: $python" }
if (-not (Test-Path $video)) { throw "Vídeo não encontrado: $video" }
if (-not (Test-Path (Join-Path $dir 'gerar_dois_videos.py'))) { throw 'Pasta do gerador ausente' }

& $python -m pip install opencv-python numpy

& $python (Join-Path $dir 'gerar_dois_videos.py') `
    --video $video `
    --saida (Join-Path $dir 'SAIDAS')
```

Se `ffmpeg` estiver instalado e acessível, o gerador usa H.264/AAC (áudio original opcional, se existir). Caso contrário, salva MP4 `mp4v` **sem áudio**, o que é explicitado no terminal. Pode levar tempo significativo para processar 5142 quadros 4K e codificar simultaneamente dois vídeos.

### Prévia de três segundos antes da versão final

```powershell
& $python (Join-Path $dir 'gerar_dois_videos.py') `
    --video $video `
    --saida (Join-Path $dir 'PREVIA_3_SEGUNDOS') `
    --limite-quadros 90
```

Não confundir essa prévia de teste com os MP4 completos. O gerador valida automaticamente que o arquivo de entrada contém 5142 quadros, 30 FPS e dimensão 3840 × 2160.

## De onde vêm os números?

- `FONTES/T17_pipeline_5142_quadros.csv`: seleção de ROI e regressão por largura com agregação por segundo (modelo transferido de outro voo); não é ground truth.
- `FONTES/T19_depth_pro_126_medidas_Z_exploratorias.csv`: **126** medições previamente computadas do Depth Pro, em **Z axial**, apenas em quadros amostrados. O último valor pode permanecer indicado por até 1 segundo, **sempre rotulado como amostra anterior com idade explícita**, e não como nova inferência de todos os quadros.
- `FONTES/FlightRecord_2026-09-24_14-12-36_corrigido.csv`: distância horizontal corrigida drone–HOME (`distance_home_corrigida_m`) e demais campos de telemetria.
- `FONTES/PTS_TODOS_QUADROS.csv`: PTS auditados de 5142 quadros.
- Sincronização exploratória padrão: `t_telemetria = PTS_video + 10,566666667s`; pode ser mudada com `--offset 11.2` para análise de sensibilidade, **sem alegar validação definitiva**.

Quando a referência não existe ou é menor que 2 m, o percentual aparece como `N/D`, evitando divisões quase nulas. Quadros sem ROI, sem regressão ou sem amostra Depth exibem explicitamente a indisponibilidade. **A ROI selecionada nem sempre corresponde ao drone**; a caixa é identificada como proposta não validada.

## CUIDADO: porcentagem do vídeo padrão NÃO é erro métrico do TCC

Na geração padrão o painel exibe, com aviso, a **distância corrigida ao HOME**, não a distância câmera–drone. Calcula-se a diferença absoluta percentual exploratória:

`100 * abs(D_estimada - distance_home_corrigida_m) / distance_home_corrigida_m`, somente quando denominador ≥2 m.

Comparar regressão com a distância horizontal HOME e Depth Pro axial Z com HOME é uma comparação *entre grandezas potencialmente não equivalentes*. Assim, no vídeo é escrito `DIF. % vs HOME*` e há aviso persistente de não equivalência. **Não chamar esses números de MAPE, MAE, RMSE, precisão certificada ou erro de alcance câmera–drone.**

A documentação científica consolidada diz explicitamente que a posição da câmera, a compatibilidade da calibração e a referência física independente no **novo voo específico** não estão comprovadas. Existem informações anteriores referentes a outra configuração/captação (ex.: câmera fixa, altura de 1,5 m; separação nominal de GPS), mas sua aplicabilidade ao `IMG_5962_editado.mov` de 3840 × 2160 não está estabelecida neste dossiê. Por essa razão o código **não pressupõe posição da câmera**.

### Opção futura — referência geométrica CAMERA (não ativada automaticamente)

Se obtivermos latitude, longitude e altura da **câmera desse vídeo**, aferidas para a mesma origem vertical que `height_m`, o programa admite:

```powershell
# Exemplo de chamada com valores REAIS, quando estiverem confirmados:
# acrescente à chamada os seguintes parâmetros:
# --referencia camera --camera-lat <LAT_VERIFICADA> --camera-lon <LON_VERIFICADA> --camera-altura-m <ALT_VERIFICADA>
```

Nesse modo a distância radial é calculada usando latitude/longitude interpoladas do drone e diferença de altura. Para comparar Depth Pro Z com alcance R é necessária calibração intrínseca completa do vídeo (opções `--fx --fy --cx --cy`): **sem ela, o percentual do Depth Pro não é calculado**. Mesmo com parâmetros, a referência continua **derivada de GPS**, sujeita a incertezas e ao sincronismo provisório; não vira ground truth certificada por simples cálculo.

## Limitações importantes

1. Este gerador **não executa YOLO/Depth Pro novamente**; mostra dados originais já produzidos, com o vídeo inteiro como suporte visual.
2. A regressão transferida não foi validada para câmera/zoom deste novo voo e é repetida ao longo do segundo de origem com identificação explícita.
3. Apenas 126 quadros têm medição Depth Pro previamente computada; **exibir o indicador ao longo de 171,4 s não implica ter inferência em 5142 quadros**.
4. Os dois cenários de offset continuam hipóteses; não são sincronismo certificado.
5. Para resultados científicos de erro percentual verdadeiro, precisaríamos de referência independente câmera–drone temporal e geometricamente válida, ou demonstrar adequadamente um modelo de referência, com incerteza.

## Testes de software já realizados

- Verificação sintática de `gerar_dois_videos.py`.
- Teste funcional do pipeline de leitura, composição, auditoria e codificação de **ambos os MP4** com **vídeo artificial curto**: foi testada tanto a opção OpenCV quanto FFmpeg. Esses MP4 artificiais de teste **não são resultados do TCC** e não integram o pacote final.
- Foram geradas duas imagens estáticas de prévia com o frame exportado `MARCO_DECOLAGEM_00137.jpg`. Essas imagens são **simulação do layout de vídeo com uma imagem originalmente reduzida**, não frames extraídos de uma execução completa com MOV original.
