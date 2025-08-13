# Terrain_Merged

# Overview

This project creates a merged mapbox TerrainRGB mbtiles file from multiple independent source datasets. It uses a custom version of rio-rgbify which adds a 'rio merge' function and aditional resampling options, locatioed in the merge branch at https://github.com/acalcutt/rio-rgbify/tree/merge

# Steps

1.) Generate each dataset you would like to use with the best settings possible for that dataset. Each dataset folder includes scripts to download an generate the source terrainrgb datasets

### Right now the following datasets are available  
[Austrian DTM 1m 2024](https://data.bev.gv.at/geonetwork/srv/ger/catalog.search#/metadata/5ce253fc-b7c5-4362-97af-6556c18a45d9)  
[German OpenDTM 1m 2024](https://www.opendem.info/opendtm_de.html)  
GEBCO  
Italy_Sudtirol  
JAXA_AW3D30  
MASSGIS  
RGE_ALTI  
SonnyDem_EUROPE  
SwissAlti  
Tinitaly  

2.) Use 'rio merge' and json files like the examples in the 'merge' folder to combine and layer the datasets into one file like shown at https://github.com/acalcutt/terrain_merged/tree/main/merge#example-usage

2.) ***optional*** If you have different level merged files (like in my example) and want to create a sparse tileset, use the tools/combine.py script like shown at https://github.com/acalcutt/terrain_merged/tree/main/merge#create-sparse-tiles-from-merged-datasets
