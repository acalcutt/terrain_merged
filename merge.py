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
import tempfile
import multiprocessing

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
                "crs": "EPSG:3857"
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

def tile_to_raster(tile_data, bounds):
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

def get_tile_bounds(tile):
  return mercantile.bounds(tile)

def clip_raster(raster, bounds):
  """Clips a rasterio raster object with a polygon."""
  if not bounds:
    return raster

  # create the clipping area based on the bounds of the tile
  clip_poly = Polygon([(bounds.west, bounds.south), (bounds.east, bounds.south), (bounds.east, bounds.north),
                (bounds.west, bounds.north)])
  try:
    if not clip_poly.is_valid:
      print(" - Error during clipping of raster: Clipping area is invalid")
      return None
    print(f" - Clipping area bounds: {clip_poly.bounds}")
    print(f" - Raster bounds {raster.bounds}")
    with mask.mask(raster, [clip_poly], crop=True) as (clipped_array, clipped_transform):
      kwargs = raster.meta.copy()
      kwargs.update(
        {
          'height': clipped_array.shape[1],
          'width': clipped_array.shape[2],
          'transform': clipped_transform
        }
      )
      with rasterio.MemoryFile() as memfile_clipped:
        with memfile_clipped.open(**kwargs) as memraster:
          memraster.write(clipped_array)
          return memraster
  except Exception as e:
    print(f" - Error during clipping of raster: {e}")
    return None

def _process_tile(mbtiles_path, zoom, tile, meta):
    """Processes a single tile (used in parallel) and returns the tile data and meta."""
    tile_x, tile_y = tile.x, tile.y
    tile_obj = mercantile.Tile(x=tile_x, y=tile_y, z=zoom)
    bounds = get_tile_bounds(tile_obj)
    
    tile_data, source_zoom = extract_tile_data(mbtiles_path, zoom, tile_x, tile_y)
    
    if tile_data:
        data, tile_meta = tile_to_raster(tile_data, bounds)
        if data is not None:
          if source_zoom != zoom:
              
            # calculate the new transform based on the target tile
            transform, width, height = calculate_default_transform(
                tile_meta['crs'], tile_meta['crs'], 
                tile_meta['width'], tile_meta['height'], 
                *rasterio.transform.array_bounds(1, 1, tile_meta['transform']), 
                resolution=(tile_meta['transform'][2] - tile_meta['transform'][0]) / tile_meta['width']
            )
            target_bounds = get_tile_bounds(tile_obj)
            target_transform = rasterio.transform.from_bounds(
              target_bounds.west, target_bounds.south, target_bounds.east, target_bounds.north,
              tile_meta['width'], tile_meta['height']
            )
            
            
            kwargs = tile_meta.copy()
            kwargs.update({
                  "crs": tile_meta['crs'],
                  "transform": target_transform,
                  "width": tile_meta['width'],
                  "height": tile_meta['height'],
            })
              
            # Create reprojected raster
            out_memfile = rasterio.MemoryFile()
            with out_memfile.open(**kwargs) as dst:
              reproject(
                source=data,
                destination=rasterio.band(dst, 1),
                src_transform=tile_meta['transform'],
                src_crs=tile_meta['crs'],
                dst_transform=target_transform,
                dst_crs=tile_meta['crs'],
                resampling=Resampling.nearest,
              )
            data = out_memfile.read()
            tile_meta = kwargs
          else:
            # Create a new MemoryFile for each tile
            memfile = rasterio.MemoryFile()
            with memfile.open(**tile_meta) as dst:
                dst.write(data)
            # Read and return the bytes
            data = memfile.read()
            
          return data, tile_meta
        else:
            print(f" - Error converting tile to raster: tile_to_raster failed for {tile.x}, {tile.y}")
    else:
        return None, None
    return None, None

def mbtiles_to_raster(mbtiles_path, zoom, selected_tiles=None, processes=multiprocessing.cpu_count()):
  """Converts an MBTiles database to a list of (data, metadata) tuples, using multiprocessing."""
  sources = []
  if not selected_tiles:
      selected_tiles = get_tiles_from_mbtiles(mbtiles_path, zoom)

  print(f" - : Processing {len(selected_tiles)} tiles from {mbtiles_path} at zoom {zoom}")
  
  with multiprocessing.Pool(processes=processes) as pool:
      results = pool.starmap(_process_tile, [(mbtiles_path, zoom, tile, None) for tile in selected_tiles])

      for data, meta in results:
        if data is not None:
            memfile = rasterio.MemoryFile(data)
            sources.append((memfile, meta))

  if not sources:
      return None
  return sources

def merge_mbtiles(mbtiles_path1, mbtiles_path2, zoom, selected_tiles=None):
    """Merges two MBTiles databases with a clipping area."""
    print(f" - Starting raster extraction from input files")
    rasters1 = mbtiles_to_raster(mbtiles_path1, zoom, selected_tiles)
    rasters2 = mbtiles_to_raster(mbtiles_path2, zoom, selected_tiles)

    if not rasters1 and not rasters2:
      print(" - No raster data found, skipping merge")
      return None, None
      
    if not rasters1:
        print(" - No rasters for file 1, skipping it")
        all_sources = rasters2
    elif not rasters2:
        print(" - No rasters for file 2, skipping it")
        all_sources = rasters1
    else:
        # Get target metadata
        target_memfile, target_meta = rasters2[0] if rasters2 else rasters1[0]

        try:
            # Process first set of rasters
            reprojected_rasters = []
            for memfile, meta in rasters1:
                if meta['crs'] is not None:
                    transform, width, height = calculate_default_transform(
                        meta['crs'], target_meta['crs'],
                        meta['width'], meta['height'],
                        *rasterio.transform.array_bounds(1, 1, meta['transform']),
                        resolution=target_meta.get('res', (target_meta['transform'][2] - target_meta['transform'][0]) / target_meta['width']
                    ))

                    kwargs = meta.copy()
                    kwargs.update({
                        "crs": target_meta['crs'],
                        "transform": transform,
                        "width": width,
                        "height": height,
                    })

                    # Read source data
                    with memfile.open() as src:
                        data = src.read()

                    # Create reprojected raster
                    out_memfile = rasterio.MemoryFile()
                    with out_memfile.open(**kwargs) as dst:
                        reproject(
                            source=data,
                            destination=rasterio.band(dst, 1),
                            src_transform=meta['transform'],
                            src_crs=meta['crs'],
                            dst_transform=transform,
                            dst_crs=target_meta['crs'],
                            resampling=Resampling.nearest,
                        )
                    reprojected_rasters.append((out_memfile, kwargs))
                else:
                    print(" - Skipping re-projection as the CRS is None")
                    reprojected_rasters.append((memfile, meta))

            # Combine all sources
            all_sources = rasters2 + reprojected_rasters
            if not all_sources:
                return None, None
            
            print(" - Starting raster merge")

            # Open all sources for merging
            raster_sources = []
            for memfile, _ in all_sources:
                raster_sources.append(memfile.open())

            # Perform merge
            merged_array, merged_transform = merge(raster_sources, nodata=np.nan)

            # Update metadata for merged result
            merged_meta = target_meta.copy()
            merged_meta.update({
                "driver": "GTiff",
                "height": merged_array.shape[1],
                "width": merged_array.shape[2],
                "transform": merged_transform,
            })

            # Create final output - return both the data and metadata
            return merged_array, merged_meta

        finally:
            # Clean up resources
            for src in raster_sources:
                src.close()
            for memfile, _ in all_sources:
                memfile.close()

def create_mbtiles_from_raster(raster_data, raster_meta, output_mbtiles_path, zoom):
    if raster_data is not None:
      _create_tiles_from_raster(raster_data, raster_meta, output_mbtiles_path, zoom)
    else:
      print(" - No raster data provided, skipping tile creation")
def _create_tiles_from_raster(raster_data, raster_meta, output_mbtiles_path, zoom):
  """Create a new MBTiles file from raster data at a zoom level."""
  conn = sqlite3.connect(output_mbtiles_path)
  cursor = conn.cursor()
  
  try:
    # Check if the 'tiles' table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tiles';")
    table_exists = cursor.fetchone()

    if not table_exists:
      # Create the 'tiles' table only if it doesn't exist
      cursor.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);")
      conn.commit()
      
    # Create a memory file with the complete raster for bounds calculation
    with rasterio.MemoryFile() as memfile:
        with memfile.open(**raster_meta) as src:
            # Write the data
            src.write(raster_data)

            # Get bounds for tile calculation
            bounds = src.bounds

            # Create tiles based on zoom level
            tiles = list(mercantile.tiles(
                bounds.left, bounds.bottom,
                bounds.right, bounds.top,
                zooms=[zoom]
            ))

            print(f" - Creating {len(tiles)} output tiles")

            for i, tile in enumerate(tiles):
                bounds = get_tile_bounds(tile)

                # Create window for the current tile
                window = src.window(bounds.west, bounds.south, bounds.east, bounds.north)

                # Read data for this tile
                tile_data = src.read(window=window)

                # Insert tile data into database
                cursor.execute(
                  "INSERT INTO tiles VALUES (?, ?, ?, ?)",
                  (tile.z, tile.x, tile.y, sqlite3.Binary(tile_data.tobytes()))
                )
                conn.commit()
                
                if (i + 1) % 100 == 0:
                    print(f" Created {i + 1} output tiles")
    
    print(" - Finished tile creation")

  finally:
    conn.close()
def reproject_bounds(bounds, in_crs, out_crs):
  """Reprojects bounds to a new crs"""
  project = pyproj.Transformer.from_crs(in_crs, out_crs, always_xy=True).transform
  min_x, min_y = project(bounds[0], bounds[1])
  max_x, max_y = project(bounds[2], bounds[3])
  return min_x, min_y, max_x, max_y

def load_shapefile(shapefile_path):
  """Loads a shapefile and returns the first Polygon in it."""
  with fiona.open(shapefile_path) as source:
    for feature in source:
      if feature['geometry']['type'] == 'Polygon':
        return shape(feature['geometry'])
    return None

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
    mbtiles_path1 = "/opt/JAXA_AW3D30_2024_terrainrgb_z0-Z12_webp.mbtiles"
    mbtiles_path2 = "/opt/swissALTI3D_2024_terrainrgb_z0-Z16.mbtiles"
    output_mbtiles_path = "/opt/exclude_terrain.mbtiles"
    min_zoom = 10 # Desired zoom level for merging
    output_bounds_wgs84 = None # no bounds

    # Determine the max zoom
    max_zoom = get_max_zoom_level(mbtiles_path2)
    print(f"Max zoom of mbtiles file: {max_zoom}")

    for zoom in range(min_zoom, max_zoom + 1):
        print(f"Starting merge for zoom: {zoom}")
        # Calculate tiles to extract based on bounds and zoom level
        if output_bounds_wgs84:
            selected_tiles = list(mercantile.tiles(*output_bounds_wgs84, zooms=[zoom]))
        else:
            selected_tiles = get_tiles_from_mbtiles(mbtiles_path2, zoom)

        merged_array, merged_meta = merge_mbtiles(mbtiles_path1, mbtiles_path2, zoom, selected_tiles)

        if merged_array is not None:
            _create_tiles_from_raster(merged_array, merged_meta, output_mbtiles_path, zoom)
            print(f"Successfully created mbtiles for zoom {zoom}")
        else:
            print(f"Could not merge mbtiles for zoom {zoom}, please check your data")
