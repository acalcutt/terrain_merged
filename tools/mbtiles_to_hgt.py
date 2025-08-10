
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

def process_tile_for_mp(tile_info, mbtiles_path, target_zoom_level, encoding, interval, base_val, source_nodata_values=None):
    """
    Processes a single tile for multiprocessing with improved coordinate handling.
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
            nodata_mask = np.zeros_like(elevations, dtype=bool)
            for nodata_val in source_nodata_values:
                nodata_mask |= np.isclose(elevations, nodata_val, rtol=1e-09, atol=1e-09)
            elevations[nodata_mask] = -32768.0
        
        # Mask obvious nodata values
        elevations[elevations < -30000] = -32768.0
        elevations[np.isnan(elevations)] = -32768.0
        elevations[np.isinf(elevations)] = -32768.0

        bounds = mercantile.bounds(tile)
        
        # Calculate HGT cell key using LOWER-LEFT (southwest) corner coordinates
        hgt_cell_key_lat = math.floor(bounds.south)
        hgt_cell_key_lon = math.floor(bounds.west)
        
        cell_identifier_key = (hgt_cell_key_lat, hgt_cell_key_lon)

        # Calculate precise tile bounds in degrees
        tile_height_deg = bounds.north - bounds.south
        tile_width_deg = bounds.east - bounds.west
        
        # Calculate pixel size in degrees
        pixel_height_deg = tile_height_deg / elevations.shape[0]
        pixel_width_deg = tile_width_deg / elevations.shape[1]
        
        # HGT grid parameters (1 arc-second resolution, 3601x3601 grid)
        hgt_resolution = 1.0 / 3600.0  # 1 arc-second in degrees
        
        # Calculate mapping from tile pixels to HGT grid
        # HGT grid: [0,0] is northwest corner, [3600,3600] is southeast corner
        hgt_north = hgt_cell_key_lat + 1.0  # North edge of HGT cell
        hgt_west = hgt_cell_key_lon        # West edge of HGT cell
        
        results = []
        
        # Process each pixel in the tile
        for row in range(elevations.shape[0]):
            for col in range(elevations.shape[1]):
                # Calculate pixel center coordinates
                pixel_lat = bounds.north - (row + 0.5) * pixel_height_deg
                pixel_lon = bounds.west + (col + 0.5) * pixel_width_deg
                
                # Check if pixel is within the HGT cell bounds
                if (hgt_cell_key_lat <= pixel_lat < hgt_cell_key_lat + 1.0 and
                    hgt_cell_key_lon <= pixel_lon < hgt_cell_key_lon + 1.0):
                    
                    # Calculate HGT grid indices
                    hgt_row = int(round((hgt_north - pixel_lat) / hgt_resolution))
                    hgt_col = int(round((pixel_lon - hgt_west) / hgt_resolution))
                    
                    # Clamp to valid range
                    hgt_row = max(0, min(3600, hgt_row))
                    hgt_col = max(0, min(3600, hgt_col))
                    
                    elevation_value = elevations[row, col]
                    
                    results.append((cell_identifier_key, hgt_row, hgt_col, elevation_value))
        
        return results if results else None

    except Exception as e:
        print(f"Error processing tile {tile} in worker: {e}")
        return None
    finally:
        if conn:
            conn.close()

# --- Main Conversion Logic ---

def convert_mbtiles_to_hgt(mbtiles_path, output_dir, zoom_level=16, encoding='mapbox', interval=0.01, base_val=-10000.0, source_nodata_values=None):
    """
    Converts MBTiles to HGT files using improved coordinate mapping.
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

        # Identify unique HGT cells
        print("Identifying unique HGT cells...")
        unique_hgt_cells = set()
        for zoom_level_db, x_db, y_db in tiles_info:
            xyz_y = (2 ** zoom_level_db) - y_db - 1
            tile = mercantile.Tile(x=x_db, y=xyz_y, z=zoom_level_db)
            bounds = mercantile.bounds(tile)
            
            hgt_cell_key_lat = math.floor(bounds.south)
            hgt_cell_key_lon = math.floor(bounds.west)
                
            unique_hgt_cells.add((hgt_cell_key_lat, hgt_cell_key_lon))
        
        print(f"Found {len(unique_hgt_cells)} unique HGT cells.")

        # Pre-allocate HGT grids with proper NODATA value (-32768)
        main_hgt_cells = {}
        for cell_id in unique_hgt_cells:
            main_hgt_cells[cell_id] = np.full((3601, 3601), -32768, dtype=np.float32)
        
        print(f"Starting parallel processing of {total_tiles} tiles...")
        
        num_workers = min(os.cpu_count() or 4, 8)  # Limit to 8 workers to avoid memory issues
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
                if (i + 1) % 100 == 0 or (i + 1) == len(futures):
                    print(f"Processing {i+1}/{total_tiles} tiles...")

                try:
                    results = future.result()
                    if results:
                        for cell_id, hgt_row, hgt_col, elevation in results:
                            if cell_id in main_hgt_cells:
                                # Use average for overlapping pixels (simple approach)
                                current_val = main_hgt_cells[cell_id][hgt_row, hgt_col]
                                if current_val == -32768:  # First value
                                    main_hgt_cells[cell_id][hgt_row, hgt_col] = elevation
                                else:  # Average with existing value
                                    if elevation != -32768:  # Don't average with nodata
                                        main_hgt_cells[cell_id][hgt_row, hgt_col] = (current_val + elevation) / 2.0
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
            # HGT naming convention
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
                # Convert to int16 and handle nodata properly
                hgt_grid_int16 = np.where(hgt_grid == -32768, -32768, 
                                         np.clip(np.round(hgt_grid), -32767, 32767)).astype(np.int16)
                
                # Convert to big-endian int16 for HGT format
                binary_data = hgt_grid_int16.astype('>i2').tobytes()
                
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
        description="Convert MBTiles (Terrarium v1 or Mapbox TerrainRGB) to HGT files using improved coordinate mapping.",
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
