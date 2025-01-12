import sqlite3
import rasterio
import mercantile
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
import numpy as np
from shapely.geometry import Polygon, shape
from shapely.ops import transform as geom_transform
import pyproj
import fiona
import io
from rasterio import mask
from PIL import Image
from io import BytesIO
from osgeo import gdal
import math

def decode_terrainrgb(image_data, debug=False):
    """Decodes terrain rgb data into elevation data"""
    try:
        if not image_data:
            if debug:
                print(" - Error decoding terrain rgb: image_data was None")
            return None, None
        if not isinstance(image_data, bytes) or len(image_data) == 0:
            if debug:
                print(" - Error decoding terrain rgb: image_data is not valid bytes")
            return None, None

        # Convert the image to a png using Pillow
        image = Image.open(io.BytesIO(image_data))
        image_png = io.BytesIO()

        # Force to RGB (to ensure it's not paletted or other weirdness)
        image = image.convert('RGB')
        # Force output to an 8-bit PNG
        image.save(image_png, format='PNG', bits=8)
        image_png.seek(0)

        if debug:
            print(f" - image_png size: {len(image_png.getvalue())}")

        with rasterio.open(image_png, driver='PNG') as dataset:
            rgb = dataset.read(masked = False).astype(np.int32) # add masked = False to ensure there is no mask
            print(f" - rgb data={rgb}") # print the rgb data
            if rgb.shape[0] != 3:
                if debug:
                    print(f" - Error decoding terrain rgb: Expected 3 bands, got {rgb.shape[0]}")
                return None, None
            r, g, b = rgb[0], rgb[1], rgb[2]
            print(f"RGB values: R min={np.min(r)}, max={np.max(r)}, G min={np.min(g)}, max={np.max(g)}, B min={np.min(b)}, max={np.max(b)}")
            try:
                elevation = -10000 + ((r * 256 * 256 + g * 256 + b) * 0.1)
                print(f" - Elevation min={np.min(elevation)} max={np.max(elevation)}")
            except Exception as e:
                if debug:
                    print(f" - Error decoding terrain rgb (elevation): {e}")
                return None, None

            # create the new meta data for our single band elevation array
            kwargs = dataset.meta.copy()
            kwargs.update({
                "count": 1,
                "dtype": rasterio.float32,
                "driver": 'GTiff'
            })

            elevation_raster_data = None
            elevation_raster_meta = None
            temp_file = f"/opt/test_{tile_x}_{tile_y}_{zoom}.tif"
            with rasterio.open(temp_file, 'w', **kwargs) as transformed_raster:
               transformed_raster.write(np.expand_dims(elevation, axis=0))
            
            np.savetxt(f"/opt/elevation_data_{tile_x}_{tile_y}_{zoom}.csv", elevation, delimiter=",") # write data as csv

            elevation_raster_data = rasterio.open(temp_file) # open the file for reading
            elevation_raster_meta = elevation_raster_data.meta  # Capture the meta data

        return elevation_raster_data, elevation_raster_meta

    except Exception as e:
        if debug:
            print(f" - Error decoding terrain rgb: {e}")
        return None, None
    
def output_rgb_data(image_data, output_path, debug=False):
    """Outputs raw RGB data to a file."""
    try:
        if not image_data:
            if debug:
                print(" - Error outputting rgb: image_data was None")
            return None
        if not isinstance(image_data, bytes) or len(image_data) == 0:
            if debug:
                print(" - Error outputting rgb: image_data is not valid bytes")
            return None

        # Convert the image to a png using Pillow
        image = Image.open(io.BytesIO(image_data))
        image_png = io.BytesIO()

        # Force to RGB (to ensure it's not paletted or other weirdness)
        image = image.convert('RGB')
        # Force output to an 8-bit PNG
        image.save(image_png, format='PNG', bits=8)
        image_png.seek(0)

        with rasterio.open(image_png, driver='PNG') as dataset:
            rgb = dataset.read().astype(np.int32)
            with open(output_path, 'w') as f:
              for i in range(rgb.shape[1]):
                for j in range(rgb.shape[2]):
                  r, g, b = rgb[0,i,j], rgb[1,i,j], rgb[2,i,j]
                  f.write(f"r={r}, g={g}, b={b}\n")
        
    except Exception as e:
        if debug:
            print(f" - Error outputting rgb: {e}")
        return None
    
def tile_to_raster(tile_data, bounds, output_path):
    """Converts a tile to a rasterio raster object."""
    if not tile_data:
        print(" - Error converting tile to raster: tile_data is None")
        return None
        
    elevation_raster_data, elevation_raster_meta = decode_terrainrgb(tile_data, debug = True) # this will return a raster object
    print(f" - elevation_raster_data: {elevation_raster_data}")
    print(f" - elevation_raster_meta: {elevation_raster_meta}")

    if not elevation_raster_data or not elevation_raster_meta:
        print(" - Error converting tile to raster: could not decode tile_data")
        return None

    # Create a copy of the base meta
    kwargs = elevation_raster_meta.copy()
    kwargs.update({
        'transform': rasterio.transform.from_bounds(bounds.west, bounds.south, bounds.east, bounds.north, elevation_raster_meta['width'], elevation_raster_meta['height'])
    })


    try:
        with rasterio.open(output_path, 'w', **kwargs) as transformed_raster: # Write to a tif file
            transformed_raster.write(elevation_raster_data.read()) # Write to the raster
        return transformed_raster
        
    except Exception as e:
        print(f" - Error converting tile to raster: {e}")
        return None
    
def extract_tile_data(mbtiles_path, zoom, tile_x, tile_y):
    """Extract a tile from MBTiles as bytes."""
    conn = sqlite3.connect(mbtiles_path)
    cursor = conn.cursor()
    cursor.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?", (zoom, tile_x, tile_y))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_tiles_from_mbtiles(mbtiles_path, zoom):
    """Extracts tile coordinates from MBTiles."""
    conn = sqlite3.connect(mbtiles_path)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT tile_column, tile_row FROM tiles WHERE zoom_level = ?', (zoom,))
    results = cursor.fetchall()
    conn.close()
    return [mercantile.Tile(x=tile_x, y=tile_y, z=zoom) for (tile_x, tile_y) in results]

def select_central_tile(mbtiles_path, zoom):
    """Selects a tile closest to the center of the dataset."""
    tiles = get_tiles_from_mbtiles(mbtiles_path, zoom)
    if not tiles:
        return None

    sum_x = 0
    sum_y = 0
    for tile in tiles:
      sum_x += tile.x
      sum_y += tile.y

    center_x = sum_x / len(tiles)
    center_y = sum_y / len(tiles)

    closest_tile = None
    min_dist = float('inf')
    for tile in tiles:
        dist = math.sqrt((tile.x - center_x)**2 + (tile.y - center_y)**2)
        if dist < min_dist:
            min_dist = dist
            closest_tile = tile
    
    return closest_tile



if __name__ == "__main__":
    mbtiles_path1 = "/opt/JAXA_AW3D30_2024_terrainrgb_z0-Z12_webp.mbtiles"
    
    zoom = 10 # Desired zoom level for testing
    
    # Get a single tile for testing (replace with a real tile from your MBTiles)
    central_tile = select_central_tile(mbtiles_path1, zoom)

    if central_tile:
        tile_x = central_tile.x
        tile_y = central_tile.y

        tile_data = extract_tile_data(mbtiles_path1, zoom, tile_x, tile_y)
        output_rgb_path = f"/opt/rgb_output_{tile_x}_{tile_y}_{zoom}.txt"
        output_rgb_data(tile_data, output_rgb_path, debug=True)
        
        tile_obj = mercantile.Tile(x=tile_x, y=tile_y, z=zoom)
        bounds = mercantile.bounds(tile_obj)

        if tile_data:
            output_path = f"/opt/output_tile_{tile_x}_{tile_y}_{zoom}.tif"
            raster = tile_to_raster(tile_data, bounds, output_path)
            if raster:
                print(f"Successfully created raster at: {output_path}")
            else:
                print("Could not convert tile to raster.")
        else:
            print("Tile was not extracted")
    else:
        print("Could not select a central tile")
