#!/bin/bash

# Set defaults for rio-rgbify
[[ $THREADS ]] || THREADS=16
[[ $BATCH ]] || BATCH=32
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=15
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=cubic
[[ $INPUT_DIR ]] || INPUT_DIR=./download_france
[[ $WARP_OUTPUT_DIR ]] || WARP_OUTPUT_DIR=./france_warped
[[ $BASE_VALUE ]] || BASE_VALUE=-10000
[[ $INTERVAL ]] || INTERVAL=0.1
[[ $COMMON_SRS ]] || COMMON_SRS="EPSG:4326"

[ -d "$WARP_OUTPUT_DIR" ] || mkdir -p "$WARP_OUTPUT_DIR" || { echo "error: $WARP_OUTPUT_DIR " 1>&2; exit 1; }

function myconvert() {
  local COMMON_SRS=$0
  local WARP_OUTPUT_DIR=$1
  local RESAMPLING=$2
  local BASE_VALUE=$3
  local FILE=$4
    echo "myconvert function: COMMON_SRS='$COMMON_SRS', WARP_OUTPUT_DIR='$WARP_OUTPUT_DIR', RESAMPLING='$RESAMPLING', BASE_VALUE='$BASE_VALUE', FILE='$FILE'"
  local directory=$(dirname "$FILE")
  local directory_name=$(basename "$directory")
  local baseName=$(basename "$FILE")

  local outFile="${WARP_OUTPUT_DIR}/${directory_name}-${baseName%.*}.tif"
  local outFileWarpped="${WARP_OUTPUT_DIR}/${directory_name}-${baseName%.*}_warped_EPSG3857.tif"


    if [[ ! -f $outFileWarpped ]]; then
         echo "Converting $FILE"
        if [[ $baseName =~ "LAMB93" ]]; then
          echo "Converting LAMB93 file $FILE to $outFile"
          gdal_translate -a_srs EPSG:2154 -of GTiff -ot Float32 -r "$RESAMPLING"  "$FILE" "$outFile"
        elif [[ $baseName =~ "RGAF09UTM20" ]]; then
          echo "Converting RGAF09UTM20 file $FILE to $outFile"
          gdal_translate -a_srs EPSG:5490 -of GTiff -ot Float32 -r "$RESAMPLING" "$FILE" "$outFile"
        elif [[ $baseName =~ "WGS84UTM20" ]]; then
          echo "Converting WGS84UTM20 file $FILE to $outFile"
           gdal_translate -a_srs EPSG:32620 -of GTiff -ot Float32 -r "$RESAMPLING"  "$FILE" "$outFile"
        elif [[ $baseName =~ "RGFG95UTM22" ]]; then
          echo "Converting RGFG95UTM22 file $FILE to $outFile"
          gdal_translate -a_srs EPSG:2972 -of GTiff -ot Float32 -r "$RESAMPLING"  "$FILE" "$outFile"
        elif [[ $baseName =~ "RGM04UTM38S" ]]; then
          echo "Converting RGM04UTM38S file $FILE to $outFile"
          gdal_translate -a_srs EPSG:4471 -of GTiff -ot Float32 -r "$RESAMPLING"  "$FILE" "$outFile"
        elif [[ $baseName =~ "RGR92UTM40S" ]]; then
           echo "Converting RGR92UTM40S file $FILE to $outFile"
          gdal_translate -a_srs EPSG:2975 -of GTiff -ot Float32 -r "$RESAMPLING" "$FILE" "$outFile"
        elif [[ $baseName =~ "RGSPM06U21" ]]; then
           echo "Converting RGSPM06U21 file $FILE to $outFile"
          gdal_translate -a_srs EPSG:4467 -of GTiff -ot Float32 -r "$RESAMPLING" "$FILE" "$outFile"
        fi

        # warp to new projection, add nodata
        echo "gdalwarp -r \"$RESAMPLING\" -t_srs \"$COMMON_SRS\" -dstnodata \"$BASE_VALUE\" \"$outFile\" \"$outFileWarpped\""
        gdalwarp -r "$RESAMPLING" -t_srs "$COMMON_SRS" -dstnodata "$BASE_VALUE" "$outFile" "$outFileWarpped"
        
        rm "$outFile"
     fi
}

export -f myconvert

# run the conversions in parallel
find "$INPUT_DIR" -iname "*.asc" -print0 | xargs -0 -n 1 -P "$THREADS" bash -c 'myconvert "$1" "$2" "$3" "$4" "$5"' "$COMMON_SRS" "$WARP_OUTPUT_DIR" "$RESAMPLING" "$BASE_VALUE"
