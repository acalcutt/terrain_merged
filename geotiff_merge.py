import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
import numpy as np
from shapely.geometry import Polygon, shape
from shapely.ops import transform as geom_transform
import pyproj
import fiona
from rasterio import mask
from osgeo import gdal
import tempfile
import multiprocessing
import itertools
import gc
import os
import mercantile
from shapely.geometry import box
import math

def should_exclude(data_values, nodata_value=0):
    """
    Returns a boolean mask indicating which values should be excluded based on a nodata value.
    
    Args:
      data_values (np.ndarray): A numpy array containing the data to check.
      nodata_value (float or int, optional): The value that indicates no data.
        Defaults to 0.

    Returns:
      np.ndarray: A boolean mask where True indicates the value should be excluded.
    """
    
    return data_values == nodata_value

def get_tile_bounds(tile):
  return mercantile.bounds(tile)
  
def _create_geotiff_from_tile_wrapper(kwargs):
  """Wraps the create geotiff function to be used with multiprocessing"""
  print(f"  - Starting Processing Tile: {kwargs.get('tile')}")
  create_geotiff_from_tile(**kwargs)
  print(f"  - Finished Processing Tile: {kwargs.get('tile')}")
  
def _extract_tile_from_raster(raster_path, bounds, target_width, target_height, resampling, nodata_value=0):
    """Extracts data corresponding to the given bounds from a raster (GeoTIFF or VRT)."""
    try:
        with rasterio.open(raster_path) as src:
            
            # transform bounds to the source crs
            src_crs = src.crs
            
            polygon = box(bounds.west, bounds.south, bounds.east, bounds.north)

            # Reproject to the source CRS
            project =  pyproj.Transformer.from_crs("EPSG:4326", src_crs, always_xy=True).transform
            polygon_src_crs = geom_transform(project, polygon)
            
            # Read the data within the polygon
            try:
              out_image, out_transform  = mask.mask(src, [polygon_src_crs], crop=True)
            except ValueError as e:
              print(f" - Value Error skipping tile: {e} - {bounds}")
              return None, None

            out_meta = src.meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform
            })
           
            # check for upscaling needed
            if (out_meta["width"] != target_width or out_meta["height"] != target_height):
                
                # calculate the new transform based on the target tile
                transform, width, height = calculate_default_transform(
                    out_meta['crs'], out_meta['crs'], 
                    out_meta['width'], out_meta['height'], 
                    *rasterio.transform.array_bounds(1, 1, out_meta['transform']), 
                    resolution=(out_meta['transform'][2] - out_meta['transform'][0]) / out_meta['width']
                )
                target_transform = rasterio.transform.from_bounds(
                bounds.west, bounds.south, bounds.east, bounds.north,
                target_width, target_height
                )

                kwargs = out_meta.copy()
                kwargs.update({
                      "transform": target_transform,
                      "width": target_width,
                      "height": target_height,
                })
                # Create reprojected raster
                out_memfile = rasterio.MemoryFile()
                with out_memfile.open(**kwargs) as dst:
                    reproject(
                    source=out_image,
                    destination=rasterio.band(dst, 1),
                    src_transform=out_meta['transform'],
                    src_crs=out_meta['crs'],
                    dst_transform=target_transform,
                    dst_crs=out_meta['crs'],
                    resampling=resampling,
                )
                out_image = out_memfile.read()
                out_meta = kwargs
                
        return out_image, out_meta
    except Exception as e:
        print(f" - Error extracting tile: {e}")
        return None, None

def create_geotiff_from_tile(raster_path1, raster_path2, output_dir, zoom, tile, resampling, nodata_value=0):
    """Extracts a tile from the rasters and saves it as a GeoTIFF."""
    bounds = get_tile_bounds(tile)
    target_width = 256
    target_height = 256
    
    data1, meta1 = _extract_tile_from_raster(raster_path1, bounds, target_width, target_height, resampling, nodata_value)
    
    if data1 is not None:
        data2, meta2 = _extract_tile_from_raster(raster_path2, bounds, target_width, target_height, resampling, nodata_value)
        
        if data2 is not None:
            mask = should_exclude(data2, nodata_value)
            data2 = np.where(mask, data1, data2) # the overlay is done here.
            output_path = os.path.join(output_dir, f"tile_{tile.z}_{tile.x}_{tile.y}.tif")
            with rasterio.open(output_path, 'w', **meta2) as dst:
                dst.write(data2)
            print(f" - Created {output_path}")
        else:
          output_path = os.path.join(output_dir, f"tile_{tile.z}_{tile.x}_{tile.y}.tif")
          with rasterio.open(output_path, 'w', **meta1) as dst:
              dst.write(data1)
          print(f" - Created {output_path}")

    else:
        print(f" - Error extracting tile {tile.x}, {tile.y} from either source, skipping tile")

def get_tiles_from_zoom(zoom, bounds):
    """Generates tiles at a given zoom level within the specified bounds."""
    tiles = []
    min_tile = mercantile.tile(bounds[0],bounds[3] , zoom)
    max_tile = mercantile.tile(bounds[2],bounds[1] , zoom)

    for x in range(min_tile.x, max_tile.x + 1):
      for y in range(min_tile.y, max_tile.y + 1):
        tiles.append(mercantile.Tile(x=x, y=y, z=zoom))
    
    return tiles


def get_bounds_from_raster(raster_path):
    """Gets the bounds of a raster image in EPSG:4326"""
    with rasterio.open(raster_path) as src:
      crs = src.crs
      bounds = src.bounds
      
      project =  pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
      
      min_x, min_y = project(bounds.left, bounds.bottom)
      max_x, max_y = project(bounds.right, bounds.top)
      return min_x, min_y, max_x, max_y


if __name__ == "__main__":
    raster_path1 = "/work/output/jaxa_warp.vrt"  # Path to the first raster file (can be VRT)
    raster_path2 = "/work/output/swiss_warp.vrt"  # Path to the second raster file (can be VRT)
    output_geotiff_dir = "/opt/merge_tiles/output_geotiffs"  # Output directory for merged GeoTIFFs
    resampling_option = Resampling.lanczos
    zoom_level = 12
    processes = multiprocessing.cpu_count()
    nodata_value = 0


    # Create the output directory if it doesn't exist
    os.makedirs(output_geotiff_dir, exist_ok=True)
    
    # Get Bounds
    bounds = get_bounds_from_raster(raster_path2)
    
    print(f"Bounds of raster: {bounds}")
    
    selected_tiles = get_tiles_from_zoom(zoom_level, bounds)
    print(f"Processing {len(selected_tiles)} tiles")

    # Print Parameters before executing
    tile_params =  [
          {
              "raster_path1": raster_path1,
              "raster_path2": raster_path2,
              "output_dir": output_geotiff_dir,
              "zoom": zoom_level,
              "tile": tile,
              "resampling": resampling_option,
              "nodata_value": nodata_value
           } for tile in selected_tiles]

    for i, params in enumerate(tile_params):
      print(f"  - Preparing tile {i+1}/{len(tile_params)}: {params['tile']}")

    with multiprocessing.Pool(processes=processes) as pool:
        pool.map(_create_geotiff_from_tile_wrapper, tile_params)

    print("Finished GeoTIFF creation")