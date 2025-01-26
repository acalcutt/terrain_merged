#!/bin/bash

# needs 'pip install gdown'

# Set the folder id here.
FOLDER_ID="0BxphPoRgwhnoWkRoTFhMbTM3RDA"

# Download the folder with gdown
gdown --folder  "$FOLDER_ID"

# Enter the downloaded folder
cd  "$FOLDER_ID"

# Extract all zip files in the folder
find . -type f -name "*.zip" -exec 7z x {} \;

echo "Extraction complete!"