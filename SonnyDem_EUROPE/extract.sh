#!/bin/bash

cd  download

# Extract all zip files in the folder
find . -type f -name "*.zip" -exec 7z x {} \;
