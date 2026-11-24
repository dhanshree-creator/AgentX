import httpx, re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
}

for i in range(5):
    r = httpx.post("https://html.duckduckgo.com/html/", data={"q": f"who is the prime minister of india {i}"}, headers=headers, timeout=10)
    print(f"Request {i}: status={r.status_code}")
    if r.status_code == 202:
        with open("logs/202_body.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        print("Wrote 202 body! Lines:")
        for line in r.text.splitlines():
            if any(k in line.lower() for k in ["form", "action", "captcha", "challenge", "bot", "error", "title", "result", "h2", "snippet"]):
                print("  ", line.strip()[:120])
        break
