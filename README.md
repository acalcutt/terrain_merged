# Terrain_Merged

# Overview

This project creates a merged mapbox TerrainRGB mbtiles file from multiple independent sources. It uses a custom version of rio-rgbify which adds a 'rio merge' function and aditional resampling options, locatioed in the merge branch at https://github.com/acalcutt/rio-rgbify/tree/merge

# Steps

1.) Generate each dataset you would like to use with the best settings possible for that dataset. Each dataset folder includes scripts to download an generate the source terrainrgb datasets

### Right now the following datasets are available  
GEBCO  
JAXA_AW3D30  
MASSGIS  
RGE_ALTI  
SonnyDem_EUROPE  
SwissAlti  
Tinitaly  

2.) Use 'rio merge' and json files like the examples in the 'merge' folder to combine and layer the datasets into one file like shown at https://github.com/acalcutt/terrain_merged/tree/main/merge#example-usage

2.) ***optional*** If you have different level merged files (like in my example) and want to create a sparse tileset, use the tool merge/combine.py like shown at https://github.com/acalcutt/terrain_merged/tree/main/merge#create-sparse-tiles-from-merged-datasets
