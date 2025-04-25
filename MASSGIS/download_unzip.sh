[[ $DOWNLOAD_DIR ]] || DOWNLOAD_DIR=./download
[ -d "$DOWNLOAD_DIR" ] || mkdir -p "$DOWNLOAD_DIR" || { echo "error: $DOWNLOAD_DIR " 1>&2; exit 1; }

cd "$DOWNLOAD_DIR"
wget https://s3.us-east-1.amazonaws.com/download.massgis.digital.mass.gov/lidar/2021_LIDAR/Lidar_Elevation_2013to2021_jp2.zip

unzip Lidar_Elevation_2013to2021_jp2.zip

