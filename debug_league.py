import os, requests

year = os.environ["SEASON_ID"]
lid  = os.environ["LEAGUE_ID"]
s2   = os.environ["ESPN_S2"]
swid = os.environ["SWID"]

headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": f"https://fantasy.espn.com/football/league?leagueId={lid}&seasonId={year}",
    "x-fantasy-platform": "kona",
    "x-fantasy-source": "kona"
}
cookies = {"espn_s2": s2, "SWID": swid}

urls = [
    f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{lid}?view=mTeam",
    f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{lid}?view=mTeam",
    f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{lid}?view=mMatchup",
    f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{lid}?view=mMatchup"
]

for url in urls:
    r = requests.get(url, headers=headers, cookies=cookies, timeout=20)
    print("GET", url, "->", r.status_code)
    if r.status_code == 200:
        print("OK (first 200 chars):", r.text[:200])
        break

