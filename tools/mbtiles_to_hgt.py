import mercantile
from PIL import Image
import numpy as np
import os
import io
import argparse
import sqlite3
import concurrent.futures
import math

# --- Decoding Functions ---

def decode_elevation_from_rgb_rio(data: np.ndarray, encoding: str, interval: float = 0.01, base_val: float = -10000.0) -> np.ndarray:
    """
    Decodes RGB encoded data using logic similar to rio-rgbify's _decode function.

    Parameters
    ----------
    data: np.ndarray
        RGB data (shape HxWx3) to decode.
    encoding: str
        Encoding type ('terrarium' or 'mapbox').
    interval: float
        Interval value for 'mapbox' encoding.
    base_val: float
        Base value for 'mapbox' encoding.

    Returns
    -------
    np.ndarray
        Decoded elevation data.
    """
    data = data.astype(np.float64)

    if encoding == "terrarium":
        # Terrarium v1 decoding formula: (R * 256 + G + B / 256) - 32768
        return (data[..., 0] * 256.0 + data[..., 1] + data[..., 2] / 256.0) - 32768.0
    else: # 'mapbox' encoding
        # Mapbox encoding formula: base_val + (((R * 256 * 256) + (G * 256) + B) * interval)
        return base_val + (((data[..., 0] * 256.0 * 256.0) + (data[..., 1] * 256.0) + data[..., 2]) * interval)

# --- Tile Processing Function (for multiprocessing) ---

# This function must be defined at the top level for multiprocessing to pickle it.
def process_tile_for_mp(tile_info, mbtiles_path, target_zoom_level, encoding, interval, base_val, source_nodata_values=None):
    """
    Processes a single tile for multiprocessing.
    Applies source no-data masking if specified.
    Returns a tuple: (cell_identifier_key, slice_start_lat, slice_end_lat, slice_start_lon, slice_end_lon, elevations_slice_int16)
    or None if an error occurred or no valid data was produced.
    """
    tile_z, tile_x, tile_y = tile_info
    
    # Convert from TMS to XYZ coordinates for mercantile
    # MBTiles uses TMS (Y=0 at bottom), mercantile expects XYZ (Y=0 at top)
    xyz_y = (2 ** tile_z) - tile_y - 1
    tile = mercantile.Tile(x=tile_x, y=xyz_y, z=tile_z)

    conn = None
    try:
        conn = sqlite3.connect(mbtiles_path)
        cursor = conn.cursor()

        # Fetch tile data (using original TMS coordinates for database query)
        tile_data_query = "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?"
        cursor.execute(tile_data_query, (tile_z, tile_x, tile_y))
        result = cursor.fetchone()
        
        if result is None:
            return None
        
        tile_data_bytes = result[0]

        img = Image.open(io.BytesIO(tile_data_bytes)).convert("RGB")
        pixels = np.array(img) # Shape HxWx3

        elevations = decode_elevation_from_rgb_rio(pixels, encoding, interval=interval, base_val=base_val)

        # Apply source NoData value handling if specified
        if source_nodata_values:
            # Use a mask for pixels matching any source nodata value
            # np.isclose is good for float comparisons
            nodata_mask = np.zeros_like(elevations, dtype=bool)
            for nodata_val in source_nodata_values:
                nodata_mask |= np.isclose(elevations, nodata_val, rtol=1e-09, atol=1e-09)
            
            # Set matched elevations to HGT nodata value BEFORE conversion to int16
            elevations[nodata_mask] = -32768.0
        
        # Also mask any obvious nodata values that might not be in the source_nodata_values list
        # Common nodata indicators in terrain data
        elevations[elevations < -30000] = -32768.0  # Very low values are likely nodata
        elevations[np.isnan(elevations)] = -32768.0  # NaN values
        elevations[np.isinf(elevations)] = -32768.0  # Infinite values

        bounds = mercantile.bounds(tile)
        
        # Calculate HGT cell key using LOWER-LEFT (southwest) corner coordinates
        # HGT naming convention uses the southwest corner, not northwest
        hgt_cell_key_lat = math.floor(bounds.south)  # Use south boundary
        hgt_cell_key_lon = math.floor(bounds.west)   # Use west boundary
        
        cell_identifier_key = (hgt_cell_key_lat, hgt_cell_key_lon)

        # Calculate HGT slice indices based on tile bounds and cell start
        # For HGT files, latitude decreases from north to south (top to bottom)
        # So we need to flip the latitude calculations
        
        # Calculate pixel resolution at this zoom level
        # At zoom level z, each pixel represents (360 / (256 * 2^z)) degrees
        pixel_resolution = 360.0 / (256.0 * (2 ** tile.z))
        
        # Convert to arc-seconds (3600 arc-seconds per degree)
        arcsec_per_pixel = pixel_resolution * 3600.0
        
        # Calculate indices in HGT grid (3601x3601 for 1 degree cells)
        # HGT files start from the southwest corner and go north/east
        # HGT row 0 = north edge, row 3600 = south edge
        # HGT col 0 = west edge, col 3600 = east edge
        
        lat_offset_from_south = bounds.south - hgt_cell_key_lat  # Distance from south edge of cell
        lon_offset_from_west = bounds.west - hgt_cell_key_lon    # Distance from west edge of cell
        
        # Convert to HGT indices (0-3600)
        start_hgt_lat_idx = int(round((1.0 - (bounds.north - hgt_cell_key_lat)) * 3600))  # Flip for HGT: north=0, south=3600
        start_hgt_lon_idx = int(round(lon_offset_from_west * 3600))                        # West=0, east=3600
        
        # Calculate end indices based on tile size
        end_hgt_lat_idx = start_hgt_lat_idx + elevations.shape[0]
        end_hgt_lon_idx = start_hgt_lon_idx + elevations.shape[1]

        # Clamp to valid HGT grid range [0, 3600]
        slice_start_lat = max(0, start_hgt_lat_idx)
        slice_end_lat = min(3601, end_hgt_lat_idx)
        slice_start_lon = max(0, start_hgt_lon_idx)
        slice_end_lon = min(3601, end_hgt_lon_idx)

        # Calculate corresponding slice in tile data
        tile_data_start_row = max(0, -start_hgt_lat_idx)
        tile_data_start_col = max(0, -start_hgt_lon_idx)
        
        hgt_rows_in_slice = slice_end_lat - slice_start_lat
        hgt_cols_in_slice = slice_end_lon - slice_start_lon

        tile_data_end_row = tile_data_start_row + hgt_rows_in_slice
        tile_data_end_col = tile_data_start_col + hgt_cols_in_slice

        # Ensure we don't exceed tile data dimensions
        tile_data_end_row = min(tile_data_end_row, elevations.shape[0])
        tile_data_end_col = min(tile_data_end_col, elevations.shape[1])
        
        # If the resulting slice is valid
        if tile_data_end_row > tile_data_start_row and tile_data_end_col > tile_data_start_col:
            elevations_slice = elevations[tile_data_start_row:tile_data_end_row, tile_data_start_col:tile_data_end_col]
            
            # Convert to int16 and clamp to valid HGT range in the worker process
            # Values already set to -32768.0 (from source nodata) will remain -32768 after conversion
            elev_slice_int16 = np.clip(np.round(elevations_slice).astype(np.int16), -32767, 32767)
            
            return (cell_identifier_key, slice_start_lat, slice_start_lat + elev_slice_int16.shape[0], slice_start_lon, slice_start_lon + elev_slice_int16.shape[1], elev_slice_int16)
        else:
            return None

    except Exception as e:
        print(f"Error processing tile {tile} in worker: {e}")
        return None
    finally:
        if conn:
            conn.close()

# --- Main Conversion Logic ---

def convert_mbtiles_to_hgt(mbtiles_path, output_dir, zoom_level=16, encoding='mapbox', interval=0.01, base_val=-10000.0, source_nodata_values=None):
    """
    Converts MBTiles to HGT files using multiprocessing for faster tile processing.
    Handles source no-data values by mapping them to HGT nodata (-32768).
    """

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    if not os.path.exists(mbtiles_path):
        print(f"Error: MBTiles file not found at '{mbtiles_path}'")
        return

    conn = None
    try:
        conn = sqlite3.connect(mbtiles_path)
        cursor = conn.cursor()

        # Get metadata
        cursor.execute("SELECT name, value FROM metadata")
        metadata = {name: value for name, value in cursor.fetchall()}

        max_zoom = 0
        if 'maxzoom' in metadata:
            try:
                max_zoom = int(metadata['maxzoom'])
            except (ValueError, TypeError) as e:
                print(f"Warning: Could not parse 'maxzoom' from MBTiles metadata: {e}.")
                max_zoom = 0

        target_zoom_level = min(zoom_level, max_zoom) if max_zoom > 0 else zoom_level
        print(f"Using zoom level: {target_zoom_level}")
        print(f"Using encoding: {encoding}")
        if encoding == 'mapbox':
            print(f"Mapbox parameters: Interval={interval}, Base Value={base_val}")
        if source_nodata_values:
            print(f"Source NoData Values: {source_nodata_values}")

        # Fetch tile information
        tile_query = "SELECT zoom_level, tile_column, tile_row FROM tiles WHERE zoom_level = ?"
        cursor.execute(tile_query, (target_zoom_level,))
        
        tiles_info = cursor.fetchall()

        if not tiles_info:
            print(f"No tiles found for zoom level {target_zoom_level}.")
            conn.close()
            return
        
        total_tiles = len(tiles_info)
        print(f"Found {total_tiles} tiles at zoom level {target_zoom_level}.")

        # Identify unique HGT cells (using southwest corner coordinates)
        print("Identifying unique HGT cells...")
        unique_hgt_cells = set()
        for zoom_level_db, x_db, y_db in tiles_info:
            # Convert from TMS to XYZ coordinates for mercantile
            xyz_y = (2 ** zoom_level_db) - y_db - 1
            tile = mercantile.Tile(x=x_db, y=xyz_y, z=zoom_level_db)
            bounds = mercantile.bounds(tile)
            
            # HGT naming uses southwest corner coordinates
            hgt_cell_key_lat = math.floor(bounds.south)  # Use south boundary
            hgt_cell_key_lon = math.floor(bounds.west)   # Use west boundary
                
            unique_hgt_cells.add((hgt_cell_key_lat, hgt_cell_key_lon))
        
        print(f"Found {len(unique_hgt_cells)} unique HGT cells.")

        # Pre-allocate HGT grids with proper NODATA value (-32768)
        main_hgt_cells = {}
        for cell_id in unique_hgt_cells:
            main_hgt_cells[cell_id] = np.full((3601, 3601), -32768, dtype=np.int16)
        
        print(f"Starting parallel processing of {total_tiles} tiles...")
        
        num_workers = os.cpu_count() or 4
        print(f"Using {num_workers} worker processes.")

        successful_tiles = 0
        failed_tiles = 0
        
        # Use ProcessPoolExecutor
        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = []
            for tile_info in tiles_info:
                futures.append(executor.submit(
                    process_tile_for_mp,
                    tile_info,
                    mbtiles_path,
                    target_zoom_level,
                    encoding,
                    interval,
                    base_val,
                    source_nodata_values
                ))

            # Process results as they complete
            for i, future in enumerate(futures):
                if (i + 1) % 1000 == 0 or (i + 1) == len(futures):
                    print(f"Processing {i+1}/{total_tiles} tiles...")

                try:
                    result = future.result()
                    if result:
                        cell_id, s_lat, e_lat, s_lon, e_lon, elev_slice_int16 = result
                        
                        # Data is already converted to int16 in the worker process
                        # Just place it directly into the HGT grid
                        hgt_grid = main_hgt_cells[cell_id]
                        hgt_grid[s_lat:e_lat, s_lon:e_lon] = elev_slice_int16
                        successful_tiles += 1
                    else:
                        failed_tiles += 1
                except Exception as e:
                    print(f"Error processing future result: {e}")
                    failed_tiles += 1

        print(f"Finished processing tiles. Successful: {successful_tiles}, Failed: {failed_tiles}.")
        
        # Write HGT files with correct naming convention
        print(f"Writing {len(main_hgt_cells)} HGT files...")
        for (lat_idx_key, lon_idx_key), hgt_grid in main_hgt_cells.items():
            # HGT naming convention: NxxWxxx.hgt or SxxExxx.hgt
            # Where xx/xxx are zero-padded latitude/longitude values
            if lat_idx_key >= 0:
                lat_str = f"N{lat_idx_key:02d}"
            else:
                lat_str = f"S{abs(lat_idx_key):02d}"
                
            if lon_idx_key < 0:
                lon_str = f"W{abs(lon_idx_key):03d}"
            else:
                lon_str = f"E{lon_idx_key:03d}"
            
            hgt_filename = f"{lat_str}{lon_str}.hgt"
            hgt_filepath = os.path.join(output_dir, hgt_filename)

            try:
                # Convert to big-endian int16 for HGT format
                binary_data = hgt_grid.astype('>i2').tobytes()
                
                expected_size = 3601 * 3601 * 2  # 25,934,402 bytes
                if len(binary_data) != expected_size:
                    print(f"Warning: Data size mismatch for {hgt_filename}: {len(binary_data)} vs {expected_size} bytes")

                with open(hgt_filepath, 'wb') as f:
                    f.write(binary_data)
                    
                print(f"Written: {hgt_filename} ({len(binary_data)} bytes)")
                
            except Exception as e:
                print(f"Error writing HGT file {hgt_filepath}: {e}")

    finally:
        if conn:
            conn.close()
    print("Conversion complete.")

# --- Command-Line Interface ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert MBTiles (Terrarium v1 or Mapbox TerrainRGB) to HGT files using multiprocessing.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "mbtiles_file",
        help="Path to the input MBTiles file (.mbtiles)."
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="output_hgt_files",
        help="Directory to save the generated HGT files."
    )
    parser.add_argument(
        "-z", "--zoom-level",
        type=int,
        default=16,
        help="The zoom level to extract data from."
    )
    parser.add_argument(
        "-e", "--encoding",
        choices=['terrarium', 'mapbox'],
        default='mapbox',
        help="The encoding format of the MBTiles tiles."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.01,
        help="The interval value for 'mapbox' encoding."
    )
    parser.add_argument(
        "--base-val",
        type=float,
        default=-10000.0,
        help="The base value for 'mapbox' encoding."
    )
    parser.add_argument(
        "--source-nodata",
        nargs='+',
        type=float,
        default=None,
        help="List of elevation values from the source data that should be treated as no-data. These will be mapped to the HGT nodata value (-32768). Example: --source-nodata -10000 -9999"
    )

    args = parser.parse_args()

    convert_mbtiles_to_hgt(args.mbtiles_file, args.output_dir, args.zoom_level, args.encoding, args.interval, args.base_val, args.source_nodata)
