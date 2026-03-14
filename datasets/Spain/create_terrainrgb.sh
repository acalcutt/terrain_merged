#!/bin/bash

#custom version of rio rgbify which adds speed improvements is reccomended https://github.com/acalcutt/rio-rgbify/tree/merge

INPUT_DIR=./swissalti
OUTPUT_DIR=./output
INTERMEDIATE_VRT_DIR=./vrt_intermediate

[[ $THREADS ]] || THREADS=12
[[ $BATCH ]] || BATCH=1
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=15
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=cubic
[[ $COMMON_SRS ]] || COMMON_SRS="EPSG:4326"
[[ $BASE_VALUE ]] || BASE_VALUE=-10000
[[ $INTERVAL ]] || INTERVAL=0.1
# Note: If generating a standalone MBTiles source (not merging later),
# setting NODATA=0 via env var is recommended for a more visually correct map.
[[ $NODATA ]] || NODATA=$BASE_VALUE

BASENAME=Spain_2002-2015_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
vrtfile=${OUTPUT_DIR}/${BASENAME}.vrt
mbtiles=${OUTPUT_DIR}/${BASENAME}.mbtiles
vrtfile2=${OUTPUT_DIR}/${BASENAME}_warp.vrt
list_of_vrts=${INTERMEDIATE_VRT_DIR}/list_of_vrts.txt

[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }
[ -d "$INTERMEDIATE_VRT_DIR" ] || mkdir -p $INTERMEDIATE_VRT_DIR || { echo "error: $INTERMEDIATE_VRT_DIR " 1>&2; exit 1; }

# Clear previous intermediate files and lists
rm -f ${INTERMEDIATE_VRT_DIR}/*.vrt ${list_of_vrts}

# Process each file from downloaded_files.txt individually
# Create an intermediate VRT for each file, warping it to the common CRS
# This handles the heterogeneous projection issue
echo "Creating intermediate VRTs for each file..."
while read -r line; do
    filename=$(basename -- "$line")
    vrt_name="${filename%.*}.vrt"
    vrt_path=${INTERMEDIATE_VRT_DIR}/${vrt_name}
    
    gdalwarp -overwrite -of VRT -t_srs $COMMON_SRS -r $RESAMPLING "$line" "$vrt_path"
    echo "$vrt_path" >> "$list_of_vrts"
done < downloaded_files.txt

# Build a final VRT from the intermediate VRTs
echo "Building final VRT from intermediate VRTs..."
gdalbuildvrt -overwrite -resolution highest -r $RESAMPLING -input_file_list ${list_of_vrts} ${vrtfile}

# Clean up the temporary list of VRTs
rm ${list_of_vrts}

# The rest of your commands remain the same, but now the initial vrtfile is correct
# gdalwarp is no longer needed since it was done on individual files
echo "Processing final VRT to generate mbtiles..."
rio rgbify -v -b $BASE_VALUE -i $INTERVAL --min-z $MINZOOM --max-z $MAXZOOM -j $THREADS --batch-size $BATCH --resampling $RESAMPLING --format $FORMAT ${vrtfile} ${mbtiles}