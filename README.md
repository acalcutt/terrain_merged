Steps

1.) Update the "USER:PASSWORD" in download_zip_jaxa.sh to match your jaxa account

2.) Download the source geotiff files from jaxa, swissalti, and tinitaly
./download_zip_jaxa.sh
./download_tif_swissalti.sh
./download_zip_tinitaly.sh

3.) Convert the jaxa images to Float32 to match the swissalti and tinitaly datasets
./convert_jaxa_images.sh

4.) Create a terrainrgb mbtiles file with the merged datasets
./create_terrainrgb.sh