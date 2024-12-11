#!/bin/bash
# Fix error Warning 1: gdalbuildvrt does not support heterogeneous band data type: expected Int16, got Float32. Skipping ./output/swiss_warp.vrt

INPUT_DIR=./download_france

function myconvert()
{
	OUTPUT_DIR=./france
	[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

	FILE=$1
	directory=$(dirname $FILE)
	directory_name=$(basename $directory)
	baseName=$(basename $FILE)
	vrtFile="${OUTPUT_DIR}/${directory_name}-${baseName}.vrt"
	outFile="${OUTPUT_DIR}/${directory_name}-${baseName}.tif"
	if [ ! -f $vrtFile ]; then

		echo "Conveting $FILE file to $outFile"

		if [[ $baseName =~ "LAMB93" ]]; then
			echo "Conveting LAMB93 file $FILE to $outFile"
			gdal_translate -a_srs EPSG:2154 -of GTiff -ot Float32 -r lanczos $FILE $outFile
		elif [[ $baseName =~ "RGAF09UTM20" ]]; then
			echo "Conveting RGAF09UTM20 file $FILE to $outFile"
			gdal_translate -a_srs EPSG:5490 -of GTiff -ot Float32 -r lanczos $FILE $outFile
		elif [[ $baseName =~ "WGS84UTM20" ]]; then
			echo "Conveting WGS84UTM20 file $FILE to $outFile"
			gdal_translate -a_srs EPSG:32620 -of GTiff -ot Float32 -r lanczos $FILE $outFile
		elif [[ $baseName =~ "RGFG95UTM22" ]]; then
			echo "Conveting RGFG95UTM22 file $FILE to $outFile"
			gdal_translate -a_srs EPSG:2972 -of GTiff -ot Float32 -r lanczos $FILE $outFile
		elif [[ $baseName =~ "RGM04UTM38S" ]]; then
			echo "Conveting RGM04UTM38S file $FILE to $outFile"
			gdal_translate -a_srs EPSG:4471 -of GTiff -ot Float32 -r lanczos $FILE $outFile
		elif [[ $baseName =~ "RGR92UTM40S" ]]; then
			echo "Conveting RGR92UTM40S file $FILE to $outFile"
			gdal_translate -a_srs EPSG:2975 -of GTiff -ot Float32 -r lanczos $FILE $outFile
		elif [[ $baseName =~ "RGSPM06U21" ]]; then
			echo "Conveting RGSPM06U21 file $FILE to $outFile"
			gdal_translate -a_srs EPSG:4467 -of GTiff -ot Float32 -r lanczos $FILE $outFile
		fi

		gdalwarp -r lanczos -t_srs EPSG:3857 -dstnodata 0 ${outFile} ${vrtFile}
	fi
}

export -f myconvert

# run curl in parallel using 8 thread/connection
find ${INPUT_DIR} -name *MNT*.asc | xargs -P 8 -I {} bash -c "myconvert '{}'"
