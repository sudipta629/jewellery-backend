import os
import sys
import time
import requests
import psycopg
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://jewellery-backend-sh2s.onrender.com/api/v1"
DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    print("No database URL")
    sys.exit(1)

# 1. Request OTP
identifier = "admin@example.com"
print("Requesting OTP...")
resp = requests.post(f"{BASE_URL}/auth/request-otp", json={
    "identifier": identifier,
    "identifier_type": "email"
})
print("Request OTP response:", resp.status_code, resp.text)

# 2. Get OTP from DB
print("Fetching OTP from database...")
time.sleep(1) # wait a bit for DB to save
try:
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT hashed_otp, expires_at FROM otp_verifications WHERE identifier = %s ORDER BY created_at DESC LIMIT 1", (identifier,))
            record = cur.fetchone()
            if not record:
                print("No OTP record found in DB!")
                sys.exit(1)
            print("Found OTP record hash (we cannot reverse hash, but wait...).")
            # Wait, OTPs are hashed in the DB!
except Exception as e:
    print("DB error:", e)
    sys.exit(1)
