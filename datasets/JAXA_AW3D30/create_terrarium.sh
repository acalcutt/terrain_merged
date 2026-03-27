#!/bin/bash

# Custom version of rio rgbify which adds speed improvements is required:
# https://github.com/acalcutt/rio-rgbify/tree/merge

# --- Paths ---
INPUT_DIR=./jaxa
OUTPUT_DIR=./output

# --- Options (Defaults) ---
[[ $THREADS ]] || THREADS=32
[[ $BATCH ]] || BATCH=1
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=12
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=cubic
[[ $COMMON_SRS ]] || COMMON_SRS="EPSG:4326"
[[ $BOUNDS ]] || BOUNDS="-180 -85.0511287798066 180 85.0511287798066"
[[ $BASE_VALUE ]] || BASE_VALUE=-32768
# Note: If generating a standalone MBTiles source (not merging later),
# setting NODATA=0 via env var is recommended for a more visually correct map.
[[ $NODATA ]] || NODATA=$BASE_VALUE

# --- File Naming ---



BASENAME=JAXA_AW3D30_2024_Terrarium_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
vrtfile=${OUTPUT_DIR}/${BASENAME}.vrt
vrtfile2=${OUTPUT_DIR}/${BASENAME}_warp.vrt
mbtiles=${OUTPUT_DIR}/${BASENAME}.mbtiles

# Create output directory
[ -d "$OUTPUT_DIR" ] || mkdir -p "$OUTPUT_DIR" || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

# Set max file limit to handle large JAXA tile counts
ulimit -s 65536

# 1. Build the VRT
# Map JAXA NoData from the source TIFs to the VRT
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" \
    -srcnodata -9999 -vrtnodata -9999 \
    "${vrtfile}" "${INPUT_DIR}"/*_DSM.tif

# 2. Warp to common SRS (Defaulting to EPSG:4326)
# We use -dstnodata "$NODATA" to match the Terrarium floor
gdalwarp -r "$RESAMPLING" -t_srs "$COMMON_SRS" -dstnodata "$NODATA" -te $BOUNDS "${vrtfile}" "${vrtfile2}"

# 3. Convert to Terrarium RGB MBTiles
# Note: -i (interval) and -b (base) are not used in terrarium mode
rio rgbify -v \
    -e terrarium \
    --min-z "$MINZOOM" \
    --max-z "$MAXZOOM" \
    -j "$THREADS" \
    --batch-size "$BATCH" \
    --resampling "$RESAMPLING" \
    --format "$FORMAT" \
    "${vrtfile2}" "${mbtiles}"