# Rastreabilidade da referência e porcentagens

**Referência efetivamente disponível:** coluna `distance_home_corrigida_m` do CSV corrigido. Esta representa a distância horizontal drone–HOME derivada do GPS. Não é diretamente a distância radial câmera–drone. Existem momentos próximos do HOME em que a referência é inferior a 2 m, sendo inviável apresentar porcentagens estáveis e significativas: o software escreve N/D nesses casos.

**Regressão:** `distancia_regressao_exploratoria_m`, modelo global calibrado em outra aquisição, repetido por segundo conforme T17; sem validação métrica no novo voo.

**Depth Pro:** `Z_axial_p25_m`, 126 medições em ROI não validada; a dimensão é profundidade axial e não alcance radial. Um valor retido visualmente por 1 segundo é uma última amostra, e não estimativa nova.

**Sincronização:** offset exploratório +10,566666667 s (alternativa histórica +11,2 s). PTS do MOV íntegros (5142 quadros), mas a sincronização com a telemetria ainda não é certificada. Nenhuma variável do modelo ajusta automaticamente o offset para melhorar erro de IA.

**Importância científica:** os percentuais em modo HOME indicam discrepância numérica relativa ao HOME, não erro de distância entre câmera e drone. Portanto, não reaproveitar esses percentuais em resultados estatísticos de erro de alcance do TCC. O modo `camera` está preparado, mas exige coordenadas e alturas verificadas; a adequação de erro real exigirá mais que isso.
