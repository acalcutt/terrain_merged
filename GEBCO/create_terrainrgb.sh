#!/bin/bash

#custom version of rio rgbify which adds speed improvements is reccomended https://github.com/acalcutt/rio-rgbify/tree/merge

INPUT_DIR=./gebco
OUTPUT_DIR=./output

[[ $THREADS ]] || THREADS=16
[[ $BATCH ]] || BATCH=32
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=8
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=cubic
[[ $BASE_VALUE ]] || BASE_VALUE=-10000
[[ $INTERVAL ]] || INTERVAL=0.1

BASENAME=GEBCO_2024_TerrainRGB_${MINZOOM}-${MAXZOOM}_${RESAMPLING}_${FORMAT}
vrtfile=${OUTPUT_DIR}/${BASENAME}.vrt
vrtfile2=${OUTPUT_DIR}/${BASENAME}_warp.vrt
mbtiles=${OUTPUT_DIR}/${BASENAME}.mbtiles

[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" ${vrtfile} ${INPUT_DIR}/*.tif
gdalwarp -r "$RESAMPLING" -s_srs epsg:4326 -t_srs EPSG:3857 -dstnodata "$BASE_VALUE" ${vrtfile} ${vrtfile2}
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" ${vrtfile2} ${mbtiles}

