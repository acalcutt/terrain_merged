#!/bin/bash

# --- Configuration ---
USERNAME="jaxa_account"
PASSWORD="jaxa_password"
INPUT_FILE="file_list_zip_jaxa.txt" # Updated filename
DL_DIR="download_jaxa"
EXTRACT_DIR="jaxa"

mkdir -p "$DL_DIR" "$EXTRACT_DIR"

# --- Functions ---
mycurl() {
    local url=$1
    local user=$2
    local pass=$3
    local dl_dir=$4
    local filename=$(basename "$url")
    
    if [ ! -f "$dl_dir/$filename" ]; then
        echo "Downloading $filename..."
        curl -sL --user "$user:$pass" -o "$dl_dir/$filename" "$url"
    else
        echo "$filename already exists, skipping download."
    fi
}

myunzip() {
    local zipfile=$1
    local dl_dir=$2
    local target_dir=$3
    local full_path="$dl_dir/$zipfile"
    
    if ! unzip -t "$full_path" &>/dev/null; then
        echo "ERROR: $full_path is corrupt, deleting!"
        rm -f "$full_path"
        return 1
    fi

    unzip -j -o "$full_path" "*_DSM.tif" -d "$target_dir"
}

export -f mycurl myunzip

# --- Execution ---
if [ ! -f "$INPUT_FILE" ]; then
    echo "[!] Error: $INPUT_FILE not found."
    exit 1
fi

echo "[*] Starting parallel downloads..."
xargs -P 8 -a "$INPUT_FILE" -I {} bash -c "mycurl '{}' '$USERNAME' '$PASSWORD' '$DL_DIR'"

echo "[*] Starting parallel extraction..."
ls "$DL_DIR" | xargs -P 8 -I {} bash -c "myunzip '{}' '$DL_DIR' '$EXTRACT_DIR'"

echo "[+] Process complete."
