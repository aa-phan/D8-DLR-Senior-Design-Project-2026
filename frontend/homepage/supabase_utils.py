import requests
from django.conf import settings

SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_KEY

headers = {
    "apikey": SUPABASE_KEY,
    "Content-Type": "application/json",
    "Authorization": f"Bearer {SUPABASE_KEY}"
}

def fetch_from_supabase(table_name, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"
    response = requests.get(
        url, 
        headers=headers,
        params=params,
        timeout=15
    )
    response.raise_for_status()
    return response.json()