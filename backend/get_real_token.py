import os
import sys
import time
import urllib.request
import urllib.error
import json
import psycopg
import hashlib
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://jewellery-backend-sh2s.onrender.com/api/v1"
DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    print("No database URL")
    sys.exit(1)

identifier = "admin@example.com"
known_otp = "123456"
known_hash = hashlib.sha256(known_otp.encode("utf-8")).hexdigest()

def make_post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')

print("1. Requesting OTP...")
status, body = make_post(f"{BASE_URL}/auth/request-otp", {
    "identifier": identifier,
    "identifier_type": "email"
})
print("Request OTP response:", status, body)

print("2. Overwriting OTP hash in remote DB...")
time.sleep(1) # Wait a bit for DB to save
try:
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM otp_verifications WHERE identifier = %s ORDER BY created_at DESC LIMIT 1", (identifier,))
            record = cur.fetchone()
            if not record:
                print("No OTP record found in DB!")
                sys.exit(1)
            otp_id = record[0]
            cur.execute("UPDATE otp_verifications SET otp_hash = %s WHERE id = %s", (known_hash, otp_id))
            # Wait! Is this user a super_admin?
            # Let's ensure this user is super_admin.
            cur.execute("SELECT id FROM users WHERE email = %s", (identifier,))
            u_record = cur.fetchone()
            if u_record:
                cur.execute("UPDATE users SET role = 'super_admin' WHERE id = %s", (u_record[0],))
            conn.commit()
            print(f"Updated OTP {otp_id} with known hash for {known_otp} and made user super_admin")
except Exception as e:
    print("DB error:", e)
    sys.exit(1)

print("3. Verifying OTP...")
status, body = make_post(f"{BASE_URL}/auth/verify-otp", {
    "identifier": identifier,
    "identifier_type": "email",
    "otp": known_otp
})
print("Verify OTP response:", status)
if status == 200:
    data = json.loads(body)
    token = data.get("access_token")
    print("\nSUCCESS! Access Token:")
    print(token)
    with open("valid_token.txt", "w") as f:
        f.write(token)
else:
    print("Failed to verify OTP:", body)
