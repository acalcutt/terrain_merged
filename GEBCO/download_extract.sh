#!/bin/bash

INPUT_DIR=./gebco
[ -d "$INPUT_DIR" ] || mkdir -p $INPUT_DIR || { echo "error: $INPUT_DIR " 1>&2; exit 1; }
cd $INPUT_DIR
wget -O gebco_2024_sub_ice_topo_geotiff.zip https://www.bodc.ac.uk/data/open_download/gebco/gebco_2024_sub_ice_topo/geotiff/

unzip gebco_2024_sub_ice_topo_geotiff.zip
cd ..

