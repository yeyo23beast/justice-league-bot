import os, requests, datetime, pytz
from espn_http import get

WEBHOOK_URL = os.environ["WEBHOOK_URL"]
TZ = os.environ.get("TIMEZONE", "America/Denver")

def send(embed):
    requests.post(WEBHOOK_URL, json={"username":"Justice League Bot","embeds":[embed]}, timeout=20).raise_for_status()

def current_week():
    data = get("mSettings")
    return data["status"]["currentMatchupPeriod"]

def team_name(team):
    return f"{team['location']} {team['nickname']}"

def build_awards_embed():
    week = max(1, current_week() - 1)
    data = get("mMatchup")
    teams = {t["id"]: t for t in data["teams"]}
    schedule = [s for s in data.get("schedule", []) if s.get("matchupPeriodId") == week]

    scores = []              # (teamId, pts)
    match_results = []       # (winnerId, loserId, margin)
    for s in schedule:
        h_id = s["home"]["teamId"]; a_id = s["away"]["teamId"]
        h_pts = float(s["home"].get("totalPoints", 0) or 0.0)
        a_pts = float(s["away"].get("totalPoints", 0) or 0.0)
        scores.append((h_id, h_pts)); scores.append((a_id, a_pts))
        if h_pts != a_pts:
            if h_pts > a_pts:
                match_results.append((h_id, a_id, h_pts - a_pts))
            else:
                match_results.append((a_id, h_id, a_pts - h_pts))

    high = max(scores, key=lambda x: x[1]) if scores else None
    low  = min(scores, key=lambda x: x[1]) if scores else None
    blow = max(match_results, key=lambda x: x[2]) if match_results else None
    close= min(match_results, key=lambda x: x[2]) if match_results else None

    embed = {
      "title": f"Trophies of the Week — Week {week}",
      "description": "Justice League Fantasy Football",
      "color": 0x0B1F35,
      "fields": [],
      "footer": {"text": f"Generated {datetime.datetime.now(pytz.timezone(TZ)).strftime('%Y-%m-%d %H:%M %Z')}"}
    }
    if high:  embed["fields"].append({"name":"👑 High score 👑", "value": f"{team_name(teams[high[0]])} with {high[1]:.2f} points", "inline": False})
    if low:   embed["fields"].append({"name":"💩 Low score 💩",  "value": f"{team_name(teams[low[0]])} with {low[1]:.2f} points", "inline": False})
    if blow:  embed["fields"].append({"name":"😱 Blow out 😱",   "value": f"{team_name(teams[blow[0]])} blew out {team_name(teams[blow[1]])} by {blow[2]:.2f} points", "inline": False})
    if close: embed["fields"].append({"name":"😅 Close win 😅",  "value": f"{team_name(teams[close[0]])} barely beat {team_name(teams[close[1]])} by {close[2]:.2f} points", "inline": False})
    return embed

if __name__ == "__main__":
    send(build_awards_embed())
