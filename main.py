import os
import math
import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
import uvicorn

app = FastAPI()

# Enable CORS for cross-origin frontend requests (Vercel -> Render)
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Connect to MongoDB Atlas if MONGO_URI env variable exists; fall back to localhost
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
db = MongoClient(MONGO_URI)["gamefinder2"]

def parse_size_to_gb(size_str):
    if not size_str or size_str in ("N/A", "JUNK", ""):
        return None
    match = re.search(r'([\d]+(?:[.,]\d{1,3})?)\s*(MB|GB)', size_str, re.IGNORECASE)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", "."))
        unit = match.group(2).upper()
        return value / 1024 if unit == "MB" else value
    except ValueError:
        return None

@app.get("/genres")
async def get_genres():
    genres = db.games.distinct("genres")
    skip = {
        "games", "game", "", None,
        "3d", "2d", "third-person", "first-person", "top-down",
        "isometric", "side-view", "top", "cars", "real-time",
        "pausable real-time", "rts", "jump and run"
    }
    return sorted([g for g in genres if g and g.lower() not in skip])

@app.get("/mirrors")
async def get_mirrors():
    """Return all unique mirror names for the dropdown."""
    mirrors = db.games.distinct("mirrors")
    return sorted([m for m in mirrors if m])

@app.get("/games/filter")
async def filter_games(
    page: int = 1,
    title: str = None,
    genre: str = None,
    max_size: float = None,
    min_size: float = None,
    min_rating: float = None,
    mirror: str = None,
    sort: str = "newest"
):
    query = {"is_junk": {"$ne": True}}
    if title:
        query["title"] = {"$regex": title, "$options": "i"}
    if genre:
        query["genres"] = genre
    if min_rating:
        query["rating"] = {"$gte": min_rating}
    if mirror:
        query["mirrors"] = mirror  # filter by mirror name

    limit = 12

    if sort == "newest":
        total = db.games.count_documents(query)
        skip = (page - 1) * limit
        cursor = db.games.find(query).sort("_id", -1).skip(skip).limit(limit)
        games = []
        for g in cursor:
            g["_id"] = str(g["_id"])
            g.setdefault("size_raw", "N/A")
            g.setdefault("synopsis", "No description.")
            g.setdefault("cover", "")
            g.setdefault("mirrors", [])
            g["size_gb"] = parse_size_to_gb(g.get("size_raw"))
            games.append(g)
        return {"games": games, "total": total, "pages": math.ceil(total / limit) or 1}

    all_docs = list(db.games.find(query, {
        "_id": 1, "title": 1, "link": 1, "source": 1,
        "cover": 1, "rating": 1, "genres": 1,
        "size_raw": 1, "synopsis": 1, "mirrors": 1
    }))

    for g in all_docs:
        g["size_gb"] = parse_size_to_gb(g.get("size_raw", ""))

    if min_size is not None:
        all_docs = [g for g in all_docs if g["size_gb"] and g["size_gb"] >= min_size]
    if max_size is not None:
        all_docs = [g for g in all_docs if g["size_gb"] and g["size_gb"] <= max_size]

    if sort == "size_asc":
        all_docs.sort(key=lambda g: g["size_gb"] or 9999)
    elif sort == "size_desc":
        all_docs.sort(key=lambda g: g["size_gb"] or -1, reverse=True)

    total = len(all_docs)
    pages = math.ceil(total / limit) or 1
    start = (page - 1) * limit
    games = all_docs[start:start + limit]

    for g in games:
        g["_id"] = str(g["_id"])
        g.setdefault("size_raw", "N/A")
        g.setdefault("synopsis", "No description.")
        g.setdefault("cover", "")
        g.setdefault("mirrors", [])

    return {"games": games, "total": total, "pages": pages}

if __name__ == "__main__":
    # Render overrides port with environment variable, but defaults to 8000 locally
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)