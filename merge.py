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
from pathlib import Path
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Tuple, List
from contextlib import contextmanager
from datetime import datetime

class EncodingType(Enum):
    MAPBOX = "mapbox"
    TERRARIUM = "terrarium"

@dataclass
class MBTilesSource:
    """Configuration for an MBTiles source file"""
    path: Path
    encoding: EncodingType

@dataclass
class ProcessTileArgs:
    """Arguments for parallel tile processing"""
    tile: mercantile.Tile
    primary_source: MBTilesSource
    secondary_source: MBTilesSource
    output_path: Path
    output_encoding: EncodingType
    resampling: int

@dataclass
class TileData:
    """Container for decoded tile data"""
    data: np.ndarray
    meta: dict
    source_zoom: int

class TerrainRGBMerger:
    def __init__(
        self,
        primary_source: MBTilesSource,
        secondary_source: MBTilesSource,
        output_path: Path,
        output_encoding: EncodingType = EncodingType.MAPBOX,
        resampling: int = Resampling.lanczos,
        processes: Optional[int] = None,
        default_tile_size: int = 512
    ):
        print(f"__init__ called")
        self.primary_source = primary_source
        self.secondary_source = secondary_source
        self.output_path = Path(output_path)
        self.output_encoding = output_encoding
        self.resampling = resampling
        self.processes = processes or multiprocessing.cpu_count()
        self.logger = logging.getLogger(__name__)
        self.default_tile_size = default_tile_size

    @contextmanager
    def _db_connection(self, db_path: Path):
        """Context manager for database connections"""
        print(f"_db_connection called with db_path: {db_path}")
        conn = sqlite3.connect(db_path)
        try:
            yield conn
        finally:
            conn.close()
    
    def _decode_elevation(self, rgb: np.ndarray, encoding: EncodingType) -> np.ndarray:
        """
        Decode RGB values to elevation data based on specified encoding format and mask 0 and -1
        """
        r, g, b = rgb[0], rgb[1], rgb[2]

        if encoding == EncodingType.TERRARIUM:
            # Terrarium encoding: (red * 256 + green + blue / 256) - 32768
            elevation = (r * 256 + g + b / 256) - 32768
        else:
            # Mapbox encoding: -10000 + ((R * 256 * 256 + G * 256 + B) * 0.1)
            elevation = -10000 + ((r * 256 * 256 + g * 256 + b) * 0.1)
        
        # Mask 0 and -1 elevation values
        mask = np.logical_or(elevation == 0, elevation == -1)

        return np.where(mask, np.nan, elevation)

    def _encode_elevation(self, elevation: np.ndarray) -> np.ndarray:
        """
        Encode elevation data to RGB values using output encoding format
        """
        # Reshape the elevation array to ensure it's 2D
        if elevation.ndim > 2:
          elevation = elevation[0]
          
        if elevation.ndim == 1:
          elevation = elevation.reshape((1,elevation.shape[0]))
         

        # Replace NaN with 0 before encoding to avoid errors
        elevation = np.nan_to_num(elevation, nan=0)
        rows, cols = elevation.shape
        rgb = np.zeros((3, rows, cols), dtype=np.uint8)

        if self.output_encoding == EncodingType.TERRARIUM:
            # Clip elevation to valid range for Terrarium encoding
            elevation = np.clip(elevation, -32768, 32767)
            scaled = elevation + 32768

            # Calculate RGB values
            rgb[0] = np.floor(scaled / 256)     # Red
            rgb[1] = np.floor(scaled % 256)      # Green
            rgb[2] = np.floor((scaled - np.floor(scaled)) * 256)  # Blue
        else:
            # Mapbox encoding
            elevation = np.clip(elevation, -10000, 8900)
            scaled = (elevation + 10000) / 0.1
            
            rgb[0] = (scaled // (256 * 256)) % 256
            rgb[1] = (scaled // 256) % 256
            rgb[2] = scaled % 256
            
        return rgb

    def _decode_tile(self, tile_data: bytes, tile: mercantile.Tile, encoding: EncodingType) -> Tuple[Optional[np.ndarray], dict]:
        """Decode tile data using specified encoding format"""
        if not isinstance(tile_data, bytes) or len(tile_data) == 0:
            raise ValueError("Invalid tile data")
            
        try:
            # Log the size of the tile data to make sure it's non-empty
            #self.logger.debug(f"Tile data size for {tile.z}/{tile.x}/{tile.y}: {len(tile_data)} bytes")
                
            # Convert the image to a PNG using Pillow
            image = Image.open(io.BytesIO(tile_data))
            image = image.convert('RGB')  # Force to RGB
            image_png = io.BytesIO()
            image.save(image_png, format='PNG', bits=8)
            image_png.seek(0)
                
            with rasterio.open(image_png) as dataset:
                # Check if we can read data properly
                rgb = dataset.read(masked=False).astype(np.int32)
                #self.logger.debug(f"Decoded tile RGB shape: {rgb.shape}, dtype: {rgb.dtype}")
                    
                if rgb.ndim != 3 or rgb.shape[0] != 3:
                    self.logger.error(f"Unexpected RGB shape in tile {tile.z}/{tile.x}/{tile.y}: {rgb.shape}")
                    return None, {}

                elevation = self._decode_elevation(rgb, encoding)
                    
                bounds = mercantile.bounds(tile)
                meta = dataset.meta.copy()
                meta.update({
                    'count': 1,
                    'dtype': rasterio.float32,
                    'driver': 'GTiff',
                    'crs': 'EPSG:3857',
                    'transform': rasterio.transform.from_bounds(
                        bounds.west, bounds.south, bounds.east, bounds.north,
                        meta['width'], meta['height']
                    )
                })
                    
                #self.logger.debug(f"Decoded elevation: min={np.nanmin(elevation)}, max={np.nanmax(elevation)}")
                return elevation, meta
        except Exception as e:
            self.logger.error(f"Failed to decode tile data, returning None, None: {e}")
            return None, {}

    def _extract_tile(self, source: MBTilesSource, zoom: int, x: int, y: int) -> Optional[TileData]:
        """Extract and decode a tile, with fallback to parent tiles"""
        #print(f"_extract_tile called with source: {source}, zoom: {zoom}, x: {x}, y: {y}")
        current_zoom = zoom
        current_x, current_y = x, y

        while current_zoom >= 0:
            with self._db_connection(source.path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                    (current_zoom, current_x, current_y)
                )
                result = cursor.fetchone()
                
                if result is not None:
                    try:
                        data_meta = self._decode_tile(result[0], mercantile.Tile(current_x, current_y, current_zoom), source.encoding)
                        #self.logger.debug(f"decoded data for {current_zoom}/{current_x}/{current_y}: data is {data_meta[0] is None}, meta is {data_meta[1] is None}")
                        if data_meta[0] is None:
                            return None
                        if data_meta[0].size == 0:
                          return None
                        return TileData(data_meta[0], data_meta[1], current_zoom)
                    except Exception as e:
                        self.logger.error(f"Failed to decode tile {current_zoom}/{current_x}/{current_y}: {e}")
                        return None
            
            if current_zoom > 0:
                current_x //= 2
                current_y //= 2
            current_zoom -= 1
        
        return None

    def _merge_tiles(self, primary: Optional[TileData], secondary: Optional[TileData], target_tile: mercantile.Tile) -> Optional[np.ndarray]:
      """Merge two tiles, handling upscaling and priorities"""
      #print(f"_merge_tiles called with primary: {primary}, secondary: {secondary}, target_tile: {target_tile}")
      if primary is None and secondary is None:
        return None

      bounds = mercantile.bounds(target_tile)
      
      # Use the tile size of the primary tile, or the default if no primary tile
      tile_size = self.default_tile_size
      if primary is not None and 'width' in primary.meta and 'height' in primary.meta:
        tile_size = primary.meta['width']

      target_transform = rasterio.transform.from_bounds(
          bounds.west, bounds.south, bounds.east, bounds.north,
          tile_size, tile_size  # Use determined tile size
      )

      result = None

      # Process primary tile if available
      if primary is not None:
        result = self._resample_if_needed(primary, target_tile, target_transform, tile_size)
      

      # Process and merge secondary tile if available
      if secondary is not None:
        secondary_data = self._resample_if_needed(secondary, target_tile, target_transform, tile_size)
        if result is None:
            # If no primary tile, the result is just the secondary
            result = secondary_data
        else:
            # Merge using secondary data where valid (secondary is prioritized)
            mask = ~np.isnan(secondary_data)
            if np.any(mask): # Check if there are valid pixels to merge
                result[mask] = secondary_data[mask]
      
      return result

    def _resample_if_needed(self, tile_data: TileData, target_tile: mercantile.Tile, target_transform, tile_size) -> np.ndarray:
        """Resample tile data if source zoom differs from target"""
        #print(f"_resample_if_needed called with tile_data: {tile_data}, target_tile: {target_tile}")
        if tile_data.source_zoom != target_tile.z:
            with rasterio.io.MemoryFile() as memfile:
                with memfile.open(**tile_data.meta) as src:
                    dst_data = np.zeros((1, tile_size, tile_size), dtype=np.float32)
                    reproject(
                        source=tile_data.data,
                        destination=dst_data,
                        src_transform=tile_data.meta['transform'],
                        src_crs=tile_data.meta['crs'],
                        dst_transform=target_transform,
                        dst_crs=tile_data.meta['crs'],
                        resampling=self.resampling
                    )
                    
                    if dst_data.ndim == 3:
                      return dst_data[0]
                    else:
                      return dst_data
        if tile_data.data.ndim == 3:
            return tile_data.data[0]
        else:
            return tile_data.data
        

    def process_tile(self, tile: mercantile.Tile) -> None:
        """Process a single tile, merging data from both sources"""
        #print(f"process_tile called with tile: {tile}")
        try:
            # Extract tiles from both sources
            primary_data = self._extract_tile(self.primary_source, tile.z, tile.x, tile.y)
            secondary_data = self._extract_tile(self.secondary_source, tile.z, tile.x, tile.y)
            
            if primary_data is None and secondary_data is None:
                self.logger.debug(f"No data found for tile {tile.z}/{tile.x}/{tile.y}")
                return
            
            # Merge the elevation data
            merged_elevation = self._merge_tiles(primary_data, secondary_data, tile)
            
            if merged_elevation is not None:
                # Encode using output format and save
                rgb_data = self._encode_elevation(merged_elevation)
                self._save_tile(tile, rgb_data)
                self.logger.info(f"Successfully processed tile {tile.z}/{tile.x}/{tile.y}")
        except Exception as e:
            self.logger.error(f"Error processing tile {tile.z}/{tile.x}/{tile.y}: {e}")
            raise

    def _save_tile(self, tile: mercantile.Tile, rgb_data: np.ndarray) -> None:
      """Save processed tile to output MBTiles"""
      #print(f"_save_tile called with tile: {tile}, rgb_data shape: {rgb_data.shape}")
      with self._db_connection(self.output_path) as conn:
          cursor = conn.cursor()

          # Ensure table exists
          cursor.execute("""
              CREATE TABLE IF NOT EXISTS tiles (
                  zoom_level INTEGER,
                  tile_column INTEGER,
                  tile_row INTEGER,
                  tile_data BLOB,
                  PRIMARY KEY (zoom_level, tile_column, tile_row)
              )
          """)
          
          # Convert the RGB array to a PNG image
          if rgb_data.size > 0:
            if rgb_data.ndim == 3:
              image = Image.fromarray(np.moveaxis(rgb_data, 0, -1), 'RGB')
            else:
              tile_size = self.default_tile_size
              image = Image.fromarray(np.moveaxis(np.zeros((3,tile_size,tile_size),dtype=np.uint8), 0, -1), 'RGB')

            image_bytes = io.BytesIO()
            image.save(image_bytes, format='PNG')
            image_bytes = image_bytes.getvalue()

            cursor.execute(
                "INSERT OR REPLACE INTO tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
                (tile.z, tile.x, tile.y, sqlite3.Binary(image_bytes))
              )
          
          conn.commit()

    def _get_tiles_for_zoom(self, zoom: int) -> List[mercantile.Tile]:
        """Get list of tiles to process for a given zoom level"""
        print(f"_get_tiles_for_zoom called with zoom: {zoom}")
        tiles = set()
        
        # Get tiles ONLY from the secondary source
        source = self.secondary_source
        with self._db_connection(source.path) as conn:
          cursor = conn.cursor()
          cursor.execute(
            'SELECT DISTINCT tile_column, tile_row FROM tiles WHERE zoom_level = ?',
            (zoom,)
          )
          rows = cursor.fetchall()
            
          if not rows:
            self.logger.warning(f"No tiles found for zoom level {zoom} in source {source.path}")
          else:
            #self.logger.debug(f"Rows fetched for zoom level {zoom}: {rows}")
            for row in rows:
              if isinstance(row, tuple) and len(row) == 2:
                x, y = row
                tiles.add(mercantile.Tile(x=x, y=y, z=zoom))
              else:
                self.logger.warning(f"Skipping invalid row: {row}")
        
        return list(tiles)

    @staticmethod
    def _process_tile_wrapper(args: ProcessTileArgs) -> None:
        """Static wrapper method for parallel tile processing"""
        print(f"_process_tile_wrapper called with args: {args}")
        try:
            merger = TerrainRGBMerger(
                primary_source=args.primary_source,
                secondary_source=args.secondary_source,
                output_path=args.output_path,
                output_encoding=args.output_encoding,
                resampling=args.resampling,
                processes=1,
                default_tile_size=512
            )
            merger.process_tile(args.tile)
        except Exception as e:
            logging.error(f"Error processing tile {args.tile}: {e}")

    def process_zoom_level(self, zoom: int):
        """Process all tiles for a given zoom level in parallel"""
        print(f"process_zoom_level called with zoom: {zoom}")
        self.logger.info(f"Processing zoom level {zoom}")
        
        # Get list of tiles to process
        tiles = self._get_tiles_for_zoom(zoom)
        self.logger.info(f"Found {len(tiles)} tiles to process")
        
        # Prepare arguments for parallel processing
        process_args = [
            ProcessTileArgs(
                tile=tile,
                primary_source=self.primary_source,
                secondary_source=self.secondary_source,
                output_path=self.output_path,
                output_encoding=self.output_encoding,
                resampling=self.resampling
            )
            for tile in tiles
        ]
        
        # Process tiles in parallel
        with multiprocessing.Pool(self.processes) as pool:
            for _ in pool.imap_unordered(self._process_tile_wrapper, process_args):
                pass

    def get_max_zoom_level(self) -> int:
        """Get the maximum zoom level from both sources"""
        print("_get_max_zoom_level called")
        max_zoom = 0
        for source in [self.primary_source, self.secondary_source]:
            with self._db_connection(source.path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(zoom_level) FROM tiles")
                result = cursor.fetchone()
                if result[0] is not None:
                    max_zoom = max(max_zoom, result[0])
        return max_zoom

    def process_all(self, min_zoom: int = 0):
        """Process all zoom levels from min_zoom to max available"""
        print(f"process_all called with min_zoom: {min_zoom}")
        max_zoom = self.get_max_zoom_level()
        self.logger.info(f"Processing zoom levels {min_zoom} to {max_zoom}")

        for zoom in range(min_zoom, max_zoom + 1):
            self.process_zoom_level(zoom)

        self.logger.info("Completed processing all zoom levels")

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # Generate timestamp for the output path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_output_path = Path(f"/opt/output_{timestamp}.mbtiles")

    
    merger = TerrainRGBMerger(
        primary_source=MBTilesSource(
            path=Path("/opt/JAXA_AW3D30_2024_terrainrgb_z0-Z12_webp.mbtiles"),
            encoding=EncodingType.MAPBOX
        ),
        secondary_source=MBTilesSource(
            path=Path("/opt/swissALTI3D_2024_terrainrgb_z0-Z16.mbtiles"),
            encoding=EncodingType.MAPBOX
        ),
        output_path=base_output_path, # Use the single timestamped output path
        output_encoding=EncodingType.MAPBOX,
        default_tile_size = 512,
        resampling = Resampling.bilinear
    )
    
    merger.process_all()
