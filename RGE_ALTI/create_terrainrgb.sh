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

find "${INPUT_DIR}" -name "*_warped_EPSG3857.tif" > "${OUTPUT_DIR}/warped.txt"

# France & Corsica (Combined)
BASENAME=RGE_Alti_FranceCorsica_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
final_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"
WEST_3857=-573295.3775853589
SOUTH_3857=5059656.78801645
EAST_3857=1065327.5268916283
NORTH_3857=6639001.663761314
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" -te "${WEST_3857}" "${SOUTH_3857}" "${EAST_3857}" "${NORTH_3857}" "${final_vrt}" -input_file_list "${OUTPUT_DIR}/warped.txt"
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" "${final_vrt}" "${mbtiles}"

# Saint Pierre and Miquelon
BASENAME=RGE_Alti_SPM_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
final_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"
WEST_3857=-6292890.814543755
SOUTH_3857=5899738.2348553855
EAST_3857=-6241683.848778849
NORTH_3857=5966592.351410026
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" -te "${WEST_3857}" "${SOUTH_3857}" "${EAST_3857}" "${NORTH_3857}" "${final_vrt}" -input_file_list "${OUTPUT_DIR}/warped.txt"
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" "${final_vrt}" "${mbtiles}"

# Caribbean Islands
BASENAME=RGE_Alti_Caribbean_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
final_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"
WEST_3857=-7030939.038503159
SOUTH_3857=1617849.359942787
EAST_3857=-6768225.040231032
NORTH_3857=2052770.4405624238
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" -te "${WEST_3857}" "${SOUTH_3857}" "${EAST_3857}" "${NORTH_3857}" "${final_vrt}" -input_file_list "${OUTPUT_DIR}/warped.txt"
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" "${final_vrt}" "${mbtiles}"

# South America (Guyana)
BASENAME=RGE_Alti_Guyana_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
final_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"
WEST_3857=-6079157.392220669
SOUTH_3857=233823.2881134177
EAST_3857=-5745198.919840849
NORTH_3857=642283.0496044686
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" -te "${WEST_3857}" "${SOUTH_3857}" "${EAST_3857}" "${NORTH_3857}" "${final_vrt}" -input_file_list "${OUTPUT_DIR}/warped.txt"
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" "${final_vrt}" "${mbtiles}"

# Indian Ocean Islands
BASENAME=RGE_Alti_Indian_Ocean_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
final_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"
WEST_3857=5010490.2806052435
SOUTH_3857=-2439638.726529993
EAST_3857=6217193.56080433
NORTH_3857=-1417491.8275866346
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" -te "${WEST_3857}" "${SOUTH_3857}" "${EAST_3857}" "${NORTH_3857}" "${final_vrt}" -input_file_list "${OUTPUT_DIR}/warped.txt"
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" "${final_vrt}" "${mbtiles}"
