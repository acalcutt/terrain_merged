#!/bin/bash

# Set defaults
[[ $THREADS ]] || THREADS=8
[[ $BATCH ]] || BATCH=1
[[ $MINZOOM ]] || MINZOOM=0
[[ $MAXZOOM ]] || MAXZOOM=14
[[ $FORMAT ]] || FORMAT=webp
[[ $RESAMPLING ]] || RESAMPLING=cubic
[[ $INPUT_FILE ]] || INPUT_FILE=download/Lidar_Elevation_2013to2021.jp2
[[ $OUTPUT_DIR ]] || OUTPUT_DIR=./output
[[ $BASE_VALUE ]] || BASE_VALUE=-10000
[[ $INTERVAL ]] || INTERVAL=0.1
[[ $COMMON_SRS ]] || COMMON_SRS="EPSG:4326"

# --- Derived Variables ---
BASENAME=MASSGIS_TerrainRGB_z${MINZOOM}-Z${MAXZOOM}_${RESAMPLING}_${FORMAT}
mbtiles="${OUTPUT_DIR}/${BASENAME}.mbtiles"
source_vrt="${OUTPUT_DIR}/${BASENAME}.vrt"
final_vrt="${OUTPUT_DIR}/${BASENAME}_warped.vrt"

# --- Setup ---
[ -d "$OUTPUT_DIR" ] || mkdir -p "$OUTPUT_DIR" || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

# --- 1. Build Initial VRT ---
gdalbuildvrt -overwrite -resolution highest -r "$RESAMPLING" -srcnodata 1099 "${source_vrt}" "${INPUT_FILE}"

# --- 2. Get Source Raster Information (Bounding Box in Source CRS) ---
ul_line=$(gdalinfo "${INPUT_FILE}" | grep "Upper Left")
lr_line=$(gdalinfo "${INPUT_FILE}" | grep "Lower Right")
echo "$ul_line"
echo "$lr_line"

# Use sed to extract ONLY the x and y coordinates
ulx=$(echo "$ul_line" | sed -E 's/.*\( *([0-9.]+),.*/\1/g')
uly=$(echo "$ul_line" | sed -E 's/.*, *([0-9.]+)\).*/\1/g')
lrx=$(echo "$lr_line" | sed -E 's/.*\( *([0-9.]+),.*/\1/g')
lry=$(echo "$lr_line" | sed -E 's/.*, *([0-9.]+)\).*/\1/g')

echo "$ulx"
echo "$uly"
echo "$lrx"
echo "$lry"

# --- 2a. Check if coordinates are numeric ---
if ! [[ "$ulx" =~ ^[0-9.-]+$ && "$uly" =~ ^[0-9.-]+$ && "$lrx" =~ ^[0-9.-]+$ && "$lry" =~ ^[0-9.-]+$ ]]; then
  echo "ERROR: Could not extract numeric coordinates from gdalinfo output."
  echo "gdalinfo output:"
  gdalinfo "${INPUT_FILE}"
  exit 1
fi

echo "Original UL: $ulx, $uly"
echo "Original LR: $lrx, $lry"

# --- 3. Transform Corner Coordinates to Target CRS (EPSG:4326) ---
transformed_ulx=$(echo "$ulx $uly" | gdaltransform -s_srs EPSG:26919 -t_srs "$COMMON_SRS" | awk '{print $1}')
transformed_uly=$(echo "$ulx $uly" | gdaltransform -s_srs EPSG:26919 -t_srs "$COMMON_SRS" | awk '{print $2}')
transformed_lrx=$(echo "$lrx $lry" | gdaltransform -s_srs EPSG:26919 -t_srs "$COMMON_SRS" | awk '{print $1}')
transformed_lry=$(echo "$lrx $lry" | gdaltransform -s_srs EPSG:26919 -t_srs "$COMMON_SRS" | awk '{print $2}')

# --- 4. Debug: Print Transformed Coordinates ---
echo "Transformed UL: $transformed_ulx, $transformed_uly"
echo "Transformed LR: $transformed_lrx, $transformed_lry"

# --- 5.  Warp with Explicit Extent and Resolution ---
# Ensure correct order: minx miny maxx maxy (longitude, latitude)
# Correct order: minx lry maxx uly (longitude, latitude)
gdalwarp -overwrite \
  -r "$RESAMPLING" \
  -t_srs "$COMMON_SRS" \
  -te "$transformed_ulx" "$transformed_lry" "$transformed_lrx" "$transformed_uly" \
  -dstnodata "$BASE_VALUE" \
  "${source_vrt}" \
  "${final_vrt}"
# Check if gdalwarp command succeeded
if [ $? -ne 0 ]; then
    echo "ERROR: gdalwarp command failed!"
    exit 1
fi
# Check if final_vrt has been written
if [ ! -f "${final_vrt}" ]; then
    echo "ERROR: final_vrt was not created by gdalwarp!"
    exit 1
fi
# --- 6. rio rgbify ---
rio rgbify -v -b "$BASE_VALUE" -i "$INTERVAL" --min-z "$MINZOOM" --max-z "$MAXZOOM" -j "$THREADS" --batch-size "$BATCH" --resampling "$RESAMPLING" --format "$FORMAT" "${final_vrt}" "${mbtiles}"

echo "Script finished!"
