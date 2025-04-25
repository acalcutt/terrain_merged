#!/bin/bash

#custom version of rio rgbify which adds speed improvements is reccomended https://github.com/acalcutt/rio-rgbify/tree/merge

INPUT_DIR=./download
OUTPUT_DIR=./output

[[ $THREADS ]] || THREADS=16
[[ $BATCH ]] || BATCH=50
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=13
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=cubic

BASENAME=SONNY_DEM_2024_Europe_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
vrtfile=${OUTPUT_DIR}/${BASENAME}.vrt
mbtiles=${OUTPUT_DIR}/${BASENAME}.mbtiles
vrtfile2=${OUTPUT_DIR}/${BASENAME}_warp.vrt

[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

gdalbuildvrt -overwrite -resolution highest -r $RESAMPLING -srcnodata -9999 -vrtnodata -9999 ${vrtfile} ${INPUT_DIR}/*.hgt
gdalwarp -r $RESAMPLING -t_srs EPSG:3857 -dstnodata 0 ${vrtfile} ${vrtfile2}
rio rgbify -v -e terrarium --min-z $MINZOOM --max-z $MAXZOOM -j $THREADS --batch-size $BATCH --resampling $RESAMPLING --format $FORMAT ${vrtfile2} ${mbtiles}
