# steamrip.py
import cloudscraper
from bs4 import BeautifulSoup
from pymongo import MongoClient
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from webdriver_manager.microsoft import EdgeChromiumDriverManager
import time
import random
import re
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


client = MongoClient("mongodb://localhost:27017/")
db = client["gamefinder2"]
collection = db["games"]

BASE_URL = "https://steamrip.com"

CATEGORIES = [
    "action", "adventure", "rpg", "simulation", "strategy",
    "sports", "racing", "indie", "casual", "puzzle",
    "horror", "fighting", "shooter", "platformer", "sandbox"
]

JUNK_WORDS = ["faq", "troubleshooting", "about", "donations", "how to", "contact"]

def is_real_game(title):
    return not any(word in title.lower() for word in JUNK_WORDS)

def fix_url(href):
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return BASE_URL + "/" + href.lstrip("/")

def get_driver():
    options = Options()
    # options.add_argument("--headless=new")  # uncomment after confirming it works
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Edge(
        service=Service(EdgeChromiumDriverManager().install()),
        options=options
    )
    return driver

def wait_for_cloudflare(driver, timeout=30):
    print("  ⏳ Waiting for Cloudflare...", end=" ", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        title = driver.title
        if "Just a moment" not in title and "Cloudflare" not in title:
            print(f"✅ {title[:40]}")
            return True
        time.sleep(1)
    print("❌ Timed out")
    return False

def scrape_steamrip_selenium():
    print("🚀 STEAMRIP: Opening Firefox...")
    driver = get_driver()
    inserted = 0

    try:
        print("  🌐 Testing connection...")
        driver.get(BASE_URL)
        if not wait_for_cloudflare(driver, timeout=30):
            print("❌ Can't get past Cloudflare.")
            return

        print("  ✅ Connected! Starting scrape...")
        time.sleep(2)

        for cat in CATEGORIES:
            print(f"\n🎮 Category: {cat.upper()}")
            page = 1

            while True:
                url = f"{BASE_URL}/category/{cat}/page/{page}/" if page > 1 else f"{BASE_URL}/category/{cat}/"
                print(f"  📂 Page {page}...")
                driver.get(url)

                if not wait_for_cloudflare(driver, timeout=30):
                    print(f"  ⚠️  Skipping {cat} page {page}")
                    break

                time.sleep(2)

                if "not found" in driver.title.lower():
                    print(f"  🏁 End of {cat}")
                    break

                soup = BeautifulSoup(driver.page_source, "html.parser")
                game_links = []

                for sel in ["article h2 a", "article h3 a", ".entry-title a", "h2 a", "h3 a"]:
                    tags = soup.select(sel)
                    if tags:
                        for a in tags:
                            title = a.get_text(strip=True)
                            link = fix_url(a.get("href", ""))
                            if title and link and len(title) > 3:
                                game_links.append((title, link))
                        break

                if not game_links:
                    print(f"  🏁 No games — end of {cat}")
                    break

                print(f"  Found {len(game_links)} games")

                for title, link in game_links:
                    if not is_real_game(title):
                        continue
                    if any(s in link for s in ["/category/", "/tag/", "/page/", "#"]):
                        continue
                    if collection.find_one({"link": link}):
                        continue

                    print(f"    📦 {title[:50]}...")
                    driver.get(link)
                    wait_for_cloudflare(driver, timeout=20)
                    time.sleep(1)

                    soup2 = BeautifulSoup(driver.page_source, "html.parser")

                    og = soup2.select_one('meta[property="og:image"]')
                    cover = og["content"] if og and og.get("content") else ""

                    size = "N/A"
                    full_text = soup2.get_text()
                    match = re.search(r'(?:Game Size|Size)[:\s]*([\d.,]+\s*(?:MB|GB))', full_text, re.IGNORECASE)
                    if match:
                        size = match.group(1).strip()
                    else:
                        match = re.search(r'([\d.,]+\s*GB)', full_text, re.IGNORECASE)
                        if match:
                            size = match.group(1).strip()

                    genres = [cat.capitalize()]
                    for a in soup2.select("a[rel='category tag'], .cat-links a, .entry-meta a"):
                        text = a.get_text(strip=True)
                        if text and len(text) < 25 and text.lower() not in ["read more", "download", "steamrip"]:
                            genres.append(text)
                    genres = list(dict.fromkeys(genres))[:5]

                    synopsis = "SteamRIP Game."
                    for p in soup2.select(".entry-content p"):
                        text = p.get_text(strip=True)
                        if len(text) > 80 and not any(w in text.lower() for w in ["genre", "size", "language", "repack"]):
                            synopsis = text[:150] + "..."
                            break

                    collection.insert_one({
                        "title": title, "link": link, "source": "SteamRIP",
                        "cover": cover, "rating": 5.0, "genres": genres,
                        "size_raw": size, "synopsis": synopsis
                    })
                    print(f"    ✅ {title[:45]} → {size}")
                    inserted += 1

                page += 1
                time.sleep(random.uniform(2, 4))

    except KeyboardInterrupt:
        print(f"\n⏹️  Stopped — {inserted} games saved")
    finally:
        driver.quit()

    print(f"\n🎉 Done — {inserted} new games added")

def count():
    total = collection.count_documents({"source": "SteamRIP"})
    print(f"📊 SteamRIP in DB: {total} games")

if __name__ == "__main__":
    count()
    scrape_steamrip_selenium()