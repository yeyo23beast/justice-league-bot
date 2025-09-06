def build_preview():
    week = current_week()
    # Pull schedule from mMatchup
    mm = get("mMatchup")
    schedule = [s for s in mm.get("schedule", []) if s.get("matchupPeriodId") == week]

    # Build a robust team name map from mTeam (more reliable for names)
    mt = get("mTeam")
    team_map = {t["id"]: t for t in mt["teams"]}

    def name_for(tid):
        t = team_map.get(tid, {})
        # Try common fields in order
        for a,b in [("location","nickname"), ("teamLocation","teamNickname")]:
            loc, nick = t.get(a), t.get(b)
            if loc or nick:
                return f"{(loc or '').strip()} {(nick or '').strip()}".strip()
        return t.get("name") or t.get("abbrev") or f"Team {tid}"

    embed = {
      "title": f"Week {week} Matchup Preview",
      "description": "Justice League Fantasy Football",
      "color": 0x1F8B4C,
      "fields": [],
      "footer": {"text": f"Generated {datetime.datetime.now(pytz.timezone(TZ)).strftime('%Y-%m-%d %H:%M %Z')}"}
    }

    for s in schedule:
        home_name = name_for(s["home"]["teamId"])
        away_name = name_for(s["away"]["teamId"])
        embed["fields"].append({"name":"\u200b","value":f"**{home_name}** vs **{away_name}**", "inline": False})

    if not embed["fields"]:
        embed["description"] = "_No scheduled matchups found for this week yet_"

    return embed
