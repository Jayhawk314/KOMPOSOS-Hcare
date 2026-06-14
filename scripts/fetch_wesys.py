import os
import requests
import zipfile

def fetch_wesys_model():
    """
    Downloads the official NREL WESyS Model from GitHub.
    Note: The model itself (stmx files) requires Stella Architect to run.
    This script retrieves the data and documentation.
    """
    url = "https://github.com/NREL/WESyS-Model/archive/refs/heads/master.zip"
    target_dir = "data/external"
    zip_path = os.path.join(target_dir, "wesys_model.zip")

    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    print(f"Fetching WESyS Model from {url}...")
    response = requests.get(url)
    
    if response.status_code == 200:
        with open(zip_path, 'wb') as f:
            f.write(response.content)
        print(f"Downloaded to {zip_path}")
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(target_dir)
        print(f"Extracted to {target_dir}")
        os.remove(zip_path)
    else:
        print(f"Failed to fetch model. Status code: {response.status_code}")

if __name__ == "__main__":
    fetch_wesys_model()
