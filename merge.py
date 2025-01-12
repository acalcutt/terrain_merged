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
            print(f"RGB values: R min={np.min(r)}, max={np.max(r)}, G min={np.min(g)}, max={np.max(g)}, B min={np.min(b)}, max={np.max(b)}")
            try:
                elevation = -10000 + ((r * 256 * 256 + g * 256 + b) * 0.1)
                mask = np.vectorize(should_exclude)(r,g,b)
                elevation = np.where(mask, np.nan, elevation)
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
                "driver": "GTiff"
            })
        
        return np.expand_dims(elevation, axis=0), kwargs, dataset.meta

    except Exception as e:
        if debug:
            print(f" - Error decoding terrain rgb: {e}")
        return None, None, None


def extract_tile_data(mbtiles_path, zoom, tile_x, tile_y):
    """Extract a tile from MBTiles as bytes."""
    conn = sqlite3.connect(mbtiles_path)
    cursor = conn.cursor()
    cursor.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?", (zoom, tile_x, tile_y))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def tile_to_raster(tile_data, bounds):
    """Converts a tile to a rasterio raster object."""
    if not tile_data:
        print(" - Error converting tile to raster: tile_data is None")
        return None, None
        
    elevation, elevation_meta, base_meta = decode_terrainrgb(tile_data, debug = True)
    if elevation is None or elevation_meta is None:
        print(" - Error converting tile to raster: could not decode tile_data")
        return None, None

    # Create a copy of the base meta
    kwargs = elevation_meta.copy()
    kwargs.update({
        'transform': rasterio.transform.from_bounds(bounds.west, bounds.south, bounds.east, bounds.north, elevation_meta['width'], elevation_meta['height'])
    })

    try:
      with rasterio.MemoryFile() as memfile:
        with memfile.open(**kwargs) as transformed_raster:
            transformed_raster.write(elevation)
            return transformed_raster.read(), transformed_raster.meta # read the data
          
    except Exception as e:
        print(f" - Error converting tile to raster: {e}")
        return None, None

def get_tile_bounds(tile):
    return mercantile.bounds(tile)


def mbtiles_to_raster(mbtiles_path, zoom, selected_tiles=None):
    """Converts an MBTiles database to a rasterio object."""
    conn = sqlite3.connect(mbtiles_path)
    cursor = conn.cursor()

    sources = []
    if selected_tiles:
        print(f" - : Processing {len(selected_tiles)} tiles")
        for i, tile in enumerate(selected_tiles):
            cursor.execute(
                "SELECT DISTINCT tile_column, tile_row FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
                (zoom, tile.x, tile.y),
            )
            result = cursor.fetchone()
            if result:
                tile_x, tile_y = result
                tile_obj = mercantile.Tile(x=tile_x, y=tile_y, z=zoom)
                bounds = get_tile_bounds(tile_obj)
                tile_data = extract_tile_data(mbtiles_path, zoom, tile_x, tile_y)
                if tile_data:
                    raster, meta = tile_to_raster(tile_data, bounds)
                    if raster is not None:
                      sources.append((raster, meta))
                else:
                    print(f" - Error extracting tile_data: tile_to_raster failed for {tile.x}, {tile.y}")
            if (i + 1) % 100 == 0:
                print(f" Processed {i + 1} tiles")

    else:
        cursor.execute("SELECT DISTINCT tile_column, tile_row FROM tiles WHERE zoom_level = ?", (zoom,))
        results = cursor.fetchall()
        for i, (tile_x, tile_y) in enumerate(results):
            tile = mercantile.Tile(x=tile_x, y=tile_y, z=zoom)
            bounds = get_tile_bounds(tile)
            tile_data = extract_tile_data(mbtiles_path, zoom, tile_x, tile_y)
            if tile_data:
                raster, meta = tile_to_raster(tile_data, bounds)
                if raster is not None:
                  sources.append((raster,meta))
            else:
                print(f" - Error extracting tile_data: tile_to_raster failed for {tile.x}, {tile.y}")
            if (i + 1) % 100 == 0:
                print(f" Processed {i + 1} tiles")
    conn.close()

    if not sources:
        return None

    return sources


def merge_mbtiles(mbtiles_path1, mbtiles_path2, zoom, selected_tiles=None):
    """Merges two MBTiles databases with a clipping area."""
    # 1 - Get all rasters for mbtiles files
    print(f" - Starting raster extraction from input files")
    rasters1 = mbtiles_to_raster(mbtiles_path1, zoom, selected_tiles)
    rasters2 = mbtiles_to_raster(mbtiles_path2, zoom, selected_tiles)

    if not rasters1 or not rasters2:
        return None

    # 2 - Find a target raster, should be a high resolution dataset, from our two inputs
    target_raster = None
    if rasters2:
        target_raster = rasters2[0]

    if not target_raster:
        if rasters1:
            target_raster = rasters1[0]

    if not target_raster:
        return None

    if target_raster:
        target_meta = target_raster[1]
    else:
        return None
    
    # 3 - reproject and clip the rasters, if needed.
    reprojected_rasters = []
    for raster, meta in rasters1:
        if raster is not None and meta['crs'] is not None:
            transform, width, height = calculate_default_transform(
                meta['crs'], target_meta['crs'], meta['width'], meta['height'], *rasterio.transform.array_bounds(1, 1, meta['transform']), resolution=target_meta.get('res', (target_meta['transform'][2] - target_meta['transform'][0]) / target_meta['width'])
            )

            kwargs = meta.copy()
            kwargs.update(
                {
                    "crs": target_meta['crs'],
                    "transform": transform,
                    "width": width,
                    "height": height,
                }
            )
            with rasterio.MemoryFile() as memfile:
                with memfile.open(**kwargs) as dst:
                    reproject(
                        source=rasterio.band(rasterio.open(io.BytesIO(raster.tobytes())), 1),
                        destination=rasterio.band(dst, 1),
                        src_transform=meta['transform'],
                        src_crs=meta['crs'],
                        dst_transform=transform,
                        dst_crs=target_meta['crs'],
                        resampling=Resampling.nearest,
                    )
                    reprojected_rasters.append((dst.read(), dst.meta))
        else:
            print(" - Skipping re-projection as the CRS is None")
            reprojected_rasters.append((raster, meta))
            
    clipped_rasters_2 = []
    for raster, meta in rasters2:
        clipped_rasters_2.append((raster,meta))
      
    all_sources = clipped_rasters_2 + reprojected_rasters

    # 4 - merge all rasters
    if not all_sources:
        return None
    print(" - Starting raster merge")
      
    raster_sources = []
    for raster, meta in all_sources:
      if raster is not None:
        with rasterio.MemoryFile() as memfile:
            with memfile.open(**meta) as r:
              raster_sources.append(r.read())

    merged_array, merged_transform = merge(raster_sources, nodata = np.nan)
    
    merged_meta = target_meta.copy()
    merged_meta.update({
        "driver": "GTiff",
        "height": merged_array.shape[1],
        "width": merged_array.shape[2],
        "transform": merged_transform,
    })

    with rasterio.MemoryFile() as memfile:
      with memfile.open(**merged_meta) as dest:
        dest.write(merged_array)
        return dest

def create_mbtiles_from_raster(raster, output_mbtiles_path, zoom):
    """Create a new MBTiles file from a raster at a zoom level."""
    conn = sqlite3.connect(output_mbtiles_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);")
    conn.commit()

    # Create tiles based on zoom level
    tiles = list(mercantile.tiles(raster.bounds[0], raster.bounds[1], raster.bounds[2], raster.bounds[3], zooms=[zoom]))
    print(f" - Creating {len(tiles)} output tiles")
    for i, tile in enumerate(tiles):
      bounds = get_tile_bounds(tile)

      # create the clipping area based on the bounds of the tile
      clip_poly = Polygon([(bounds.west, bounds.south), (bounds.east, bounds.south), (bounds.east, bounds.north),
                          (bounds.west, bounds.north)])

      # clip the raster to the current tile
      with rasterio.MemoryFile(raster) as memfile:
        with memfile.open() as r:
          tile_bytes = r.read().tobytes()
          cursor.execute("INSERT INTO tiles VALUES (?, ?, ?, ?)", (tile.z, tile.x, tile.y, sqlite3.Binary(tile_bytes)))
          conn.commit()
      if (i + 1) % 100 == 0:
          print(f" Created {i + 1} output tiles")
    print(" - Finished tile creation")

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

        merged_raster_obj = merge_mbtiles(mbtiles_path1, mbtiles_path2, zoom, selected_tiles)

        if merged_raster_obj:
            create_mbtiles_from_raster(merged_raster_obj, output_mbtiles_path, zoom)
            print(f"Successfully created mbtiles for zoom {zoom}")
        else:
            print(f"Could not merge mbtiles for zoom {zoom}, please check your data")
