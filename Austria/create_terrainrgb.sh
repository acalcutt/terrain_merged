#!/bin/bash

#custom version of rio rgbify which adds speed improvements is reccomended https://github.com/acalcutt/rio-rgbify/tree/merge

INPUT_DIR=./austria
OUTPUT_DIR=./output

[[ $THREADS ]] || THREADS=12
[[ $BATCH ]] || BATCH=25
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=15
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=lanczos

BASENAME=Austria_2024_TerrainRGB_z${MINZOOM}-z${MAXZOOM}_${RESAMPLING}_${FORMAT}
vrtfile=${OUTPUT_DIR}/${BASENAME}.vrt
mbtiles=${OUTPUT_DIR}/${BASENAME}.mbtiles
vrtfile2=${OUTPUT_DIR}/${BASENAME}_warp.vrt

[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

#set max file limit
ulimit -s 65536

gdalbuildvrt -overwrite -resolution highest -r lanczos ${vrtfile} ${INPUT_DIR}/*.tif
gdalwarp -r lanczos -s_srs EPSG:3035 -t_srs EPSG:3857 -dstnodata 0 ${vrtfile} ${vrtfile2}
rio rgbify -v -b -10000 -i 0.1 --min-z $MINZOOM --max-z $MAXZOOM -j $THREADS --batch-size $BATCH --resampling $RESAMPLING --format $FORMAT ${vrtfile2} ${mbtiles}
