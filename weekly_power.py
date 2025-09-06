import os, requests, datetime, pytz
from espn_http import get

WEBHOOK_URL = os.environ["WEBHOOK_URL"]
TZ = os.environ.get("TIMEZONE", "America/Denver")

def send(embed):
    requests.post(WEBHOOK_URL, json={"username":"Justice League Bot","embeds":[embed]}, timeout=20).raise_for_status()

def build_power():
    data = get("mTeam")
    teams = data["teams"]
    teams_sorted = sorted(teams, key=lambda t: -t["record"]["overall"]["pointsFor"])
    lines = []
    for i, t in enumerate(teams_sorted, start=1):
        name = f"{t['location']} {t['nickname']}"
        rec  = t["record"]["overall"]
        pf   = rec["pointsFor"]
        w,l,ties = rec["wins"], rec["losses"], rec.get("ties", 0)
        lines.append(f"**{i}. {name}** — PF: {pf:.1f} (Record {w}-{l}-{ties})")
    embed = {
      "title": "Power Rankings",
      "description": "\n".join(lines),
      "color": 0xFFD166,
      "footer": {"text": f"ESPN League {data['id']} • {datetime.datetime.now(pytz.timezone(TZ)).strftime('%Y-%m-%d %H:%M %Z')}"}
    }
    return embed

if __name__ == "__main__":
    send(build_power())
