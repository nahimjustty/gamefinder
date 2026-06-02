import cloudscraper
from bs4 import BeautifulSoup
from pymongo import MongoClient
import time
import random
import re
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

client = MongoClient("mongodb://localhost:27017/")
db = client["gamefinder2"]
collection = db["games"]
progress = db["scrape_progress"]

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True}
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

JUNK_WORDS = [
    "updates digest", "upcoming repacks", "denuvo games", "faq",
    "troubleshooting", "about", "dns problems", "memecoin",
    "hypervisor", "donations", "pragmata release", "good read",
    "get the fuck out", "call for donations", "status update"
]

def is_real_game(title):
    return not any(word in title.lower() for word in JUNK_WORDS)

def get_img_src(tag):
    img = tag.find("img")
    if not img:
        return ""
    src = img.get("data-orig-file") or img.get("data-src") or img.get("src") or ""
    if src:
        src = re.sub(r'-\d+x\d+\.(jpg|png|jpeg|webp)', r'.\1', src)
    return src

def parse_size(text):
    match = re.search(r'Repack Size[:\s]+([0-9.,\-–]+\s*(?:MB|GB))', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r'Original Size[:\s]+([0-9.,\-–]+\s*(?:MB|GB))', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return "N/A"

def get_mirrors_from_page(soup):
    """Extract download mirror names from a FitGirl game page."""
    mirrors = []
    for a in soup.select(".entry-content a"):
        text = a.get_text(strip=True)
        match = re.search(r'Filehoster:\s*(.+?)(?:\s*[\(\[]|$)', text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if name and len(name) < 40:
                mirrors.append(name)
    return list(dict.fromkeys(mirrors))

def get_deep_details(url):
    try:
        time.sleep(random.uniform(0.5, 1.2))
        res = scraper.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        size = "N/A"
        for strong in soup.find_all("strong"):
            text = strong.get_text()
            if "Repack Size" in text:
                size = text.split(":")[-1].strip()
                break
        if size == "N/A":
            content = soup.select_one(".entry-content")
            if content:
                size = parse_size(content.get_text())

        genres = []
        for a in soup.select("a[rel='tag'], .entry-tags a"):
            text = a.get_text(strip=True)
            if text and len(text) < 25:
                genres.append(text)
        if not genres:
            genres = ["Games"]

        mirrors = get_mirrors_from_page(soup)

        desc_tag = soup.select_one(".entry-content p")
        synopsis = desc_tag.get_text(strip=True)[:150] + "..." if desc_tag else "FitGirl Repack."

        return size, genres, synopsis, mirrors
    except Exception as e:
        print(f"    ⚠️  Deep scrape failed for {url}: {e}")
        return "N/A", ["Games"], "No description available.", []

def scrape_fitgirl(pages_to_run=5):
    prog_doc = progress.find_one({"source": "fitgirl"})
    start_page = prog_doc["last_page"] + 1 if prog_doc else 1
    print(f"🚀 FITGIRL: Starting from page {start_page}...")

    for page in range(start_page, start_page + pages_to_run):
        url = f"https://fitgirl-repacks.site/page/{page}/"
        try:
            res = scraper.get(url, timeout=20)
            if res.status_code == 404:
                print("🏁 Reached the end of the site.")
                break

            soup = BeautifulSoup(res.text, "html.parser")
            articles = soup.find_all("article")
            if not articles:
                print(f"  ⚠️  No articles on page {page}.")
                break

            page_inserted = 0
            for art in articles:
                title_tag = art.select_one(".entry-title a")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                link = title_tag["href"]

                if not is_real_game(title):
                    continue
                if collection.find_one({"link": link}):
                    continue

                print(f"  📦 {title[:50]}...")
                size, genres, synopsis, mirrors = get_deep_details(link)
                collection.insert_one({
                    "title": title,
                    "link": link,
                    "source": "FitGirl",
                    "cover": get_img_src(art),
                    "rating": 5.0,
                    "genres": genres,
                    "size_raw": size,
                    "synopsis": synopsis,
                    "mirrors": mirrors
                })
                page_inserted += 1

            progress.update_one({"source": "fitgirl"}, {"$set": {"last_page": page}}, upsert=True)
            print(f"✅ Page {page} done — {page_inserted} new games.")
            time.sleep(random.uniform(2, 4))

        except Exception as e:
            print(f"❌ Error on page {page}: {e}")
            break

def delete_junk():
    print("🗑️  Deleting junk entries...")
    deleted = 0
    for word in JUNK_WORDS:
        result = collection.delete_many({"title": {"$regex": word, "$options": "i"}})
        if result.deleted_count > 0:
            print(f"  '{word}' → deleted {result.deleted_count}")
            deleted += result.deleted_count
    print(f"✅ Total junk deleted: {deleted}")

def count_missing():
    total = collection.count_documents({"source": "FitGirl"})
    missing = collection.count_documents({
        "source": "FitGirl",
        "$or": [
            {"size_raw": {"$exists": False}},
            {"size_raw": "N/A"},
            {"size_raw": ""}
        ]
    })
    print(f"📊 FitGirl: {total} total | {missing} missing size | {total - missing} complete")

def backfill_mirrors(limit=100):
    """Backfill mirrors for FitGirl games that don't have them yet."""
    games = list(collection.find({
        "source": "FitGirl",
        "mirrors": {"$exists": False}
    }).limit(limit))

    if not games:
        print("✅ All FitGirl games have mirrors!")
        return

    print(f"🔗 Backfilling mirrors for {len(games)} games...")
    updated = 0

    for i, game in enumerate(games):
        try:
            time.sleep(random.uniform(0.8, 1.5))
            res = scraper.get(game["link"], headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            mirrors = get_mirrors_from_page(soup)
            collection.update_one(
                {"_id": game["_id"]},
                {"$set": {"mirrors": mirrors}}
            )
            print(f"  [{i+1}/{len(games)}] {game['title'][:45]} → {mirrors}")
            updated += 1
        except Exception as e:
            print(f"  [{i+1}/{len(games)}] ❌ {game['title'][:40]} → {e}")
            collection.update_one(
                {"_id": game["_id"]},
                {"$set": {"mirrors": []}}
            )

    print(f"✅ Done — {updated} games updated.")

def count_mirrors():
    total = collection.count_documents({"source": "FitGirl"})
    done = collection.count_documents({"source": "FitGirl", "mirrors": {"$exists": True}})
    print(f"📊 Mirrors: {done}/{total} FitGirl games done")

if __name__ == "__main__":
    count_mirrors()
    backfill_mirrors(limit=2000)
    # scrape_fitgirl(pages_to_run=50)