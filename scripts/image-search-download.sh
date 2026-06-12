#!/usr/bin/env bash
set -euo pipefail

OUT_DIR_DEFAULT="${IMG_OUT_DIR:-${HOME}/image-search-results}"
LIMIT_DEFAULT=5
EDGE_TTS_VENV="${EDGE_TTS_VENV:-${HOME}/.venvs/edge-tts}"
PYTHON_BIN="${PYTHON_BIN:-${EDGE_TTS_VENV}/bin/python}"

usage() {
  cat <<'EOF'
Usage:
  image-search-download.sh -s <source> -q <query> [options]

Sources:
  irasutoya   Open search page on いらすとや
  commons     Wikimedia Commons search page
  pixabay     Pixabay search page
  pexels      Pexels search page

Options:
  -s SOURCE   Source site
  -q QUERY    Search query
  -o DIR      Output directory (default: ~/image-search-results)
  -l N        Max results to print/save as links (default: 5)
  -d          For `commons`, also download the first candidate image file
  -h          Show help

What this script does:
  - Builds a search URL for the chosen site
  - Fetches the page HTML when possible
  - Saves the raw HTML locally for inspection
  - Prints the search URL
  - Prints a best-effort first candidate image/page URL for `commons`
  - Optional: download the first candidate image from `commons`

Note:
  This script does NOT reliably download final image binaries from all sites,
  because many sites use anti-bot protection, JS rendering, or indirect image URLs.
  It is meant as a practical search helper and page saver.
EOF
}

source_site=""
query=""
out_dir="$OUT_DIR_DEFAULT"
limit="$LIMIT_DEFAULT"
download_first=0

while getopts ":s:q:o:l:dh" opt; do
  case "$opt" in
    s) source_site="$OPTARG" ;;
    q) query="$OPTARG" ;;
    o) out_dir="$OPTARG" ;;
    l) limit="$OPTARG" ;;
    d) download_first=1 ;;
    h)
      usage
      exit 0
      ;;
    :)
      echo "Option -$OPTARG requires an argument" >&2
      exit 1
      ;;
    \?)
      echo "Unknown option: -$OPTARG" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$source_site" || -z "$query" ]]; then
  usage >&2
  exit 1
fi

mkdir -p "$out_dir"
ts="$(date +%Y%m%d-%H%M%S)"
slug="$(printf '%s' "$query" | tr ' /' '__' | LC_ALL=C tr -cd '[:alnum:]_.-ぁ-んァ-ン一-龯')"
html_path="$out_dir/${source_site}-${slug}-${ts}.html"
meta_path="$out_dir/${source_site}-${slug}-${ts}.txt"

"$PYTHON_BIN" - "$source_site" "$query" <<'PY' > "$meta_path"
import sys, urllib.parse
site = sys.argv[1]
query = sys.argv[2]
enc = urllib.parse.quote(query)
if site == 'irasutoya':
    url = f'https://www.irasutoya.com/search?q={enc}'
elif site == 'commons':
    url = f'https://commons.wikimedia.org/w/index.php?search={enc}&title=Special:MediaSearch&type=image'
elif site == 'pixabay':
    url = f'https://pixabay.com/images/search/{enc}/'
elif site == 'pexels':
    url = f'https://www.pexels.com/search/{enc}/'
else:
    raise SystemExit(f'Unsupported source: {site}')
print(url)
PY

search_url="$(cat "$meta_path")"

echo "Search URL: $search_url"
echo "Output dir: $out_dir"

auth_ua='Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
if curl -L --fail --silent --show-error -A "$auth_ua" "$search_url" -o "$html_path"; then
  echo "Saved HTML: $html_path"
else
echo "Failed to fetch HTML for: $search_url" >&2
  exit 1
fi

echo
if [[ "$source_site" == "commons" ]]; then
  candidate_page="$("$PYTHON_BIN" - "$html_path" <<'PY'
import sys
from bs4 import BeautifulSoup
from pathlib import Path
p = Path(sys.argv[1])
soup = BeautifulSoup(p.read_text(errors='ignore'), 'html.parser')
for a in soup.select('a[href]'):
    href = a.get('href', '')
    title = (a.get('title') or '').strip()
    if '/wiki/File:' in href:
        if href.startswith('/'):
            href = 'https://commons.wikimedia.org' + href
        print(href)
        break
PY
)"
  if [[ -n "$candidate_page" ]]; then
    echo "Candidate page: $candidate_page"
    if [[ "$download_first" == "1" ]]; then
      image_url="$("$PYTHON_BIN" - "$candidate_page" <<'PY'
import sys, requests
from bs4 import BeautifulSoup
url = sys.argv[1]
r = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=20)
r.raise_for_status()
soup = BeautifulSoup(r.text, 'html.parser')
meta = soup.find('meta', property='og:image')
print(meta['content'] if meta and meta.get('content') else '')
PY
)"
      if [[ -n "$image_url" ]]; then
        ext="${image_url##*.}"
        ext="${ext%%\?*}"
        [[ -n "$ext" ]] || ext="jpg"
        image_path="$out_dir/${source_site}-${slug}-${ts}.${ext}"
        curl -L --fail --silent --show-error -A "$auth_ua" "$image_url" -o "$image_path"
        echo "Downloaded image: $image_path"
        echo "Image URL: $image_url"
      fi
    fi
  else
    echo "Candidate page: NONE"
  fi
fi

echo "Saved search page. Open it in a browser or inspect locally."
echo "If you want, paste a candidate image/page URL next, and I can help you download the actual image."
