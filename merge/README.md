# Example Usage
*** note: requires custom rio rgbify from https://github.com/acalcutt/rio-rgbify/tree/merge

rio merge --config merge_mass.json -j 24  
rio merge --config merge_europe.json -j 24  
rio merge --config merge_italy.json -j 24  
rio merge --config merge_france.json -j 24  
rio merge --config merge_austria.json -j 24  
rio merge --config merge_germany.json -j 24  
rio merge --config merge_swiss.json -j 24  

# Create Sparse Tiles from merged datasets  
python3 ../tools/combine.py JAXA_z0-12_SonnyDTM_z0-Z13_Italy_z0-Z14_France_z0-Z15_Switzerland_z0-Z16_Merged_Sparse_cubic.mbtiles output/Germany_Merged_2024_z0-Z16_cubic_webp.mbtiles output/Austria_Merged_2024_z0-Z16_cubic_webp.mbtiles output/Europe_Merged_2024_z0-Z13_cubic_webp.mbtiles output/Italy_Merged_2024_z0-Z14_cubic_webp.mbtiles output/France_Merged_2024_z0-Z15_cubic_webp.mbtiles output/Switzerland_Merged_2024_z0-Z16_cubic_webp.mbtiles
