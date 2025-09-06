import os, requests, datetime, pytz
from espn_http import get
from team_utils import team_display

WEBHOOK_URL = os.environ["WEBHOOK_URL"]
TZ = os.environ.get("TIMEZONE", "America/Denver")

def send(embed):
    requests.post(WEBHOOK_URL, json={"username":"Justice League Bot","embeds":[embed]}, timeout=20).raise_for_status()

def build_power():
    data = get("mTeam")  # Teams + records
    teams = data["teams"]

    # Some shapes use record.overall.pointsFor; keep a safe getter:
    def points_for(t):
        try:
            return float(t["record"]["overall"]["pointsFor"])
        except Exception:
            return float(t.get("points", t.get("pointsFor", 0.0)) or 0.0)

    def rec_tuple(t):
        r = t.get("record", {}).get("overall", {})
        return int(r.get("wins", 0)), int(r.get("losses", 0)), int(r.get("ties", 0))

    teams_sorted = sorted(teams, key=lambda tt: -points_for(tt))

    lines = []
    for i, t in enumerate(teams_sorted, start=1):
        name = team_display(t)
        w, l, ti = rec_tuple(t)
        pf = points_for(t)
        lines.append(f"**{i}. {name}** — PF: {pf:.1f} (Record {w}-{l}-{ti})")

    embed = {
      "title": "Power Rankings",
      "description": "\n".join(lines) if lines else "_No data yet_",
      "color": 0xFFD166,
      "footer": {"text": f"ESPN League {data.get('id','?')} • {datetime.datetime.now(pytz.timezone(TZ)).strftime('%Y-%m-%d %H:%M %Z')}"}
    }
    return embed

if __name__ == "__main__":
    send(build_power())
