"""Create (or reset the password of) a dashboard user.  Usage: python create_user.py <username> [role]"""
import getpass
import sys

from werkzeug.security import generate_password_hash

from db import get_db, init_db

if len(sys.argv) < 2:
    sys.exit("Usage: python create_user.py <username> [role]")
username = sys.argv[1].strip()
role = sys.argv[2] if len(sys.argv) > 2 else "farmer"
pw = getpass.getpass("Password (min 8 characters): ")
if len(pw) < 8:
    sys.exit("Password too short.")
if pw != getpass.getpass("Repeat password: "):
    sys.exit("Passwords do not match.")
init_db()
conn = get_db()
conn.execute(
    "INSERT INTO Users (username, password_hash, role) VALUES (?,?,?) "
    "ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, role = excluded.role",
    (username, generate_password_hash(pw), role))
conn.commit()
conn.close()
print(f"User '{username}' saved (password stored as a salted hash).")
