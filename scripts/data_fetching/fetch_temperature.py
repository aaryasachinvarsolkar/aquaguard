import requests
import os

url = "https://www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr/202401/oisst-avhrr-v02r01.20240101.nc"

response = requests.get(url)

os.makedirs("data_raw/ocean", exist_ok=True)

with open("data_raw/ocean/sst.nc","wb") as f:
    f.write(response.content)

print("Temperature data downloaded")