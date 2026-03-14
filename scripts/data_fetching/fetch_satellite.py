import requests
import os

os.makedirs("../../data_raw/satellite_images", exist_ok=True)

url = "https://eoimages.gsfc.nasa.gov/images/imagerecords/79000/79803/deepwater_horizon_oli_2010125_lrg.jpg"

file_path = "../../data_raw/satellite_images/oil_spill_sample.jpg"

print("Downloading satellite image...")

response = requests.get(url, stream=True)

if response.status_code == 200:
    with open(file_path, "wb") as f:
        for chunk in response.iter_content(1024):
            f.write(chunk)

    print("Image downloaded successfully")

else:
    print("Download failed:", response.status_code)