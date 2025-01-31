#!/bin/bash

# Set defaults for rio-rgbify
[[ $THREADS ]] || THREADS=16
[[ $BATCH ]] || BATCH=32
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=15
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=cubic
[[ $INPUT_DIR ]] || INPUT_DIR=./france_warped
[[ $OUTPUT_DIR ]] || OUTPUT_DIR=./output
[[ $BASE_VALUE ]] || BASE_VALUE=-10000
[[ $INTERVAL ]] || INTERVAL=0.1
BASENAME=RGE_Alti_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
final_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"

[ -d "$OUTPUT_DIR" ] || mkdir -p "$OUTPUT_DIR" || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

find "${INPUT_DIR}" -name "*_warped_EPSG3857.tif" > "${OUTPUT_DIR}/warped.txt"
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" "${final_vrt}" -input_file_list "${OUTPUT_DIR}/warped.txt"

# convert that final raster into a mbtiles file
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" "${final_vrt}" "${mbtiles}"