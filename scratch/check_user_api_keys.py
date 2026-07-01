import os
import requests
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), "..", "backend", ".env")
load_dotenv(dotenv_path=env_path)

supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

headers = {
    "apikey": supabase_service_role_key,
    "Authorization": f"Bearer {supabase_service_role_key}",
    "Content-Type": "application/json",
}

try:
    response = requests.get(
        f"{supabase_url}/rest/v1/user_api_keys",
        headers=headers,
        timeout=10,
    )
    if response.status_code == 200:
        data = response.json()
        print(f"Total API Keys in DB: {len(data)}")
        for row in data:
            print(
                f"User ID: {row.get('user_id')} | Exchange: {row.get('exchange')} | Env: {row.get('broker_env')}\n"
                f"  Account No: {row.get('kis_account_no')} | Code: {row.get('kis_account_code')}\n"
                f"  Toss Account No: {row.get('toss_account_no')} | Toss Seq: {row.get('toss_account_seq')}\n"
                f"  Created: {row.get('created_at')}\n"
                + "-" * 90
            )
    else:
        print("API Error:", response.status_code, response.text)
except Exception as e:
    print("Error querying database:", e)
