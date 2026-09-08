from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

client = AsyncIOMotorClient(settings.mongo_url)
db = client[settings.database_name]

def get_db():
    return db

async def close_mongodb():
    client.close()
