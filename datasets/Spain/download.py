#pip3 install selenium
#wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
#sudo apt install ./google-chrome-stable_current_amd64.deb
#rm google-chrome-stable_current_amd64.deb
#python3 download.py

import os
import time
import subprocess
import uuid
import shutil
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.common.by import By
from urllib.parse import urlparse

def kill_chrome_processes():
    """Kill any existing Chrome processes"""
    try:
        subprocess.run(["pkill", "-f", "chrome"], check=False)
        time.sleep(2)
    except Exception:
        pass

def create_chrome_driver(download_dir, worker_id):
    """Create a Chrome driver instance for a worker with a unique user data directory"""
    user_data_dir = f"/tmp/chrome_worker_{worker_id}_{uuid.uuid4()}"
    os.makedirs(user_data_dir, exist_ok=True)
    
    options = ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    })
    
    return Chrome(options=options), user_data_dir

def download_file(url, base_download_dir, worker_id):
    """
    Downloads and verifies a specific file based on the filename on the webpage,
    but skips the download if the file already exists.
    """
    driver = None
    user_data_dir = None
    temp_download_dir = None
    final_path = None
    
    try:
        print(f"[Worker {worker_id}] Processing: {url}")
        
        # Create driver just to get the filename first
        driver, user_data_dir = create_chrome_driver(None, worker_id) # Using None for temp_download_dir initially
        
        # Get the page and retrieve the filename from the source
        driver.get(url)
        time.sleep(5)
        
        try:
            # This XPath is correct for the filename, as it has a span
            filename_element = driver.find_element(By.XPATH, "//p[contains(strong, 'Fichero:')]/span")
            expected_filename = filename_element.text.strip()
            print(f"[Worker {worker_id}] Expected file: {expected_filename}")
        except Exception:
            print(f"[Worker {worker_id}] Could not find filename on page. Aborting.")
            return f"FAILED: Filename not found on page for {url}", None

        try:
            # This new XPath targets the <p> element itself
            year_element = driver.find_element(By.XPATH, "//p[contains(strong, 'Fecha:')]")
            
            # Get all text from the <p> tag and remove the "Fecha:" part and any leading/trailing whitespace
            full_text = year_element.text.strip()
            expected_year = full_text.replace('Fecha:', '').strip()
            
            print(f"[Worker {worker_id}] Expected year: {expected_year}")
        except Exception:
            print(f"[Worker {worker_id}] Could not find year on page. Aborting.")
            return f"FAILED: Year not found on page for {url}", None

        # --- Check if the file already exists in the final directory ---
        year_path = os.path.join(base_download_dir, expected_year)
        os.makedirs(year_path, exist_ok=True)

        # Check if a file with the same name (case-insensitively) exists
        # in the target directory
        for existing_file in os.listdir(year_path):
            if existing_file.lower() == expected_filename.lower():
                # A case-insensitive match was found
                final_path = os.path.join(year_path, existing_file)
                print(f"[Worker {worker_id}] File '{existing_file}' already exists. Skipping download.")
                return f"SKIPPED: {existing_file}", final_path

        # If no match was found, proceed with the download
        final_path = os.path.join(year_path, expected_filename)

        # If the file doesn't exist, proceed with the download
        print(f"[Worker {worker_id}] File not found locally. Starting download...")
        
        # Quit the initial driver to create a new one with the correct download path
        driver.quit()
        
        # Create a unique temporary directory for this download
        temp_download_dir = os.path.join(base_download_dir, f"temp_{worker_id}_{uuid.uuid4().hex[:8]}")
        os.makedirs(temp_download_dir, exist_ok=True)
        
        # Re-create driver with the correct temporary download directory
        driver, user_data_dir = create_chrome_driver(temp_download_dir, worker_id)
        driver.get(url)
        time.sleep(5)

        # Click the download button
        download_icon = driver.find_element(By.CSS_SELECTOR, "i.fa-download")
        parent = download_icon.find_element(By.XPATH, "..")
        parent.click()
        print(f"[Worker {worker_id}] Download button clicked for {url}")
        
        # Wait for the specific expected file to appear in the temp directory
        max_wait_time = 60
        start_time = time.time()
        
        download_path = None
        while time.time() - start_time < max_wait_time:
            # Check for the downloaded file in the temporary directory
            downloaded_files = os.listdir(temp_download_dir)
            for file in downloaded_files:
                # Make the check case-insensitive for the filename
                if file.lower() == expected_filename.lower() and not file.endswith('.crdownload'):
                    download_path = os.path.join(temp_download_dir, file)
                    break
            
            if download_path:
                # Wait for the file to finish writing
                old_size = -1
                while True:
                    new_size = os.path.getsize(download_path)
                    if new_size == old_size and new_size > 0:
                        print(f"[Worker {worker_id}] Download of '{os.path.basename(download_path)}' complete.")
                        break
                    old_size = new_size
                    time.sleep(1)
                break
            time.sleep(1)
        
        if download_path:
            # Move the verified file to the final destination
            shutil.move(download_path, final_path)
            print(f"[Worker {worker_id}] Moved '{os.path.basename(download_path)}' to final directory.")
            return f"SUCCESS: {os.path.basename(download_path)}", final_path
        else:
            print(f"[Worker {worker_id}] Expected file '{expected_filename}' not detected within time limit.")
            return f"FAILED: File '{expected_filename}' not found for {url}", None
            
    except Exception as e:
        print(f"[Worker {worker_id}] Error processing {url}: {e}")
        return f"ERROR: {url} - {str(e)}", None
        
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        
        if user_data_dir and os.path.exists(user_data_dir):
            try:
                shutil.rmtree(user_data_dir)
            except Exception:
                pass
        
        if temp_download_dir and os.path.exists(temp_download_dir):
            try:
                shutil.rmtree(temp_download_dir)
            except Exception:
                pass

def get_sort_key(file_path):
    """
    Extracts sorting keys from the folder name:
    1. The last year.
    2. The number of years (negative for descending order).
    3. The full folder name to group like folders together.
    """
    # Get the folder name
    folder_name = os.path.basename(os.path.dirname(file_path))

    # Use a regex to find all four-digit numbers (years)
    years = re.findall(r'\b\d{4}\b', folder_name)

    # If years are found, create a tuple for sorting:
    # (last_year, number_of_years, folder_name)
    if years:
        last_year = int(years[-1])
        num_years = len(years)
        return (last_year, -num_years, folder_name)
    else:
        # For non-year folders, use a tuple that places them at the end
        return (9999, 9999, folder_name)


def main():
    kill_chrome_processes()
    
    current_dir = os.getcwd()
    base_download_dir = os.path.join(current_dir, "input")
    os.makedirs(base_download_dir, exist_ok=True)
    
    with open("file_list_pages.txt", "r") as f:
        urls = [line.strip() for line in f if line.strip()]
    
    print(f"Starting parallel downloads for {len(urls)} URLs with max 32 workers...")
    
    results = []
    downloaded_files = [] # New list to store paths of downloaded files
    
    with ThreadPoolExecutor(max_workers=32) as executor:
        future_to_url = {
            executor.submit(download_file, url, base_download_dir, i): url for i, url in enumerate(urls)
        }
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result, file_path = future.result()
                results.append(result)
                if result.startswith("SUCCESS") or result.startswith("SKIPPED"):
                    downloaded_files.append(file_path) # Append the path to the new list
            except Exception as exc:
                error_msg = f"ERROR: {url} generated an exception: {exc}"
                results.append(error_msg)
                print(error_msg)
    
    kill_chrome_processes()
    
    print(f"\n=== DOWNLOAD SUMMARY ===")
    print(f"Total URLs processed: {len(urls)}")
    successful = len([r for r in results if r.startswith("SUCCESS")])
    failed = len([r for r in results if r.startswith("FAILED")])
    errors = len([r for r in results if r.startswith("ERROR")])
    
    print(f"Successful downloads: {successful}")
    print(f"Failed downloads: {failed}")
    print(f"Errors: {errors}")

    if failed > 0 or errors > 0:
        print(f"\n=== FAILED/ERROR DETAILS ===")
        for result in results:
            if result.startswith("FAILED") or result.startswith("ERROR"):
                print(result)

    # --- New section for generating and writing the file list ---
    if downloaded_files:
        print("\n=== GENERATING FILE LIST ===")
        # Sort the list using the custom key function
        downloaded_files.sort(key=get_sort_key)
        
        output_filename = "downloaded_files.txt"
        with open(output_filename, "w") as f:
            for path in downloaded_files:
                f.write(f"{path}\n")
        
        print(f"✅ List of downloaded files generated in '{output_filename}'.")
    else:
        print("\nNo files were downloaded or skipped to generate a list.")


if __name__ == "__main__":
    main()
