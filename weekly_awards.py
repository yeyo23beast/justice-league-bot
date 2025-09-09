import os, requests, datetime, pytz
from espn_http import get  # must support: get(view, params=dict)

WEBHOOK_URL = os.environ["WEBHOOK_URL"]
TZ = os.environ.get("TIMEZONE", "America/Denver")

# Turn this False if anything looks off for your league shape
COMPUTE_OPTIMAL = True
DEBUG_PROJ = True  # <- turn off later if you want quieter logs

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

def _sum_proj_from_entry_list(entry_list, week):
    """Return (found_any, sum) of starter projections from an entry list if stats are attached."""
    total = 0.0
    found_any = False
    starters = 0
    for e in entry_list:
        slot = e.get("lineupSlotId")
        # EXCLUDE ONLY: Bench(20), IR(21). FLEX(23) **IS a starter** on ESPN.
        if slot in (20, 21, None):
            continue
        starters += 1
        ppe = e.get("playerPoolEntry") or {}
        stats = (ppe.get("player", {}) or {}).get("stats", []) or []
        for s in stats:
            if (s.get("scoringPeriodId") == week and s.get("statSourceId") == 1 and s.get("statSplitTypeId") == 1):
                total += float(s.get("appliedTotal") or 0.0)
                found_any = True
                break
    if DEBUG_PROJ:
        print(f"[proj] entries week={week}: starters={starters} total_proj={total:.2f} found_any={found_any}")
    return found_any, total

def projected_points_for_team(team_id: int, week: int) -> float:
    """Sum projected points for that team's starters for the given week via mRoster."""
    roster = get("mRoster", params={"scoringPeriodId": week})
    team = next((t for t in roster.get("teams", []) if t.get("id") == team_id), None)
    if not team:
        if DEBUG_PROJ: print(f"[proj] team {team_id} not in mRoster week={week}")
        return 0.0

    entries = ((team.get("roster") or {}).get("entries")) or []
    total = 0.0
    starters = 0
    for e in entries:
        slot = e.get("lineupSlotId")
        if slot in (20, 21, None):  # exclude bench + IR only
            continue
        starters += 1
        ppe = e.get("playerPoolEntry") or {}
        p = ppe.get("player") or {}
        stats = p.get("stats", []) or []
        proj = 0.0
        for s in stats:
            # statSourceId==1 (projection), statSplitTypeId==1 (total), for that week
            if (s.get("scoringPeriodId") == week and s.get("statSourceId") == 1 and s.get("statSplitTypeId") == 1):
                proj = float(s.get("appliedTotal") or 0.0)
                break
        total += proj
    if DEBUG_PROJ:
        print(f"[proj] mRoster team={team_id} week={week}: starters={starters} total_proj={total:.2f}")
    return total

def collect_entries_points(side):
    """Returns (num_starters, actual_points, all_points_list) for best/worst manager calc."""
    entries = (((side.get("rosterForCurrentScoringPeriod") or {}).get("entries")) or [])
    pts_all = []
    starters_pts = []
    starters_count = 0
    for e in entries:
        slot = e.get("lineupSlotId")
        if slot in (20, 21, None):  # exclude bench + IR only
            continue
        starters_count += 1
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
        starters_pts.append(pts)
    return starters_count, sum(starters_pts), pts_all

def build_awards_embed():
    # Recap prior week
    week = max(1, current_week() - 1)
    mm = get("mMatchup")
    schedule = [s for s in mm.get("schedule", []) if s.get("matchupPeriodId") == week]
    id_to_team, name_for = name_map()

    team_week = {}
    match_results = []

    def ensure_team(tid):
        if tid not in team_week:
            team_week[tid] = {"tid": tid, "score": 0.0, "proj": 0.0}

    for s in schedule:
        h_id = s["home"]["teamId"]; a_id = s["away"]["teamId"]
        ensure_team(h_id); ensure_team(a_id)

        h_side, a_side = s["home"], s["away"]
        h_pts = safe_score(h_side); a_pts = safe_score(a_side)
        h_proj = safe_proj(h_side);  a_proj = safe_proj(a_side)

        # Fallback to roster-based projections when zeros
        if h_proj == 0:
            h_proj = projected_points_for_team(h_id, week)
        if a_proj == 0:
            a_proj = projected_points_for_team(a_id, week)

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

    if not team_week or (max(t["score"] for t in team_week.values()) == 0.0 and
                         min(t["score"] for t in team_week.values()) == 0.0):
        return {
          "title": f"Trophies of the Week — Week {week}",
          "description": "_No completed matchups yet—awards will post after games conclude_",
          "color": 0x0B1F35,
          "fields": []
        }

    high = max(team_week.values(), key=lambda x: x["score"])
    low  = min(team_week.values(), key=lambda x: x["score"])
    blow = max(match_results, key=lambda x: x[2]) if match_results else None
    close= min(match_results, key=lambda x: x[2]) if match_results else None

    diffs = [(t["tid"],
              float(t.get("score",0.0)) - float(t.get("proj",0.0)),
              float(t.get("score",0.0)),
              float(t.get("proj",0.0)))
             for t in team_week.values()]
    over  = max(diffs, key=lambda x: x[1]) if diffs else None
    under = min(diffs, key=lambda x: x[1]) if diffs else None

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

    embed = {
      "title": f"Trophies of the Week — Week {week}",
      "description": "Justice League Fantasy Football",
      "color": 0x0B1F35,
      "fields": [],
      "footer": {"text": f"Generated {datetime.datetime.now(pytz.timezone(TZ)).strftime('%Y-%m-%d %H:%M %Z')}"}
    }

    embed["fields"].append({"name":"👑 High score 👑", "value": f"{name_for(high['tid'])} with {high['score']:.2f} points", "inline": False})
    embed["fields"].append({"name":"💩 Low score 💩",  "value": f"{name_for(low['tid'])} with {low['score']:.2f} points",  "inline": False})

    if blow:
        embed["fields"].append({"name":"😱 Blow out 😱", "value": f"{name_for(blow[0])} blew out {name_for(blow[1])} by {blow[2]:.2f} points", "inline": False})
    if close:
        embed["fields"].append({"name":"😅 Close win 😅", "value": f"{name_for(close[0])} barely beat {name_for(close[1])} by {close[2]:.2f} points", "inline": False})

    if lucky:
        lw = allplay_wins[lucky[0]]
        embed["fields"].append({"name":"🍀 Lucky 🍀", "value": f"{name_for(lucky[0])} was {lw}-{(n-1-lw)} in all-play but still got the W", "inline": False})
    if unlucky:
        uw = allplay_wins[unlucky[0]]
        embed["fields"].append({"name":"😡 Unlucky 😡", "value": f"{name_for(unlucky[0])} was {uw}-{(n-1-uw)} in all-play but still took the L", "inline": False})

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
