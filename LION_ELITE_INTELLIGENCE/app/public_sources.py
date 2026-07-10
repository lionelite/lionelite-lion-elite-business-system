import os
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


ALLOWED_SOURCE_DOMAINS = {
    domain.strip().lower()
    for domain in os.getenv("ALLOWED_SOURCE_DOMAINS", "").split(",")
    if domain.strip()
}


def is_allowed_source(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return bool(hostname) and any(hostname == domain or hostname.endswith(f".{domain}") for domain in ALLOWED_SOURCE_DOMAINS)


def fetch_public_business_page(url: str) -> dict:
    if not is_allowed_source(url):
        raise ValueError("Source domain is not in ALLOWED_SOURCE_DOMAINS")

    headers = {"User-Agent": os.getenv("PUBLIC_SOURCE_USER_AGENT", "LionEliteIntelligence/1.0")}
    with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = " ".join(soup.get_text(" ", strip=True).split())[:12000]
    emails = sorted({a.get("href", "")[7:] for a in soup.select('a[href^="mailto:"]') if a.get("href")})
    phones = sorted({a.get("href", "")[4:] for a in soup.select('a[href^="tel:"]') if a.get("href")})

    return {
        "source_url": str(response.url),
        "title": title,
        "text": text,
        "public_emails": emails,
        "public_phones": phones,
    }
