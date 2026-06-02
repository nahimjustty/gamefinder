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

CLIENT_ID = "h8buojbvr83im2wr4wyanzfaqeo08j"
CLIENT_SECRET = "ge7n2wpmeox642hbcr9slk0sw4tysw"

token_cache = {"token": None, "expires_at": 0}

def get_access_token():
    if token_cache["token"] and time.time() < token_cache["expires_at"]:
        return token_cache["token"]
    res = requests.post("https://id.twitch.tv/oauth2/token", params={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    })
    data = res.json()
    token_cache["token"] = data["access_token"]
    token_cache["expires_at"] = time.time() + data["expires_in"] - 60
    print("  🔑 Got access token.")
    return token_cache["token"]

def igdb_request(endpoint, query):
    token = get_access_token()
    res = requests.post(
        f"https://api.igdb.com/v4/{endpoint}",
        headers={
            "Client-ID": CLIENT_ID,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        data=query,
        timeout=10
    )
    return res.json()

def clean_title(title):
    title = re.sub(r'[\(\[].*?[\)\]]', '', title)
    title = re.sub(r'v\d+[\d.]+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'build\s*\d+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'free download', '', title, flags=re.IGNORECASE)
    title = re.sub(r'repack', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title).strip().rstrip(' -–:,')
    return title

def search_igdb(title):
    clean = clean_title(title)
    if not clean:
        return None
    query = f'''
        search "{clean}";
        fields name, rating, genres.name, summary, cover.image_id, first_release_date;
        limit 5;
    '''
    results = igdb_request("games", query)
    if not results or isinstance(results, dict):
        return None
    for game in results:
        if game.get("name", "").lower() == clean.lower():
            return game
    return results[0] if results else None

def get_cover_url(image_id):
    return f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg" if image_id else ""

def enrich_batch(limit=100, source=None):
    query = {"igdb_matched": {"$exists": False}}
    if source:
        query["source"] = source

    games = list(collection.find(query).limit(limit))
    if not games:
        print("✅ All games already enriched!")
        return

    print(f"🔍 Enriching {len(games)} games...")
    enriched = 0
    not_found = 0

    for i, game in enumerate(games):
        title = game.get("title", "")
        print(f"  [{i+1}/{len(games)}] {title[:50]}...", end=" ")

        igdb = search_igdb(title)
        if not igdb:
            collection.update_one({"_id": game["_id"]}, {"$set": {"igdb_matched": False}})
            print("→ ❌ Not found")
            not_found += 1
            time.sleep(0.35)
            continue

        update = {"igdb_matched": True, "igdb_id": igdb.get("id")}

        if igdb.get("rating"):
            update["rating"] = round(igdb["rating"] / 10, 1)
        if igdb.get("genres"):
            update["genres"] = [g["name"] for g in igdb["genres"] if g.get("name")]
        if igdb.get("summary") and not game.get("synopsis") or game.get("synopsis") in ["No description available.", "FitGirl Repack.", "SteamRIP Game."]:
            update["synopsis"] = igdb["summary"][:300]
        if igdb.get("cover") and not game.get("cover"):
            update["cover"] = get_cover_url(igdb["cover"]["image_id"])

        collection.update_one({"_id": game["_id"]}, {"$set": update})
        print(f"→ ⭐{update.get('rating', '–')} | {update.get('genres', [])[:2]}")
        enriched += 1
        time.sleep(0.35)

    print(f"\n✅ Done — {enriched} enriched, {not_found} not found")

def count_status():
    total = collection.count_documents({})
    enriched = collection.count_documents({"igdb_matched": True})
    failed = collection.count_documents({"igdb_matched": False})
    pending = total - enriched - failed
    print(f"📊 Total: {total} | Enriched: {enriched} | Not found: {failed} | Pending: {pending}")

def get_access_token():
    if token_cache["token"] and time.time() < token_cache["expires_at"]:
        return token_cache["token"]
    res = requests.post("https://id.twitch.tv/oauth2/token", params={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    })
    data = res.json()
    print(f"  🔍 Token response: {data}")  # add this line
    token_cache["token"] = data["access_token"]
    token_cache["expires_at"] = time.time() + data["expires_in"] - 60
    print("  🔑 Got access token.")
    return token_cache["token"]

if __name__ == "__main__":
    count_status()
    enrich_batch(limit=100)
    count_status()