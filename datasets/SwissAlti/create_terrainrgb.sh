#!/bin/bash

# Custom version of rio rgbify which adds speed improvements is required:
# https://github.com/acalcutt/rio-rgbify/tree/merge

# --- Paths ---
INPUT_DIR=./swissalti
OUTPUT_DIR=./output

# --- Options (Defaults) ---
[[ $THREADS ]] || THREADS=12
[[ $BATCH ]] || BATCH=1
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=16
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=cubic
[[ $COMMON_SRS ]] || COMMON_SRS="EPSG:4326"
[[ $BASE_VALUE ]] || BASE_VALUE=-10000
[[ $INTERVAL ]] || INTERVAL=0.1
# Note: If generating a standalone MBTiles source (not merging later),
# setting NODATA=0 via env var is recommended for a more visually correct map.
[[ $NODATA ]] || NODATA=$BASE_VALUE

# --- File Naming ---
BASENAME=SWISS_Alti_2024_TerrainRGB_${MINZOOM}-${MAXZOOM}_${FORMAT}
vrtfile=${OUTPUT_DIR}/${BASENAME}.vrt
vrtfile2=${OUTPUT_DIR}/${BASENAME}_warp.vrt
mbtiles=${OUTPUT_DIR}/${BASENAME}.mbtiles

# Create output directory
[ -d "$OUTPUT_DIR" ] || mkdir -p "$OUTPUT_DIR" || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

# Set max file limit
ulimit -s 65536

# 1. Build the VRT
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" \
    "${vrtfile}" "${INPUT_DIR}"/*.tif

# 2. Warp to common SRS
gdalwarp -r "$RESAMPLING" -t_srs "$COMMON_SRS" -dstnodata "$NODATA" \
    "${vrtfile}" "${vrtfile2}"

# 3. Convert to Terrain-RGB MBTiles
rio rgbify -v \
    -b "$BASE_VALUE" \
    -i "$INTERVAL" \
    --min-z "$MINZOOM" \
    --max-z "$MAXZOOM" \
    -j "$THREADS" \
    --batch-size "$BATCH" \
    --resampling "$RESAMPLING" \
    --format "$FORMAT" \
    "${vrtfile2}" "${mbtiles}"