def team_display(t: dict) -> str:
    """
    Return a human-friendly team name using whatever fields ESPN provides.
    Tries (location + nickname) → (teamLocation + teamNickname) → name → abbrev → 'Team {id}'.
    """
    loc = t.get("location")
    nick = t.get("nickname")
    if loc or nick:
        return f"{(loc or '').strip()} {(nick or '').strip()}".strip()

    loc2 = t.get("teamLocation")
    nick2 = t.get("teamNickname")
    if loc2 or nick2:
        return f"{(loc2 or '').strip()} {(nick2 or '').strip()}".strip()

    if t.get("name"):
        return str(t["name"]).strip()

    if t.get("abbrev"):
        return str(t["abbrev"]).strip()

    return f"Team {t.get('id','?')}"
