# Materiais suplementares — Google Drive

[Pasta principal](https://drive.google.com/drive/folders/1Rk8uiL-aYO58WyFALP71eKlLxL9mtjuJ). Links publicados com autorização expressa do autor em 05/11/2026. A divulgação dos links não substitui as licenças dos materiais de terceiros.

| Material | Link | Estado da verificação |
|---|---|---|
| Detector best.pt | [Arquivo](https://drive.google.com/file/d/1JLCl_LLR5cV4wROwWfqvDhIZNg90s_Pt/view) | Baixado; SHA-256 coincide com o registro histórico |
| Depth Pro | [Arquivo](https://drive.google.com/file/d/16rMropPr7fG5I4SvjnWnz-TAFHEDgsZ8/view) | Localizado; hash e identidade histórica ainda não verificados |
| Vídeo Farol | [Arquivo](https://drive.google.com/file/d/14NcZVEYLTC39N6xAPMMdUQCW8I5xci6G/view) | Nome: video_final_farol.mov; confirmar equivalência com a entrada histórica |
| Vídeo segundo voo | [Arquivo](https://drive.google.com/file/d/19iqaDQylxnRCsIGqUBQYIjekryvSu6jz/view) | IMG_5962_editado.mov; hash ainda não conferido |
| Dataset próprio | [Pasta](https://drive.google.com/drive/folders/1xkUs16ZfIzqc_rNjZK22lfyly0ro1Bqs) | Subpastas images e labels localizadas; completude dos splits não auditada |
| Ensaio iPhone XR | [Pasta](https://drive.google.com/drive/folders/1NRC_Me97WegCeQ9ULlBHC2KQHx0QnQ1K) | IMG_2860.MOV e CSV; não comprova recuperação do conjunto de 34 imagens |
| Telemetria Farol | [CSV](https://drive.google.com/file/d/174A4G5aGyCk7Sfdt1NNrp_9mkxvriTd6/view) | Para reprodução numérica, usar a versão tratada do repositório |
| Telemetria segundo voo | [CSV corrigido](https://drive.google.com/file/d/1qPRQw1zJOkUmBi_o19rPdVUh5CkaLP11/view) | Confirmar configuração de sincronismo antes de nova inferência |

## Instalação

1. Baixe best.pt e coloque em models/best.pt. SHA-256 verificado:
   2ca8f89b9d946a6a06a12177db471cb7419b69b4a25ce619cc608c55267a61d8.
2. O peso Depth Pro deve ficar em external/ml-depth-pro/checkpoints/depth_pro.pt. Registre o commit do código e o hash do peso utilizado. O arquivo fornecido não foi comprovado como idêntico ao checkpoint histórico.
3. Não extraia arquivos .pt: o formato PyTorch pode aparecer como arquivo compactado no Drive.
4. Confira o hash do vídeo Farol em data/external_assets.json antes de colocá-lo em inputs/video/farol.mov. O hash registrado é o histórico, não uma verificação do arquivo agora compartilhado. Se diferir, investigue edição/recompressão; não altere o registro histórico silenciosamente.
5. Configure o caminho de IMG_5962_editado.mov para o segundo voo e utilize o CSV correspondente.
6. Para o dataset, conserve as divisões e compare os arquivos com os manifestos recuperados antes de afirmar reprodução integral do treinamento.

No Windows PowerShell:

```powershell
Get-FileHash .\models\best.pt -Algorithm SHA256
```

No Colab, monte o Drive e copie os arquivos para os caminhos indicados pelo notebook. Uma pasta compartilhada pode exigir adicionar um atalho ao Meu Drive. O notebook 01 reproduz os números arquivados sem baixar pesos ou vídeos.

## Limites desta atualização

A listagem das pastas foi acessada e o best.pt foi baixado e validado. Os vídeos grandes e o Depth Pro não tiveram download integral/hash conferidos. As 274 imagens antes apontadas como ausentes ainda precisam de confronto com o inventário. Os dois vídeos anotados finais precisam ser identificados explicitamente: o nome video_final_farol.mov não comprova que seja uma saída anotada. A inferência completa GPU/Colab continua pendente.
