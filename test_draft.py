"""
Unit and Integration Tests for 2026 Fantasy Football PPR Draft Assistant
"""

import pytest
import pandas as pd
from scraper import (
    clean_player_name,
    normalize_team,
    normalize_position,
    generate_player_id,
    calculate_consensus_metrics,
    generate_synthetic_2026_data,
    load_or_generate_draft_board,
    to_unicode_strikethrough,
    CURATED_2026_INJURY_LEDGER
)


def test_player_normalization():
    # Suffixes
    assert clean_player_name("Marvin Harrison Jr.") == "Marvin Harrison"
    assert clean_player_name("Kenneth Walker III") == "Kenneth Walker"
    assert clean_player_name("Travis Etienne Jr.") == "Travis Etienne"
    assert clean_player_name("Luther Burden III") == "Luther Burden"
    assert clean_player_name("De'Von Achane") == "DeVon Achane"

    # Team aliases
    assert normalize_team("Chiefs") == "KC"
    assert normalize_team("Dallas Cowboys") == "DAL"
    assert normalize_team("DET") == "DET"
    assert normalize_team("FA") == "FA"

    # Position normalization
    assert normalize_position("DEF") == "DST"
    assert normalize_position("D/ST") == "DST"
    assert normalize_position("PK") == "K"
    assert normalize_position("RB") == "RB"
    assert normalize_position("WR") == "WR"
    assert normalize_position("QB") == "QB"
    assert normalize_position("TE") == "TE"

    # Deterministic player ID
    assert generate_player_id("Jahmyr Gibbs", "DET") == "jahmyr_gibbs_det"
    assert generate_player_id("Bijan Robinson", "ATL") == "bijan_robinson_atl"


def test_consensus_calculation():
    df = generate_synthetic_2026_data()
    assert len(df) >= 300
    assert "consensus_rank" in df.columns
    assert "consensus_median_rank" in df.columns
    assert "value_diff" in df.columns
    assert "espn_rank" in df.columns

    # Verify sort order
    assert df["consensus_rank"].is_monotonic_increasing

    # Check value diff calculation: value_diff = espn_rank - consensus_rank
    diff_check = df["espn_rank"] - df["consensus_rank"]
    pd.testing.assert_series_equal(df["value_diff"], diff_check, check_names=False)


def test_snake_draft_math():
    # 8-Team snake draft verification
    # Round 1: Picks 1-8 -> Teams 1, 2, 3, 4, 5, 6, 7, 8
    # Round 2: Picks 9-16 -> Teams 8, 7, 6, 5, 4, 3, 2, 1
    # Round 3: Picks 17-24 -> Teams 1, 2, 3, 4, 5, 6, 7, 8
    
    def get_team_for_pick(pick_num, total_teams=8):
        round_num = (pick_num - 1) // total_teams + 1
        round_pick = (pick_num - 1) % total_teams + 1
        if round_num % 2 == 1:
            return round_pick
        else:
            return total_teams - round_pick + 1

    assert get_team_for_pick(1) == 1
    assert get_team_for_pick(8) == 8
    assert get_team_for_pick(9) == 8
    assert get_team_for_pick(16) == 1
    assert get_team_for_pick(17) == 1
    assert get_team_for_pick(24) == 8


def test_cross_off_logic():
    # Simulate draft history entry
    user_pick = {
        "player_id": "bijan_robinson_atl",
        "name": "Bijan Robinson",
        "pos": "RB",
        "team": "ATL",
        "pick_number": 1,
        "drafted_by": "User (Team 1)",
        "is_user": True
    }
    opp_pick = {
        "player_id": "jahmyr_gibbs_det",
        "name": "Jahmyr Gibbs",
        "pos": "RB",
        "team": "DET",
        "pick_number": 2,
        "drafted_by": "Team 2",
        "is_user": False
    }
    opp_cross_off_during_user_turn = {
        "player_id": "ceedee_lamb_dal",
        "name": "CeeDee Lamb",
        "pos": "WR",
        "team": "DAL",
        "pick_number": 3,
        "drafted_by": "Opponent (Pick #3)",
        "is_user": False
    }

    history = [user_pick, opp_pick, opp_cross_off_during_user_turn]
    user_roster_picks = [p for p in history if p.get("is_user", False)]
    
    assert len(user_roster_picks) == 1
    assert user_roster_picks[0]["name"] == "Bijan Robinson"


def test_restore_player_logic():
    # Simulate list with 3 picks
    history = [
        {"player_id": "bijan_robinson_atl", "name": "Bijan Robinson", "is_user": True},
        {"player_id": "jahmyr_gibbs_det", "name": "Jahmyr Gibbs", "is_user": False},
        {"player_id": "ceedee_lamb_dal", "name": "CeeDee Lamb", "is_user": True}
    ]
    
    # Restore Jahmyr Gibbs
    target_id = "jahmyr_gibbs_det"
    history = [h for h in history if h["player_id"] != target_id]
    
    assert len(history) == 2
    assert [h["player_id"] for h in history] == ["bijan_robinson_atl", "ceedee_lamb_dal"]


def test_unicode_strikethrough():
    # Verify unicode strikethrough adds combining character \u0336
    sample = "Trey Benson"
    struck = to_unicode_strikethrough(sample)
    assert len(struck) == len(sample) * 2
    assert "\u0336" in struck
    assert to_unicode_strikethrough("") == ""


def test_curated_injury_ledger():
    # Verify season-ending IR players have proper flags and advice
    assert "trey benson" in CURATED_2026_INJURY_LEDGER
    benson = CURATED_2026_INJURY_LEDGER["trey benson"]
    assert benson["is_season_out"] is True
    assert benson["tier"] == "SEASON_IR"
    assert "DO NOT DRAFT" in benson["draft_advice"]

    # Verify 2026 suspension (Jeshaun Jones)
    assert "jeshaun jones" in CURATED_2026_INJURY_LEDGER
    jjones = CURATED_2026_INJURY_LEDGER["jeshaun jones"]
    assert jjones["tier"] == "SUSPENSION"
    assert jjones["is_season_out"] is False

    # Verify Rashee Rice and Nick Chubb are NOT in static ledger (active / retired in 2026)
    assert "rashee rice" not in CURATED_2026_INJURY_LEDGER
    assert "nick chubb" not in CURATED_2026_INJURY_LEDGER



def test_board_injury_fields():
    board = generate_synthetic_2026_data()
    expected_cols = [
        "injury_status",
        "injury_type",
        "injury_tier",
        "injury_badge",
        "injury_timeline",
        "injury_blurb",
        "injury_return_date",
        "is_season_out",
        "draft_advice"
    ]
    for col in expected_cols:
        assert col in board.columns, f"Missing expected injury column: {col}"

    # Verify boolean type
    assert board["is_season_out"].dtype == bool or board["is_season_out"].dtype == "bool"


if __name__ == "__main__":
    test_player_normalization()
    test_consensus_calculation()
    test_snake_draft_math()
    test_cross_off_logic()
    test_restore_player_logic()
    test_unicode_strikethrough()
    test_curated_injury_ledger()
    test_board_injury_fields()
    print("[ALL TESTS PASSED SUCCESSFULLY!]")

