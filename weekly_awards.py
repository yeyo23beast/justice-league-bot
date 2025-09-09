import os, requests, datetime, pytz
from espn_http import get  # uses the working headers + reads host

WEBHOOK_URL = os.environ["WEBHOOK_URL"]
TZ = os.environ.get("TIMEZONE", "America/Denver")

# Turn this False if anything looks off for your league shape
COMPUTE_OPTIMAL = True
DEBUG_PROJ = False  # set True to log projection-source info to Actions

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
    for k in ("totalPoints", "appliedTotal", "points"):
        v = side.get(k)
        if v is not None:
            return float(v)
    return 0.0

def safe_proj(side):
    for k in ("totalProjectedPointsLive", "totalProjectedPoints", "projectedTotal"):
        v = side.get(k)
        if v is not None:
            return float(v)
    return 0.0

def _ppe_player_id(ppe: dict) -> int | None:
    """Be liberal in how we pull a player id from playerPoolEntry."""
    if not ppe:
        return None
    # Common locations for the id:
    return (
        ppe.get("id") or
        ppe.get("playerId") or
        (ppe.get("player") or {}).get("id")
    )

def _sum_proj_from_entry_list(entry_list, week):
    """Return (found_any, sum) of starter projections from an entry list if stats are already attached."""
    total = 0.0
    found_any = False
    for e in entry_list:
        slot = e.get("lineupSlotId")
        if slot in (20, 21, 23, None):  # bench/IR/taxi
            continue
        ppe = e.get("playerPoolEntry") or {}
        stats = (ppe.get("player", {}) or {}).get("stats", []) or []
        for s in stats:
            if (s.get("scoringPeriodId") == week and s.get("statSourceId") == 1 and s.get("statSplitTypeId") == 1):
                total += float(s.get("appliedTotal") or 0.0)
                found_any = True
                break
    return found_any, total

def projected_points_from_entries(side, week):
    """
    Sum projected points for starters for the given week.
    1) Try projections already present on matchup roster entries
    2) If none, fetch mRoster?scoringPeriodId=week and sum projections there
    """
    entries = (((side.get("rosterForCurrentScoringPeriod") or {}).get("entries")) or [])

    # (1) Try from entries on the matchup payload
    found_any, total = _sum_proj_from_entry_list(entries, week)
    if found_any:
        if DEBUG_PROJ:
            print(f"[proj] used entries for week={week}: total={total:.2f}")
        return total

    # (2) Fallback: fetch mRoster for that week, build playerId->proj, sum starters
    roster = get("mRoster", params={"scoringPeriodId": week})
    proj_by_player = {}
    for team in roster.get("teams", []):
        for e in ((team.get("roster") or {}).get("entries") or []):
            ppe = e.get("playerPoolEntry") or {}
            pid = _ppe_player_id(ppe)
            p = ppe.get("player") or {}
            stats = p.get("stats", []) or []
            proj = 0.0
            for s in stats:
                # statSourceId==1 → projected | statSplitTypeId==1 → total
                if (s.get("scoringPeriodId") == week and s.get("statSourceId") == 1 and s.get("statSplitTypeId") == 1):
                    proj = float(s.get("appliedTotal") or 0.0)
                    break
            if pid is not None:
                proj_by_player[pid] = proj

    total = 0.0
    starters_count = 0
    matched = 0
    for e in entries:
        slot = e.get("lineupSlotId")
        if slot in (20, 21, 23, None):   # bench/IR/taxi
            continue
        starters_count += 1
        ppe = e.get("playerPoolEntry") or {}
        pid = _ppe_player_id(ppe)
        if pid is not None:
            total += float(proj_by_player.get(pid, 0.0))
            if pid in proj_by_player:
                matched += 1

    if DEBUG_PROJ:
        print(f"[proj] used mRoster fallback week={week}: starters={starters_count} matched={matched} total={total:.2f}")

    return total

def collect_entries_points(side):
    """
    Returns (num_starters, actual_points, all_points_list)
    all_points_list = list of per-player points (float) for all entries (starters + bench)
    """
    entries = (((side.get("rosterForCurrentScoringPeriod") or {}).get("entries")) or [])
    pts_all = []
    starters_pts = []
    starters_count = 0
    for e in entries:
        slot = e.get("lineupSlotId")
        ppe = e.get("playerPoolEntry") or {}
        pts = ppe.get("appliedStatTotal")
        if pts is None:
            stats = ppe.get("player", {}).get("stats", [])
            pts = 0.0
            for s in stats or []:
                if s.get("appliedTotal") is not None:
                    pts = max(pts, float(s["appliedTotal"]))
        pts = float(pts or 0.0)
        pts_all.append(pts)

        if slot not in (20, 21, 23, None):
            starters_count += 1
            starters_pts.append(pts)

    return starters_count, sum(starters_pts), pts_all

def build_awards_embed():
    # Recap *prior* week
    week = max(1, current_week() - 1)
    mm = get("mMatchup")
    schedule = [s for s in mm.get("schedule", []) if s.get("matchupPeriodId") == week]
    id_to_team, name_for = name_map()

    team_week = {}     # tid -> {score, proj, actual_lineup?, optimal_lineup?}
    match_results = [] # (winnerId, loserId, margin)

    def ensure_team(tid):
        if tid not in team_week:
            team_week[tid] = {"tid": tid, "score": 0.0, "proj": 0.0}

    for s in schedule:
        h_id = s["home"]["teamId"]; a_id = s["away"]["teamId"]
        ensure_team(h_id); ensure_team(a_id)

        h_side, a_side = s["home"], s["away"]
        h_pts = safe_score(h_side); a_pts = safe_score(a_side)
        h_proj = safe_proj(h_side);  a_proj = safe_proj(a_side)

        # Fallback to player-sum projections if side-level is zero
        if h_proj == 0:
            h_proj = projected_points_from_entries(h_side, week)
        if a_proj == 0:
            a_proj = projected_points_from_entries(a_side, week)

        team_week[h_id]["score"] = h_pts
        team_week[a_id]["score"] = a_pts
        team_week[h_id]["proj"]  = h_proj
        team_week[a_id]["proj"]  = a_proj

        if h_pts != a_pts:
            if h_pts > a_pts:
                match_results.append((h_id, a_id, h_pts - a_pts))
            else:
                match_results.append((a_id, h_id, a_pts - h_pts))

        if COMPUTE_OPTIMAL:
            try:
                h_starters, h_actual, h_all = collect_entries_points(h_side)
                a_starters, a_actual, a_all = collect_entries_points(a_side)

                def optimal_sum(all_pts, starters):
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
                pass

    # If nothing scored (preseason / very early), bail politely
    if not team_week or (max(t["score"] for t in team_week.values()) == 0.0 and
                         min(t["score"] for t in team_week.values()) == 0.0):
        return {
          "title": f"Trophies of the Week — Week {week}",
          "description": "_No completed matchups yet—awards will post after games conclude_",
          "color": 0x0B1F35,
          "fields": []
        }

    # High/Low
    high = max(team_week.values(), key=lambda x: x["score"])
    low  = min(team_week.values(), key=lambda x: x["score"])

    # Blowout/Close
    blow = max(match_results, key=lambda x: x[2]) if match_results else None
    close= min(match_results, key=lambda x: x[2]) if match_results else None

    # Over/Under (actual - projection) and keep actual/proj for display
    diffs = [(t["tid"],
              float(t.get("score",0.0)) - float(t.get("proj",0.0)),
              float(t.get("score",0.0)),
              float(t.get("proj",0.0)))
             for t in team_week.values()]
    over  = max(diffs, key=lambda x: x[1]) if diffs else None
    under = min(diffs, key=lambda x: x[1]) if diffs else None

    # All-play Lucky/Unlucky
    scores = sorted([(t["tid"], t["score"]) for t in team_week.values()],
                    key=lambda x: x[1], reverse=True)
    n = len(scores)
    tid_to_idx = {tid: i for i,(tid,_) in enumerate(scores)}
    allplay_wins = {tid: (n - 1 - tid_to_idx[tid]) for tid,_ in scores}

    real_wins = {tid: 0 for tid in team_week}
    for w,l,_ in match_results:
        real_wins[w] = 1
        real_wins[l] = 0

    lucky_candidates   = [(tid, allplay_wins[tid]) for tid,win in real_wins.items() if win == 1]
    unlucky_candidates = [(tid, allplay_wins[tid]) for tid,win in real_wins.items() if win == 0]

    lucky   = min(lucky_candidates, key=lambda x: x[1]) if lucky_candidates else None
    unlucky = max(unlucky_candidates, key=lambda x: x[1]) if unlucky_candidates else None

    # Best/Worst Manager (approximate optimal)
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

    # Build embed
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

    # Over/Under with full numbers
    if over:
        embed["fields"].append({
            "name":"📈 Overachiever 📈",
            "value": f"{name_for(over[0])} scored {over[2]:.2f} vs {over[3]:.2f} projected (+{over[1]:.2f})",
            "inline": False
        })
    if under:
        embed["fields"].append({
            "name":"📉 Underachiever 📉",
            "value": f"{name_for(under[0])} scored {under[2]:.2f} vs {under[3]:.2f} projected ({under[1]:.2f})",
            "inline": False
        })

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
