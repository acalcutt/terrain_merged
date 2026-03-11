#!/bin/bash

# --- Configuration ---
USERNAME="jaxa_account"
PASSWORD="jaxa_password"
BASE_URL="https://www.eorc.jaxa.jp/ALOS/en/aw3d30/data/"
INDEX_URL="${BASE_URL}index.htm"
COOKIE_FILE="jaxa_cookies.txt"
OUTPUT_FILE="file_list_zip_jaxa.txt"  # Updated filename

echo "[*] Connecting to JAXA and fetching index..."
INDEX_HTML=$(curl -s --user "$USERNAME:$PASSWORD" --cookie-jar "$COOKIE_FILE" "$INDEX_URL")

# Extract grid names (e.g., n080w030_n090e000)
GRID_LIST=$(echo "$INDEX_HTML" | grep -oP 'href="\./html_v2404/\K[^"]+(?=\.htm)')

if [ -z "$GRID_LIST" ]; then
    echo "[!] Error: No grids found. Check credentials or URL."
    exit 1
fi

echo "[*] Extracting ZIP URLs from XML files..."

# This line OVERWRITES the file (truncates it) so it's fresh for this run
> "$OUTPUT_FILE"

for grid in $GRID_LIST; do
    # Convert to UPPERCASE for the XML path
    GRID_UPPER=$(echo "$grid" | tr '[:lower:]' '[:upper:]')
    XML_URL="${BASE_URL}html_v2404/xml/${GRID_UPPER}_5_5.xml"
    
    # Fetch XML and extract zip links - using >> here to add each grid's 
    # links to the now-empty file
    curl -sL -f --user "$USERNAME:$PASSWORD" --cookie "$COOKIE_FILE" "$XML_URL" | \
    grep -oP 'https?://[a-zA-Z0-9./_-]+\.zip' >> "$OUTPUT_FILE"
    
    echo "  > Processed: $GRID_UPPER"
done

echo "[+] Done! Created $OUTPUT_FILE with $(wc -l < $OUTPUT_FILE) links."
rm "$COOKIE_FILE"
