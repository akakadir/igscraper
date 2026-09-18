import html
import re
import time
from pathlib import Path

from flask import Flask, jsonify, request
import httpx

app = Flask(__name__)
app.json.ensure_ascii = False


BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

CRAWLER_HEADERS = {
    "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def get_httpx(url, headers):
    response = httpx.get(
        url,
        headers=headers,
        timeout=20,
        follow_redirects=True,
    )
    return response.status_code, response.text


def get_curl_cffi(url):
    from curl_cffi import requests as cffi

    response = cffi.get(
        url,
        impersonate="chrome",
        headers={
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"
        },
        timeout=20,
    )
    return response.status_code, response.text


def fetch_html(username):
    url = f"https://www.instagram.com/{username}/"
    path = Path(f"{username}.html")

    strategies = [
        ("curl_cffi chrome", lambda: get_curl_cffi(url)),
        ("httpx tarayici basliklari", lambda: get_httpx(url, BROWSER_HEADERS)),
        ("httpx onizleme botu", lambda: get_httpx(url, CRAWLER_HEADERS)),
    ]

    text = ""

    for name, strategy in strategies:
        try:
            status, text = strategy()
        except ImportError:
            continue
        except Exception:
            continue

        found = 'property="og:title"' in text

        if found:
            break

        time.sleep(3)

    path.write_text(text, encoding="utf-8")
    return path


def parse_meta(page):
    result = {}

    for tag in re.findall(r"<meta\s[^>]*>", page):
        key = re.search(
            r'(?:property|name)="([^"]+)"',
            tag
        )

        value = re.search(
            r'content="([^"]*)"',
            tag
        )

        if key and value:
            result[key.group(1)] = html.unescape(
                value.group(1)
            )

    return result


def parse_html(path, username):
    page = path.read_text(encoding="utf-8")
    meta = parse_meta(page)

    description = meta.get("description") or ""
    title = meta.get("og:title") or ""

    bio_match = re.search(
        r':\s*"(.*)"\s*$',
        description,
        re.DOTALL
    )

    counts_match = re.match(
        r"\s*([^\s,]+)\s+[^,]+,\s*([^\s,]+)\s+[^,]+,\s*([^\s,]+)\s+",
        description
    )

    name_match = re.match(
        r"(.*?)\s*\(@",
        title
    )

    return {
        "username": username,
        "full_name": name_match.group(1) if name_match else None,
        "bio": bio_match.group(1) if bio_match else None,
        "followers": counts_match.group(1) if counts_match else None,
        "following": counts_match.group(2) if counts_match else None,
        "posts": counts_match.group(3) if counts_match else None,
        "profile_pic": meta.get("og:image"),
    }


@app.get("/")
def home():
    return jsonify({
        "status": "ok",
        "service": "igscraper"
    })


@app.get("/api/scraper")
def scraper():
    usernames = request.args.getlist("username")

    cleaned_usernames = []

    for value in usernames:
        for username in value.split(","):
            username = username.strip().lstrip("@")

            if username and username not in cleaned_usernames:
                cleaned_usernames.append(username)

    if not cleaned_usernames:
        return jsonify({
            "error": "username parametresi gerekli."
        }), 400

    results = []

    for username in cleaned_usernames:
        path = None

        try:
            path = fetch_html(username)
            profile = parse_html(path, username)
            results.append(profile)

        except Exception as e:
            results.append({
                "username": username,
                "error": str(e)
            })

        finally:
            if path is not None and path.exists():
                path.unlink()

    return jsonify({
        "users": results
    })
