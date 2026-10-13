import html
import subprocess
import tempfile
import math
from pathlib import Path
from collections import Counter

# Extensions classées par langage.
EXTENSIONS = {
    ".html": "HTML",
    ".htm": "HTML",
    ".ejs": "EJS",

    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "SCSS",
    ".less": "CSS",

    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",

    ".c": "C/C++",
    ".h": "C/C++",
    ".cpp": "C/C++",
    ".cc": "C/C++",
    ".cxx": "C/C++",
    ".hpp": "C/C++",
    ".hh": "C/C++",
    ".hxx": "C/C++",

    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".py": "Python",

    ".ml": "OCaml",
    ".mli": "OCaml",
    ".mll": "OCaml",
    ".mly": "OCaml",

    ".xml": "XML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".mdx": "Markdown",

    ".php": "PHP",
    ".rb": "Ruby",
    ".go": "Go",
    ".rs": "Rust",
    ".swift": "Swift",
    ".sh": "Shell",
    ".bash": "Shell",
    ".sql": "SQL",
    ".r": "R",
    ".dart": "Dart",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".lua": "Lua",
    ".hs": "Haskell",
    ".scala": "Scala",
    ".sc": "Scala",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".clj": "Clojure",
    ".cljs": "Clojure",
    ".pl": "Perl",
    ".pm": "Perl",
    ".vim": "Vim",
}

# Dossiers qui ne doivent pas être analysés.
IGNORED_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    ".settings",
    ".metadata",
    ".gradle",
    ".fleet",
    ".vs",
    "_build",
    "_opam",
    "_esy",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    "target",
    "out",
    "bin",
    "obj",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "generated",
    "third_party",
    "deps",
    "pods",
    ".dart_tool",
    ".terraform",
    "carthage",
    "javadoc",  # Ignorer les dossiers Javadoc
    "docs",     # Ignorer les documentations en général
    "doc",
}

# Fichiers générés, dépendances ou fichiers non représentatifs
# du code source que l'on veut mesurer.
IGNORED_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "composer.lock",
    "Cargo.lock",
    "poetry.lock",
    "Pipfile.lock",
    "flake.lock",
    "Gemfile.lock",
    "mix.lock",
    "pubspec.lock",
    ".merlin",
}

COLORS = [
    "#e34c26",
    "#563d7c",
    "#f1e05a",
    "#3572A5",
    "#3178c6",
    "#663399",
    "#00ADD8",
    "#b07219",
    "#6e4a7e",
    "#2b7489",
    "#dea584",
    "#8b949e",
]

MAX_FILE_SIZE = 1_000_000
MAX_FILES_PER_REPO = 5000


def count_nonempty_lines(content):
    """Compte les lignes qui ne contiennent pas que des espaces."""
    return sum(1 for line in content.splitlines() if line.strip())

def remove_java_comments(content):
    """Retire les commentaires Java, y compris Javadoc, sans supprimer
    les marqueurs de commentaires présents dans les chaînes de caractères."""
    import re
    pattern = re.compile(
        r'"(?:\\.|[^"\\])*"'       # Chaînes Java
        r'|\'(?:\\.|[^\'\\])*\''
        r'|//[^\n]*'               # Commentaires //
        r'|/\*[\s\S]*?\*/'         # Commentaires /* ... */, Javadoc inclus
    )
    def replace(match):
        text = match.group(0)
        if text.startswith("//") or text.startswith("/*"):
            return re.sub(r'[^\n]', ' ', text)
        return text
    return pattern.sub(replace, content)

def should_ignore(relative_path):
    """Indique si le fichier doit être exclu des statistiques."""
    if relative_path.name in IGNORED_FILES:
        return True

    # Vérification insensible à la casse pour les dossiers (ex: JavaDoc, javadoc)
    if any(part.lower() in IGNORED_DIRS for part in relative_path.parts):
        return True

    # Fichiers compilés ou binaires fréquents.
    if relative_path.suffix.lower() in {
        ".class", ".pyc", ".pyo", ".o", ".obj",
        ".a", ".so", ".dll", ".exe", ".bin",
        ".jar", ".war", ".zip", ".png", ".jpg",
        ".jpeg", ".gif", ".ico", ".pdf", ".woff",
        ".woff2", ".ttf", ".eot", ".mp4", ".mp3",
    }:
        return True

    return False


# Lire la liste des dépôts publics.
repos_file = Path("repos.txt")

if not repos_file.exists():
    raise SystemExit(
        "Fichier repos.txt introuvable. "
        "Crée-le avec un dépôt public par ligne."
    )

with repos_file.open(encoding="utf-8") as f:
    repos = list(dict.fromkeys(
        line.strip()
        for line in f
        if line.strip() and not line.lstrip().startswith("#")
    ))

if not repos:
    raise SystemExit("repos.txt ne contient aucun dépôt.")

lines_by_language = Counter()
files_by_language = Counter()
failed_repos = []

print(f"{len(repos)} dépôts à analyser.")

# Le répertoire temporaire est supprimé automatiquement à la fin.
with tempfile.TemporaryDirectory(prefix="github-langs-") as temp:
    temp_root = Path(temp)

    for index, repo in enumerate(repos, start=1):
        # Vérifier que la ligne a bien le format propriétaire/dépôt.
        if repo.count("/") != 1:
            print(f"[{index}/{len(repos)}] Nom de dépôt invalide : {repo}")
            failed_repos.append(repo)
            continue

        destination = temp_root / f"repo-{index}"
        url = f"https://github.com/{repo}.git"

        print(f"\n[{index}/{len(repos)}] Clonage : {repo}")

        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth", "1",
                "--filter=blob:none",
                url,
                str(destination),
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"Échec du clonage : {repo}")
            if result.stderr.strip():
                print(result.stderr.strip())
            failed_repos.append(repo)
            continue

        analyzed_files = 0

        for file in destination.rglob("*"):
            if not file.is_file():
                continue

            relative = file.relative_to(destination)

            if should_ignore(relative):
                continue

            language = EXTENSIONS.get(file.suffix.lower())

            # Reconnaître aussi les fichiers sans extension.
            if file.name.lower() == "makefile":
                language = "Makefile"
            elif file.name.lower() == "dockerfile":
                language = "Dockerfile"

            if not language:
                continue

            if analyzed_files >= MAX_FILES_PER_REPO:
                print(f"Limite de fichiers atteinte : {repo}")
                break

            try:
                size = file.stat().st_size

                if size > MAX_FILE_SIZE:
                    continue

                content = file.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

                # Éviter de compter les fichiers binaires mal identifiés.
                if "\x00" in content:
                    continue
                
                # Exclure les commentaires Java du compte des lignes
                if language == "Java":
                    content = remove_java_comments(content)
                count = count_nonempty_lines(content)

                lines_by_language[language] += count
                files_by_language[language] += 1
                analyzed_files += 1

            except (OSError, UnicodeError) as error:
                print(f"Fichier ignoré : {relative}: {error}")

        print(f"Terminé : {repo} ({analyzed_files} fichiers analysés)")

# Afficher le classement.
total_lines = sum(lines_by_language.values())

if total_lines == 0:
    raise SystemExit(
        "\nAucune ligne trouvée. Vérifie repos.txt "
        "et les erreurs de clonage."
    )

print("\n===== LIGNES PAR LANGAGE =====")

for language, count in lines_by_language.most_common():
    percent = count / total_lines * 100
    print(
        f"{language:14} {count:8} lignes "
        f"({percent:5.1f} %) | "
        f"{files_by_language[language]} fichiers"
    )

print(f"\nTOTAL : {total_lines:,} lignes non vides")

# Générer la carte SVG.
top = lines_by_language.most_common(12)

width = 600
bar_total_width = 540
bar_x = 30
bar_y = 65  # Décalé vers le bas pour le titre
bar_height = 14

# Calculer la hauteur dynamique en fonction du nombre de lignes (2 colonnes)
rows = math.ceil(len(top) / 2)
height = 115 + rows * 35 # Hauteur ajustée

svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" '
    f'width="{width}" height="{height}" '
    f'viewBox="0 0 {width} {height}">',
    '<style>',
    'text { font-family: "Segoe UI", Arial, sans-serif; font-size: 14px; fill: #586e75; }',
    '.title { font-size: 20px; font-weight: 600; fill: #2f6bf3; }', # Style du titre
    '</style>',
    # Fond transparent avec une fine bordure comme sur l'image
    '<rect width="100%" height="100%" rx="12" fill="transparent" stroke="#e1e4e8" stroke-width="1"/>',
    # Titre
    '<text x="30" y="40" class="title">Most Used Languages</text>',
    '<defs>',
    '<clipPath id="bar-clip">',
    f'<rect x="{bar_x}" y="{bar_y}" width="{bar_total_width}" height="{bar_height}" rx="{bar_height/2}"/>',
    '</clipPath>',
    '</defs>',
    '<g clip-path="url(#bar-clip)">'
]

# Dessiner la barre empilée
current_x = bar_x
for index, (language, count) in enumerate(top):
    percent = count / total_lines
    w = bar_total_width * percent
    color = COLORS[index % len(COLORS)]
    
    # Ne pas dessiner les rectangles infiniment petits
    if w > 0:
        svg.append(f'<rect x="{current_x:.2f}" y="{bar_y}" width="{w:.2f}" height="{bar_height}" fill="{color}"/>')
        current_x += w

svg.append('</g>')

# Dessiner la légende sur 2 colonnes
for index, (language, count) in enumerate(top):
    percent = (count / total_lines) * 100
    color = COLORS[index % len(COLORS)]
    
    col = index % 2
    row = index // 2
    
    x_pos = 50 + col * 260
    y_pos = 120 + row * 35 # Décalé vers le bas
    
    svg.append(
        f'<circle cx="{x_pos}" cy="{y_pos - 4}" r="5" fill="{color}"/>'
    )
    svg.append(
        f'<text x="{x_pos + 15}" y="{y_pos}">{html.escape(language)} {percent:.2f}%</text>'
    )

svg.append("</svg>")

Path("languages.svg").write_text(
    "\n".join(svg),
    encoding="utf-8",
)

print("\nCarte générée : languages.svg")
