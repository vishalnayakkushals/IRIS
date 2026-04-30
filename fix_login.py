import psycopg2, hashlib, secrets

def hash_pw(plain):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 120000).hex()
    return "pbkdf2_sha256" + "$" + salt + "$" + digest

conn = psycopg2.connect("postgresql://iris_user:iris_password@127.0.0.1:5432/iris_db")
cur = conn.cursor()
new_hash = hash_pw("ChangeMe123!")
cur.execute("UPDATE users SET password_hash = %s WHERE email = %s", (new_hash, "vishal.nayak@kushals.com"))
print("Rows updated:", cur.rowcount)
conn.commit()

# Verify
cur.execute("SELECT email, is_active FROM users WHERE email = %s", ("vishal.nayak@kushals.com",))
print("User:", cur.fetchone())
conn.close()
print("Done")
