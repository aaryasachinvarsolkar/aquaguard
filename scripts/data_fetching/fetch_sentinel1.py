import requests

# 🔐 Replace with YOUR credentials
USERNAME = "aaryavarsolkar@gmail.com"
PASSWORD = "Aarya@111825"

# Step 1: Get Token
url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

data = {
    "client_id": "cdse-public",
    "grant_type": "password",
    "username": USERNAME,
    "password": PASSWORD,
    "scope": "openid"
}

response = requests.post(url, data=data)

if response.status_code != 200:
    print("❌ Login Failed:", response.text)
    exit()

token = response.json()["access_token"]
print("✅ Token generated")

# Step 2: Fetch Sentinel-1 Products
headers = {
    "Authorization": f"Bearer {token}"
}

catalog_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

params = {
    "$filter": "Collection/Name eq 'SENTINEL-1'"
}

response = requests.get(catalog_url, headers=headers, params=params)

data = response.json()

products = data["value"]

print("📡 Products found:", len(products))

# Print first product name
if len(products) > 0:
    print("Sample product:", products[0]["Name"])