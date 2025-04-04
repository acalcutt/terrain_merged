#!/bin/bash

# Set defaults for rio-rgbify
[[ $THREADS ]] || THREADS=16
[[ $BATCH ]] || BATCH=5
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=15
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=cubic
[[ $INPUT_DIR ]] || INPUT_DIR=./france_warped
[[ $OUTPUT_DIR ]] || OUTPUT_DIR=./output
[[ $BASE_VALUE ]] || BASE_VALUE=-10000
[[ $INTERVAL ]] || INTERVAL=0.1

[ -d "$OUTPUT_DIR" ] || mkdir -p "$OUTPUT_DIR" || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

find "${INPUT_DIR}" -name "*_warped_EPSG4326.tif" > "${OUTPUT_DIR}/warped.txt"

# France & Corsica (Combined)
BASENAME=RGE_Alti_FranceCorsica_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
final_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"
WEST_4326=-5.15
SOUTH_4326=41.32
EAST_4326=9.57
NORTH_4326=51.10
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" -te "${WEST_4326}" "${SOUTH_4326}" "${EAST_4326}" "${NORTH_4326}" "${final_vrt}" -input_file_list "${OUTPUT_DIR}/warped.txt"
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" "${final_vrt}" "${mbtiles}"

# Saint Pierre and Miquelon
BASENAME=RGE_Alti_SPM_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
final_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"
WEST_4326=-56.53
SOUTH_4326=46.74
EAST_4326=-56.07
NORTH_4326=47.15
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" -te "${WEST_4326}" "${SOUTH_4326}" "${EAST_4326}" "${NORTH_4326}" "${final_vrt}" -input_file_list "${OUTPUT_DIR}/warped.txt"
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" "${final_vrt}" "${mbtiles}"

# Caribbean Islands
BASENAME=RGE_Alti_Caribbean_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
final_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"
WEST_4326=-63.16
SOUTH_4326=14.38
EAST_4326=-60.80
NORTH_4326=18.13
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" -te "${WEST_4326}" "${SOUTH_4326}" "${EAST_4326}" "${NORTH_4326}" "${final_vrt}" -input_file_list "${OUTPUT_DIR}/warped.txt"
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" "${final_vrt}" "${mbtiles}"

# South America (Guyana)
BASENAME=RGE_Alti_Guyana_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
final_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"
WEST_4326=-54.61
SOUTH_4326=2.10
EAST_4326=-51.61
NORTH_4326=5.76
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" -te "${WEST_4326}" "${SOUTH_4326}" "${EAST_4326}" "${NORTH_4326}" "${final_vrt}" -input_file_list "${OUTPUT_DIR}/warped.txt"
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" "${final_vrt}" "${mbtiles}"

# Indian Ocean Islands
BASENAME=RGE_Alti_Indian_Ocean_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
final_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"
WEST_4326=45.01
SOUTH_4326=-21.40
EAST_4326=55.85
NORTH_4326=-12.63
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" -te "${WEST_4326}" "${SOUTH_4326}" "${EAST_4326}" "${NORTH_4326}" "${final_vrt}" -input_file_list "${OUTPUT_DIR}/warped.txt"
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" "${final_vrt}" "${mbtiles}"
