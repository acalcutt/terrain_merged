#!/bin/bash

INPUT_DIR=./gebco
[ -d "$INPUT_DIR" ] || mkdir -p $INPUT_DIR || { echo "error: $INPUT_DIR " 1>&2; exit 1; }
cd $INPUT_DIR
wget -O gebco_2025_sub_ice_topo_geotiff.zip https://dap.ceda.ac.uk/bodc/gebco/global/gebco_2025/sub_ice_topography_bathymetry/geotiff/

unzip gebco_2025_sub_ice_topo_geotiff.zip
cd ..

