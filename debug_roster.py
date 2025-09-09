import os
from espn_http import get

def main():
    week = 1  # hardcode Week 1 for inspection
    roster = get("mRoster", params={"scoringPeriodId": week})
    print("Teams:", len(roster.get("teams", [])))
    for team in roster.get("teams", []):
        tname = (team.get("location","") + " " + team.get("nickname","")).strip()
        print("\n===", tname, "===")
        entries = ((team.get("roster") or {}).get("entries")) or []
        for e in entries[:3]:  # only show 3 players per team for brevity
            p = (e.get("playerPoolEntry") or {}).get("player", {}) or {}
            name = p.get("fullName")
            stats = p.get("stats", [])
            print(" ", name)
            for s in stats:
                if s.get("scoringPeriodId") == week:
                    print("   statSourceId:", s.get("statSourceId"),
                          "split:", s.get("statSplitTypeId"),
                          "appliedTotal:", s.get("appliedTotal"))

if __name__ == "__main__":
    main()
