"""
Fetch Sentinel-1 product list from Copernicus Dataspace.
Credentials are loaded from environment variables — never hardcode them.
"""
import os
import requests
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


def get_copernicus_token() -> str:
    username = os.getenv("COPERNICUS_USERNAME")
    password = os.getenv("COPERNICUS_PASSWORD")

    if not username or not password:
        raise EnvironmentError("COPERNICUS_USERNAME and COPERNICUS_PASSWORD must be set in .env")

    url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    data = {
        "client_id": "cdse-public",
        "grant_type": "password",
        "username": username,
        "password": password
    }

    resp = requests.post(url, data=data, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_sentinel1_products(token: str) -> list:
    headers = {"Authorization": f"Bearer {token}"}
    catalog_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
    params = {"$filter": "Collection/Name eq 'SENTINEL-1'", "$top": 10}

    resp = requests.get(catalog_url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("value", [])


if __name__ == "__main__":
    token = get_copernicus_token()
    products = fetch_sentinel1_products(token)
    logger.info(f"Products found: {len(products)}")
    for p in products:
        logger.info(p.get("Name"))
