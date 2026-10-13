import json
import os
import html
import urllib.request
from collections import Counter

API = "https://api.github.com/repos/"
token = os.getenv("GITHUB_TOKEN")
languages = Counter()

headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "contributed-languages-card",
}

if token:
    headers["Authorization"] = f"Bearer {token}"

with open("repos.txt", encoding="utf-8") as f:
    repos = [
        line.strip()
        for line in f
        if line.strip() and not line.lstrip().startswith("#")
    ]

if not repos:
    raise SystemExit("Ajoute des dépôts dans repos.txt")

for repo in repos:
    try:
        req = urllib.request.Request(
            API + repo + "/languages",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.load(response)

        languages.update(data)
        print(f"OK: {repo}")
    except Exception as error:
        print(f"Échec: {repo}: {error}")

total = sum(languages.values())

if total == 0:
    raise SystemExit(
        "Aucun langage récupéré. Vérifie les noms des dépôts."
    )

top = languages.most_common(10)
width = 600
bar_width = 540
height = 65 + len(top) * 39

colors = [
    "#3178c6", "#f1e05a", "#b07219", "#e34c26",
    "#663399", "#3572A5", "#00ADD8", "#555555",
    "#6e4a7e", "#2b7489"
]

svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" '
    f'width="{width}" height="{height}" '
    f'viewBox="0 0 {width} {height}">',
    '<rect width="100%" height="100%" rx="12" fill="#0d1117"/>',
    '<text x="25" y="32" fill="#e6edf3" font-size="18" '
    'font-family="Arial" font-weight="bold">'
    'Languages in My Projects</text>',
]

for i, (name, size) in enumerate(top):
    y = 57 + i * 39
    percent = size / total * 100
    length = bar_width * percent / 100
    color = colors[i % len(colors)]

    svg.append(
        f'<text x="25" y="{y}" fill="#e6edf3" '
        f'font-family="Arial" font-size="13">'
        f'{html.escape(name)}</text>'
    )
    svg.append(
        f'<text x="575" y="{y}" text-anchor="end" '
        f'fill="#8b949e" font-family="Arial" font-size="12">'
        f'{percent:.1f}%</text>'
    )
    svg.append(
        f'<rect x="25" y="{y+7}" width="{bar_width}" '
        f'height="10" rx="5" fill="#30363d"/>'
    )
    svg.append(
        f'<rect x="25" y="{y+7}" width="{length:.2f}" '
        f'height="10" rx="5" fill="{color}"/>'
    )

svg.append("</svg>")

with open("languages.svg", "w", encoding="utf-8") as f:
    f.write("\n".join(svg))

print("Carte créée : languages.svg")
