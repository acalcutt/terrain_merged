import numpy as np
import rasterio
import io
from rasterio.shutil import copy

def test_rasterio_gdal():
    """
    Tests basic rasterio and GDAL functionality.
    """
    try:
        # 1. Create a simple 2x2 raster in memory
        width = 2
        height = 2
        raster_array = np.array([[1, 2], [3, 4]], dtype=np.float32)

        # Define raster metadata
        meta = {
            'driver': 'GTiff',
            'dtype': rasterio.float32,
            'count': 1,
            'width': width,
            'height': height,
            'crs': 'EPSG:4326', # WGS 84
            'transform': rasterio.transform.from_origin(-180, 90, 180/width, 180/height)
        }

        # 2. Write the raster data to MemoryFile
        with rasterio.MemoryFile() as memfile:
            with memfile.open(**meta) as dst:
                dst.write(np.expand_dims(raster_array, axis=0))

                # 3. Read the raster data back from the memory file
                read_raster_array = dst.read(1)

                # Validate the read data
                if not np.array_equal(raster_array, read_raster_array):
                    print(" - Error: Read raster data does not match original data")
                    return False

            # 4. copy the memfile to another memory file using GDALCreateCopy
            with rasterio.MemoryFile() as memfile_copy:
                with memfile.open() as memfile_read: # <-- Re-open the memfile with 'r' as a read flag
                    with rasterio.shutil.copy(memfile_read, memfile_copy) as copy_dst:
                        copy_read_raster_array = copy_dst.read(1)

                        if not np.array_equal(raster_array, copy_read_raster_array):
                            print(" - Error: Copied raster data does not match original data")
                            return False

        print(" - Success: rasterio and GDAL test passed")
        return True

    except Exception as e:
        print(f" - Error: rasterio and GDAL test failed: {e}")
        return False


if __name__ == "__main__":
    test_rasterio_gdal()
