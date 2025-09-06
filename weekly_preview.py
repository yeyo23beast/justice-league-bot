import os, requests, datetime, pytz
from espn_http import get
from team_utils import team_display

WEBHOOK_URL = os.environ["WEBHOOK_URL"]
TZ = os.environ.get("TIMEZONE", "America/Denver")

def send(embed):
    requests.post(WEBHOOK_URL, json={"username":"Justice League Bot","embeds":[embed]}, timeout=20).raise_for_status()

def current_week():
    data = get("mSettings")
    return data["status"]["currentMatchupPeriod"]

def build_preview():
    week = current_week()
    data = get("mMatchup")
    schedule = [s for s in data.get("schedule", []) if s.get("matchupPeriodId") == week]
    teams = {t["id"]: t for t in data["teams"]}

    embed = {
      "title": f"Week {week} Matchup Preview",
      "description": "Justice League Fantasy Football",
      "color": 0x1F8B4C,
      "fields": [],
      "footer": {"text": f"Generated {datetime.datetime.now(pytz.timezone(TZ)).strftime('%Y-%m-%d %H:%M %Z')}"}
    }

    for s in schedule:
        home = teams.get(s["home"]["teamId"], {})
        away = teams.get(s["away"]["teamId"], {})
        home_name = team_display(home)
        away_name = team_display(away)
        embed["fields"].append({"name":"\u200b","value":f"**{home_name}** vs **{away_name}**", "inline": False})

    if not embed["fields"]:
        embed["description"] = "_No scheduled matchups found for this week yet_"

    return embed

if __name__ == "__main__":
    send(build_preview())
