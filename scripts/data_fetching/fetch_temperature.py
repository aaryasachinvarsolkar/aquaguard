import requests
import os

print("Downloading Sea Surface Temperature data...")

# create folder
os.makedirs("../../data_raw/temperature", exist_ok=True)

# Working ERDDAP dataset query
url = (
    "https://coastwatch.pfeg.noaa.gov/erddap/griddap/"
    "erdHadISST.csv?"
    "sst[(2020-01-01T00:00:00Z)][(-10):1:(10)][(60):1:(80)]"
)

try:
    response = requests.get(url)

    if response.status_code == 200:

        file_path = "../../data_raw/temperature/temperature_data.csv"

        with open(file_path, "wb") as f:
            f.write(response.content)

        print("Temperature dataset downloaded successfully")
        print("Saved at:", file_path)

    else:
        print("Download failed:", response.status_code)
        print(response.text)

except Exception as e:
    print("Error:", e)