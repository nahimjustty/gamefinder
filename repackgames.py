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

CATEGORIES = [
    "action", "adventure", "rpg", "simulation", "strategy",
    "sports", "racing", "indie", "casual", "puzzle",
    "horror", "fighting", "shooter"
]

JUNK_WORDS = ["faq", "troubleshooting", "about", "donations",
              "contact", "adult", "porn", "comics", "dmca"]

def is_real_game(title):
    return not any(word in title.lower() for word in JUNK_WORDS)

def fix_url(href):
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return BASE_URL + "/" + href.lstrip("/")

def get_game_links_from_soup(soup):
    """Extract game title+link pairs from a page."""
    game_links = []

    # Primary: h3 a (confirmed working)
    for a in soup.select("h3 a"):
        title = a.get_text(strip=True)
        link = fix_url(a.get("href", ""))
        if title and link and len(title) > 3:
            game_links.append((title, link))

    # Fallback: li > a > strong (the list format we saw in HTML)
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
        time.sleep(random.uniform(0.8, 1.5))
        res = scraper.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        # Cover
        og = soup.select_one('meta[property="og:image"]')
        cover = og["content"] if og and og.get("content") else ""

        # Size
        size = "N/A"
        full_text = soup.get_text()
        for pattern in [
            r'(?:Repack Size|Game Size|Size)[:\s]*([\d.,]+\s*(?:MB|GB))',
            r'([\d.,]+\s*GB)',
        ]:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                size = match.group(1).strip()
                break

        # Genres
        genres = []
        for a in soup.select("a[rel='category tag'], .cat-links a, "
                             ".entry-meta a, [class*='category'] a"):
            text = a.get_text(strip=True)
            if text and len(text) < 25 and text.lower() not in [
                "read more", "download", "repack-games", "free download"
            ]:
                genres.append(text)
        genres = list(dict.fromkeys(genres))[:5]
        if not genres:
            genres = ["Games"]

        # Synopsis
        synopsis = "RepackGames."
        for p in soup.select(".entry-content p, .post-content p"):
            text = p.get_text(strip=True)
            if len(text) > 80 and not any(w in text.lower() for w in
                    ["genre", "size", "language", "repack", "download", "click"]):
                synopsis = text[:150] + "..."
                break

        return size, genres, synopsis, cover

    except Exception as e:
        print(f"    ⚠️  Deep scrape failed: {e}")
        return "N/A", ["Games"], "No description available.", ""

def get_resume_page(cat):
    doc = progress.find_one({"source": f"repackgames_{cat}"})
    return doc["last_page"] if doc else 0

def save_resume_page(cat, page):
    progress.update_one(
        {"source": f"repackgames_{cat}"},
        {"$set": {"last_page": page}},
        upsert=True
    )

def scrape_latest(pages=10):
    """Scrape homepage/latest pages."""
    print(f"🚀 REPACKGAMES: Scraping {pages} latest pages...")
    inserted = 0

    for page in range(1, pages + 1):
        url = f"{BASE_URL}/page/{page}/" if page > 1 else f"{BASE_URL}/"
        print(f"  📂 Page {page}...")

        try:
            res = scraper.get(url, headers=HEADERS, timeout=20)
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
            time.sleep(random.uniform(2, 4))

        except Exception as e:
            print(f"  ❌ Page {page} error: {e}")
            break

    print(f"✅ Latest done — {inserted} new games")

def scrape_by_category(category):
    inserted = 0
    start_page = get_resume_page(category) + 1
    current = start_page

    while True:
        url = (f"{BASE_URL}/category/{category}/page/{current}/"
               if current > 1 else f"{BASE_URL}/category/{category}/")
        print(f"  📂 {category} — page {current}...")

        try:
            res = scraper.get(url, headers=HEADERS, timeout=20)
            if res.status_code == 404:
                print(f"  🏁 End of {category}")
                break

            soup = BeautifulSoup(res.text, "html.parser")
            game_links = get_game_links_from_soup(soup)

            if not game_links:
                print(f"  🏁 No games — end of {category}")
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

                cat_cap = category.capitalize()
                if cat_cap not in genres:
                    genres.insert(0, cat_cap)

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

            save_resume_page(category, current)
            current += 1
            time.sleep(random.uniform(2, 4))

        except Exception as e:
            print(f"  ❌ Error: {e}")
            break

    return inserted

def scrape_all_categories():
    total = 0
    for cat in CATEGORIES:
        print(f"\n🎮 Category: {cat.upper()}")
        n = scrape_by_category(cat)
        total += n
        print(f"  ✅ {cat} done — {n} new games")
        time.sleep(random.uniform(3, 5))
    print(f"\n🎉 Total: {total} new RepackGames added")

def count():
    total = collection.count_documents({"source": "RepackGames"})
    print(f"📊 RepackGames in DB: {total} games")

if __name__ == "__main__":
    count()
    scrape_latest(pages=10)
    # scrape_all_categories()  # uncomment after latest works