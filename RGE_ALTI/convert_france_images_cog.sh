#!/bin/bash
# Convert all files to a common Projected COG format
INPUT_DIR=./download_france
OUTPUT_DIR=./france_cog
COMMON_SRS="EPSG:3857"

function myconvert() {
    FILE=$1
    directory=$(dirname "$FILE")
    directory_name=$(basename "$directory")
    baseName=$(basename "$FILE")
    outFile="${OUTPUT_DIR}/${directory_name}-${baseName}.tif"
    if [[ ! -f $outFile ]]; then
        echo "Converting $FILE file to $outFile"
        if [[ $baseName =~ "LAMB93" ]]; then
            echo "Converting LAMB93 file $FILE to $outFile"
            gdal_translate -a_srs EPSG:2154 -of GTiff -ot Float32 -r lanczos $FILE $outFile
        elif [[ $baseName =~ "RGAF09UTM20" ]]; then
            echo "Converting RGAF09UTM20 file $FILE to $outFile"
            gdal_translate -a_srs EPSG:5490 -of GTiff -ot Float32 -r lanczos $FILE $outFile
        elif [[ $baseName =~ "WGS84UTM20" ]]; then
            echo "Converting WGS84UTM20 file $FILE to $outFile"
            gdal_translate -a_srs EPSG:32620 -of GTiff -ot Float32 -r lanczos $FILE $outFile
        elif [[ $baseName =~ "RGFG95UTM22" ]]; then
            echo "Converting RGFG95UTM22 file $FILE to $outFile"
            gdal_translate -a_srs EPSG:2972 -of GTiff -ot Float32 -r lanczos $FILE $outFile
        elif [[ $baseName =~ "RGM04UTM38S" ]]; then
            echo "Converting RGM04UTM38S file $FILE to $outFile"
            gdal_translate -a_srs EPSG:4471 -of GTiff -ot Float32 -r lanczos $FILE $outFile
        elif [[ $baseName =~ "RGR92UTM40S" ]]; then
            echo "Converting RGR92UTM40S file $FILE to $outFile"
            gdal_translate -a_srs EPSG:2975 -of GTiff -ot Float32 -r lanczos $FILE $outFile
        elif [[ $baseName =~ "RGSPM06U21" ]]; then
            echo "Converting RGSPM06U21 file $FILE to $outFile"
            gdal_translate -a_srs EPSG:4467 -of GTiff -ot Float32 -r lanczos $FILE $outFile
        fi
        
        #warp to new projection, add nodata
        gdalwarp -r lanczos -t_srs $COMMON_SRS -dstnodata -9999  ${outFile} "${outFile/.tif/_warped.tif}"
        
        # convert to COG
        gdal_translate -of COG "${outFile/.tif/_warped.tif}" "${outFile/.tif/_cog.tif}"
        rm "${outFile/.tif/_warped.tif}"
    fi
}

export -f myconvert

[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

# run the conversions in parallel using 8 threads/connections
find ${INPUT_DIR} -name *MNT*.asc | xargs -P 8 -I {} bash -c "myconvert '{}'"


# Set defaults for rio-rgbify
[[ $THREADS ]] || THREADS=16
[[ $BATCH ]] || BATCH=25
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=15
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=lanczos

BASENAME=RGE_Alti_TerrainRGB_${MINZOOM}-${MAXZOOM}_${FORMAT}
OUTPUT_DIR=./output
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
cog_dir=${OUTPUT_DIR}/cogs
final_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"

[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

#set max file limit
ulimit -s 65536

# build one single vrt out of the cogs. this will be fast because of cog
find ${OUTPUT_DIR}/../france_cog -name *_cog.tif > ${OUTPUT_DIR}/cogs.txt
gdalbuildvrt -overwrite -r lanczos ${final_vrt}  -input_file_list ${OUTPUT_DIR}/cogs.txt

# convert that final raster into a mbtiles file
rio rgbify -v -b -10000 -i 0.1 --min-z $MINZOOM --max-z $MAXZOOM -j $THREADS --batch-size $BATCH --resampling $RESAMPLING --format $FORMAT ${final_vrt} ${mbtiles}