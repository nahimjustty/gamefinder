from pymongo import MongoClient
import requests
from bs4 import BeautifulSoup
import time

client = MongoClient("mongodb://localhost:27017/")
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
        print(f"Stopped at page {page}")
        break

    soup = BeautifulSoup(response.text, "html.parser")
    games = soup.find_all("article")
    if not games:
        break

    batch = []
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
            size_gb = float(repack_size_raw.lower()
                          .replace("gb", "")
                          .replace("from", "")
                          .replace("[selective download]", "")
                          .strip()
                          .split()[0])
        except:
            size_gb = 0

        genres = [a.text for a in p_tag.find_all("a") if "/tag/" in a.get("href", "")]
        link = title_tag.find("a")["href"]

        batch.append({
            "title": title,
            "size_raw": repack_size_raw,
            "size_gb": size_gb,
            "genres": genres,
            "link": link
        })

    if batch:
        collection.insert_many(batch)
        print(f"Page {page} done — {len(batch)} games saved")

    page += 1
    time.sleep(1)

print(f"Done! Total: {collection.count_documents({})} games")