import httpx, re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
}

for i in range(10):
    r = httpx.post("https://html.duckduckgo.com/html/", data={"q": f"test query {i}"}, headers=headers, timeout=10)
    print(f"Request {i}: status={r.status_code}, len={len(r.text)}")
    if r.status_code == 202:
        print("202 BODY PREVIEW:")
        print(r.text[:500])
        break
