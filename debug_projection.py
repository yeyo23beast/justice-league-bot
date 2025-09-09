import os, json
from espn_http import get

def main():
    week = get("mSettings")["status"]["currentMatchupPeriod"]
    mm = get("mMatchup")
    schedule = [s for s in mm.get("schedule", []) if s.get("matchupPeriodId") == week]
    print("Debugging projections for week", week)

    # Print just one team’s roster JSON for inspection
    if schedule:
        side = schedule[0]["home"]  # first team we find
        entries = ((side.get("rosterForCurrentScoringPeriod") or {}).get("entries")) or []
        for e in entries:
            slot = e.get("lineupSlotId")
            name = (e.get("playerPoolEntry") or {}).get("player", {}).get("fullName")
            stats = (e.get("playerPoolEntry") or {}).get("player", {}).get("stats", [])
            print("\n", name, "slot", slot)
            for s in stats:
                if s.get("scoringPeriodId") == week:
                    print("  statSourceId:", s.get("statSourceId"),
                          "split:", s.get("statSplitTypeId"),
                          "appliedTotal:", s.get("appliedTotal"))

if __name__ == "__main__":
    main()
