import os, requests

year = os.environ["SEASON_ID"]
lid  = os.environ["LEAGUE_ID"]
s2   = os.environ["ESPN_S2"]
swid = os.environ["SWID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": f"https://fantasy.espn.com/football/league?leagueId={lid}&seasonId={year}",
    "Accept": "application/json",
    "X-Fantasy-Platform": "kona",
    "X-Fantasy-Source": "kona",
}
COOKIES = {"espn_s2": s2, "SWID": swid}

BASES = [
    f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{lid}",
    f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{lid}",
]
VIEWS = ["mTeam", "mMatchup", "mSettings"]

def try_url(url):
    r = requests.get(url, headers=HEADERS, cookies=COOKIES, timeout=20, allow_redirects=True)
    ctype = r.headers.get("content-type","")
    print(f"GET {url} -> {r.status_code} | content-type: {ctype} | final: {r.url} | redirects: {[h.status_code for h in r.history]}")
    if r.status_code == 200 and "application/json" in ctype.lower():
        print("JSON OK (first 200 chars):", (r.text[:200].replace("\n"," ")) )
        return True
    else:
        # Show a small HTML snippet for diagnosis
        print("Body peek (first 200):", r.text[:200].replace("\n"," "))
        return False

ok = False
for base in BASES:
    for view in VIEWS:
        if try_url(f"{base}?view={view}"):
            ok = True
            break
    if ok: break

if not ok:
    raise SystemExit("No JSON 200 from any endpoint/view. Check headers/cookies/season/league.")
