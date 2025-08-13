import mercantile
from PIL import Image
import numpy as np
import os
import io
import argparse
import sqlite3
import concurrent.futures
import math
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rasterio.io import MemoryFile

# --- Decoding Functions ---
def decode_elevation_from_rgb_rio(data: np.ndarray, encoding: str, interval: float = 0.1, base_val: float = -10000.0) -> np.ndarray:
    data = data.astype(np.float64)
    if encoding == "terrarium":
        return (data[..., 0] * 256.0 + data[..., 1] + data[..., 2] / 256.0) - 32768.0
    else: # 'mapbox' encoding
        return base_val + (((data[..., 0] * 256.0 * 256.0) + (data[..., 1] * 256.0) + data[..., 2]) * interval)

def process_tile_data_with_debug(tile_info, mbtiles_path, encoding, interval, base_val, source_nodata_values, tile_src_crs):
    # Debugging prints for a few pixels from the first tile (or a tile you know has positive elevation)
    tile_z, tile_x, tile_y = tile_info
    
    # Convert from MBTiles TMS to XYZ for mercantile
    tile_xyz_y = (2 ** tile_z) - tile_y - 1
    tile = mercantile.Tile(x=tile_x, y=tile_xyz_y, z=tile_z)

    conn = None
    try:
        conn = sqlite3.connect(mbtiles_path)
        cursor = conn.cursor()

        tile_data_query = "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?"
        cursor.execute(tile_data_query, (tile_z, tile_x, tile_y))
        result = cursor.fetchone()

        if result is None:
            # print(f"Warning: No data found for tile {tile_z}/{tile_x}/{tile_y}") # Suppress for cleaner output unless debugging
            return None

        tile_data_bytes = result[0]
        img = Image.open(io.BytesIO(tile_data_bytes)).convert("RGB")
        pixels = np.array(img)
        #print(f"\n--- Debugging for tile {tile_z}/{tile_x}/{tile_y} ---")
        #print(f"Sample RGB values (top-left 3x3):")
        #for r in range(min(3, pixels.shape[0])):
        #    for c in range(min(3, pixels.shape[1])):
        #        rgb = pixels[r, c]
        #        numeric_value = (rgb[0] * 256.0 * 256.0) + (rgb[1] * 256.0) + rgb[2]
        #        scaled_value = numeric_value * interval
        #        decoded_elev = base_val + scaled_value
        #        print(f"  RGB: {rgb}, Numeric: {numeric_value:.0f}, Scaled: {scaled_value:.2f}, Decoded Elev: {decoded_elev:.2f}")
        #print(f"--- End Debugging ---")

        # Decode elevations
        elevations = decode_elevation_from_rgb_rio(pixels, encoding, interval=interval, base_val=base_val)
        
        # Apply nodata handling from source_nodata_values if provided
        if source_nodata_values:
            for nodata_val in source_nodata_values:
                elevations[np.isclose(elevations, nodata_val, rtol=1e-09, atol=1e-09)] = -32768.0
        
        # Ensure NaNs and extreme values become nodata, as done previously.
        elevations[np.isnan(elevations)] = -32768.0
        elevations[(elevations < -30000) | (elevations > 15000)] = -32768.0 # Clamping as per your original logic

        bounds = mercantile.bounds(tile)
        height, width = elevations.shape

        # THIS IS THE MOST CRITICAL PART: Ensuring the transform matches the src_crs
        # If src_crs is EPSG:3857, mercantile bounds are in degrees.
        # rasterio.transform.from_bounds expects bounds in the CRS's units.
        # For EPSG:4326 (degrees), it works directly.
        # For EPSG:3857 (meters), we would need to reproject the bounds first.
        # HOWEVER, since we are reprojecting FROM src_crs TO EPSG:4326,
        # rasterio can handle the conversion as long as the src_crs is correct
        # AND the bounds provided to from_bounds are in the src_crs's units.
        # Mercantile provides lat/lon bounds, which are units for EPSG:4326.
        # So, if src_crs is EPSG:3857, we *should* use a transform for EPSG:3857.
        # But if mercantile.bounds gives us lat/lon, and we *tell* rasterio the src_crs is 3857, it will expect meters.

        # The MOST reliable approach is to treat all source data as if it's referenced in EPSG:4326
        # for the purposes of creating the initial transform, then let rasterio handle the reprojection.
        # This means we'll consistently use EPSG:4326 for the tile's transform generation,
        # and then tell rasterio that the source data is *geographically* defined by these lat/lon bounds,
        # regardless of how it was *generated*.
        # So, we'll use EPSG:4326 for the transform generation, and pass the correct tile_src_crs for interpretation.

        # Create a transform for the tile data assuming lat/lon bounds
        # This is generally safe because rasterio can reproject from any source CRS to any target CRS
        # as long as the source CRS and transform are correctly specified.
        tile_transform = rasterio.transform.from_bounds(
            bounds.west, bounds.south, bounds.east, bounds.north, width=width, height=height
        )

        # The source CRS we are declaring for the data we've extracted.
        # This tells rasterio how to interpret the `tile_transform` and `bounds`.
        # If your MBTiles were *generated* from EPSG:3857, but the bounds are lat/lon,
        # declaring `src_crs` as EPSG:4326 for the reprojection step is often more robust
        # because mercantile.bounds IS in lat/lon.
        # Let's default to EPSG:4326 for the source interpretation if `tile_src_crs` is specified as 3857,
        # because `mercantile.bounds` gives lat/lon.
        # If your MBTiles were generated in a GIS directly in EPSG:3857 and THEN converted to MBTiles,
        # you might need a different approach.
        # However, for typical web tiles, declaring src_crs=EPSG:4326 here is safer.

        actual_src_crs_for_reproject = 'EPSG:4326' # Assume lat/lon for the source data's bounds

        # print(f"    Tile {tile_z}/{tile_x}/{tile_y}: Declaring src_crs='{actual_src_crs_for_reproject}' for reprojection.")

        return {
            'elevations': elevations.astype(np.float32),
            'transform': tile_transform,
            'src_crs': actual_src_crs_for_reproject, # Use 4326 for transform interpretation
            'bounds': bounds
        }

    except Exception as e:
        print(f"Error processing tile {tile_z}/{tile_x}/{tile_y}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def create_hgt_with_proper_merging_flexible(tile_data_list, hgt_bounds, output_path, resampling_method=Resampling.bilinear):
    west, south, east, north = hgt_bounds
    
    hgt_width, hgt_height = 3601, 3601
    hgt_transform = rasterio.transform.from_bounds(west, south, east, north, hgt_width, hgt_height)
    
    hgt_elevation = np.full((hgt_height, hgt_width), np.nan, dtype=np.float32)
    hgt_count = np.zeros((hgt_height, hgt_width), dtype=np.int32)
    
    print(f"  Merging {len(tile_data_list)} tiles into HGT grid using {resampling_method.name}...")
    
    any_valid_data_in_hgt = False # Flag to see if ANY data was written to the HGT grid

    for i, tile_data in enumerate(tile_data_list):
        try:
            temp_elevation = np.full((hgt_height, hgt_width), np.nan, dtype=np.float32)
            
            reproject(
                source=tile_data['elevations'],
                destination=temp_elevation,
                src_transform=tile_data['transform'],
                src_crs=tile_data['src_crs'],
                dst_transform=hgt_transform,
                dst_crs='EPSG:4326',
                resampling=resampling_method,
                src_nodata=np.nan,
                dst_nodata=np.nan
            )
            
            valid_mask = (~np.isnan(temp_elevation)) & (temp_elevation > -30000) & (temp_elevation < 15000)
            
            if np.any(valid_mask):
                any_valid_data_in_hgt = True # Mark that we've written some data to this HGT grid
                
                first_data_mask = np.isnan(hgt_elevation) & valid_mask
                hgt_elevation[first_data_mask] = temp_elevation[first_data_mask]
                hgt_count[first_data_mask] = 1
                
                additional_data_mask = (~np.isnan(hgt_elevation)) & valid_mask
                if np.any(additional_data_mask):
                    current_count = hgt_count[additional_data_mask]
                    current_sum = hgt_elevation[additional_data_mask] * current_count
                    new_sum = current_sum + temp_elevation[additional_data_mask]
                    new_count = current_count + 1
                    hgt_elevation[additional_data_mask] = new_sum / new_count
                    hgt_count[additional_data_mask] = new_count
            # else:
                # print(f"    Tile {i+1}: no valid data according to mask") # Uncomment for detailed debugging
                
        except Exception as e:
            print(f"    Error processing tile {i+1} for {output_path}: {e}")
            continue

    # If after processing all tiles, NO valid data was ever written to hgt_elevation
    # then the final check will catch it.
    if not any_valid_data_in_hgt:
        print(f"  No valid data was written to the HGT grid for {output_path} from any tile.")
        return False
    
    final_elevation = np.where(np.isnan(hgt_elevation), -32768.0, hgt_elevation)
    hgt_int16 = np.clip(np.round(final_elevation), -32767, 32767).astype(np.int16)
    hgt_int16[final_elevation == -32768.0] = -32768

    valid_pixels = np.sum(hgt_int16 != -32768)
    total_pixels = hgt_int16.size
    coverage = (valid_pixels / total_pixels) * 100
    
    if valid_pixels > 0:
        valid_elevations = hgt_int16[hgt_int16 != -32768]
        min_elev = valid_elevations.min()
        max_elev = valid_elevations.max()
        print(f"  Final HGT stats: {coverage:.1f}% coverage, {valid_pixels} pixels, range {min_elev} to {max_elev}")
    else:
        print(f"  Final HGT stats: No valid data") # This case means all pixels ended up as nodata
        return False
    
    try:
        with open(output_path, 'wb') as f:
            f.write(hgt_int16.astype('>i2').tobytes())
        return True
    except Exception as e:
        print(f"  Error saving HGT file '{output_path}': {e}")
        return False

def convert_mbtiles_to_hgt_flexible(mbtiles_path, output_dir, zoom_level=12, encoding='mapbox', interval=0.1, base_val=-10000.0, source_nodata_values=None, tile_src_crs_arg='EPSG:3857', resampling_method=Resampling.bilinear):
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    print(f"Converting {mbtiles_path} at zoom level {zoom_level}")
    print(f"Encoding: {encoding}, Interval: {interval}, Base: {base_val}")
    # We need to explicitly set the CRS that mercantile.bounds will interpret our data in.
    # Since mercantile.bounds always returns lat/lon, and HGT is WGS84, we'll assume the source data,
    # even if generated from 3857, is being referenced by lat/lon bounds.
    # So, for the `src_crs` that rasterio.reproject *interprets* the transform with, EPSG:4326 is usually the safest bet if mercantile bounds are used.
    # The `tile_src_crs_arg` from the command line is more about the *original* source data's projection.
    # We will pass 'EPSG:4326' to the worker as the CRS for interpreting the transform.
    source_crs_for_worker = 'EPSG:4326' 
    print(f"Source MBTiles CRS for interpretation: {source_crs_for_worker}")
    print(f"Resampling method for upscaling: {resampling_method.name}")

    conn = sqlite3.connect(mbtiles_path)
    cursor = conn.cursor()
    
    tile_query = "SELECT zoom_level, tile_column, tile_row FROM tiles WHERE zoom_level = ? ORDER BY tile_column, tile_row"
    cursor.execute(tile_query, (zoom_level,))
    all_tiles = cursor.fetchall()
    conn.close()
    
    if not all_tiles:
        print(f"No tiles found at zoom level {zoom_level}")
        return
        
    print(f"Processing {len(all_tiles)} tiles...")
    
    processed_tiles = []
    num_workers = min(8, os.cpu_count() or 8)
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_tile_data_with_debug, tile_info, mbtiles_path, encoding, interval, base_val, source_nodata_values, source_crs_for_worker): tile_info 
                 for tile_info in all_tiles}
        
        tile_count = 0
        for future in concurrent.futures.as_completed(futures):
            tile_count += 1
            if tile_count % 100 == 0 or tile_count == len(all_tiles):
                print(f"  Processed {tile_count}/{len(all_tiles)} tiles...")
            try:
                result = future.result()
                if result:
                    processed_tiles.append(result)
            except Exception as e:
                print(f"  Error processing tile result: {e}")

    print(f"Successfully processed {len(processed_tiles)} tiles")
    
    if not processed_tiles:
        print("No tiles processed successfully")
        return
        
    all_bounds = [tile['bounds'] for tile in processed_tiles]
    if not all_bounds:
        print("No valid tile bounds found.")
        return
        
    west = min(b.west for b in all_bounds)
    south = min(b.south for b in all_bounds)    
    east = max(b.east for b in all_bounds)
    north = max(b.north for b in all_bounds)
    
    print(f"Coverage bounds: W={west:.6f}, S={south:.6f}, E={east:.6f}, N={north:.6f}")
    
    lat_start = math.floor(south)
    lat_end = math.floor(north)
    lon_start = math.floor(west)
    lon_end = math.floor(east)
    
    hgt_cells_to_generate = []
    for lat in range(lat_start, lat_end + 1):
        for lon in range(lon_start, lon_end + 1):
            hgt_cells_to_generate.append((lat, lon))
    
    print(f"Generating {len(hgt_cells_to_generate)} HGT files...")
    
    for hgt_lat, hgt_lon in hgt_cells_to_generate:
        hgt_bounds = (hgt_lon, hgt_lat, hgt_lon + 1, hgt_lat + 1)
        
        overlapping_tiles = []
        for tile_data in processed_tiles:
            tb = tile_data['bounds']
            if (tb.east > hgt_bounds[0] and tb.west < hgt_bounds[2] and 
                tb.north > hgt_bounds[1] and tb.south < hgt_bounds[3]):
                overlapping_tiles.append(tile_data)
        
        if not overlapping_tiles:
            continue
            
        lat_str = f"N{hgt_lat:02d}" if hgt_lat >= 0 else f"S{abs(hgt_lat):02d}"
        lon_str = f"W{abs(hgt_lon):03d}" if hgt_lon < 0 else f"E{hgt_lon:03d}"
        hgt_filename = f"{lat_str}{lon_str}.hgt"
        hgt_filepath = os.path.join(output_dir, hgt_filename)
        
        print(f"  Creating {hgt_filename} from {len(overlapping_tiles)} tiles...")
        
        success = create_hgt_with_proper_merging_flexible(overlapping_tiles, hgt_bounds, hgt_filepath, resampling_method=resampling_method)
        
        if success:
            print(f"  ✓ Successfully created {hgt_filename}")
        else:
            print(f"  ✗ Failed to create {hgt_filename}")
            
    print("Conversion completed!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fixed MBTiles to HGT converter")
    parser.add_argument("mbtiles_file", help="Path to MBTiles file")
    parser.add_argument("-o", "--output-dir", default="fixed_hgt", help="Output directory")
    parser.add_argument("-z", "--zoom-level", type=int, default=12, help="Zoom level")
    parser.add_argument("-e", "--encoding", choices=['terrarium', 'mapbox'], default='mapbox', help="Encoding")
    parser.add_argument("--interval", type=float, default=0.1, help="Mapbox interval")
    parser.add_argument("--base-val", type=float, default=-10000.0, help="Mapbox base value")
    parser.add_argument("--source-nodata", nargs='+', type=float, default=None, help="List of values to treat as no-data in source tiles.")
    # The --tile-src-crs argument is actually not directly used by reproject because mercantile bounds are lat/lon.
    # We are *interpreting* the source data's bounds in EPSG:4326 for transform generation.
    # If the source MBTiles were generated from 3857 data, the `decode_elevation_from_rgb_rio` might need
    # to be aware of that if it was doing projection internally, but here it's just decoding RGB.
    # For reprojection, assuming source data's spatial reference is aligned with mercantile.bounds (lat/lon) is usually best.
    # So, we'll enforce src_crs='EPSG:4326' for the reprojection step.
    parser.add_argument("--tile-src-crs", default='EPSG:4326', help="CRS of the source MBTiles tiles (e.g., EPSG:4326, EPSG:3857). This is mostly informational for debugging. Reprojection will use EPSG:4326 for source interpretation based on mercantile bounds.")
    
    parser.add_argument("--resampling", default='bilinear', choices=['nearest', 'bilinear', 'cubic', 'average'], help="Resampling method for upscaling.")

    args = parser.parse_args()

    resampling_map = {
        'nearest': Resampling.nearest,
        'bilinear': Resampling.bilinear,
        'cubic': Resampling.cubic,
        'average': Resampling.average
    }
    selected_resampling = resampling_map.get(args.resampling, Resampling.bilinear)

    convert_mbtiles_to_hgt_flexible(
        args.mbtiles_file,
        args.output_dir,
        args.zoom_level,
        args.encoding,
        args.interval,
        args.base_val,
        args.source_nodata,
        # We are explicitly setting the CRS for reprojection to EPSG:4326 because
        # mercantile.bounds provides lat/lon, which aligns with EPSG:4326.
        # The original --tile-src-crs argument is more for understanding the origin of the data.
        'EPSG:4326', 
        selected_resampling
    )
