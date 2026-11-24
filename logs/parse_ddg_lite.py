import httpx, re, urllib.parse
from html import unescape

def search_ddg_lite(query: str, limit: int = 5):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://lite.duckduckgo.com/",
    }
    r = httpx.post("https://lite.duckduckgo.com/lite/", data={"q": query}, headers=headers, timeout=10)
    print("Status:", r.status_code)
    if r.status_code != 200:
        return []

    # Match either order of href and class
    link_pattern = re.compile(r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]+class=['\"]result-link['\"][^>]*>(.*?)</a>", re.DOTALL)
    snippet_pattern = re.compile(r"<td[^>]+class=['\"]result-snippet['\"][^>]*>(.*?)</td>", re.DOTALL)

    links = link_pattern.findall(r.text)
    snippets = snippet_pattern.findall(r.text)

    results = []
    for (href, title_raw), snip_raw in zip(links, snippets):
        title = unescape(re.sub(r"<[^>]+>", "", title_raw)).strip()
        snippet = unescape(re.sub(r"<[^>]+>", "", snip_raw)).strip()
        actual_url = href
        if "uddg=" in href:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            if "uddg" in parsed:
                actual_url = parsed["uddg"][0]
        results.append({"title": title, "url": actual_url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results

res = search_ddg_lite("Prime Minister of India", 5)
print(f"Extracted {len(res)} results:")
for i, r in enumerate(res, 1):
    print(f"{i}. {r['title']}")
    print(f"   URL: {r['url']}")
    print(f"   Snippet: {r['snippet'][:100]}...")
