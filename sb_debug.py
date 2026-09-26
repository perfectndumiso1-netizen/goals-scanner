import requests, json, time, sys
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
Q = "factsCenter/pcUpcomingEvents?sportId=sr%3Asport%3A1&marketId=1&pageSize=2&pageNum=1&option=1"
def show(tag, r):
    body = r.text
    print(f"\n=== {tag}: HTTP {r.status_code} len={len(body)} http={r.raw.version if hasattr(r.raw,'version') else '?'}")
    for k in ("server", "x-cache", "via", "content-type", "set-cookie", "x-amzn-waf-action", "request-country", "current-country"):
        if k in r.headers: print(f"  {k}: {r.headers[k][:160]}")
    print("  body:", body[:600].replace("\n", " "))
    try:
        d = r.json(); print("  JSON bizCode", d.get("bizCode"), "totalNum", d.get("data", {}).get("totalNum"))
    except Exception: pass
    sys.stdout.flush()

# 1 plain
r = requests.get("https://www.sportybet.com/api/za/" + Q, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30); show("plain za", r)
# 2 full browser headers
full = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-ZA,en;q=0.9", "Referer": "https://www.sportybet.com/za/sport/football",
        "Origin": "https://www.sportybet.com", "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
        "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"', "sec-fetch-dest": "empty", "sec-fetch-mode": "cors", "sec-fetch-site": "same-origin",
        "clientid": "web", "platform": "web", "operid": "2"}
r = requests.get("https://www.sportybet.com/api/za/" + Q, headers=full, timeout=30); show("full headers za", r)
# 3 session with homepage first
s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "en-ZA,en;q=0.9"})
h = s.get("https://www.sportybet.com/za/", timeout=30); show("homepage za", h)
r = s.get("https://www.sportybet.com/api/za/" + Q, headers={"Accept": "application/json", "Referer": "https://www.sportybet.com/za/"}, timeout=30); show("session za after homepage", r)
# 4 other countries
for cc in ("ng", "gh", "ke", "ug", "tz", "zm"):
    r = requests.get(f"https://www.sportybet.com/api/{cc}/" + Q, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30); show(f"plain {cc}", r)
# 5 wap endpoint + event endpoint
r = requests.get("https://www.sportybet.com/api/za/factsCenter/wapUpcomingEvents?sportId=sr%3Asport%3A1&marketId=1&pageSize=2&pageNum=1&option=1", headers={"User-Agent": UA}, timeout=30); show("wap za", r)
# 6 curl http2
import subprocess
out = subprocess.run(["curl", "-s", "--http2", "-D", "-", "-o", "/tmp/c.txt", "-A", UA, "https://www.sportybet.com/api/za/" + Q], capture_output=True, text=True)
print("\n=== curl http2 headers:\n", out.stdout[:800]); print("body:", open("/tmp/c.txt").read()[:300])
# 7 retry loop
for i in range(3):
    time.sleep(3)
    r = requests.get("https://www.sportybet.com/api/za/" + Q, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30); print("retry", i, r.status_code)
