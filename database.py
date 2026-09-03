"""
MongoDB-backed persistence for the Diskwala bot (using motor, the async
MongoDB driver, so calls don't block pyrogram's event loop).

Collections:
  users        - _id: user_id (int)
                 first_seen, is_banned, premium_lifetime, premium_until
  daily_counts - _id: "{user_id}:{YYYY-MM-DD}"
                 user_id, day, count
  downloads    - one doc per completed download: user_id, ts
  file_cache   - _id: "{link}::{quality}"
                 link, quality, file_id, name, size, quality_label, cached_at
"""

from datetime import datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_URI, MONGO_DB_NAME

_client = AsyncIOMotorClient(MONGO_URI)
_db = _client[MONGO_DB_NAME]

users_col = _db["users"]
daily_counts_col = _db["daily_counts"]
downloads_col = _db["downloads"]
file_cache_col = _db["file_cache"]


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------
# Users / registration
# ---------------------------------------------------------------------

async def register_user_if_new(user_id: int) -> bool:
    result = await users_col.update_one(
        {"_id": user_id},
        {"$setOnInsert": {
            "first_seen": datetime.utcnow(),
            "is_banned": False,
            "premium_lifetime": False,
            "premium_until": None,
        }},
        upsert=True,
    )
    return result.upserted_id is not None


# ---------------------------------------------------------------------
# Bans
# ---------------------------------------------------------------------

async def set_banned(user_id: int, banned: bool):
    await users_col.update_one(
        {"_id": user_id},
        {"$set": {"is_banned": banned},
         "$setOnInsert": {"first_seen": datetime.utcnow(), "premium_lifetime": False, "premium_until": None}},
        upsert=True,
    )


async def is_banned(user_id: int) -> bool:
    doc = await users_col.find_one({"_id": user_id}, {"is_banned": 1})
    return bool(doc and doc.get("is_banned"))


# ---------------------------------------------------------------------
# Premium
# ---------------------------------------------------------------------

async def set_premium(user_id: int, days):
    """days=None means lifetime."""
    if days is None:
        update = {"premium_lifetime": True, "premium_until": None}
    else:
        update = {"premium_lifetime": False, "premium_until": datetime.utcnow() + timedelta(days=days)}

    await users_col.update_one(
        {"_id": user_id},
        {"$set": update,
         "$setOnInsert": {"first_seen": datetime.utcnow(), "is_banned": False}},
        upsert=True,
    )


async def remove_premium(user_id: int):
    await users_col.update_one(
        {"_id": user_id},
        {"$set": {"premium_lifetime": False, "premium_until": None}},
    )


async def get_premium_status(user_id: int) -> dict:
    doc = await users_col.find_one({"_id": user_id}, {"premium_lifetime": 1, "premium_until": 1})

    if not doc:
        return {"is_premium": False, "lifetime": False, "expires_at": None}

    if doc.get("premium_lifetime"):
        return {"is_premium": True, "lifetime": True, "expires_at": None}

    until = doc.get("premium_until")
    if until and until > datetime.utcnow():
        return {"is_premium": True, "lifetime": False, "expires_at": until}

    return {"is_premium": False, "lifetime": False, "expires_at": None}


# ---------------------------------------------------------------------
# Daily free-download limit
# ---------------------------------------------------------------------

async def get_daily_count(user_id: int) -> int:
    doc = await daily_counts_col.find_one({"_id": f"{user_id}:{_today()}"}, {"count": 1})
    return doc["count"] if doc else 0


async def bump_daily_count(user_id: int):
    day = _today()
    await daily_counts_col.update_one(
        {"_id": f"{user_id}:{day}"},
        {"$inc": {"count": 1}, "$setOnInsert": {"user_id": user_id, "day": day}},
        upsert=True,
    )


# ---------------------------------------------------------------------
# Download stats
# ---------------------------------------------------------------------

async def bump_total_downloads(user_id: int):
    await downloads_col.insert_one({"user_id": user_id, "ts": datetime.utcnow()})


async def get_stats_summary() -> dict:
    total_users = await users_col.count_documents({})
    banned_count = await users_col.count_documents({"is_banned": True})
    now = datetime.utcnow()
    premium_count = await users_col.count_documents({
        "$or": [
            {"premium_lifetime": True},
            {"premium_until": {"$ne": None, "$gt": now}},
        ]
    })
    total_downloads = await downloads_col.count_documents({})
    total_files_cached = await file_cache_col.count_documents({})

    return {
        "total_users": total_users,
        "premium_count": premium_count,
        "banned_count": banned_count,
        "total_downloads": total_downloads,
        "total_files_cached": total_files_cached,
    }


async def all_chat_ids() -> list:
    cursor = users_col.find({}, {"_id": 1})
    return [doc["_id"] async for doc in cursor]


# ---------------------------------------------------------------------
# File cache (instant resend via cached file_id)
# ---------------------------------------------------------------------

def _cache_key(link: str, quality: str) -> str:
    return f"{link}::{quality}"


async def get_cached_file(link: str, quality: str):
    doc = await file_cache_col.find_one({"_id": _cache_key(link, quality)})
    if not doc:
        return None
    return {
        "file_id": doc["file_id"],
        "name": doc["name"],
        "size": doc["size"],
        "quality_label": doc["quality_label"],
    }


async def set_cached_file(link, quality, file_id, name, size, quality_label):
    await file_cache_col.update_one(
        {"_id": _cache_key(link, quality)},
        {"$set": {
            "link": link,
            "quality": quality,
            "file_id": file_id,
            "name": name,
            "size": size,
            "quality_label": quality_label,
            "cached_at": datetime.utcnow(),
        }},
        upsert=True,
    )


async def delete_cached_file(link: str, quality: str):
    await file_cache_col.delete_one({"_id": _cache_key(link, quality)})
