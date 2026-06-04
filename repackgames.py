# repackgames.py
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

BASE_URL = "https://repack-games.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": BASE_URL,
}

CATEGORIES = {
    "action-games": "Action",
    "adventure-games": "Adventure",
    "rpg-pc-games": "RPG",
    "simulation-game": "Simulation",
    "strategy-games": "Strategy",
    "sport-game": "Sports",
    "racing-game": "Racing",
    "puzzle": "Puzzle",
    "horror-games": "Horror",
    "fighting-games": "Fighting",
    "shooting-games": "Shooter",
    "survival-games": "Survival",
    "open-world-game": "Open World",
    "multiplayer-games": "Multiplayer",
    "sci-fi-games": "Sci-Fi",
}

JUNK_WORDS = [
    "faq", "troubleshooting", "about", "donations", "contact",
    "comics", "dmca", "sexy", "femboy", "futa", "hentai", "nsfw",
    "18+", "porn", "adult", "nudity", "uncensored", "erotic",
    "meat urinal", "lucky bastard", "freshwomen", "being a dik",
    "fallen doll", "corruption", "temptation", "hardest interview",
    "lisc season", "our meat", "free love"
]

def is_real_game(title):
    return not any(word in title.lower() for word in JUNK_WORDS)

def fix_url(href):
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return BASE_URL + "/" + href.lstrip("/")

def get_game_links_from_soup(soup):
    game_links = []

    # Primary: h3 a
    for a in soup.select("h3 a"):
        title = a.get_text(strip=True)
        link = fix_url(a.get("href", ""))
        if title and link and len(title) > 3:
            game_links.append((title, link))

    # Fallback: li > a > strong
    if not game_links:
        for a in soup.select("li a"):
            strong = a.find("strong")
            if strong:
                title = strong.get_text(strip=True)
                link = fix_url(a.get("href", ""))
                if title and link and len(title) > 3:
                    game_links.append((title, link))

    # Dedupe by link
    seen = set()
    result = []
    for title, link in game_links:
        if link not in seen:
            seen.add(link)
            result.append((title, link))
    return result

def get_deep_details(url):
    try:
        time.sleep(random.uniform(1, 2))
        res = scraper.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, "html.parser")

        # Skip adult games
        for a in soup.select(".single-category a"):
            href = a.get("href", "")
            if "adult" in href or "nudity" in href:
                return None, None, None, None

        # Cover
        og = soup.select_one('meta[property="og:image"]')
        cover = og["content"] if og and og.get("content") else ""

        # Size
        size = "N/A"
        full_text = soup.get_text()
        for pattern in [
            r'[Gg]ame\s*[Ss]ize[:\s]*([\d.,]+\s*(?:MB|GB))',
            r'(?:Repack Size|Size)[:\s]*([\d.,]+\s*(?:MB|GB))',
            r'([\d.,]+\s*GB)',
        ]:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                size = match.group(1).strip()
                break

        # Genres — use single-category class
        genres = []
        skip_genres = [
            "best pc games to play", "top games", "recently updated",
            "adult games", "porn games", "comics", "3d comics",
            "emulator games", "top pc games"
        ]
        for a in soup.select(".single-category a"):
            text = a.get_text(strip=True)
            if text and len(text) < 30 and not any(
                s in text.lower() for s in skip_genres
            ):
                genres.append(text.title())

        genres = list(dict.fromkeys(genres))[:5]
        if not genres:
            genres = ["Games"]

        # Synopsis
        synopsis = "RepackGames."
        for p in soup.select(".entry-content p, .post-content p"):
            text = p.get_text(strip=True)
            if len(text) > 80 and not any(w in text.lower() for w in [
                "genre", "size", "language", "repack", "download", "click"
            ]):
                synopsis = text[:150] + "..."
                break

        return size, genres, synopsis, cover

    except Exception as e:
        print(f"    ⚠️  Deep scrape failed: {e}")
        return "N/A", ["Games"], "No description available.", ""

def get_resume_page(slug):
    doc = progress.find_one({"source": f"repackgames_{slug}"})
    return doc["last_page"] if doc else 0

def save_resume_page(slug, page):
    progress.update_one(
        {"source": f"repackgames_{slug}"},
        {"$set": {"last_page": page}},
        upsert=True
    )

def reset_progress():
    result = progress.delete_many({"source": {"$regex": "repackgames_"}})
    print(f"✅ Progress reset — {result.deleted_count} entries cleared")

def scrape_latest(pages=10):
    print(f"🚀 REPACKGAMES: Scraping {pages} latest pages...")
    inserted = 0

    for page in range(1, pages + 1):
        url = f"{BASE_URL}/page/{page}/" if page > 1 else f"{BASE_URL}/"
        print(f"  📂 Page {page}...")

        res = None
        for attempt in range(3):
            try:
                res = scraper.get(url, headers=HEADERS, timeout=30)
                break
            except Exception as e:
                wait = (attempt + 1) * 5
                print(f"  ⚠️  Attempt {attempt+1} failed, retrying in {wait}s...")
                time.sleep(wait)

        if not res:
            print(f"  ❌ Page {page} failed after 3 attempts, skipping")
            continue

        if res.status_code == 404:
            break

        soup = BeautifulSoup(res.text, "html.parser")
        game_links = get_game_links_from_soup(soup)

        if not game_links:
            print(f"  🏁 No games on page {page}")
            break

        print(f"  Found {len(game_links)} games")

        for title, link in game_links:
            if not is_real_game(title):
                continue
            if any(s in link for s in ["/category/", "/tag/", "/page/", "#"]):
                continue
            if collection.find_one({"link": link}):
                continue

            print(f"    📦 {title[:55]}...")
            size, genres, synopsis, cover = get_deep_details(link)

            if size is None:
                print(f"    🚫 Skipping adult: {title[:40]}")
                continue

            print(f"        → {size} | {genres[:2]}")

            collection.insert_one({
                "title": title,
                "link": link,
                "source": "RepackGames",
                "cover": cover,
                "rating": 5.0,
                "genres": genres,
                "size_raw": size,
                "synopsis": synopsis
            })
            inserted += 1

        print(f"  ✅ Page {page} done")
        time.sleep(random.uniform(3, 6))

    print(f"✅ Latest done — {inserted} new games")

def scrape_by_category(slug, name):
    inserted = 0
    start_page = get_resume_page(slug) + 1
    current = start_page
    consecutive_failures = 0
    MAX_FAILURES = 3  # stop after 3 consecutive failed pages

    while True:
        url = (f"{BASE_URL}/category/{slug}/page/{current}/"
               if current > 1 else f"{BASE_URL}/category/{slug}/")
        print(f"  📂 {name} — page {current}...")

        res = None
        for attempt in range(3):
            try:
                res = scraper.get(url, headers=HEADERS, timeout=30)
                break
            except Exception as e:
                wait = (attempt + 1) * 5
                print(f"  ⚠️  Attempt {attempt+1} failed, retrying in {wait}s...")
                time.sleep(wait)

        if not res:
            consecutive_failures += 1
            print(f"  ❌ Failed ({consecutive_failures}/{MAX_FAILURES})")
            if consecutive_failures >= MAX_FAILURES:
                print(f"  🛑 Too many failures — stopping {name}")
                break
            save_resume_page(slug, current)
            current += 1
            continue

        # Reset failure counter on success
        consecutive_failures = 0

        if res.status_code == 404:
            print(f"  🏁 End of {name}")
            break

        soup = BeautifulSoup(res.text, "html.parser")
        game_links = get_game_links_from_soup(soup)

        if not game_links:
            print(f"  🏁 No games — end of {name}")
            break

        print(f"  Found {len(game_links)} games")

        for title, link in game_links:
            if not is_real_game(title):
                continue
            if any(s in link for s in ["/category/", "/tag/", "/page/", "#"]):
                continue
            if collection.find_one({"link": link}):
                continue

            print(f"    📦 {title[:55]}...")
            size, genres, synopsis, cover = get_deep_details(link)

            if size is None:
                print(f"    🚫 Skipping adult: {title[:40]}")
                continue

            if name not in genres:
                genres.insert(0, name)

            print(f"        → {size} | {genres[:2]}")

            collection.insert_one({
                "title": title,
                "link": link,
                "source": "RepackGames",
                "cover": cover,
                "rating": 5.0,
                "genres": genres,
                "size_raw": size,
                "synopsis": synopsis
            })
            inserted += 1

        save_resume_page(slug, current)
        current += 1
        time.sleep(random.uniform(2, 4))

    return inserted

def scrape_all_categories():
    total = 0
    for slug, name in CATEGORIES.items():
        print(f"\n🎮 Category: {name.upper()}")
        n = scrape_by_category(slug, name)
        total += n
        print(f"  ✅ {name} done — {n} new games")
        time.sleep(random.uniform(3, 5))
    print(f"\n🎉 Total: {total} new RepackGames added")

def count():
    total = collection.count_documents({"source": "RepackGames"})
    print(f"📊 RepackGames in DB: {total} games")

if __name__ == "__main__":
    count()
    reset_progress()  # clears the bad page 2604 progress
    scrape_all_categories()