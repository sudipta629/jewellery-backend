import os
import psycopg
import sys

DB_URL = "postgresql://jewellery_user:WIzaIbE7LyLouWUUtitIikkXKS8ZOCli@dpg-daro4rnavr4c73fgbnlg-a.ohio-postgres.render.com/jewellery_db_nnob"

try:
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET role = 'super_admin' WHERE email = 'admin@example.com'")
            conn.commit()
            print("Successfully updated admin@example.com to super_admin.")
except Exception as e:
    print("DB Error:", e)
