const API = "http://localhost:8000";
let currentPage = 1;

async function loadGenres() {
    try {
        const res = await fetch(`${API}/genres`);
        const genres = await res.json();
        const select = document.getElementById("genre");
        select.innerHTML = '<option value="">All Genres</option>';
        genres.forEach(g => {
            select.innerHTML += `<option value="${g}">${g}</option>`;
        });
    } catch (e) {
        console.error("Failed to load genres:", e);
    }
}

async function loadMirrors() {
    try {
        const res = await fetch(`${API}/mirrors`);
        const mirrors = await res.json();
        const select = document.getElementById("mirrorFilter");
        if (!select) return;
        select.innerHTML = '<option value="">All Mirrors</option>';
        mirrors.forEach(m => {
            select.innerHTML += `<option value="${m}">${m}</option>`;
        });
    } catch (e) {
        console.error("Failed to load mirrors:", e);
    }
}

async function searchGames(page = 1) {
    currentPage = page;

    const title   = document.getElementById("gameTitle")?.value.trim() || "";
    const maxSize = document.getElementById("maxSize")?.value || "";
    const genre   = document.getElementById("genre")?.value || "";
    const sort    = document.getElementById("sortOrder")?.value || "newest";
    const rating  = document.getElementById("gameRating")?.value || "";
    const mirror  = document.getElementById("mirrorFilter")?.value || "";

    let url = `${API}/games/filter?page=${page}&sort=${sort}`;
    if (title)   url += `&title=${encodeURIComponent(title)}`;
    if (maxSize) url += `&max_size=${maxSize}`;
    if (genre)   url += `&genre=${encodeURIComponent(genre)}`;
    if (rating)  url += `&min_rating=${rating}`;
    if (mirror)  url += `&mirror=${encodeURIComponent(mirror)}`;

    try {
        const res = await fetch(url);
        const data = await res.json();

        document.getElementById("count").textContent = `${data.total.toLocaleString()} games found`;

        const results = document.getElementById("results");
        results.innerHTML = "";

        if (!data.games || data.games.length === 0) {
            results.innerHTML = "<p style='color:#888;text-align:center;grid-column:1/-1'>No games found. Try different filters.</p>";
            renderPagination(0, 1);
            return;
        }

        data.games.forEach(game => {
            const cover = game.cover
                ? `<img src="${game.cover}" onerror="this.style.display='none'" style="width:100%;border-radius:8px;margin-bottom:10px;">`
                : "";
            const size = game.size_raw && game.size_raw !== "N/A"
                ? `💾 ${game.size_raw}`
                : `<span style="color:#555">Size N/A</span>`;
            const genres = (game.genres || []).filter(g => g && g.toLowerCase() !== "games");
            const genreHTML = genres.length
                ? `<div class="game-genres">🏷️ ${genres.join(", ")}</div>`
                : "";
            const ratingHTML = game.rating
                ? `<div style="color:#ffd700;margin:6px 0">⭐ ${game.rating}/10</div>`
                : "";
            const synopsis = game.synopsis && game.synopsis !== "No description available."
                ? `<div style="color:#aaa;font-size:0.78rem;margin-bottom:10px;line-height:1.4">${game.synopsis.slice(0, 120)}...</div>`
                : "";
const sourceBadge = `<span class="source-badge">${game.source || "?"}</span>`;
const mirrors = game.mirrors || [];
const mirrorHTML = mirrors.length
    ? `<div class="mirror-badges">
         ${mirrors.map(m => `
            <span class="mirror-badge ${m.toLowerCase().includes('fucking') || m.toLowerCase().includes('fast') ? 'fast' : ''}">
                ⚡ ${m}
            </span>
         `).join("")}
       </div>`
    : "";

            results.innerHTML += `
                <div class="game-card">
                    ${cover}
                    ${sourceBadge}
                    <div class="game-title">${game.title}</div>
                    ${synopsis}
                    ${genreHTML}
                    ${mirrorHTML}
                    <div class="game-size">${size}</div>
                    ${ratingHTML}
                    <a class="download-btn" href="${game.link}" target="_blank">Download</a>
                </div>
            `;
        });

        renderPagination(data.pages, page);

    } catch (e) {
        console.error("Search error:", e);
        document.getElementById("results").innerHTML =
            "<p style='color:red;text-align:center;grid-column:1/-1'>Server error. Is the backend running?</p>";
    }
}

function renderPagination(totalPages, activePage) {
    const nav = document.getElementById("pagination");
    nav.innerHTML = "";
    if (totalPages <= 1) return;

    const addBtn = (label, page, active = false, disabled = false) => {
        const btn = document.createElement("button");
        btn.textContent = label;
        btn.disabled = disabled;
        btn.style.cssText = `
            padding: 8px 14px;
            border: 1px solid #333;
            border-radius: 6px;
            cursor: ${disabled ? "default" : "pointer"};
            background: ${active ? "#00ff88" : "#1e1e1e"};
            color: ${active ? "#000" : "#fff"};
            font-weight: ${active ? "700" : "400"};
        `;
        btn.onclick = () => {
            if (!disabled) {
                searchGames(page);
                window.scrollTo({ top: 0, behavior: "smooth" });
            }
        };
        nav.appendChild(btn);
    };

    addBtn("«", 1, false, activePage === 1);
    addBtn("‹", activePage - 1, false, activePage === 1);

    const start = Math.max(1, activePage - 2);
    const end = Math.min(totalPages, start + 4);

    if (start > 1) addBtn("...", start - 1);
    for (let i = start; i <= end; i++) addBtn(i, i, i === activePage);
    if (end < totalPages) addBtn("...", end + 1);

    addBtn("›", activePage + 1, false, activePage === totalPages);
    addBtn("»", totalPages, false, activePage === totalPages);
}

document.addEventListener("DOMContentLoaded", () => {
    loadGenres();
    loadMirrors();
    searchGames();
    document.getElementById("gameTitle")?.addEventListener("keydown", e => {
        if (e.key === "Enter") searchGames();
    });
});