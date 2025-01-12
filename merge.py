import sqlite3
import rasterio
import mercantile
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
import tempfile
import multiprocessing
import itertools
import gc
import os

def should_exclude(r,g,b):
  """returns true if the r,g,b value indicates the tile should be excluded"""
  if r == 1 and g == 134 and b == 160:
    return True
  if r == 1 and g == 134 and b == 150:
    return True
    
  return False

def decode_terrainrgb(image_data, debug=False):
    """Decodes terrain rgb data into elevation data"""
    try:
        if not image_data:
            if debug:
                print(" - Error decoding terrain rgb: image_data was None")
            return None, None, None
        if not isinstance(image_data, bytes) or len(image_data) == 0:
            if debug:
                print(" - Error decoding terrain rgb: image_data is not valid bytes")
            return None, None, None

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
            rgb = dataset.read(masked = False).astype(np.int32)
            if rgb.shape[0] != 3:
                if debug:
                    print(f" - Error decoding terrain rgb: Expected 3 bands, got {rgb.shape[0]}")
                return None, None, None
            r, g, b = rgb[0], rgb[1], rgb[2]
            if debug:
                print(f"RGB values: R min={np.min(r)}, max={np.max(r)}, G min={np.min(g)}, max={np.max(g)}, B min={np.min(b)}, max={np.max(b)}")
            try:
                elevation = -10000 + ((r * 256 * 256 + g * 256 + b) * 0.1)
                mask = np.vectorize(should_exclude)(r,g,b)
                elevation = np.where(mask, np.nan, elevation)
                if debug:
                    print(f" - Elevation min={np.nanmin(elevation)} max={np.nanmax(elevation)}")
            except Exception as e:
                if debug:
                    print(f" - Error decoding terrain rgb (elevation): {e}")
                return None, None, None

            # create the new meta data for our single band elevation array
            kwargs = dataset.meta.copy()
            kwargs.update({
                "count": 1,
                "dtype": rasterio.float32,
                "driver": "GTiff",
                "crs": "EPSG:3857" # Setting the CRS here
            })
        
        return np.expand_dims(elevation, axis=0), kwargs, dataset.meta

    except Exception as e:
        if debug:
            print(f" - Error decoding terrain rgb: {e}")
        return None, None, None

def extract_tile_data(mbtiles_path, zoom, tile_x, tile_y):
    """Extract a tile from MBTiles as bytes, with upscaling logic."""
    conn = sqlite3.connect(mbtiles_path)
    cursor = conn.cursor()
    
    current_zoom = zoom

    while current_zoom >= 0:
        cursor.execute(
            "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (current_zoom, tile_x, tile_y),
        )
        result = cursor.fetchone()
        if result:
            conn.close()
            return result[0], current_zoom  # Return found tile data and zoom
        
        # Calculate parent tile coordinates
        if current_zoom > 0:
            tile_x //= 2
            tile_y //= 2
        current_zoom -= 1
    
    conn.close()
    return None, None  # No tile found at any level

def get_tile_bounds(tile):
  return mercantile.bounds(tile)

def _create_geotiff_from_tile_wrapper(kwargs):
  """Wraps the create geotiff function to be used with multiprocessing"""
  create_geotiff_from_tile(**kwargs)

def create_geotiff_from_tile(mbtiles_path1, mbtiles_path2, output_dir, zoom, tile, resampling):
    """Extracts a tile and saves it as a GeoTIFF."""
    tile_x, tile_y = tile.x, tile.y
    bounds = get_tile_bounds(tile)
    
    tile_data1, source_zoom1 = extract_tile_data(mbtiles_path1, zoom, tile_x, tile_y)
    
    if tile_data1:
        data1, tile_meta = _tile_to_raster(tile_data1, bounds)
        if source_zoom1 != zoom:
            # calculate the new transform based on the target tile
            transform, width, height = calculate_default_transform(
                tile_meta['crs'], tile_meta['crs'], 
                tile_meta['width'], tile_meta['height'], 
                *rasterio.transform.array_bounds(1, 1, tile_meta['transform']), 
                resolution=(tile_meta['transform'][2] - tile_meta['transform'][0]) / tile_meta['width']
            )
            target_bounds = get_tile_bounds(tile)
            target_transform = rasterio.transform.from_bounds(
              target_bounds.west, target_bounds.south, target_bounds.east, target_bounds.north,
              tile_meta['width'], tile_meta['height']
            )
            
            
            kwargs = tile_meta.copy()
            kwargs.update({
                  "transform": target_transform,
                  "width": tile_meta['width'],
                  "height": tile_meta['height'],
            })
              
            # Create reprojected raster
            out_memfile = rasterio.MemoryFile()
            with out_memfile.open(**kwargs) as dst:
              reproject(
                source=data1,
                destination=rasterio.band(dst, 1),
                src_transform=tile_meta['transform'],
                src_crs=tile_meta['crs'],
                dst_transform=target_transform,
                dst_crs=tile_meta['crs'],
                resampling=resampling,
              )
            data1 = out_memfile.read()
            tile_meta = kwargs
        
        tile_data2, source_zoom2 = extract_tile_data(mbtiles_path2, zoom, tile_x, tile_y)
        if tile_data2:
            data2, _ = _tile_to_raster(tile_data2, bounds)
            if data2.shape[0] == 3:
                mask = np.vectorize(should_exclude)(data2[0],data2[1],data2[2])
                data2 = np.where(mask, data1, data2) # the overlay is done here.
            output_path = os.path.join(output_dir, f"tile_{tile.z}_{tile.x}_{tile.y}.tif")
            with rasterio.open(output_path, 'w', **tile_meta) as dst:
                dst.write(data2)
            print(f" - Created {output_path}")
        else:
          output_path = os.path.join(output_dir, f"tile_{tile.z}_{tile.x}_{tile.y}.tif")
          with rasterio.open(output_path, 'w', **tile_meta) as dst:
              dst.write(data1)
          print(f" - Created {output_path}")
    else:
        tile_data2, source_zoom2 = extract_tile_data(mbtiles_path2, zoom, tile_x, tile_y)
        if tile_data2:
          data2, tile_meta = _tile_to_raster(tile_data2, bounds)
          if data2.shape[0] == 3:
            mask = np.vectorize(should_exclude)(data2[0],data2[1],data2[2])
            data2 = np.where(mask, np.nan, data2)
          output_path = os.path.join(output_dir, f"tile_{tile.z}_{tile.x}_{tile.y}.tif")
          with rasterio.open(output_path, 'w', **tile_meta) as dst:
            dst.write(data2)
          print(f" - Created {output_path}")
        else:
            print(f" - Error extracting tile {tile.x}, {tile.y} from either source, skipping tile")

def _tile_to_raster(tile_data, bounds):
    """Converts a tile to a rasterio raster object and its metadata."""
    if not tile_data:
        print(" - Error converting tile to raster: tile_data is None")
        return None, None
        
    elevation, elevation_meta, base_meta = decode_terrainrgb(tile_data, debug=False)
    if elevation is None or elevation_meta is None:
        print(" - Error converting tile to raster: could not decode tile_data")
        return None, None

    kwargs = elevation_meta.copy()
    kwargs.update({
        'transform': rasterio.transform.from_bounds(
        bounds.west, bounds.south, bounds.east, bounds.north, 
        elevation_meta['width'], elevation_meta['height']
        ),
        "driver": "GTiff"
    })
        
    # Return the numpy array and metadata instead of the raster object
    return elevation, kwargs


def get_tiles_from_mbtiles(mbtiles_path, zoom):
    """Extracts tile coordinates from MBTiles."""
    conn = sqlite3.connect(mbtiles_path)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT tile_column, tile_row FROM tiles WHERE zoom_level = ?', (zoom,))
    results = cursor.fetchall()
    conn.close()
    return [mercantile.Tile(x=tile_x, y=tile_y, z=zoom) for (tile_x, tile_y) in results]

def get_max_zoom_level(mbtiles_path):
    """Determines the maximum zoom level in an MBTiles database."""
    conn = sqlite3.connect(mbtiles_path)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(zoom_level) FROM tiles")
    result = cursor.fetchone()
    conn.close()
    return result[0] if result[0] is not None else 0 # if nothing is found, default to 0


if __name__ == "__main__":
    mbtiles_path1 = "/opt/JAXA_AW3D30_2024_terrainrgb_z0-Z12_webp.mbtiles"  # Path to the first MBTiles file
    mbtiles_path2 = "/opt/swissALTI3D_2024_terrainrgb_z0-Z16.mbtiles"  # Path to the second MBTiles file
    output_geotiff_dir = "/opt/output_geotiffs"  # Output directory for GeoTIFFs
    resampling_option = Resampling.lanczos
    processes = multiprocessing.cpu_count()

    # Create the output directory if it doesn't exist
    os.makedirs(output_geotiff_dir, exist_ok=True)

    # Determine the max zoom
    max_zoom = get_max_zoom_level(mbtiles_path2)
    print(f"Max zoom of mbtiles file: {max_zoom}")
    
    print(f"Starting GeoTIFF extraction for zoom: {max_zoom}")
    
    selected_tiles = get_tiles_from_mbtiles(mbtiles_path2, max_zoom)
    print(f"Processing {len(selected_tiles)} tiles")

    tile_params = ({
            "mbtiles_path1": mbtiles_path1,
            "mbtiles_path2": mbtiles_path2,
            "output_dir": output_geotiff_dir,
            "zoom": max_zoom,
            "tile": tile,
            "resampling": resampling_option
        } for tile in selected_tiles)
        
    with multiprocessing.Pool(processes=processes) as pool:
        for _ in pool.imap(_create_geotiff_from_tile_wrapper, tile_params):
          pass
        
    print("Finished GeoTIFF creation")
