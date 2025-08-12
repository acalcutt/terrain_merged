#!/bin/bash

#custom version of rio rgbify which adds speed improvements is reccomended https://github.com/acalcutt/rio-rgbify/tree/merge

INPUT_DIR=./opendtm_de
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

BASENAME=OpenDTM_DE_2024_TerrainRGB_z${MINZOOM}-z${MAXZOOM}_${RESAMPLING}_${FORMAT}
vrtfile=${OUTPUT_DIR}/${BASENAME}.vrt
mbtiles=${OUTPUT_DIR}/${BASENAME}.mbtiles
vrtfile2=${OUTPUT_DIR}/${BASENAME}_warp.vrt

[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

#set max file limit
ulimit -s 65536

# A handful of files in the OpenDTM_DE dataset are missing a CRS.
for file in "${INPUT_DIR}"/*.tif; do
    if [ -f "$file" ] && [ -z "$(gdalinfo "$file" | grep -i "coordinate system")" ]; then
        echo "Setting CRS for: $file"
        gdal_edit.py -a_srs EPSG:25832 "$file"
    fi
done

gdalbuildvrt -overwrite -resolution highest -r $RESAMPLING ${vrtfile} ${INPUT_DIR}/*.tif
# Some elevation data outside the administrative boundary is broken so we clip out to avoid weird artifacts
gdalwarp -r $RESAMPLING -s_srs EPSG:25832 -t_srs $COMMON_SRS -dstnodata $BASE_VALUE -cutline "$(dirname "$0")/germany.fgb" -crop_to_cutline ${vrtfile} ${vrtfile2}
rio rgbify -v -b $BASE_VALUE -i $INTERVAL --min-z $MINZOOM --max-z $MAXZOOM -j $THREADS --batch-size $BATCH --resampling $RESAMPLING --format $FORMAT ${vrtfile2} ${mbtiles}
