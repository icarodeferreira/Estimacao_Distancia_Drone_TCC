# Preparação para GitHub — 17/10/2026

O ZIP principal recuperado tinha 46.601.099 bytes e estava truncado durante depth_all_frames.csv, sem diretório central. Foram recuperados 825 arquivos pelos cabeçalhos locais, com CRC verificado para cada arquivo completo. Não foi tratado como um ZIP íntegro. Os CSVs do Farol foram recuperados da cópia histórica local; o pós-processamento foi extraído novamente do notebook original e confrontado com as predições arquivadas. Rotinas auxiliares foram reconstruídas nesta preparação e têm validação própria, não identidade binária presumida com o pacote anterior.

A telemetria pública do segundo voo contém somente time_s, height_m, vps_height_m, velocity_z_ms e flight_mode. A redução altera o hash do arquivo, preservando os valores usados na integração. Coordenadas geográficas, demais metadados, imagens, vídeos, pesos e capítulos não integram esta branch. Os CSVs de inferência maiores estão em gzip sem alteração do conteúdo descomprimido.
