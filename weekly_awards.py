import os, requests, datetime, pytz
from espn_client import get_league
from collections import defaultdict

WEBHOOK_URL = os.environ["WEBHOOK_URL"]
TZ = os.environ.get("TIMEZONE", "America/Denver")

# Toggle this off if your roster is very custom:
COMPUTE_OPTIMAL = True

def send(embed):
    payload = {"username": "Justice League Bot", "embeds": [embed]}
    r = requests.post(WEBHOOK_URL, json=payload, timeout=20)
    r.raise_for_status()

def build_awards_embed():
    league = get_league()
    week = max(1, league.current_week - 1)  # recap previous week
    matchups = league.scoreboard(week)

    # Gather per-team stats for the week
    teams_data = {}
    all_scores = []
    for m in matchups:
        for side in [("home", m.home_team, m.home_score, m.home_projected), ("away", m.away_team, m.away_score, m.away_projected)]:
            role, team, score, proj = side
            if team is None: 
                continue
            teams_data[team.team_id] = {
                "name": team.team_name,
                "owner": team.owner,
                "score": score or 0.0,
                "proj":  proj or 0.0,
                "abbrev": team.team_abbrev
            }
            all_scores.append((team.team_id, score or 0.0))

    # High / Low
    high = max(all_scores, key=lambda x: x[1])
    low  = min(all_scores, key=lambda x: x[1])

    # Blowout / Close win (only from actual head-to-heads)
    blowout = None  # (winner_id, loser_id, margin)
    close   = None
    for m in matchups:
        if m.home_team and m.away_team:
            diff = abs((m.home_score or 0) - (m.away_score or 0))
            if blowout is None or diff > blowout[2]:
                # winner = higher score
                if (m.home_score or 0) >= (m.away_score or 0):
                    blowout = (m.home_team.team_id, m.away_team.team_id, diff)
                else:
                    blowout = (m.away_team.team_id, m.home_team.team_id, diff)
            if close is None or diff < close[2]:
                if (m.home_score or 0) >= (m.away_score or 0):
                    close = (m.home_team.team_id, m.away_team.team_id, diff)
                else:
                    close = (m.away_team.team_id, m.home_team.team_id, diff)

    # Lucky / Unlucky via all-play
    # Count "all-play wins" each team would have if they played everyone
    sorted_scores = sorted(all_scores, key=lambda x: x[1], reverse=True)
    idx = {tid:i for i,(tid,_) in enumerate(sorted_scores)}
    n = len(sorted_scores)
    # all-play wins = number of teams you outscored
    allplay_wins = {tid:(n - 1 - idx[tid]) for tid,_ in sorted_scores}

    # Map real W/L from head-to-head this week
    real_win = defaultdict(int)
    for m in matchups:
        if not (m.home_team and m.away_team): 
            continue
        h = (m.home_team.team_id, m.home_score or 0.0)
        a = (m.away_team.team_id, m.away_score or 0.0)
        if h[1] > a[1]:
            real_win[h[0]] = 1
            real_win[a[0]] = 0
        elif a[1] > h[1]:
            real_win[a[0]] = 1
            real_win[h[0]] = 0
        else:
            # tie = neither lucky nor unlucky
            real_win[h[0]] = 0
            real_win[a[0]] = 0

    # Lucky: low all-play wins but still got the W
    # Unlucky: high all-play wins but still took the L
    # We’ll choose min and max all-play winners/losers
    lucky_candidates   = [(tid, allplay_wins[tid]) for tid,w in real_win.items() if w==1]
    unlucky_candidates = [(tid, allplay_wins[tid]) for tid,w in real_win.items() if w==0]
    lucky = min(lucky_candidates, key=lambda x: x[1]) if lucky_candidates else None
    unlucky = max(unlucky_candidates, key=lambda x: x[1]) if unlucky_candidates else None

    # Over/Underachiever: compare actual vs projected
    diffs = []
    for tid, data in teams_data.items():
        diffs.append((tid, (data["score"] - data["proj"])))
    over = max(diffs, key=lambda x: x[1]) if diffs else None
    under= min(diffs, key=lambda x: x[1]) if diffs else None

    # Best/Worst Manager: optimal vs actual (approx)
    best = worst = None
    if COMPUTE_OPTIMAL:
        try:
            # Use the box_scores to compute optimal by slot
            # We approximate using lineup slot counts in league.settings
            league = get_league()
            rs = league.settings.roster_settings
            slot_counts = rs.lineup_slot_counts  # dict: slot -> count
            # Which slots count as starting scoring slots
            # Typical ESPN: QB,RB,WR,TE,FLEX, D/ST, K. We’ll map known slot ids to names via player.slot_position.
            # espn-api exposes box_scores with .home_lineup / .away_lineup, each with .points and .selected_position
            # We'll select top points per slot requirement; for FLEX we pick next-highest from RB/WR/TE not already used.
            from collections import Counter

            def optimal_for_team(players):
                # players: list of (eligibleSlots, points)
                # We will fill slots in this order as a heuristic: QB, RB, WR, TE, FLEX, D/ST, K
                need = Counter()
                order = []
                for slot, c in slot_counts.items():
                    # Ignore bench/IR/empty slots (<0 or specific bench ids handled by api)
                    if c <= 0: 
                        continue
                    name = str(slot)  # fallback
                    # espn-api maps slot strings in player.slot_position already (e.g., 'RB','WR','D/ST','K','FLEX')
                    # We’ll rely on player.eligibleSlots_names in lineup objects (see below).
                    # For heuristic, build logical map:
                    order.extend([slot]*c)

                # Normalize to a readable order preference; we’ll sort later by desirability
                # (We’ll rely on FLEX being a distinct slot key like 'FLEX' in many leagues.)
                # If not, this still works by picking best remaining regardless.

                used = set()
                total = 0.0
                remaining = players[:]
                # Greedy: each slot pick the highest scoring eligible player not used yet
                for _slot in order:
                    best_i = -1
                    best_pts = -1e9
                    for i,(elig,pts) in enumerate(remaining):
                        if i in used: continue
                        if _slot in elig or "FLEX" in _slot and any(s in elig for s in ["RB","WR","TE"]):
                            if pts > best_pts:
                                best_pts = pts
                                best_i = i
                    if best_i >= 0:
                        used.add(best_i)
                        total += max(0.0, best_pts)
                return total

            team_opt = {}
            for bs in league.box_scores(week):
                for side, lineup in [("home", bs.home_lineup), ("away", bs.away_lineup)]:
                    team = bs.home_team if side=="home" else bs.away_team
                    if team is None: continue
                    players = []
                    for p in lineup:
                        # p.lineupSlot: starting slot; p.eligibleSlots: slot names; p.points: scored
                        try:
                            elig = set(p.eligibleSlots) if hasattr(p, "eligibleSlots") else set()
                            # espn-api sometimes provides p.eligibleSlots as ids; recent versions map to names
                            # To be safe, also add p.slot_position if present
                            if hasattr(p, "slot_position") and p.slot_position:
                                elig.add(p.slot_position)
                            players.append((elig, float(p.points or 0.0)))
                        except Exception:
                            continue
                    team_opt[team.team_id] = optimal_for_team(players)

            mgr = []
            for tid, data in teams_data.items():
                actual = data["score"]
                optimal = team_opt.get(tid, actual)
                pct = (actual/optimal*100.0) if optimal > 0 else 100.0
                mgr.append((tid, pct, optimal-actual))
            best = max(mgr, key=lambda x: x[1]) if mgr else None
            worst= min(mgr, key=lambda x: x[1]) if mgr else None
        except Exception:
            COMPUTE_OPTIMAL = False  # silently disable if something off

    # Build embed
    def name(tid): 
        d = teams_data[tid]; 
        return f'{d["name"]}'

    embed = {
      "title": f"Trophies of the Week — Week {week}",
      "description": "Justice League Fantasy Football",
      "color": 0x0B1F35,
      "fields": [],
      "footer": {"text": f"Generated {datetime.datetime.now(pytz.timezone(TZ)).strftime('%Y-%m-%d %H:%M %Z')}"}
    }

    # High / Low
    embed["fields"].append({"name":"👑 High score 👑", "value": f'{name(high[0])} with {high[1]:.2f} points', "inline": False})
    embed["fields"].append({"name":"💩 Low score 💩",  "value": f'{name(low[0])} with {low[1]:.2f} points',  "inline": False})

    # Blowout / Close
    if blowout:
        embed["fields"].append({"name":"😱 Blow out 😱", "value": f'{name(blowout[0])} blew out {name(blowout[1])} by {blowout[2]:.2f} points', "inline": False})
    if close:
        embed["fields"].append({"name":"😅 Close win 😅", "value": f'{name(close[0])} barely beat {name(close[1])} by {close[2]:.2f} points', "inline": False})

    # Lucky / Unlucky
    if lucky:
        embed["fields"].append({"name":"🍀 Lucky 🍀", "value": f'{name(lucky[0])} was {allplay_wins[lucky[0]]}-{(n-1 - allplay_wins[lucky[0]])} in all-play but still got the win', "inline": False})
    if unlucky:
        embed["fields"].append({"name":"😡 Unlucky 😡", "value": f'{name(unlucky[0])} was {allplay_wins[unlucky[0]]}-{(n-1 - allplay_wins[unlucky[0]])} in all-play but still took the L', "inline": False})

    # Over / Under
    if over:
        embed["fields"].append({"name":"📈 Overachiever 📈", "value": f'{name(over[0])} was {over[1]:.2f} points over projection', "inline": False})
    if under:
        embed["fields"].append({"name":"📉 Underachiever 📉", "value": f'{name(under[0])} was {under[1]:.2f} points under projection', "inline": False})

    # Best / Worst Manager
    if COMPUTE_OPTIMAL and best and worst:
        embed["fields"].append({"name":"🤖 Best Manager 🤖", "value": f'{name(best[0])} scored {100.0 if best[1]>100 else best[1]:.2f}% of optimal', "inline": False})
        embed["fields"].append({"name":"🤡 Worst Manager 🤡", "value": f'{name(worst[0])} left {worst[2]:.2f} points on the bench', "inline": False})

    return embed

if __name__ == "__main__":
    embed = build_awards_embed()
    send(embed)
