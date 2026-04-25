import requests
import os

url = "https://oceandata.sci.gsfc.nasa.gov/cgi/getfile/AQUA_MODIS.20240101.L3m.DAY.CHL.chlor_a.4km.nc"

response = requests.get(url)

os.makedirs("data_raw/satellite", exist_ok=True)

with open("data_raw/satellite/chlorophyll.nc","wb") as f:
    f.write(response.content)

print("Chlorophyll data downloaded")