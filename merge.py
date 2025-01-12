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


def extract_tile_data(mbtiles_path, zoom, tile_x, tile_y):
    """Extract a tile from MBTiles as bytes."""
    conn = sqlite3.connect(mbtiles_path)
    cursor = conn.cursor()
    cursor.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?", (zoom, tile_x, tile_y))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

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
                    raster = tile_to_raster(tile_data, bounds)
                    if raster:
                        sources.append(raster)
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
                raster = tile_to_raster(tile_data, bounds)
                if raster:
                    sources.append(raster)
            else:
                print(f" - Error extracting tile_data: tile_to_raster failed for {tile.x}, {tile.y}")
            if (i + 1) % 100 == 0:
                print(f" Processed {i + 1} tiles")
    conn.close()

    if not sources:
        return None

    return sources


def clip_raster(raster, clipping_area):
    """Clips a rasterio raster object with a polygon."""
    if not clipping_area:
        return raster
    try:
        if not clipping_area.is_valid:
            print(" - Error during clipping of raster: Clipping area is invalid")
            return None
        print(f" - Clipping area bounds: {clipping_area.bounds}")
        print(f" - Raster bounds {raster.bounds}")
        with mask.mask(raster, [clipping_area], crop=True) as (clipped_array, clipped_transform):
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


def merge_mbtiles(mbtiles_path1, mbtiles_path2, zoom, clipping_area=None, selected_tiles=None):
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

    # 3 - reproject and clip the rasters, if needed.
    reprojected_rasters = []
    for raster in rasters1:
        if raster and raster.crs is not None and target_raster.crs is not None:
            transform, width, height = calculate_default_transform(
                raster.crs, target_raster.crs, raster.width, raster.height, *raster.bounds, resolution=target_raster.res
            )

            kwargs = raster.meta.copy()
            kwargs.update(
                {
                    "crs": target_raster.crs,
                    "transform": transform,
                    "width": width,
                    "height": height,
                }
            )
            with rasterio.MemoryFile() as memfile:
                with memfile.open(**kwargs) as dst:
                    reproject(
                        source=rasterio.band(raster, 1),
                        destination=rasterio.band(dst, 1),
                        src_transform=raster.transform,
                        src_crs=raster.crs,
                        dst_transform=transform,
                        dst_crs=target_raster.crs,
                        resampling=Resampling.nearest,
                    )
                    if clipped_raster := clip_raster(dst, clipping_area):
                        reprojected_rasters.append(clipped_raster)
        else:
            print(" - Skipping re-projection as the CRS is None")
            if clipped_raster := clip_raster(raster, clipping_area):
               reprojected_rasters.append(clipped_raster)

    clipped_rasters_2 = []
    for raster in rasters2:
        if clipped_raster := clip_raster(raster, clipping_area):
            clipped_rasters_2.append(clipped_raster)

    all_sources = clipped_rasters_2 + reprojected_rasters

    # 4 - merge all rasters
    if not all_sources:
        return None
    print(" - Starting raster merge")

    #open all the sources as rasters
    raster_sources = []
    for source in all_sources:
      with rasterio.MemoryFile(source) as memfile:
        with memfile.open() as raster:
          raster_sources.append(raster)
          

    merged_array, merged_transform = merge(raster_sources)

    merged_meta = target_raster.meta.copy()
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
      clipped_raster = clip_raster(raster, clip_poly)

      if clipped_raster:
        with rasterio.MemoryFile(clipped_raster) as memfile:
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
    output_mbtiles_path = "/opt/merged_terrain.mbtiles"
    min_zoom = 10 # Desired zoom level for merging
    shapefile_path = "switzerland_Switzerland_Country_Boundary.shp"
    output_bounds_wgs84 = None # no bounds

    # Determine the max zoom
    max_zoom = get_max_zoom_level(mbtiles_path2)
    print(f"Max zoom of mbtiles file: {max_zoom}")

    # Define the clipping area using the shapefile.
    clipping_area_wgs84 = load_shapefile(shapefile_path)

    # Reproject the bounding box from WGS84 to WebMercator for clipping
    project = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
    clipping_area = geom_transform(project, clipping_area_wgs84)

    for zoom in range(min_zoom, max_zoom + 1):
        print(f"Starting merge for zoom: {zoom}")
        # Calculate tiles to extract based on bounds and zoom level
        if output_bounds_wgs84:
            selected_tiles = list(mercantile.tiles(*output_bounds_wgs84, zooms=[zoom]))
        else:
            selected_tiles = get_tiles_from_mbtiles(mbtiles_path2, zoom)

        merged_raster_obj = merge_mbtiles(mbtiles_path1, mbtiles_path2, zoom, clipping_area, selected_tiles)

        if merged_raster_obj:
            create_mbtiles_from_raster(merged_raster_obj, output_mbtiles_path, zoom)
            print(f"Successfully created mbtiles for zoom {zoom}")
        else:
            print(f"Could not merge mbtiles for zoom {zoom}, please check your data")
