#!/bin/bash

INPUT_DIR=./spain
[ -d "$INPUT_DIR" ] || mkdir -p $INPUT_DIR || { echo "error: $INPUT_DIR " 1>&2; exit 1; }
cd $INPUT_DIR

# Define the range of numbers
START=9071136
END=9072659

# Set the number of parallel processes
# Adjust this number based on your system's capabilities and network bandwidth
PARALLEL_JOBS=10

# Create a sequence of numbers and pipe them to xargs for parallel execution
printf "%s\n" $(seq $START $END) | xargs -n 1 -P $PARALLEL_JOBS -I {} bash -c '
    # The curl command with placeholders for the file number
    # {} is a placeholder for the number passed from xargs
    curl '\''https://centrodedescargas.cnig.es/CentroDescargas/descargaDir'\'' \
      -H '\''Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'\'' \
      -H '\''Accept-Language: en-US,en;q=0.9'\'' \
      -H '\''Cache-Control: no-cache'\'' \
      -H '\''Connection: keep-alive'\'' \
      -H '\''Content-Type: application/x-www-form-urlencoded'\'' \
      -b '\''JSESSIONID=8A9CACDFCE1CCA479EB780052EDE459B'\'' \
      -H '\''Origin: https://centrodedescargas.cnig.es'\'' \
      -H '\''Pragma: no-cache'\'' \
      -H '\''Referer: https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec={}'\'' \
      -H '\''Sec-Fetch-Dest: document'\'' \
      -H '\''Sec-Fetch-Mode: navigate'\'' \
      -H '\''Sec-Fetch-Site: same-origin'\'' \
      -H '\''Sec-Fetch-User: ?1'\'' \
      -H '\''Upgrade-Insecure-Requests: 1'\'' \
      -H '\''User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'\'' \
      -H '\''sec-ch-ua: "Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"'\'' \
      -H '\''sec-ch-ua-mobile: ?0'\'' \
      -H '\''sec-ch-ua-platform: "Windows"'\'' \
      --data-raw '\''secuencial={}&secDescDirLA={}&codSerie=MDT05&codNumMD=&avisoLimiteFiles=&licenciaSeleccionada='\'' \
      --output {}.tif
'