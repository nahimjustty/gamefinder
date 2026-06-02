
import requests
from pymongo import MongoClient
import time
import re
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

client = MongoClient("mongodb://localhost:27017/")
db = client["gamefinder2"]
collection = db["games"]

API_KEY = "e0ecaa3db5234810baaf1d8261d2b759"
BASE = "https://api.rawg.io/api"

def clean_title(title):
    title = re.sub(r'[\(\[].*?[\)\]]', '', title)
    title = re.sub(r'v\d+[\d.]+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'build\s*\d+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'free download', '', title, flags=re.IGNORECASE)
    title = re.sub(r'repack', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title).strip().rstrip(' -–:,')
    return title

def search_rawg(title):
    clean = clean_title(title)
    if not clean:
        return None
    try:
        res = requests.get(f"{BASE}/games", params={
            "key": API_KEY,
            "search": clean,
            "page_size": 5,
            "search_precise": True
        }, timeout=10)
        data = res.json()
        results = data.get("results", [])
        if not results:
            return None
        # Try exact match first
        for g in results:
            if g.get("name", "").lower() == clean.lower():
                return g
        return results[0]
    except Exception as e:
        print(f"    ⚠️  RAWG error: {e}")
        return None

def enrich_batch(limit=100, source=None):
    query = {"rawg_matched": {"$exists": False}}
    if source:
        query["source"] = source

    games = list(collection.find(query).limit(limit))
    if not games:
        print("✅ All games enriched!")
        return

    print(f"🔍 Enriching {len(games)} games with RAWG...")
    enriched = 0
    not_found = 0

    for i, game in enumerate(games):
        title = game.get("title", "")
        print(f"  [{i+1}/{len(games)}] {title[:50]}...", end=" ", flush=True)

        result = search_rawg(title)

        if not result:
            collection.update_one({"_id": game["_id"]}, {"$set": {"rawg_matched": False}})
            print("→ ❌ Not found")
            not_found += 1
            time.sleep(0.3)
            continue

        update = {"rawg_matched": True}

        # Rating (RAWG gives 0-5, convert to 0-10)
        if result.get("rating"):
            update["rating"] = round(result["rating"] * 2, 1)

        # Genres
        if result.get("genres"):
            update["genres"] = [g["name"] for g in result["genres"]]

        # Cover (only if missing)
        if result.get("background_image") and not game.get("cover"):
            update["cover"] = result["background_image"]

        # Synopsis (only if missing)
        if not game.get("synopsis") or game.get("synopsis") in ["No description available.", "FitGirl Repack.", "SteamRIP Game."]:
            if result.get("description_raw"):
                update["synopsis"] = result["description_raw"][:300]

        collection.update_one({"_id": game["_id"]}, {"$set": update})
        print(f"→ ⭐{update.get('rating', '–')} | {update.get('genres', [])[:2]}")
        enriched += 1
        time.sleep(0.3)  # RAWG allows ~3 req/sec free tier

    print(f"\n✅ Done — {enriched} enriched, {not_found} not found")

def count_status():
    total = collection.count_documents({})
    enriched = collection.count_documents({"rawg_matched": True})
    failed = collection.count_documents({"rawg_matched": False})
    pending = total - enriched - failed
    print(f"📊 Total: {total} | Enriched: {enriched} | Not found: {failed} | Pending: {pending}")

if __name__ == "__main__":
    count_status()
    enrich_batch(limit=2000)
    count_status()