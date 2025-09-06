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

def build_awards_embed():
    # Recap prior week (use week-1, but don’t go below 1)
    week = max(1, current_week() - 1)

    # Pull schedule/scores
    mm = get("mMatchup")
    schedule = [s for s in mm.get("schedule", []) if s.get("matchupPeriodId") == week]

    # Build team name map from mTeam
    mt = get("mTeam")
    team_map = {t["id"]: t for t in mt["teams"]}

    def name_for(tid):
        t = team_map.get(tid, {})
        for a,b in [("location","nickname"), ("teamLocation","teamNickname")]:
            loc, nick = t.get(a), t.get(b)
            if loc or nick:
                return f"{(loc or '').strip()} {(nick or '').strip()}".strip()
        return t.get("name") or t.get("abbrev") or f"Team {tid}"

    scores = []        # (teamId, pts)
    results = []       # (winnerId, loserId, margin)

    for s in schedule:
        h_id = s["home"]["teamId"]; a_id = s["away"]["teamId"]
        h_pts = float(s["home"].get("totalPoints", 0) or 0.0)
        a_pts = float(s["away"].get("totalPoints", 0) or 0.0)
        scores.append((h_id, h_pts)); scores.append((a_id, a_pts))
        if h_pts != a_pts:
            if h_pts > a_pts: results.append((h_id, a_id, h_pts - a_pts))
            else:             results.append((a_id, h_id, a_pts - h_pts))

    # If nothing scored yet (early in week / preseason), post a friendly note instead of fake trophies
    if not scores or (max(p for _,p in scores) == 0 and min(p for _,p in scores) == 0):
        return {
          "title": f"Trophies of the Week — Week {week}",
          "description": "_No completed matchups yet—awards will post after games conclude_",
          "color": 0x0B1F35,
          "fields": []
        }

    high = max(scores, key=lambda x: x[1]) if scores else None
    low  = min(scores, key=lambda x: x[1]) if scores else None
    blow = max(results, key=lambda x: x[2]) if results else None
    close= min(results, key=lambda x: x[2]) if results else None

    embed = {
      "title": f"Trophies of the Week — Week {week}",
      "description": "Justice League Fantasy Football",
      "color": 0x0B1F35,
      "fields": [],
      "footer": {"text": f"Generated {datetime.datetime.now(pytz.timezone(TZ)).strftime('%Y-%m-%d %H:%M %Z')}"}
    }

    if high:
        embed["fields"].append({"name":"👑 High score 👑", "value": f"{name_for(high[0])} with {high[1]:.2f} points", "inline": False})
    if low:
        embed["fields"].append({"name":"💩 Low score 💩",  "value": f"{name_for(low[0])} with {low[1]:.2f} points", "inline": False})
    if blow:
        embed["fields"].append({"name":"😱 Blow out 😱",   "value": f"{name_for(blow[0])} blew out {name_for(blow[1])} by {blow[2]:.2f} points", "inline": False})
    if close:
        embed["fields"].append({"name":"😅 Close win 😅",  "value": f"{name_for(close[0])} barely beat {name_for(close[1])} by {close[2]:.2f} points", "inline": False})

    return embed
