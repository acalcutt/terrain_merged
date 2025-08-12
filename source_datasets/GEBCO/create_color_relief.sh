#!/usr/bin/env bash


INPUT_DIR=./gebco
OUTPUT_DIR=./output
vrtfile=${OUTPUT_DIR}/gebco_color_releif.vrt
vrtfile2=${OUTPUT_DIR}/gebco_color_releif2.vrt
vrtfile3=${OUTPUT_DIR}/gebco_color_releif3.vrt
mbtiles=${OUTPUT_DIR}/gebco_color_releif.mbtiles

[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

echo "Builing VRT"
gdalbuildvrt -overwrite ${vrtfile} ${INPUT_DIR}/*.tif
echo "Builing color-relief VRT"
gdaldem color-relief -of VRT ${vrtfile} -alpha ramp_bathymetry.ramp ${vrtfile2}
echo "Builing gdalwarp VRT"
gdalwarp -r cubic -s_srs epsg:4326 -t_srs EPSG:3857 ${vrtfile2} ${vrtfile3}
echo "Import VRT into MBTiles"
gdal_translate ${vrtfile3} ${mbtiles} -of MBTILES 
#echo "Backup Origional MBTiles file"
#cp ${mbtiles} ${mbtiles}.orig
echo "Create MBTiles Overview"
gdaladdo ${mbtiles}

sqlite3 ${mbtiles} 'CREATE UNIQUE INDEX tile_index on tiles (zoom_level, tile_column, tile_row);'
sqlite3 ${mbtiles} "UPDATE metadata SET value = 'GEBCO (2024) converted with gdaldem' WHERE name = 'description';"
sqlite3 ${mbtiles} "UPDATE metadata SET value = 'baselayer' WHERE name = 'type';"
sqlite3 ${mbtiles} "INSERT INTO metadata ('name','value') VALUES('attribution','GEBCO (2024)');"
sqlite3 ${mbtiles} "INSERT INTO metadata (name,value) VALUES('center','0,0,4');"