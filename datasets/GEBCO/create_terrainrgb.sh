#!/bin/bash

#custom version of rio rgbify which adds speed improvements is reccomended https://github.com/acalcutt/rio-rgbify/tree/merge

INPUT_DIR=./gebco
OUTPUT_DIR=./output

[[ $THREADS ]] || THREADS=16
[[ $BATCH ]] || BATCH=1
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=8
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=cubic
[[ $COMMON_SRS ]] || COMMON_SRS="EPSG:4326"
[[ $BASE_VALUE ]] || BASE_VALUE=-10000
[[ $INTERVAL ]] || INTERVAL=0.1
[[ $NODATA ]] || NODATA=$BASE_VALUE

BASENAME=GEBCO_2025_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
vrtfile=${OUTPUT_DIR}/${BASENAME}.vrt
vrtfile2=${OUTPUT_DIR}/${BASENAME}_warp.vrt
mbtiles=${OUTPUT_DIR}/${BASENAME}.mbtiles

[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" ${vrtfile} ${INPUT_DIR}/*.tif
gdalwarp -r "$RESAMPLING" -s_srs epsg:4326 -t_srs "$COMMON_SRS" -dstnodata "$NODATA" ${vrtfile} ${vrtfile2}
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" ${vrtfile2} ${mbtiles}


sqlite3 ${mbtiles} "CREATE UNIQUE INDEX IF NOT EXISTS tile_index on tiles (zoom_level, tile_column, tile_row);"
sqlite3 ${mbtiles} "UPDATE metadata SET value = 'GEBCO 2025 Grid converted with rio-rgbify' WHERE name = 'description';"
sqlite3 ${mbtiles} "UPDATE metadata SET value = 'baselayer' WHERE name = 'type';"
sqlite3 ${mbtiles} "INSERT INTO metadata (name,value) VALUES('attribution','<a href=\"https://www.gebco.net/\">GEBCO 2025</a>');"
