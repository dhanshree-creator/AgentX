import sys
sys.path.insert(0, '.')
import asyncio, html, re, urllib.parse
import httpx
from html import unescape
from safety.ssrf import assert_public_url
from agent.exceptions import ToolExecutionError

async def multi_search(query: str, limit: int = 5) -> list[dict[str, str]]:
    results = []

    # Strategy 1: DuckDuckGo Lite
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": query},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": "https://lite.duckduckgo.com/",
                }
            )
            if resp.status_code == 200:
                link_pattern = re.compile(r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]+class=['\"]result-link['\"][^>]*>(.*?)</a>", re.DOTALL)
                snippet_pattern = re.compile(r"<td[^>]+class=['\"]result-snippet['\"][^>]*>(.*?)</td>", re.DOTALL)
                links = link_pattern.findall(resp.text)
                snippets = snippet_pattern.findall(resp.text)

                for (href, title_raw), snip_raw in zip(links, snippets):
                    title = unescape(re.sub(r"<[^>]+>", "", title_raw)).strip()
                    snippet = unescape(re.sub(r"<[^>]+>", "", snip_raw)).strip()
                    actual_url = href
                    if "uddg=" in href:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        if "uddg" in parsed:
                            actual_url = parsed["uddg"][0]
                    try:
                        assert_public_url(actual_url)
                    except Exception:
                        continue
                    results.append({"title": title[:200], "url": actual_url, "snippet": snippet[:500]})
                    if len(results) >= limit:
                        break
    except Exception as e:
        print("DDG Lite failed:", e)

    if results:
        return results

    # Strategy 2: Wikipedia Search API (bulletproof encyclopedic fallback)
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "srlimit": limit,
                },
                headers={"User-Agent": "AgentXBot/1.0 (https://example.org/agentx; agentx@example.org)"}
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("query", {}).get("search", [])
                for it in items:
                    t = it.get("title", "").strip()
                    s = unescape(re.sub(r"<[^>]+>", "", it.get("snippet", ""))).strip()
                    u = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(t.replace(' ', '_'))}"
                    results.append({"title": t[:200], "url": u, "snippet": s[:500]})
                    if len(results) >= limit:
                        break
    except Exception as e:
        print("Wikipedia API failed:", e)

    return results

res = asyncio.run(multi_search("Prime Minister of India", 5))
print("Results:", len(res))
for r in res:
    print(r["title"], "->", r["url"])
