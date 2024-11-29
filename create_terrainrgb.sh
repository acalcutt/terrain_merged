#!/bin/bash

#custom version of rio rgbify which adds speed improvements is reccomended https://github.com/acalcutt/rio-rgbify

#set max file limit
ulimit -s 65536

JAXA_INPUT_DIR=./jaxa
ITALY_INPUT_DIR=./tinitaly
SWISS_INPUT_DIR=./swissalti
OUTPUT_DIR=./output
jaxavrt1=${OUTPUT_DIR}/jaxa.vrt
jaxavrt2=${OUTPUT_DIR}/jaxa_warp.vrt
italy1=${OUTPUT_DIR}/italy.vrt
italy2=${OUTPUT_DIR}/italy_warp.vrt
swiss1=${OUTPUT_DIR}/swiss.vrt
swiss2=${OUTPUT_DIR}/swiss_warp.vrt
outvrt=${OUTPUT_DIR}/out.vrt
mbtiles=${OUTPUT_DIR}/jaxa_swiss_italy_terrainrgb_z0-Z12_webp_lanczos.mbtiles


[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }


#Jaxa VRT (Note: This dataset needs to be converted from Int16 to Float32 first with 'convert_jaxa_images.sh' to fix the error "Warning 1: gdalbuildvrt does not support heterogeneous band data type: expected Int16, got Float32. Skipping ./output/swiss_warp.vrt")
#gdalbuildvrt -overwrite -srcnodata -9999 -vrtnodata -9999 ${jaxavrt1} ${JAXA_INPUT_DIR}/*_DSM.tif
gdalbuildvrt -overwrite -resolution highest -r lanczos -te -10.0 30.0 25.0 50.0 -srcnodata -9999 -vrtnodata -9999 ${jaxavrt1} ${JAXA_INPUT_DIR}/*_DSM.tif
gdalwarp -r lanczos -t_srs EPSG:3857 -dstnodata 0 ${jaxavrt1} ${jaxavrt2}

#Italy VRT
gdalbuildvrt -overwrite -resolution highest -r lanczos ${italy1} ${ITALY_INPUT_DIR}/*.tif
gdalwarp -r lanczos -t_srs EPSG:3857 -dstnodata 0 ${italy1} ${italy2}

#Swiss VRT
gdalbuildvrt -overwrite -resolution highest -r lanczos ${swiss1} ${SWISS_INPUT_DIR}/*.tif
gdalwarp -r lanczos -t_srs EPSG:3857 -dstnodata 0 ${swiss1} ${swiss2}

#Create an ordered list of VRTs. The order matters, the vrt lower in the list should take priority
rm filenames.txt
printf '%s\n' ${jaxavrt2} >filenames.txt
printf '%s\n' ${italy2} >>filenames.txt
printf '%s\n' ${swiss2} >>filenames.txt

#Create terrain mbtiles 
gdalbuildvrt -overwrite -resolution highest -r lanczos ${outvrt} -input_file_list filenames.txt
rio rgbify -b -10000 -i 0.1 --min-z 0 --max-z 12 -j 24 --format webp ${outvrt} ${mbtiles}

sqlite3 ${mbtiles} 'CREATE UNIQUE INDEX tile_index on tiles (zoom_level, tile_column, tile_row);'
sqlite3 ${mbtiles} 'UPDATE metadata SET value = "jaxa_swiss_italy_terrainrgb_z0-Z12_webp" WHERE name = "name" AND value = "";'
sqlite3 ${mbtiles} 'UPDATE metadata SET value = "JAXA AW3D30 (2024), swissALTI3D (2024), and Tinitaly  (2023) converted with rio rgbify" WHERE name = "description";'
sqlite3 ${mbtiles} 'UPDATE metadata SET value = "webp" WHERE name = "format";'
sqlite3 ${mbtiles} 'UPDATE metadata SET value = "1" WHERE name = "version";'
sqlite3 ${mbtiles} 'UPDATE metadata SET value = "baselayer" WHERE name = "type";'
sqlite3 ${mbtiles} "INSERT INTO metadata (name,value) VALUES('attribution','<a href=https://earth.jaxa.jp/en/data/policy/>JAXA AW3D30 (2024)</a> | <a href=https://www.swisstopo.admin.ch/en/height-model-swissalti3d>swissALTI3D (2024)</a>'); | <a href=https://tinitaly.pi.ingv.it/>Tinitaly (2023)</a>');"
sqlite3 ${mbtiles} "INSERT INTO metadata (name,value) VALUES('minzoom','0');"
sqlite3 ${mbtiles} "INSERT INTO metadata (name,value) VALUES('maxzoom','12');"
sqlite3 ${mbtiles} "INSERT INTO metadata (name,value) VALUES('bounds','-180,-90,180,90');"
sqlite3 ${mbtiles} "INSERT INTO metadata (name,value) VALUES('center','0,0,5');"

