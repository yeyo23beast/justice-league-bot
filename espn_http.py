import os, requests

def _ctx():
    lid  = os.environ["LEAGUE_ID"]
    year = os.environ["SEASON_ID"]
    return {
        "lid": lid,
        "year": year,
        "cookies": {"espn_s2": os.environ["ESPN_S2"], "SWID": os.environ["SWID"]},
        "headers": {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": f"https://fantasy.espn.com/football/league?leagueId={lid}&seasonId={year}",
            "X-Fantasy-Platform": "kona",
            "X-Fantasy-Source": "kona",
        },
        "bases": [
            f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{lid}",
            f"https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{lid}",
        ],
    }

def get(view: str, params: dict | None = None):
    c = _ctx()
    q = {"view": view}
    if params:
        q.update(params)
    for base in c["bases"]:
        r = requests.get(base, headers=c["headers"], cookies=c["cookies"], params=q, timeout=20)
        if r.status_code == 200 and "application/json" in r.headers.get("content-type","").lower():
            return r.json()
    raise RuntimeError(f"ESPN returned non-JSON or non-200 for all endpoints (view={view}, params={params})")
