import os
from espn_api.football import League

league = League(
    league_id=int(os.environ["LEAGUE_ID"]),
    year=int(os.environ["SEASON_ID"]),
    espn_s2=os.environ.get("ESPN_S2") or None,
    swid=os.environ.get("SWID") or None
)
print("LEAGUE:", league.settings.name, "| TEAMS:", len(league.teams), "| YEAR:", league.year)
print("CURRENT WEEK (from ESPN):", league.current_week)
