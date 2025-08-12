import sqlite3
import os
import argparse

def merge_mbtiles(destination_path: str, source_paths: list[str]):
    """Merges multiple MBTiles files into a single destination MBTiles file,
       with a "rightmost wins" strategy for tile conflicts, removes unused tile_data,
       and keeps metadata only from the last source file.

    Args:
        destination_path (str): Path to the destination MBTiles file.
        source_paths (list[str]): List of paths to the source MBTiles files (rightmost overwrites).
    """

    # Create or open the destination MBTiles database
    dest_conn = sqlite3.connect(destination_path)
    dest_cur = dest_conn.cursor()

    # Create tables and view in destination if they don't exist
    dest_cur.execute(
        "CREATE TABLE IF NOT EXISTS tiles_shallow ("
        "TILES_COL_Z integer, "
        "TILES_COL_X integer, "
        "TILES_COL_Y integer, "
        "TILES_COL_DATA_ID text "
        ", primary key(TILES_COL_Z,TILES_COL_X,TILES_COL_Y) "
        ") without rowid;"
    )
    dest_cur.execute(
        "CREATE TABLE IF NOT EXISTS tiles_data ("
        "tile_data_id text primary key, "
        "tile_data blob "
        ");"
    )
    dest_cur.execute(
        "CREATE TABLE IF NOT EXISTS metadata (name text, value text);"
    )
    dest_cur.execute(
        "CREATE VIEW IF NOT EXISTS tiles AS "
        "SELECT "
        "tiles_shallow.TILES_COL_Z AS zoom_level, "
        "tiles_shallow.TILES_COL_X AS tile_column, "
        "tiles_shallow.TILES_COL_Y AS tile_row, "
        "tiles_data.tile_data AS tile_data "
        "FROM tiles_shallow "
        "JOIN tiles_data ON tiles_shallow.TILES_COL_DATA_ID = tiles_data.tile_data_id;"
    )
    dest_conn.commit()

    # Iterate through source files to merge tiles
    for source_path in source_paths:
        print(f"Merging from: {source_path}")
        source_conn = None
        try:
            source_conn = sqlite3.connect(source_path)
            source_cur = source_conn.cursor()

            # Copy Tiles and Data
            source_cur.execute("SELECT TILES_COL_Z, TILES_COL_X, TILES_COL_Y, TILES_COL_DATA_ID FROM tiles_shallow")
            tiles = source_cur.fetchall()

            source_cur.execute("SELECT tile_data_id, tile_data FROM tiles_data")
            tile_data = source_cur.fetchall()

            # Insert or Update tiles_data
            for data_id, data in tile_data:
                try:
                    dest_cur.execute(
                        "INSERT OR REPLACE INTO tiles_data (tile_data_id, tile_data) VALUES (?, ?)",
                        (data_id, data),
                    )
                except sqlite3.IntegrityError as e:
                    print(f"Warning: Error inserting/replacing tile_data_id '{data_id}' from {source_path}: {e}")

            # Insert or Replace tiles_shallow (rightmost wins)
            for z, x, y, data_id in tiles:
                try:
                    dest_cur.execute(
                        "INSERT OR REPLACE INTO tiles_shallow (TILES_COL_Z, TILES_COL_X, TILES_COL_Y, TILES_COL_DATA_ID) VALUES (?, ?, ?, ?)",
                        (z, x, y, data_id),
                    )
                except sqlite3.IntegrityError as e:
                    print(f"Warning: Error inserting/replacing tile (z={z}, x={x}, y={y}) from {source_path}: {e}")

            if source_conn:
                source_conn.close()

        except sqlite3.Error as e:
            print(f"Error processing {source_path}: {e}")
            if source_conn:
                source_conn.close()
            continue

    dest_conn.commit()

    # Clear metadata table
    print("Clearing existing metadata...")
    dest_cur.execute("DELETE FROM metadata")
    dest_conn.commit()
    print("Existing metadata cleared.")

    # Copy metadata from last file
    if source_paths:  # Check if there are any source files
        last_source_path = source_paths[-1]
        print(f"Copying metadata from last file: {last_source_path}")
        try:
            last_source_conn = sqlite3.connect(last_source_path)
            last_source_cur = last_source_conn.cursor()
            last_source_cur.execute("SELECT name, value FROM metadata")
            metadata = last_source_cur.fetchall()

            for name, value in metadata:
                try:
                    dest_cur.execute(
                        "INSERT INTO metadata (name, value) VALUES (?, ?)", (name, value)
                    )
                except sqlite3.IntegrityError as e:
                    print(f"Warning: Error inserting metadata '{name}' from {last_source_path}: {e}")

            last_source_conn.close()
        except sqlite3.Error as e:
            print(f"Error copying metadata from {last_source_path}: {e}")

    dest_conn.commit()

    # Remove unused tile_data
    print("Cleaning up unused tile_data...")
    dest_cur.execute(
        "DELETE FROM tiles_data WHERE tile_data_id NOT IN (SELECT DISTINCT TILES_COL_DATA_ID FROM tiles_shallow)"
    )
    dest_conn.commit()
    print("Unused tile_data removed.")

    # Optional - optimize DB
    dest_cur.execute("VACUUM")
    dest_conn.commit()

    dest_conn.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Merge multiple MBTiles files into one (rightmost wins, metadata from last).")
    parser.add_argument("destination", help="Path to the destination MBTiles file.")
    parser.add_argument("sources", nargs="+", help="Paths to the source MBTiles files (space-separated, rightmost overwrites).")
    args = parser.parse_args()

    destination_file = args.destination
    source_files = args.sources

    # create dummy files for testing if they don't exist
    for file in source_files:
        if not os.path.exists(file):
            conn = sqlite3.connect(file)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS tiles_shallow (TILES_COL_Z integer, TILES_COL_X integer, TILES_COL_Y integer, TILES_COL_DATA_ID text, primary key(TILES_COL_Z,TILES_COL_X,TILES_COL_Y)) without rowid;")
            cursor.execute("CREATE TABLE IF NOT EXISTS tiles_data (tile_data_id text primary key, tile_data blob );")
            cursor.execute("CREATE TABLE IF NOT EXISTS metadata (name text, value text);")
            conn.commit()
            conn.close()


    merge_mbtiles(destination_file, source_files)
    print(f"MBTiles files merged into: {destination_file}")
