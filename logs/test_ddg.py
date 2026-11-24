import httpx

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

print("Testing DuckDuckGo HTML POST:")
try:
    r = httpx.post("https://html.duckduckgo.com/html/", data={"q": "Prime Minister of India"}, headers=headers, timeout=10)
    print("html.duckduckgo.com:", r.status_code, "len:", len(r.text))
except Exception as e:
    print("html err:", e)

print("\nTesting DuckDuckGo Lite POST:")
try:
    r = httpx.post("https://lite.duckduckgo.com/lite/", data={"q": "Prime Minister of India"}, headers=headers, timeout=10)
    print("lite.duckduckgo.com POST:", r.status_code, "len:", len(r.text))
except Exception as e:
    print("lite err:", e)

print("\nTesting DuckDuckGo Lite GET:")
try:
    r = httpx.get("https://lite.duckduckgo.com/lite/", params={"q": "Prime Minister of India"}, headers=headers, timeout=10)
    print("lite.duckduckgo.com GET:", r.status_code, "len:", len(r.text))
except Exception as e:
    print("lite GET err:", e)
