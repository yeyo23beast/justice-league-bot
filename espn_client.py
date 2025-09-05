import os
from espn_api.football import League

def get_league():
    league_id = int(os.environ["LEAGUE_ID"])
    season_id = int(os.environ["SEASON_ID"])
    espn_s2   = os.environ.get("ESPN_S2") or None
    swid      = os.environ.get("SWID") or None
    return League(league_id=league_id, year=season_id, espn_s2=espn_s2, swid=swid)
