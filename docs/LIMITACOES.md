# Limitações do estudo

A referência do Farol é nominal: combina telemetria e geometria informada. O ângulo horizontal desconhecido e os erros de posição, altura, focal, relógio e marcação visual não foram eliminados por uma referência metrológica independente. Concordância com essa referência não equivale a validação física das distâncias.

Depth Pro estima Z axial. Para uma câmera pinhole calibrada, um ponto de coordenadas normalizadas x=(u−cx)/fx e y=(v−cy)/fy teria R=Z sqrt(1+x²+y²). A conversão depende de intrínsecos, distorção, ponto escolhido e resolução. Aplicá-la indiscriminadamente a um percentil de uma ROI não transforma o estimador em alcance validado.

A regressão depende da dimensão aparente do drone. Modelo, atitude, orientação, lente, zoom, foco, resolução, distância e contaminação da caixa alteram a relação largura–distância. A calibração é de um voo; a validação temporal interna contém dependência entre observações. Selecionar o melhor dos oito modelos no mesmo conjunto também limita a interpretação de generalização. Há apenas dois segundos válidos acima de 40 m no suporte analisado.

A transformação XR provém de outro ensaio. É um comparador de transferência, sem garantia de aplicabilidade universal. O segundo voo tem hipóteses de sincronização e cobertura telemétrica, mas não referência independente de alcance; diferenças entre alturas sincronizadas não são erros de distância.

Revisão humana documentada é aceitável como procedimento metodológico. Deve indicar seleção da amostra, critérios, identificação do quadro, revisor e decisão. Amostras dirigidas ou corrigidas após inspeção não equivalem a teste cego aleatório; não misturar análise primária congelada e análise pós-hoc. Ausência de caixa, rejeição e falta de referência devem ser contabilizadas, nunca convertidas em zeros ou suprimidas silenciosamente.

Os pesos/modelos não foram reexecutados nesta entrega. A validação de CPU cobre reprodução analítica e rotinas auxiliares. O ambiente original completo, checkpoint Depth Pro histórico e parte das imagens não foram recuperados.
