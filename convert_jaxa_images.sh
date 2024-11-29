#!/bin/bash
# Fix error Warning 1: gdalbuildvrt does not support heterogeneous band data type: expected Int16, got Float32. Skipping ./output/swiss_warp.vrt

INPUT_DIR=./jaxa_temp
OUTPUT_DIR=./jaxa
jaxavrt1=${OUTPUT_DIR}/jaxa_convert.vrt
jaxavrt2=${OUTPUT_DIR}/jaxa_convert_warp.vrt
out=${OUTPUT_DIR}/jaxa_convert.tif

[ -d "$OUTPUT_DIR" ] || mkdir -p $OUTPUT_DIR || { echo "error: $OUTPUT_DIR " 1>&2; exit 1; }

for f in $(find ${INPUT_DIR} -type f); do
  baseName=$(basename ${f})
  outFile="${OUTPUT_DIR}/${baseName}"
  echo "Conveting $f file to $outFile"
  gdal_translate -of GTiff -ot Float32 -r lanczos $f $outFile
done


