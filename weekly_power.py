import os, requests, datetime, pytz
from espn_client import get_league

WEBHOOK_URL = os.environ["WEBHOOK_URL"]
TZ = os.environ.get("TIMEZONE", "America/Denver")

def send(embed):
    requests.post(WEBHOOK_URL, json={"username":"Justice League Bot","embeds":[embed]}, timeout=20).raise_for_status()

def build_power():
    league = get_league()
    teams = sorted(league.teams, key=lambda t: -t.points_for)
    lines = []
    for i,t in enumerate(teams, start=1):
        lines.append(f"**{i}. {t.team_name}** — PF: {t.points_for:.1f} (Record {t.wins}-{t.losses}-{t.ties})")
    embed = {
      "title": "Power Rankings",
      "description": "\n".join(lines),
      "color": 0xFFD166,
      "footer": {"text": f"ESPN League {league.league_id} • {datetime.datetime.now(pytz.timezone(TZ)).strftime('%Y-%m-%d %H:%M %Z')}"}
    }
    return embed

if __name__ == "__main__":
    send(build_power())
