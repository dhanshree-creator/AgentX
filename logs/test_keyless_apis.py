import httpx, json

headers = {"User-Agent": "AgentX/1.0 (terminal agent; contact: local)"}

print("=== Testing DuckDuckGo Instant Answer API ===")
try:
    r = httpx.get("https://api.duckduckgo.com/", params={"q": "Prime Minister of India", "format": "json", "no_html": "1"}, headers=headers, timeout=5)
    print("DDG API status:", r.status_code)
    data = r.json()
    print("Abstract:", data.get("AbstractText")[:150] if data.get("AbstractText") else "None")
    print("AbstractURL:", data.get("AbstractURL"))
    topics = data.get("RelatedTopics", [])
    print(f"RelatedTopics: {len(topics)}")
    for t in topics[:3]:
        if "Text" in t:
            print(" -", t.get("Text")[:80], "->", t.get("FirstURL"))
except Exception as e:
    print("DDG API err:", e)

print("\n=== Testing Wikipedia Search API ===")
try:
    r = httpx.get("https://en.wikipedia.org/w/api.php", params={
        "action": "query",
        "list": "search",
        "srsearch": "Prime Minister of India",
        "format": "json",
        "srlimit": 5
    }, headers=headers, timeout=5)
    print("Wikipedia API status:", r.status_code)
    wdata = r.json()
    wresults = wdata.get("query", {}).get("search", [])
    print(f"Wikipedia results: {len(wresults)}")
    for item in wresults:
        import html, re
        title = item.get("title")
        snippet = html.unescape(re.sub(r'<[^>]+>', '', item.get("snippet", "")))
        page_id = item.get("pageid")
        url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        print(f" - {title}: {snippet[:100]}... ({url})")
except Exception as e:
    print("Wikipedia err:", e)
