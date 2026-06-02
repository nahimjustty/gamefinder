import requests
from bs4 import BeautifulSoup

url = "https://fitgirl-repacks.site"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, "html.parser")
all_games = [] 
games = soup.find_all("article")

for game in games:
    # Title
    title_tag = game.find("h1", class_="entry-title")
    if not title_tag:
        continue
    title = title_tag.text.strip()

    # Find the main info paragraph (the one with height 200px)
    content = game.find("div", class_="entry-content")
    if not content:
        continue

    p_tag = content.find("p", style=lambda s: s and "200px" in s)
    if not p_tag:
        continue  # skip non-game posts like "Upcoming Repacks"

    # Repack size
    repack_size = "Unknown"
    for line in p_tag.get_text().splitlines():
        if "Repack Size:" in line:
            repack_size = line.replace("Repack Size:", "").strip()

    # Skip if still no size (blog posts, digests etc)
    if repack_size == "Unknown":
        continue

    # Genres — links inside that paragraph
    genres = [a.text for a in p_tag.find_all("a") if "/tag/" in a.get("href", "")]

    # Game page URL
    link = title_tag.find("a")["href"]
    game_data = {
        "title": title,
        "size": repack_size,
        "genres": genres,
        "link": link
    }
    all_games.append(game_data)

# AFTER the loop, print everything
print(all_games)