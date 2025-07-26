#!/bin/bash

#custom version of rio rgbify which adds speed improvements is reccomended https://github.com/acalcutt/rio-rgbify/tree/merge

INPUT_DIR=./italy_sudtirol
OUTPUT_DIR=./output

[[ $THREADS ]] || THREADS=12
[[ $BATCH ]] || BATCH=1
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=16
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=cubic
[[ $COMMON_SRS ]] || COMMON_SRS="EPSG:4326"
[[ $BASE_VALUE ]] || BASE_VALUE=-10000
[[ $INTERVAL ]] || INTERVAL=0.1
[[ $NODATA ]] || NODATA=$BASE_VALUE

BASENAME=Italy_Sudtirol_TerrainRGB_z${MINZOOM}-z${MAXZOOM}_${RESAMPLING}_${FORMAT}
vrtfile=${OUTPUT_DIR}/${BASENAME}.vrt
mbtiles=${OUTPUT_DIR}/${BASENAME}.mbtiles
vrtfile2=${OUTPUT_DIR}/${BASENAME}_warp.vrt

[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

gdalbuildvrt -overwrite -resolution highest -r $RESAMPLING ${vrtfile} ${INPUT_DIR}/*.tif
gdalwarp -r $RESAMPLING -s_srs EPSG:25832 -t_srs $COMMON_SRS -dstnodata $NODATA ${vrtfile} ${vrtfile2}
rio rgbify -v -b $BASE_VALUE -i $INTERVAL --min-z $MINZOOM --max-z $MAXZOOM -j $THREADS --batch-size $BATCH --resampling $RESAMPLING --format $FORMAT ${vrtfile2} ${mbtiles}
