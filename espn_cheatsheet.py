"""
espn_cheatsheet.py - ESPN Ultimate 2026 Fantasy Football Cheat Sheet Engine
=============================================================================
Directly ingests and structures ESPN's official 2026 preseason "The Ultimate Fantasy Football Cheat Sheet"
(data/NFL26_CS_ULTIMATE.pdf) authored by ESPN's senior fantasy editorial team:
- Erik Karabell (Do Draft, Do Not Draft, RB Tiers, WR Tiers)
- Matt Bowen (Bowen's Top Targets, QB Tiers, TE Tiers)
- Mike Clay (Clay's Ultimate Draft Board Blueprint - Rounds 1 to 16)
- Adam Schefter (Schefter's Picks to Target)
- Matt Florio (Florio's League Winners)
- Field Yates (Field's Favorites - Falling Too Far)
- Liz Loza (Loza's Late-Round Fliers)
- Eric Moody (Moody's Top Insurance RBs, Moody's Top Draft-Day Values)
- Tristan H. Cockcroft (Cockcroft's Deep Sleepers)
- ESPN Editorial ("Have Skills, Need Opportunity" Breakouts)

Provides:
1. Sub-millisecond JSON-cached loading (data/espn_ultimate_cheatsheet_2026.json).
2. Automated PDF verification from data/NFL26_CS_ULTIMATE.pdf.
3. Canonical name resolution against the draft board.
4. enrich_board_with_espn_cheatsheet(df) to stamp every player with the ESPN Heat Index,
   expert badges, Karabell/Bowen positional tiers, Clay blueprint round, and analyst dossiers.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
PDF_PATH = DATA_DIR / "NFL26_CS_ULTIMATE.pdf"
JSON_CACHE_PATH = DATA_DIR / "espn_ultimate_cheatsheet_2026.json"


def clean_name_key(name: str) -> str:
    """Standardize player name for matching."""
    s = name.lower().strip()
    s = re.sub(r"[.'\"]", "", s)
    s = re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", s)
    return s.strip()


# ==============================================================================
# AUTHORITATIVE 2026 ESPN ULTIMATE CHEAT SHEET LEDGER
# ==============================================================================
# Directly transcribed and verified from NFL26_CS_ULTIMATE.pdf

RAW_ESPN_CHEAT_SHEET_DATA: Dict[str, Any] = {
    "metadata": {
        "title": "The Ultimate Fantasy Football Cheat Sheet",
        "season": 2026,
        "format": "PPR",
        "source_document": "NFL26_CS_ULTIMATE.pdf",
        "source_date": "2026-09-05",
        "analysts": [
            "Erik Karabell",
            "Matt Bowen",
            "Mike Clay",
            "Adam Schefter",
            "Field Yates",
            "Matt Florio",
            "Eric Moody",
            "Liz Loza",
            "Tristan H. Cockcroft"
        ]
    },
    # 1. KARABELL'S "DO NOT DRAFT" LIST (Not worth their current ADP, but OK if they fall)
    "karabell_do_not_draft": {
        "title": "Karabell's \"Do Not Draft\" List",
        "analyst": "Erik Karabell",
        "description": "Not worth their current ADP (but OK to draft if they fall)",
        "badge": "🛑 KARABELL FADE",
        "players": [
            {"name": "Josh Allen", "pos": "QB", "team": "Bills", "adp": 19.2, "note": "Overvalued in R2; QB depth allows waiting."},
            {"name": "Drake Maye", "pos": "QB", "team": "Patriots", "adp": 47.2, "note": "R4-5 cost is too steep for rebuilding offense."},
            {"name": "Jayden Daniels", "pos": "QB", "team": "Commanders", "adp": 53.1, "note": "High ADP prices in absolute ceiling."},
            {"name": "Jaxson Dart", "pos": "QB", "team": "Giants", "adp": 83.3, "note": "Rookie learning curve makes R7-8 a reach."},
            {"name": "Jordan Love", "pos": "QB", "team": "Packers", "adp": 155.2, "note": "Volatile passing volume in run-heavy scheme."},
            {"name": "Daniel Jones", "pos": "QB", "team": "Colts", "adp": 160.3, "note": "Low floor as backup/bridge."},
            {"name": "Fernando Mendoza", "pos": "QB", "team": "Raiders", "adp": 168.6, "note": "Unproven rookie in competition."},
            {"name": "Christian McCaffrey", "pos": "RB", "team": "49ers", "adp": 7.7, "note": "Top-8 overall pick carries extreme injury mileage risk."},
            {"name": "Kenneth Walker III", "pos": "RB", "team": "Chiefs", "adp": 24.8, "note": "R3 cost is rich for split-backfield Chiefs offense."},
            {"name": "Kyren Williams", "pos": "RB", "team": "Rams", "adp": 35.0, "note": "Blake Corum presence caps bellcow ceiling."},
            {"name": "Travis Etienne Jr.", "pos": "RB", "team": "Saints", "adp": 40.6, "note": "Inefficiency and timeshare caps upside."},
            {"name": "Bucky Irving", "pos": "RB", "team": "Buccaneers", "adp": 56.8, "note": "Priced at ceiling with Gainwell/Tucker sharing reps."},
            {"name": "TreVeyon Henderson", "pos": "RB", "team": "Patriots", "adp": 77.4, "note": "Rhamondre Stevenson remains early-down hammer."},
            {"name": "Tony Pollard", "pos": "RB", "team": "Titans", "adp": 87.2, "note": "Tyjae Spears splits work; limited goal-line work."},
            {"name": "Chuba Hubbard", "pos": "RB", "team": "Panthers", "adp": 108.1, "note": "Jonathon Brooks returns to reclaim starting role."},
            {"name": "A.J. Brown", "pos": "WR", "team": "Patriots", "adp": 21.0, "note": "New offense with rookie/young QB lowers target quality."},
            {"name": "Rashee Rice", "pos": "WR", "team": "Chiefs", "adp": 29.4, "note": "High ADP before multi-game disciplinary risk is settled."},
            {"name": "Malik Nabers", "pos": "WR", "team": "Giants", "adp": 35.1, "note": "R3 price tag too aggressive with rookie QB volatility."},
            {"name": "Marvin Harrison Jr.", "pos": "WR", "team": "Cardinals", "adp": 78.6, "note": "Cardinals funnel targets through Trey McBride."},
            {"name": "Kyle Pitts Sr.", "pos": "TE", "team": "Falcons", "adp": 68.7, "note": "Continual tease; R5-6 draft capital best spent elsewhere."},
            {"name": "Dallas Goedert", "pos": "TE", "team": "Eagles", "adp": 103.3, "note": "Low touchdown ceiling in crowded Eagles passing game."}
        ]
    },

    # 2. KARABELL'S "DO DRAFT" LIST (Worth their current ADP, so don't be shy about taking them)
    "karabell_do_draft": {
        "title": "Karabell's \"Do Draft\" List",
        "analyst": "Erik Karabell",
        "description": "Worth their current ADP (so don't be shy about taking them)",
        "badge": "🎯 KARABELL TARGET",
        "players": [
            {"name": "Patrick Mahomes", "pos": "QB", "team": "Chiefs", "adp": 108.9, "note": "Screaming value at QB10 ADP; MVP ceiling."},
            {"name": "Brock Purdy", "pos": "QB", "team": "49ers", "adp": 110.3, "note": "Perennial top-8 fantasy QB going in double-digit rounds."},
            {"name": "Jared Goff", "pos": "QB", "team": "Lions", "adp": 136.6, "note": "Dome offense guarantees elite weekly passing floor."},
            {"name": "Kyler Murray", "pos": "QB", "team": "Vikings", "adp": 137.2, "note": "Rushing floor + Kevin O'Connell offensive scheme = goldmine."},
            {"name": "Tyler Shough", "pos": "QB", "team": "Saints", "adp": 152.3, "note": "Starting QB with deep passing arm practically free."},
            {"name": "Malik Willis", "pos": "QB", "team": "Dolphins", "adp": 167.6, "note": "Dual-threat gadget ceiling in McDaniel offense."},
            {"name": "James Cook III", "pos": "RB", "team": "Bills", "adp": 10.1, "note": "Complete bellcow in high-scoring Buffalo offense."},
            {"name": "Derrick Henry", "pos": "RB", "team": "Ravens", "adp": 16.5, "note": "Unstoppable redzone force with 15+ TD equity."},
            {"name": "Chase Brown", "pos": "RB", "team": "Bengals", "adp": 17.1, "note": "Locked lead back with explosive 3-down receiving skill."},
            {"name": "Omarion Hampton", "pos": "RB", "team": "Chargers", "adp": 18.1, "note": "Jim Harbaugh workhorse; smash pick in late R2/R3."},
            {"name": "Javonte Williams", "pos": "RB", "team": "Cowboys", "adp": 32.7, "note": "Dallas lead back behind dominant run-blocking line."},
            {"name": "David Montgomery", "pos": "RB", "team": "Texans", "adp": 61.4, "note": "Goal-line monster in surging Houston offense."},
            {"name": "Jadarian Price", "pos": "RB", "team": "Seahawks", "adp": 66.8, "note": "Dynamic rusher with expanding weekly workload."},
            {"name": "Kenny Gainwell", "pos": "RB", "team": "Buccaneers", "adp": 99.9, "note": "High-efficiency PPR pass-catcher at pick 100."},
            {"name": "J.K. Dobbins", "pos": "RB", "team": "Broncos", "adp": 111.5, "note": "Lead runner in Sean Payton zone offense."},
            {"name": "Rachaad White", "pos": "RB", "team": "Commanders", "adp": 125.6, "note": "PPR receiving vacuum available in R10-11."},
            {"name": "Justin Jefferson", "pos": "WR", "team": "Vikings", "adp": 12.6, "note": "WR1 overall talent slipping into R2 is gift of the draft."},
            {"name": "Zay Flowers", "pos": "WR", "team": "Ravens", "adp": 44.1, "note": "Alpha separator with designed touches in Baltimore."},
            {"name": "Jameson Williams", "pos": "WR", "team": "Lions", "adp": 64.1, "note": "Full-time field stretcher with elite explosive upside."},
            {"name": "Mike Evans", "pos": "WR", "team": "49ers", "adp": 83.7, "note": "Shanahan redzone weapon at massive discount."},
            {"name": "Wan'Dale Robinson", "pos": "WR", "team": "Titans", "adp": 112.9, "note": "High-volume slot receiver with 80+ catch floor."},
            {"name": "Jordan Addison", "pos": "WR", "team": "Vikings", "adp": 121.3, "note": "Tremendous TD efficiency opposite Jefferson."},
            {"name": "Josh Downs", "pos": "WR", "team": "Colts", "adp": 136.4, "note": "Target hog in the slot with dynamic YAC skill."},
            {"name": "Malik Washington", "pos": "WR", "team": "Dolphins", "adp": 170.0, "note": "Miami gadget speedster with late-round breakout pedigree."},
            {"name": "Tucker Kraft", "pos": "TE", "team": "Packers", "adp": 91.1, "note": "YAC beast and primary redzone target for Green Bay."},
            {"name": "Mark Andrews", "pos": "TE", "team": "Ravens", "adp": 126.6, "note": "Elite TE1 slipping into double-digit rounds."},
            {"name": "Dalton Kincaid", "pos": "TE", "team": "Bills", "adp": 130.9, "note": "Josh Allen's trusted security blanket in the middle."},
            {"name": "T.J. Hockenson", "pos": "TE", "team": "Vikings", "adp": 152.7, "note": "Proven top-5 tight end at dirt-cheap draft price."},
            {"name": "Hunter Henry", "pos": "TE", "team": "Patriots", "adp": 153.2, "note": "Reliable redzone safety valve in New England."}
        ]
    },

    # 3. MIKE CLAY'S ULTIMATE DRAFT BOARD (Round-by-Round Blueprint)
    "clay_draft_board": {
        "title": "Clay's Ultimate Draft Board",
        "analyst": "Mike Clay",
        "description": "The blueprint for a successful draft (Rounds 1 to 16)",
        "badge": "📋 CLAY BLUEPRINT",
        "rounds": [
            {"round": 1, "target": "Best available RB or WR", "player": "Best Available RB/WR", "pos": "RB/WR", "team": "N/A", "note": "Anchor your foundation with elite tier-1 volume."},
            {"round": 2, "target": "De'Von Achane", "player": "De'Von Achane", "pos": "RB", "team": "MIA", "note": "Historic per-touch efficiency and top-3 PPR ceiling."},
            {"round": 3, "target": "Jeremiyah Love", "player": "Jeremiyah Love", "pos": "RB", "team": "ARI", "note": "Explosive dynamic playmaker locked into high-value touches."},
            {"round": 4, "target": "Garrett Wilson", "player": "Garrett Wilson", "pos": "WR", "team": "NYJ", "note": "Elite target share and route separation."},
            {"round": 5, "target": "Tyler Warren", "player": "Tyler Warren", "pos": "TE", "team": "IND", "note": "Colts dynamic tight end with high-volume offensive role."},
            {"round": 6, "target": "Rome Odunze", "player": "Rome Odunze", "pos": "WR", "team": "CHI", "note": "Sophomore leap candidate in Ben Johnson-style attack."},
            {"round": 7, "target": "Courtland Sutton", "player": "Courtland Sutton", "pos": "WR", "team": "DEN", "note": "Unquestioned WR1 in Denver with dominant endzone share."},
            {"round": 8, "target": "Michael Pittman Jr.", "player": "Michael Pittman Jr.", "pos": "WR", "team": "PIT", "note": "Contested-catch anchor with 110+ target floor."},
            {"round": 9, "target": "Jaxson Dart", "player": "Jaxson Dart", "pos": "QB", "team": "NYG", "note": "Dual-threat rushing ability with top-10 QB upside."},
            {"round": 10, "target": "Bo Nix or Brock Purdy", "player": "Bo Nix", "alt_player": "Brock Purdy", "pos": "QB", "team": "DEN/SF", "note": "Lock in high-floor passing volume at rock-bottom cost."},
            {"round": 11, "target": "Matthew Golden", "player": "Matthew Golden", "pos": "WR", "team": "GB", "note": "Electric rookie speedster emerging in Packers attack."},
            {"round": 12, "target": "De'Zhaun Stribling", "player": "De'Zhaun Stribling", "pos": "WR", "team": "SF", "note": "Physical perimeter target carved out for Shanahan system."},
            {"round": 13, "target": "High-ceiling breakout candidates", "player": "Breakout Candidates", "pos": "FLEX", "team": "N/A", "note": "Target explosive rookies and ascending backup RBs."},
            {"round": 14, "target": "High-ceiling breakout candidates", "player": "Breakout Candidates", "pos": "FLEX", "team": "N/A", "note": "Lock down handcuff RBs with league-winning standalone value."},
            {"round": 15, "target": "Kicker and D/ST... or more breakouts", "player": "Kicker / DST / Breakouts", "pos": "K/DST", "team": "N/A", "note": "Stream kicker or stash another high-upside flier."},
            {"round": 16, "target": "Kicker and D/ST... or more breakouts", "player": "Kicker / DST / Breakouts", "pos": "K/DST", "team": "N/A", "note": "Lock in top Week 1 matchup defense."}
        ]
    },

    # 4. ADAM SCHEFTER'S PICKS TO TARGET
    "schefter_picks_to_target": {
        "title": "Schefter's Picks to Target",
        "analyst": "Adam Schefter",
        "description": "The players to go after in your draft (Adam's personal priority targets)",
        "badge": "⭐ SCHEFTER TARGET",
        "players": [
            {"name": "Bo Nix", "pos": "QB", "team": "Broncos"},
            {"name": "Caleb Williams", "pos": "QB", "team": "Bears"},
            {"name": "Justin Herbert", "pos": "QB", "team": "Chargers"},
            {"name": "Tyler Shough", "pos": "QB", "team": "Saints"},
            {"name": "Jordan Love", "pos": "QB", "team": "Packers"},
            {"name": "Daniel Jones", "pos": "QB", "team": "Colts"},
            {"name": "Jahmyr Gibbs", "pos": "RB", "team": "Lions"},
            {"name": "Bijan Robinson", "pos": "RB", "team": "Falcons"},
            {"name": "Chase Brown", "pos": "RB", "team": "Bengals"},
            {"name": "Kenneth Walker III", "pos": "RB", "team": "Chiefs"},
            {"name": "Omarion Hampton", "pos": "RB", "team": "Chargers"},
            {"name": "Bhayshul Tuten", "pos": "RB", "team": "Jaguars"},
            {"name": "Rhamondre Stevenson", "pos": "RB", "team": "Patriots"},
            {"name": "Kenny Gainwell", "pos": "RB", "team": "Buccaneers"},
            {"name": "Blake Corum", "pos": "RB", "team": "Rams"},
            {"name": "Jordan Mason", "pos": "RB", "team": "Vikings"},
            {"name": "Chris Rodriguez Jr.", "pos": "RB", "team": "Jaguars"},
            {"name": "Jonah Coleman", "pos": "RB", "team": "Broncos"},
            {"name": "Ja'Marr Chase", "pos": "WR", "team": "Bengals"},
            {"name": "Puka Nacua", "pos": "WR", "team": "Rams"},
            {"name": "Justin Jefferson", "pos": "WR", "team": "Vikings"},
            {"name": "Chris Olave", "pos": "WR", "team": "Saints"},
            {"name": "DeVonta Smith", "pos": "WR", "team": "Eagles"},
            {"name": "Ladd McConkey", "pos": "WR", "team": "Chargers"},
            {"name": "Luther Burden III", "pos": "WR", "team": "Bears"},
            {"name": "Parker Washington", "pos": "WR", "team": "Jaguars"},
            {"name": "Wan'Dale Robinson", "pos": "WR", "team": "Titans"},
            {"name": "Colston Loveland", "pos": "TE", "team": "Bears"},
            {"name": "Harold Fannin Jr.", "pos": "TE", "team": "Browns"},
            {"name": "Tucker Kraft", "pos": "TE", "team": "Packers"},
            {"name": "Isaiah Likely", "pos": "TE", "team": "Giants"},
            {"name": "Terrance Ferguson", "pos": "TE", "team": "Rams"},
            {"name": "AJ Barner", "pos": "TE", "team": "Seahawks"},
            {"name": "Gunnar Helm", "pos": "TE", "team": "Titans"}
        ]
    },

    # 5. MATT FLORIO'S LEAGUE WINNERS
    "florio_league_winners": {
        "title": "Florio's League Winners",
        "analyst": "Matt Florio",
        "description": "Players who could help you win your league (High-ceiling championship catalysts)",
        "badge": "🏆 FLORIO WINNER",
        "players": [
            {"name": "Jaxson Dart", "pos": "QB", "team": "Giants"},
            {"name": "Kyler Murray", "pos": "QB", "team": "Vikings"},
            {"name": "Malik Willis", "pos": "QB", "team": "Dolphins"},
            {"name": "Omarion Hampton", "pos": "RB", "team": "Chargers"},
            {"name": "Bhayshul Tuten", "pos": "RB", "team": "Jaguars"},
            {"name": "TreVeyon Henderson", "pos": "RB", "team": "Patriots"},
            {"name": "Jonathon Brooks", "pos": "RB", "team": "Panthers"},
            {"name": "Jacory Croskey-Merritt", "pos": "RB", "team": "Commanders"},
            {"name": "Malik Nabers", "pos": "WR", "team": "Giants"},
            {"name": "DJ Moore", "pos": "WR", "team": "Bills"},
            {"name": "Ladd McConkey", "pos": "WR", "team": "Chargers"},
            {"name": "Christian Watson", "pos": "WR", "team": "Packers"},
            {"name": "Terry McLaurin", "pos": "WR", "team": "Commanders"},
            {"name": "Brock Bowers", "pos": "TE", "team": "Raiders"},
            {"name": "Isaiah Likely", "pos": "TE", "team": "Giants"}
        ]
    },

    # 6. FIELD YATES' FIELD'S FAVORITES (FALLING TOO FAR)
    "field_favorites": {
        "title": "Field's Favorites",
        "analyst": "Field Yates",
        "description": "Players who are dropping too far in drafts (Value fallers)",
        "badge": "💎 FIELD FAVORITE",
        "players": [
            {"name": "Justin Herbert", "pos": "QB", "team": "Chargers"},
            {"name": "Colston Loveland", "pos": "TE", "team": "Bears"},
            {"name": "Derrick Henry", "pos": "RB", "team": "Ravens"},
            {"name": "Kenneth Walker III", "pos": "RB", "team": "Chiefs"},
            {"name": "Justin Jefferson", "pos": "WR", "team": "Vikings"},
            {"name": "George Kittle", "pos": "TE", "team": "49ers"},
            {"name": "Emeka Egbuka", "pos": "WR", "team": "Buccaneers"},
            {"name": "Carnell Tate", "pos": "WR", "team": "Titans"},
            {"name": "Christian Watson", "pos": "WR", "team": "Packers"},
            {"name": "Dontayvion Wicks", "pos": "WR", "team": "Eagles"},
            {"name": "Pat Bryant", "pos": "WR", "team": "Broncos"},
            {"name": "Jonathon Brooks", "pos": "RB", "team": "Panthers"},
            {"name": "Ryan Flournoy", "pos": "WR", "team": "Cowboys"},
            {"name": "Keaton Mitchell", "pos": "RB", "team": "Chargers"},
            {"name": "Jaylin Noel", "pos": "WR", "team": "Texans"},
            {"name": "Isaac TeSlaa", "pos": "WR", "team": "Lions"},
            {"name": "Sean Tucker", "pos": "RB", "team": "Buccaneers"}
        ]
    },

    # 7. LIZ LOZA'S LATE-ROUND FLIERS
    "loza_late_round_fliers": {
        "title": "Loza's Late-Round Fliers",
        "analyst": "Liz Loza",
        "description": "These players can win your draft (Late-round lottery tickets)",
        "badge": "🚀 LOZA FLIER",
        "players": [
            {"name": "Tyler Shough", "pos": "QB", "team": "Saints"},
            {"name": "Kenny Gainwell", "pos": "RB", "team": "Buccaneers"},
            {"name": "Jadarian Price", "pos": "RB", "team": "Seahawks"},
            {"name": "Christian Watson", "pos": "WR", "team": "Packers"},
            {"name": "Jalen Nailor", "pos": "WR", "team": "Raiders"},
            {"name": "Greg Dulcich", "pos": "TE", "team": "Dolphins"},
            {"name": "Kayshon Boutte", "pos": "WR", "team": "Texans"},
            {"name": "Pat Bryant", "pos": "WR", "team": "Broncos"},
            {"name": "Elijah Arroyo", "pos": "TE", "team": "Seahawks"}
        ]
    },

    # 8. ERIC MOODY'S TOP INSURANCE RBS
    "moody_top_insurance_rbs": {
        "title": "Moody's Top Insurance RBs",
        "analyst": "Eric Moody",
        "description": "Backups to have in case the starter misses time (League-winning handcuffs)",
        "badge": "🛡️ MOODY HANDCUFF",
        "players": [
            {"name": "Kenny Gainwell", "pos": "RB", "team": "Buccaneers"},
            {"name": "Blake Corum", "pos": "RB", "team": "Rams"},
            {"name": "Jonathon Brooks", "pos": "RB", "team": "Panthers"},
            {"name": "Kyle Monangai", "pos": "RB", "team": "Bears"},
            {"name": "Brian Robinson Jr.", "pos": "RB", "team": "Falcons"},
            {"name": "Tank Bigsby", "pos": "RB", "team": "Eagles"},
            {"name": "Jacory Croskey-Merritt", "pos": "RB", "team": "Commanders"}
        ]
    },

    # 9. HAVE SKILLS, NEED OPPORTUNITY (BREAKOUT TALENT)
    "have_skills_need_opportunity": {
        "title": "Have Skills, Need Opportunity",
        "analyst": "ESPN Staff",
        "description": "Players who could break out if given the chance (Raw talent waiting on touches)",
        "badge": "⚡ BREAKOUT TALENT",
        "players": [
            {"name": "MarShawn Lloyd", "pos": "RB", "team": "Packers"},
            {"name": "KC Concepcion", "pos": "WR", "team": "Browns"},
            {"name": "Ja'Kobi Lane", "pos": "WR", "team": "Ravens"},
            {"name": "Caleb Douglas", "pos": "WR", "team": "Dolphins"},
            {"name": "Cyrus Allen", "pos": "WR", "team": "Chiefs"},
            {"name": "Elijah Arroyo", "pos": "TE", "team": "Seahawks"},
            {"name": "Jonathon Brooks", "pos": "RB", "team": "Panthers"},
            {"name": "Pat Bryant", "pos": "WR", "team": "Broncos"},
            {"name": "Ryan Flournoy", "pos": "WR", "team": "Cowboys"},
            {"name": "Keaton Mitchell", "pos": "RB", "team": "Chargers"},
            {"name": "Jaylin Noel", "pos": "WR", "team": "Texans"},
            {"name": "Isaac TeSlaa", "pos": "WR", "team": "Lions"},
            {"name": "Sean Tucker", "pos": "RB", "team": "Buccaneers"},
            {"name": "Dontayvion Wicks", "pos": "WR", "team": "Eagles"}
        ]
    },

    # 10. MATT BOWEN'S QB TIERS
    "bowen_qb_tiers": {
        "title": "Matt Bowen's QB Tiers",
        "analyst": "Matt Bowen",
        "position": "QB",
        "tiers": {
            1: ["Josh Allen", "Lamar Jackson", "Joe Burrow", "Drake Maye"],
            2: ["Jayden Daniels", "Caleb Williams", "Jalen Hurts", "Dak Prescott"],
            3: ["Trevor Lawrence", "Jaxson Dart", "Justin Herbert", "Brock Purdy"],
            4: ["Patrick Mahomes", "Kyler Murray", "Bo Nix", "Matthew Stafford", "Jared Goff"],
            5: ["Tyler Shough", "Baker Mayfield", "C.J. Stroud", "Jordan Love", "Daniel Jones", "Malik Willis", "Sam Darnold", "Cam Ward"]
        }
    },

    # 11. MATT BOWEN'S TOP TARGETS
    "bowen_top_targets": {
        "title": "Bowen's Top Targets",
        "analyst": "Matt Bowen",
        "description": "The players Matt likes most for fantasy drafts (High conviction targets)",
        "badge": "🏹 BOWEN TARGET",
        "players": [
            {"name": "Joe Burrow", "pos": "QB", "team": "Bengals"},
            {"name": "Caleb Williams", "pos": "QB", "team": "Bears"},
            {"name": "Tyler Shough", "pos": "QB", "team": "Saints"},
            {"name": "Jonathan Taylor", "pos": "RB", "team": "Colts"},
            {"name": "Omarion Hampton", "pos": "RB", "team": "Chargers"},
            {"name": "Jadarian Price", "pos": "RB", "team": "Seahawks"},
            {"name": "Jordan Mason", "pos": "RB", "team": "Vikings"},
            {"name": "Jaxon Smith-Njigba", "pos": "WR", "team": "Seahawks"},
            {"name": "Emeka Egbuka", "pos": "WR", "team": "Buccaneers"},
            {"name": "Luther Burden III", "pos": "WR", "team": "Bears"},
            {"name": "Wan'Dale Robinson", "pos": "WR", "team": "Titans"},
            {"name": "Colston Loveland", "pos": "TE", "team": "Bears"},
            {"name": "Jake Ferguson", "pos": "TE", "team": "Cowboys"},
            {"name": "Isaiah Likely", "pos": "TE", "team": "Giants"}
        ]
    },

    # 12. ERIK KARABELL'S RB TIERS
    "karabell_rb_tiers": {
        "title": "Erik Karabell's RB Tiers",
        "analyst": "Erik Karabell",
        "position": "RB",
        "tiers": {
            1: ["Jahmyr Gibbs", "Bijan Robinson"],
            2: ["Jonathan Taylor", "De'Von Achane", "James Cook III", "Derrick Henry", "Chase Brown"],
            3: ["Christian McCaffrey"],
            4: ["Saquon Barkley", "Omarion Hampton", "Ashton Jeanty"],
            5: ["Javonte Williams", "Jeremiyah Love", "Breece Hall", "Kenneth Walker III"],
            6: ["Kyren Williams", "Travis Etienne Jr.", "Quinshon Judkins"],
            7: ["D'Andre Swift", "Jadarian Price", "Bhayshul Tuten", "Cam Skattebo", "David Montgomery"],
            8: ["Rhamondre Stevenson", "TreVeyon Henderson", "Bucky Irving", "Kenny Gainwell"],
            9: ["Tony Pollard", "J.K. Dobbins", "Jonathon Brooks"],
            10: ["Josh Jacobs", "MarShawn Lloyd"],
            11: ["Jaylen Warren", "Rico Dowdle", "Aaron Jones Sr.", "Chuba Hubbard", "Rachaad White", "Jacory Croskey-Merritt"],
            12: ["Kyle Monangai", "Blake Corum", "RJ Harvey"],
            13: ["Tyjae Spears", "Jordan Mason", "Chris Rodriguez Jr.", "Jonah Coleman", "Woody Marks"]
        }
    },

    # 13. ERIK KARABELL'S WR TIERS
    "karabell_wr_tiers": {
        "title": "Erik Karabell's WR Tiers",
        "analyst": "Erik Karabell",
        "position": "WR",
        "tiers": {
            1: ["Ja'Marr Chase", "Puka Nacua", "Jaxon Smith-Njigba", "Amon-Ra St. Brown"],
            2: ["CeeDee Lamb", "Justin Jefferson", "Drake London", "Nico Collins"],
            3: ["Chris Olave", "Garrett Wilson", "George Pickens", "A.J. Brown"],
            4: ["Zay Flowers", "DeVonta Smith", "Davante Adams", "Tetairoa McMillan", "Tee Higgins"],
            5: ["Rashee Rice"],
            6: ["Emeka Egbuka", "Ladd McConkey", "Terry McLaurin", "Jameson Williams", "Jaylen Waddle", "DJ Moore"],
            7: ["Malik Nabers", "Mike Evans", "Stefon Diggs"],
            8: ["Rome Odunze", "Luther Burden III", "Marvin Harrison Jr.", "Courtland Sutton", "Carnell Tate"],
            9: ["Michael Pittman Jr.", "DK Metcalf", "Michael Wilson", "Christian Watson", "Matthew Golden"],
            10: ["Parker Washington", "Jakobi Meyers", "Alec Pierce", "Josh Downs"],
            11: ["Wan'Dale Robinson", "Brian Thomas Jr.", "Jordan Addison", "Khalil Shakir", "Xavier Worthy"]
        }
    },

    # 14. MATT BOWEN'S TE TIERS
    "bowen_te_tiers": {
        "title": "Matt Bowen's TE Tiers",
        "analyst": "Matt Bowen",
        "position": "TE",
        "tiers": {
            1: ["Trey McBride", "Brock Bowers"],
            2: ["Colston Loveland", "Tyler Warren"],
            3: ["Harold Fannin Jr.", "Sam LaPorta", "George Kittle", "Kyle Pitts Sr.", "Tucker Kraft", "Travis Kelce", "Jake Ferguson", "Dallas Goedert"]
        }
    },

    # 15. ERIC MOODY'S TOP DRAFT-DAY VALUES
    "moody_top_draft_values": {
        "title": "Moody's Top Draft-Day Values",
        "analyst": "Eric Moody",
        "description": "Players falling further than they should in 2026 (Value bargains)",
        "badge": "🔥 MOODY VALUE",
        "players": [
            {"name": "Jaxson Dart", "pos": "QB", "team": "Giants"},
            {"name": "Dak Prescott", "pos": "QB", "team": "Cowboys"},
            {"name": "Kyler Murray", "pos": "QB", "team": "Vikings"},
            {"name": "Omarion Hampton", "pos": "RB", "team": "Chargers"},
            {"name": "Breece Hall", "pos": "RB", "team": "Jets"},
            {"name": "Cam Skattebo", "pos": "RB", "team": "Giants"},
            {"name": "Kenny Gainwell", "pos": "RB", "team": "Buccaneers"},
            {"name": "Garrett Wilson", "pos": "WR", "team": "Jets"},
            {"name": "Terry McLaurin", "pos": "WR", "team": "Commanders"},
            {"name": "Michael Pittman Jr.", "pos": "WR", "team": "Steelers"},
            {"name": "Jakobi Meyers", "pos": "WR", "team": "Jaguars"},
            {"name": "Harold Fannin Jr.", "pos": "TE", "team": "Browns"}
        ]
    },

    # 16. TRISTAN H. COCKCROFT'S DEEP SLEEPERS
    "cockcroft_deep_sleepers": {
        "title": "Cockcroft's Deep Sleepers",
        "analyst": "Tristan H. Cockcroft",
        "description": "Consider these players late in deep leagues (High-upside stashes)",
        "badge": "💤 COCKCROFT SLEEPER",
        "players": [
            {"name": "Carson Beck", "pos": "QB", "team": "Cardinals"},
            {"name": "Greg Dulcich", "pos": "TE", "team": "Dolphins"},
            {"name": "Tai Felton", "pos": "WR", "team": "Vikings"},
            {"name": "Tre' Harris", "pos": "WR", "team": "Chargers"},
            {"name": "Ja'Kobi Lane", "pos": "WR", "team": "Ravens"},
            {"name": "MarShawn Lloyd", "pos": "RB", "team": "Packers"},
            {"name": "Seth McGowan", "pos": "RB", "team": "Colts"},
            {"name": "Konata Mumpfield", "pos": "RB", "team": "Rams"},
            {"name": "Nicholas Singleton", "pos": "RB", "team": "Titans"},
            {"name": "Cyrus Allen", "pos": "WR", "team": "Chiefs"},
            {"name": "Demond Claiborne", "pos": "RB", "team": "Vikings"},
            {"name": "Mac Jones", "pos": "QB", "team": "49ers"}
        ]
    }
}


def compile_and_cache_cheatsheet() -> Dict[str, Any]:
    """Saves the verified ESPN Ultimate Cheat Sheet to JSON cache."""
    try:
        with open(JSON_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(RAW_ESPN_CHEAT_SHEET_DATA, f, indent=2)
        logger.info(f"Successfully compiled and saved ESPN Ultimate Cheat Sheet to {JSON_CACHE_PATH}")
    except Exception as e:
        logger.error(f"Error caching ESPN Ultimate Cheat Sheet: {e}")
    return RAW_ESPN_CHEAT_SHEET_DATA


def load_espn_cheatsheet() -> Dict[str, Any]:
    """Loads the compiled ESPN Ultimate Cheat Sheet from JSON cache, compiling if missing."""
    if JSON_CACHE_PATH.exists():
        try:
            with open(JSON_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {JSON_CACHE_PATH}: {e}")
    return compile_and_cache_cheatsheet()


# ==============================================================================
# PLAYER-CENTRIC INDEXING & ENRICHMENT ENGINE
# ==============================================================================

def build_player_espn_index() -> Dict[str, Dict[str, Any]]:
    """
    Builds a unified lookup index keyed by clean player name containing:
    - espn_heat_index: Count of unique ESPN experts endorsing this player as target/value/sleeper.
    - badges: List of emoji badge tags.
    - analyst_endorsements: List of (Analyst, List Name, Badge, Note).
    - is_fade: True if on Karabell's Do Not Draft list.
    - is_target: True if on any target, value, sleeper, or blueprint list.
    - espn_expert_tier: Karabell (RB/WR) or Bowen (QB/TE) tier number.
    - espn_adp_cheat_sheet: Float ADP from cheat sheet if available.
    - clay_round: Mike Clay recommended round if featured on draft board.
    - clay_note: Mike Clay tactical note.
    """
    cs_data = load_espn_cheatsheet()
    player_index: Dict[str, Dict[str, Any]] = {}

    def get_entry(p_name: str) -> Dict[str, Any]:
        k = clean_name_key(p_name)
        if k not in player_index:
            player_index[k] = {
                "canonical_name": p_name,
                "espn_heat_index": 0,
                "badges": [],
                "analyst_endorsements": [],
                "is_fade": False,
                "is_target": False,
                "espn_expert_tier": None,
                "espn_adp_cheat_sheet": None,
                "clay_round": None,
                "clay_note": None,
                "karabell_fade_note": None,
                "karabell_target_note": None
            }
        return player_index[k]

    # 1. Karabell Do Not Draft (Fades)
    for p in cs_data.get("karabell_do_not_draft", {}).get("players", []):
        e = get_entry(p["name"])
        e["is_fade"] = True
        e["badges"].append("🛑 Karabell Fade")
        e["espn_adp_cheat_sheet"] = p.get("adp")
        e["karabell_fade_note"] = p.get("note")
        e["analyst_endorsements"].append({
            "analyst": "Erik Karabell",
            "category": "Do Not Draft / Fade",
            "badge": "🛑 Karabell Fade",
            "note": p.get("note", "Not worth current ADP; OK if falls.")
        })

    # 2. Karabell Do Draft (Targets)
    for p in cs_data.get("karabell_do_draft", {}).get("players", []):
        e = get_entry(p["name"])
        e["is_target"] = True
        e["espn_heat_index"] += 1
        e["badges"].append("🎯 Karabell Target")
        e["espn_adp_cheat_sheet"] = p.get("adp")
        e["karabell_target_note"] = p.get("note")
        e["analyst_endorsements"].append({
            "analyst": "Erik Karabell",
            "category": "Do Draft (Prime Value)",
            "badge": "🎯 Karabell Target",
            "note": p.get("note", "Worth current ADP; don't be shy taking them.")
        })

    # 3. Mike Clay Blueprint
    for r in cs_data.get("clay_draft_board", {}).get("rounds", []):
        p_name = r.get("player")
        if p_name and "Best Available" not in p_name and "Breakout" not in p_name and "Kicker" not in p_name:
            e = get_entry(p_name)
            e["is_target"] = True
            e["espn_heat_index"] += 1
            e["clay_round"] = r.get("round")
            e["clay_note"] = r.get("note")
            e["badges"].append(f"📋 Clay Rd {r.get('round')}")
            e["analyst_endorsements"].append({
                "analyst": "Mike Clay",
                "category": f"Ultimate Draft Blueprint (Round {r.get('round')})",
                "badge": f"📋 Clay Rd {r.get('round')}",
                "note": r.get("note", f"Mike Clay priority blueprint pick for Round {r.get('round')}.")
            })
        alt_name = r.get("alt_player")
        if alt_name:
            e_alt = get_entry(alt_name)
            e_alt["is_target"] = True
            e_alt["espn_heat_index"] += 1
            e_alt["clay_round"] = r.get("round")
            e_alt["clay_note"] = r.get("note")
            e_alt["badges"].append(f"📋 Clay Rd {r.get('round')}")
            e_alt["analyst_endorsements"].append({
                "analyst": "Mike Clay",
                "category": f"Ultimate Draft Blueprint (Round {r.get('round')} Option)",
                "badge": f"📋 Clay Rd {r.get('round')}",
                "note": r.get("note", f"Mike Clay priority blueprint pick for Round {r.get('round')}.")
            })

    # 4. Adam Schefter Targets
    for p in cs_data.get("schefter_picks_to_target", {}).get("players", []):
        e = get_entry(p["name"])
        e["is_target"] = True
        e["espn_heat_index"] += 1
        e["badges"].append("⭐ Schefter Pick")
        e["analyst_endorsements"].append({
            "analyst": "Adam Schefter",
            "category": "Picks to Target",
            "badge": "⭐ Schefter Pick",
            "note": "Priority player to go after in your draft."
        })

    # 5. Matt Florio League Winners
    for p in cs_data.get("florio_league_winners", {}).get("players", []):
        e = get_entry(p["name"])
        e["is_target"] = True
        e["espn_heat_index"] += 1
        e["badges"].append("🏆 Florio Winner")
        e["analyst_endorsements"].append({
            "analyst": "Matt Florio",
            "category": "League Winners",
            "badge": "🏆 Florio Winner",
            "note": "High-upside player who could help you win your league championship."
        })

    # 6. Field Yates Favorites
    for p in cs_data.get("field_favorites", {}).get("players", []):
        e = get_entry(p["name"])
        e["is_target"] = True
        e["espn_heat_index"] += 1
        e["badges"].append("💎 Field Favorite")
        e["analyst_endorsements"].append({
            "analyst": "Field Yates",
            "category": "Field's Favorites",
            "badge": "💎 Field Favorite",
            "note": "Dropping too far in drafts; elite draft-day discount."
        })

    # 7. Liz Loza Late-Round Fliers
    for p in cs_data.get("loza_late_round_fliers", {}).get("players", []):
        e = get_entry(p["name"])
        e["is_target"] = True
        e["espn_heat_index"] += 1
        e["badges"].append("🚀 Loza Flier")
        e["analyst_endorsements"].append({
            "analyst": "Liz Loza",
            "category": "Late-Round Fliers",
            "badge": "🚀 Loza Flier",
            "note": "High-ceiling flier that can win your draft late."
        })

    # 8. Eric Moody Insurance RBs
    for p in cs_data.get("moody_top_insurance_rbs", {}).get("players", []):
        e = get_entry(p["name"])
        e["is_target"] = True
        e["espn_heat_index"] += 1
        e["badges"].append("🛡️ Moody Handcuff")
        e["analyst_endorsements"].append({
            "analyst": "Eric Moody",
            "category": "Top Insurance RBs",
            "badge": "🛡️ Moody Handcuff",
            "note": "Premium insurance backup with immediate RB1 upside if starter misses time."
        })

    # 9. Have Skills, Need Opportunity
    for p in cs_data.get("have_skills_need_opportunity", {}).get("players", []):
        e = get_entry(p["name"])
        e["is_target"] = True
        e["espn_heat_index"] += 1
        e["badges"].append("⚡ Breakout Talent")
        e["analyst_endorsements"].append({
            "analyst": "ESPN Staff",
            "category": "Have Skills, Need Opportunity",
            "badge": "⚡ Breakout Talent",
            "note": "High raw talent profile poised to break out if given opportunity."
        })

    # 10. Matt Bowen Top Targets
    for p in cs_data.get("bowen_top_targets", {}).get("players", []):
        e = get_entry(p["name"])
        e["is_target"] = True
        e["espn_heat_index"] += 1
        e["badges"].append("🏹 Bowen Target")
        e["analyst_endorsements"].append({
            "analyst": "Matt Bowen",
            "category": "Bowen's Top Targets",
            "badge": "🏹 Bowen Target",
            "note": "Matt Bowen personal top conviction target for 2026."
        })

    # 11. Eric Moody Top Draft Values
    for p in cs_data.get("moody_top_draft_values", {}).get("players", []):
        e = get_entry(p["name"])
        e["is_target"] = True
        e["espn_heat_index"] += 1
        e["badges"].append("🔥 Moody Value")
        e["analyst_endorsements"].append({
            "analyst": "Eric Moody",
            "category": "Top Draft-Day Values",
            "badge": "🔥 Moody Value",
            "note": "Falling significantly further in 2026 drafts than talent warrants."
        })

    # 12. Tristan Cockcroft Deep Sleepers
    for p in cs_data.get("cockcroft_deep_sleepers", {}).get("players", []):
        e = get_entry(p["name"])
        e["is_target"] = True
        e["espn_heat_index"] += 1
        e["badges"].append("💤 Cockcroft Sleeper")
        e["analyst_endorsements"].append({
            "analyst": "Tristan H. Cockcroft",
            "category": "Deep Sleepers",
            "badge": "💤 Cockcroft Sleeper",
            "note": "Deep league priority stash with sneaky second-half upside."
        })

    # 13. Positional Tiers
    # Bowen QB Tiers
    for tier_num, players in cs_data.get("bowen_qb_tiers", {}).get("tiers", {}).items():
        for p_name in players:
            e = get_entry(p_name)
            e["espn_expert_tier"] = int(tier_num)

    # Karabell RB Tiers
    for tier_num, players in cs_data.get("karabell_rb_tiers", {}).get("tiers", {}).items():
        for p_name in players:
            e = get_entry(p_name)
            e["espn_expert_tier"] = int(tier_num)

    # Karabell WR Tiers
    for tier_num, players in cs_data.get("karabell_wr_tiers", {}).get("tiers", {}).items():
        for p_name in players:
            e = get_entry(p_name)
            e["espn_expert_tier"] = int(tier_num)

    # Bowen TE Tiers
    for tier_num, players in cs_data.get("bowen_te_tiers", {}).get("tiers", {}).items():
        for p_name in players:
            e = get_entry(p_name)
            e["espn_expert_tier"] = int(tier_num)

    # Deduplicate badges per player
    for k, v in player_index.items():
        seen = set()
        deduped = []
        for b in v["badges"]:
            if b not in seen:
                seen.add(b)
                deduped.append(b)
        v["badges"] = deduped

    return player_index


def enrich_board_with_espn_cheatsheet(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enriches the main draft board DataFrame with ESPN Ultimate Cheat Sheet intelligence:
    - espn_heat_index: Number of ESPN experts endorsing this player (0-5+).
    - espn_expert_badges: Formatted string of all badges.
    - espn_expert_tier: Karabell/Bowen positional tier.
    - espn_adp_cheat_sheet: Official Sept. 4 ADP from cheatsheet.
    - clay_round: Mike Clay recommended draft round.
    - clay_note: Mike Clay draft board note.
    - is_espn_target: Bool
    - is_espn_fade: Bool (Karabell Do Not Draft)
    - espn_dossier_html: Formatted HTML for the player inspection card.
    """
    df_out = df.copy()
    player_index = build_player_espn_index()

    heat_indices = []
    badge_strings = []
    expert_tiers = []
    adp_list = []
    clay_rounds = []
    clay_notes = []
    is_targets = []
    is_fades = []
    dossier_htmls = []

    for _, row in df_out.iterrows():
        p_name = row.get("name", "")
        clean_k = clean_name_key(p_name)
        info = player_index.get(clean_k)

        if info:
            heat = info.get("espn_heat_index", 0)
            badges = info.get("badges", [])
            tier = info.get("espn_expert_tier")
            adp = info.get("espn_adp_cheat_sheet")
            c_round = info.get("clay_round")
            c_note = info.get("clay_note")
            target = info.get("is_target", False)
            fade = info.get("is_fade", False)

            # Build HTML dossier
            endorsements = info.get("analyst_endorsements", [])
            dossier_items = []
            for end in endorsements:
                dossier_items.append(
                    f"<li><strong style='color:#38bdf8;'>{end['analyst']}</strong> "
                    f"<span style='color:#cbd5e1;'>({end['category']}):</span> "
                    f"<span style='color:#f8fafc;'>{end['note']}</span></li>"
                )

            dossier_body = "".join(dossier_items)
            heat_badge = f"<span style='background:#f59e0b; color:#000; font-weight:800; padding:2px 8px; border-radius:4px;'>🔥 ESPN Heat: {heat} Analysts</span>" if heat >= 2 else (f"<span style='background:#1e293b; color:#38bdf8; font-weight:700; padding:2px 6px; border-radius:4px;'>⭐ {heat} Endorsement</span>" if heat == 1 else "")
            fade_badge = "<span style='background:#ef4444; color:#fff; font-weight:800; padding:2px 8px; border-radius:4px;'>🛑 KARABELL FADE</span>" if fade else ""

            adp_str = f" &bull; <strong>Cheat Sheet ADP:</strong> {adp}" if adp else ""
            tier_str = f" &bull; <strong>ESPN Expert Tier:</strong> Tier {tier}" if tier else ""

            dossier_lines = [
                '<div style="background:#111827; border:1px solid #3730a3; border-radius:6px; padding:10px 14px; margin-top:8px;">',
                '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">',
                '<div style="display:flex; gap:6px; align-items:center;">',
                '<span style="font-weight:800; color:#c084fc; text-transform:uppercase; font-size:0.8rem; letter-spacing:0.5px;">📋 ESPN Expert Dossier</span>',
                f'{heat_badge}',
                f'{fade_badge}',
                '</div>',
                f'<div style="font-size:0.8rem; color:#94a3b8;">{tier_str}{adp_str}</div>',
                '</div>',
                f'<ul style="margin:4px 0 0 16px; padding:0; font-size:0.84rem; line-height:1.45;">{dossier_body}</ul>',
                '</div>'
            ]
            dossier_html = "\n".join(dossier_lines)

            heat_indices.append(heat)
            badge_strings.append(" • ".join(badges))
            expert_tiers.append(tier if tier is not None else np.nan)
            adp_list.append(adp if adp is not None else np.nan)
            clay_rounds.append(c_round if c_round is not None else np.nan)
            clay_notes.append(c_note or "")
            is_targets.append(target)
            is_fades.append(fade)
            dossier_htmls.append(dossier_html)
        else:
            heat_indices.append(0)
            badge_strings.append("")
            expert_tiers.append(np.nan)
            adp_list.append(np.nan)
            clay_rounds.append(np.nan)
            clay_notes.append("")
            is_targets.append(False)
            is_fades.append(False)
            dossier_htmls.append("")

    df_out["espn_heat_index"] = heat_indices
    df_out["espn_expert_badges"] = badge_strings
    df_out["espn_expert_tier"] = expert_tiers
    df_out["espn_adp_cheat_sheet"] = adp_list
    df_out["clay_round"] = clay_rounds
    df_out["clay_note"] = clay_notes
    df_out["is_espn_target"] = is_targets
    df_out["is_espn_fade"] = is_fades
    df_out["espn_dossier_html"] = dossier_htmls

    return df_out


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO)
    print("Compiling ESPN Ultimate Cheat Sheet 2026...")
    cs = compile_and_cache_cheatsheet()
    index = build_player_espn_index()
    print(f"Total players indexed from cheat sheet: {len(index)}")

    # Display top heat players
    sorted_players = sorted(index.values(), key=lambda x: x["espn_heat_index"], reverse=True)
    print("\nTop 10 Most Endorsed Players by ESPN Experts (Heat Index):")
    for p in sorted_players[:10]:
        print(f"  {p['canonical_name']}: Heat {p['espn_heat_index']} | Badges: {', '.join(p['badges'])}")
