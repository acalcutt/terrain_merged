#!/bin/bash

# Define the directory to store files
INPUT_DIR="./spain"
[ -d "$INPUT_DIR" ] || mkdir -p "$INPUT_DIR" || { echo "error: $INPUT_DIR " 1>&2; exit 1; }
cd "$INPUT_DIR"

# Define the range of numbers
START=9071136
END=9072659

# Set the number of parallel processes. Adjust this number as needed.
PARALLEL_JOBS=10

# Define a function to handle the download process for a single file number
download_file() {
    local i=$1
    echo "Processing file number: $i"

    # Construct the URL for the referrer page
    local REFERER_URL="https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=$i"

    # Step 1: Fetch the webpage content to extract filename and year
    local PAGE_CONTENT=$(curl -sS "$REFERER_URL")

    # Step 2: Use grep and sed to extract the filename and year from the HTML
    local FILENAME=$(echo "$PAGE_CONTENT" | grep "Fichero:" | sed -n 's/.*<span class="breakWords">\([^<]*\)<\/span>.*/\1/p')
    local YEAR=$(echo "$PAGE_CONTENT" | awk '/Fecha:/ {getline; gsub(/^[ \t]+|[ \t]+$/, ""); print}' | tr -cd '[:digit:], ')

    # Check if we successfully extracted the year and filename
    if [[ -z "$FILENAME" || -z "$YEAR" ]]; then
        echo "Could not extract filename or year for $i. Skipping..."
        return 1
    fi

    # Construct the full destination path
    local DESTINATION_PATH="$YEAR/$FILENAME"

    # Check if the destination file already exists
    if [[ -f "$DESTINATION_PATH" ]]; then
        echo "File already exists: $DESTINATION_PATH. Skipping..."
        return 0
    fi

    # Create the destination directory based on the year
    # -p flag prevents an error if the directory already exists
    mkdir -p "$YEAR"

    # Step 3: Construct the final curl command with the extracted information
    # --output specifies the full path and filename for the downloaded file
    curl 'https://centrodedescargas.cnig.es/CentroDescargas/descargaDir' \
      -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7' \
      -H 'Accept-Language: en-US,en;q=0.9' \
      -H 'Cache-Control: no-cache' \
      -H 'Connection: keep-alive' \
      -H 'Content-Type: application/x-www-form-urlencoded' \
      -b 'JSESSIONID=8A9CACDFCE1CCA479EB780052EDE459B' \
      -H 'Origin: https://centrodedescargas.cnig.es' \
      -H 'Pragma: no-cache' \
      -H 'Referer: '"$REFERER_URL"'' \
      -H 'Sec-Fetch-Dest: document' \
      -H 'Sec-Fetch-Mode: navigate' \
      -H 'Sec-Fetch-Site: same-origin' \
      -H 'Sec-Fetch-User: ?1' \
      -H 'Upgrade-Insecure-Requests: 1' \
      -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36' \
      -H 'sec-ch-ua: "Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"' \
      -H 'sec-ch-ua-mobile: ?0' \
      -H 'sec-ch-ua-platform: "Windows"' \
      --data-raw 'secuencial='"$i"'&secDescDirLA='"$i"'&codSerie=MDT05&codNumMD=&avisoLimiteFiles=&licenciaSeleccionada=' \
      --output "$DESTINATION_PATH"
}
# Make the function available to child processes spawned by xargs
export -f download_file

# Create a sequence of numbers and pipe them to xargs for parallel execution
printf "%s\n" $(seq $START $END) | xargs -n 1 -P $PARALLEL_JOBS bash -c 'download_file "$@"' _
