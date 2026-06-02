import os
import re
import time
from bs4 import BeautifulSoup
from pymongo import MongoClient
import requests

# Fallback to local if MONGO_URI isn't set on your machine
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["gamefinder2"]
collection = db["games"]

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

page = 1

while True:
    url = "https://fitgirl-repacks.site" if page == 1 else f"https://fitgirl-repacks.site/page/{page}/"
    print(f"Scraping page {page}...")

    try:
        response = requests.get(url, headers=headers, timeout=10)
    except Exception as e:
        print(f"Connection error on page {page}, waiting 30 seconds...")
        time.sleep(30)
        continue

    if response.status_code != 200:
        print(f"Stopped at page {page} (Status Code: {response.status_code})")
        break

    soup = BeautifulSoup(response.text, "html.parser")
    games = soup.find_all("article")
    if not games:
        print(f"No articles found on page {page}. Finalizing.")
        break

    saved_count = 0
    for game in games:
        title_tag = game.find("h1", class_="entry-title")
        if not title_tag:
            continue

        title = title_tag.text.strip()
        content = game.find("div", class_="entry-content")
        if not content:
            continue

        p_tag = content.find("p", style=lambda s: s and "200px" in s)
        if not p_tag:
            continue

        repack_size_raw = "Unknown"
        for line in p_tag.get_text().splitlines():
            if "Repack Size:" in line:
                repack_size_raw = line.replace("Repack Size:", "").strip()

        if repack_size_raw == "Unknown":
            continue

        try:
            # Clean up the size string to get a raw float value
            cleaned_size = (repack_size_raw.lower()
                            .replace("gb", "")
                            .replace("from", "")
                            .replace("[selective download]", "")
                            .replace(",", ".")
                            .strip())
            size_gb = float(cleaned_size.split()[0])
        except:
            size_gb = 0

        genres = [a.text for a in p_tag.find_all("a") if "/tag/" in a.get("href", "")]
        link = title_tag.find("a")["href"]

        game_item = {
            "title": title,
            "size_raw": repack_size_raw,
            "size_gb": size_gb,
            "genres": genres,
            "link": link,
            "source": "FitGirl"  # Added a helpful source identifier for your UI badge
        }

        # Prevent duplicate entries by updating existing links or inserting new ones
        collection.update_one(
            {"link": link},
            {"$set": game_item},
            upsert=True
        )
        saved_count += 1

    print(f"Page {page} done — {saved_count} games processed/saved")
    
    page += 1
    time.sleep(1.5)  # Slightly gentler delay for remote DB connections

print(f"Done! Total database count: {collection.count_documents({})} games")