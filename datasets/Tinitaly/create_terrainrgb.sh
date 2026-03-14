#!/bin/bash

#custom version of rio rgbify which adds speed improvements is reccomended https://github.com/acalcutt/rio-rgbify/tree/merge

INPUT_DIR=./tinitaly
OUTPUT_DIR=./output

[[ $THREADS ]] || THREADS=12
[[ $BATCH ]] || BATCH=1
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=15
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=lanczos
[[ $COMMON_SRS ]] || COMMON_SRS="EPSG:4326"
[[ $BASE_VALUE ]] || BASE_VALUE=-10000
[[ $INTERVAL ]] || INTERVAL=0.1
# Note: If generating a standalone MBTiles source (not merging later),
# setting NODATA=0 via env var is recommended for a more visually correct map.
[[ $NODATA ]] || NODATA=$BASE_VALUE

BASENAME=TinItally_2024_TerrainRGB_${MINZOOM}-${MAXZOOM}_${FORMAT}
vrtfile=${OUTPUT_DIR}/${BASENAME}.vrt
mbtiles=${OUTPUT_DIR}/${BASENAME}.mbtiles
vrtfile2=${OUTPUT_DIR}/${BASENAME}_warp.vrt

[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

#set max file limit
ulimit -s 65536

gdalbuildvrt -overwrite -resolution highest -r lanczos ${vrtfile} ${INPUT_DIR}/*.tif
gdalwarp -r lanczos -t_srs "$COMMON_SRS" -dstnodata "$NODATA" ${vrtfile} ${vrtfile2}
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z $MINZOOM --max-z $MAXZOOM -j $THREADS --batch-size $BATCH --resampling $RESAMPLING --format $FORMAT ${vrtfile2} ${mbtiles}
