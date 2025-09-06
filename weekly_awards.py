import os, requests, datetime, pytz
from espn_http import get  # uses the working headers + reads host

WEBHOOK_URL = os.environ["WEBHOOK_URL"]
TZ = os.environ.get("TIMEZONE", "America/Denver")

# Turn this False if anything looks off for your league shape
COMPUTE_OPTIMAL = True

def send(embed):
    requests.post(
        WEBHOOK_URL,
        json={"username": "Justice League Bot", "embeds": [embed]},
        timeout=20
    ).raise_for_status()

def current_week():
    data = get("mSettings")
    return data["status"]["currentMatchupPeriod"]

def name_map():
    mt = get("mTeam")
    teams = mt["teams"]
    id_to_team = {t["id"]: t for t in teams}

    def name_for(tid):
        t = id_to_team.get(tid, {})
        for a,b in [("location","nickname"), ("teamLocation","teamNickname")]:
            loc, nick = t.get(a), t.get(b)
            if loc or nick:
                return f"{(loc or '').strip()} {(nick or '').strip()}".strip()
        return t.get("name") or t.get("abbrev") or f"Team {tid}"

    return id_to_team, name_for

def safe_score(side):
    # ESPN uses a few keys; read the first available
    for k in ("totalPoints", "appliedTotal", "points"):
        v = side.get(k)
        if v is not None:
            return float(v)
    return 0.0

def safe_proj(side):
    # Use live projected first if present; fall back to static projection
    for k in ("totalProjectedPointsLive", "totalProjectedPoints", "projectedTotal"):
        v = side.get(k)
        if v is not None:
            return float(v)
    return 0.0

def collect_entries_points(side):
    """
    Returns (num_starters, actual_points, all_points_list)
    all_points_list = list of per-player points (float) for all entries (starters + bench)
    We mark starters using lineupSlotId != 20 (bench), != 21 (IR), != 23 (TAXI), etc.
    """
    entries = (((side.get("rosterForCurrentScoringPeriod") or {}).get("entries")) or [])
    pts_all = []
    starters_pts = []
    starters_count = 0
    for e in entries:
        # entry like: { "lineupSlotId": 2, "playerPoolEntry": { "appliedStatTotal": 12.3, ... } }
        slot = e.get("lineupSlotId")
        ppe = e.get("playerPoolEntry") or {}
        # ESPN sometimes nests inside an "player" object; appliedStatTotal is most consistent
        pts = ppe.get("appliedStatTotal")
        if pts is None:
            # Try other shapes (rare)
            stats = ppe.get("player", {}).get("stats", [])
            pts = 0.0
            for s in stats or []:
                if s.get("appliedTotal") is not None:
                    pts = max(pts, float(s["appliedTotal"]))
        pts = float(pts or 0.0)
        pts_all.append(pts)

        # Starter heuristic: exclude bench(20), IR(21), TAXI(23) if present
        if slot not in (20, 21, 23, None):
            starters_count += 1
            starters_pts.append(pts)

    return starters_count, sum(starters_pts), pts_all

def build_awards_embed():
    # Recap prior week
    week = max(1, current_week() - 1)
    mm = get("mMatchup")
    schedule = [s for s in mm.get("schedule", []) if s.get("matchupPeriodId") == week]
    id_to_team, name_for = name_map()

    # Gather per-team stats
    # Each element: {tid, score, proj, actual_optimal (optional), optimal (optional)}
    team_week = {}

    def ensure_team(tid):
        if tid not in team_week:
            team_week[tid] = {"tid": tid, "score": 0.0, "proj": 0.0}

    match_results = []  # (winnerId, loserId, margin)

    for s in schedule:
        h_id = s["home"]["teamId"]; a_id = s["away"]["teamId"]
        ensure_team(h_id); ensure_team(a_id)

        h_side, a_side = s["home"], s["away"]
        h_pts = safe_score(h_side); a_pts = safe_score(a_side)
        h_proj = safe_proj(h_side);  a_proj = safe_proj(a_side)

        team_week[h_id]["score"] = h_pts
        team_week[a_id]["score"] = a_pts
        team_week[h_id]["proj"]  = h_proj
        team_week[a_id]["proj"]  = a_proj

        # Winner/loser for blowout/close + all-play mappings
        if h_pts != a_pts:
            if h_pts > a_pts:
                match_results.append((h_id, a_id, h_pts - a_pts))
            else:
                match_results.append((a_id, h_id, a_pts - h_pts))

        # Optional: Best/Worst manager approximation
        if COMPUTE_OPTIMAL:
            try:
                h_starters, h_actual, h_all = collect_entries_points(h_side)
                a_starters, a_actual, a_all = collect_entries_points(a_side)

                def optimal_sum(all_pts, starters):
                    # position-agnostic: take top N points from all entries
                    # (good approximation; avoids needing per-slot constraints)
                    if starters <= 0:
                        return sum(sorted(all_pts, reverse=True)[:max(1, len(all_pts))])
                    return sum(sorted(all_pts, reverse=True)[:starters])

                if h_all:
                    h_opt = optimal_sum(h_all, h_starters)
                    team_week[h_id]["actual_lineup"] = h_actual
                    team_week[h_id]["optimal_lineup"] = h_opt
                if a_all:
                    a_opt = optimal_sum(a_all, a_starters)
                    team_week[a_id]["actual_lineup"] = a_actual
                    team_week[a_id]["optimal_lineup"] = a_opt
            except Exception:
                # If anything odd in JSON, just skip optimal calc silently
                pass

    # Early-week guard: if nobody has any points yet, post friendly note
    if not team_week or (max(t["score"] for t in team_week.values()) == 0.0 and
                         min(t["score"] for t in team_week.values()) == 0.0):
        return {
          "title": f"Trophies of the Week — Week {week}",
          "description": "_No completed matchups yet—awards will post after games conclude_",
          "color": 0x0B1F35,
          "fields": []
        }

    # === High/Low ===
    high = max(team_week.values(), key=lambda x: x["score"])
    low  = min(team_week.values(), key=lambda x: x["score"])

    # === Blowout / Close ===
    blow = max(match_results, key=lambda x: x[2]) if match_results else None
    close= min(match_results, key=lambda x: x[2]) if match_results else None

    # === Over/Underachiever (actual - projection) ===
    diffs = [(t["tid"], float(t.get("score",0.0)) - float(t.get("proj",0.0))) for t in team_week.values()]
    over  = max(diffs, key=lambda x: x[1]) if diffs else None
    under = min(diffs, key=lambda x: x[1]) if diffs else None

    # === All-play Lucky/Unlucky ===
    # Rank by score (descending). all-play wins = number of teams you outscored.
    scores = sorted([(t["tid"], t["score"]) for t in team_week.values()], key=lambda x: x[1], reverse=True)
    n = len(scores)
    tid_to_idx = {tid:i for i,(tid,_) in enumerate(scores)}
    allplay_wins = {tid: (n - 1 - tid_to_idx[tid]) for tid,_ in scores}

    # Real win/loss from match_results
    real_wins = {tid: 0 for tid in team_week}
    for w,l,_ in match_results:
        real_wins[w] = 1
        real_wins[l] = 0

    lucky_candidates   = [(tid, allplay_wins[tid]) for tid,win in real_wins.items() if win == 1]
    unlucky_candidates = [(tid, allplay_wins[tid]) for tid,win in real_wins.items() if win == 0]

    lucky   = min(lucky_candidates, key=lambda x: x[1]) if lucky_candidates else None
    unlucky = max(unlucky_candidates, key=lambda x: x[1]) if unlucky_candidates else None

    # === Best/Worst Manager (approximation) ===
    mgr_list = []
    for tid, data in team_week.items():
        actual = data.get("actual_lineup")
        optimal= data.get("optimal_lineup")
        if actual is not None and optimal and optimal > 0:
            pct = (actual / optimal) * 100.0
            bench_left = optimal - actual
            mgr_list.append((tid, pct, bench_left))

    best_mgr = max(mgr_list, key=lambda x: x[1]) if mgr_list else None
    worst_mgr= min(mgr_list, key=lambda x: x[1]) if mgr_list else None

    # === Build Embed ===
    embed = {
      "title": f"Trophies of the Week — Week {week}",
      "description": "Justice League Fantasy Football",
      "color": 0x0B1F35,
      "fields": [],
      "footer": {"text": f"Generated {datetime.datetime.now(pytz.timezone(TZ)).strftime('%Y-%m-%d %H:%M %Z')}"}
    }

    # High/Low
    embed["fields"].append({"name":"👑 High score 👑", "value": f"{name_for(high['tid'])} with {high['score']:.2f} points", "inline": False})
    embed["fields"].append({"name":"💩 Low score 💩",  "value": f"{name_for(low['tid'])} with {low['score']:.2f} points",  "inline": False})

    # Blowout/Close
    if blow:
        embed["fields"].append({"name":"😱 Blow out 😱", "value": f"{name_for(blow[0])} blew out {name_for(blow[1])} by {blow[2]:.2f} points", "inline": False})
    if close:
        embed["fields"].append({"name":"😅 Close win 😅", "value": f"{name_for(close[0])} barely beat {name_for(close[1])} by {close[2]:.2f} points", "inline": False})

    # Lucky/Unlucky
    if lucky:
        lw = allplay_wins[lucky[0]]
        embed["fields"].append({"name":"🍀 Lucky 🍀", "value": f"{name_for(lucky[0])} was {lw}-{(n-1-lw)} in all-play but still got the W", "inline": False})
    if unlucky:
        uw = allplay_wins[unlucky[0]]
        embed["fields"].append({"name":"😡 Unlucky 😡", "value": f"{name_for(unlucky[0])} was {uw}-{(n-1-uw)} in all-play but still took the L", "inline": False})

    # Over/Under
    if over:
        embed["fields"].append({"name":"📈 Overachiever 📈", "value": f"{name_for(over[0])} was {over[1]:.2f} points over projection", "inline": False})
    if under:
        embed["fields"].append({"name":"📉 Underachiever 📉", "value": f"{name_for(under[0])} was {under[1]:.2f} points under projection", "inline": False})

    # Best/Worst Manager
    if best_mgr:
        pct = min(100.0, best_mgr[1])
        embed["fields"].append({"name":"🤖 Best Manager 🤖", "value": f"{name_for(best_mgr[0])} scored {pct:.2f}% of optimal", "inline": False})
    if worst_mgr:
        embed["fields"].append({"name":"🤡 Worst Manager 🤡", "value": f"{name_for(worst_mgr[0])} left {worst_mgr[2]:.2f} points on the bench", "inline": False})

    return embed

if __name__ == "__main__":
    embed = build_awards_embed()
    send(embed)
    print("Posted to Discord:", embed.get("title"))
