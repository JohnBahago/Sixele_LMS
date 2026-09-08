import asyncio
from datetime import datetime, timezone
from app.database.mongodb import db
from app.core.security import hash_password

async def main():
    email = input("Super Admin email: ").strip().lower()
    password = input("Super Admin password (min 8 chars): ")
    name = input("Super Admin name: ").strip() or "Super Admin"
    if len(password) < 8: raise SystemExit("Password must be at least 8 characters")
    if await db.users.find_one({"email": email}): raise SystemExit("User already exists")
    now = datetime.now(timezone.utc)
    await db.users.insert_one({"full_name": name, "email": email, "password_hash": hash_password(password), "is_active": True, "is_super_admin": True, "role_ids": [], "created_at": now, "updated_at": now})
    print("Super Admin created.")

if __name__ == "__main__": asyncio.run(main())
