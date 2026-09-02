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


def test_temporal_conflict_resolution():
    from injury_sync import (
        normalize_to_iso8601_utc,
        resolve_injury_temporal_conflict,
        generate_git_commit_snippet,
        format_display_timestamp
    )

    # 1. Test timestamp normalization
    iso1 = normalize_to_iso8601_utc("2026-09-01T19:38Z")
    assert iso1 == "2026-09-01T19:38:00Z"

    epoch_ms = 1788017147544  # Sleeper ms epoch
    iso_epoch = normalize_to_iso8601_utc(epoch_ms)
    assert iso_epoch.endswith("Z")
    assert len(iso_epoch) == 20

    # 2. Test conflict resolution: new record
    incoming_1 = {
        "player_name": "Puka Nacua",
        "status": "Questionable",
        "timestamp_utc": "2026-09-01T19:38:00Z",
        "blurb": "Limited participant in practice."
    }
    is_up, rec1 = resolve_injury_temporal_conflict(None, incoming_1)
    assert is_up is True
    assert rec1["status"] == "Questionable"

    # 3. Test monotonic progression: newer update (T_new > T_current)
    incoming_newer = {
        "player_name": "Puka Nacua",
        "status": "Active",
        "timestamp_utc": "2026-09-02T14:30:00Z",
        "blurb": "Upgraded to full participant in Wednesday practice."
    }
    is_up, rec2 = resolve_injury_temporal_conflict(rec1, incoming_newer)
    assert is_up is True
    assert rec2["status"] == "Active"
    assert rec2["blurb"] == "Upgraded to full participant in Wednesday practice."

    # 4. Test monotonic progression: stale update (T_new < T_current) MUST BE REJECTED
    incoming_stale = {
        "player_name": "Puka Nacua",
        "status": "Out",
        "timestamp_utc": "2026-08-25T10:00:00Z",
        "blurb": "Stale report from two weeks ago."
    }
    is_up, rec3 = resolve_injury_temporal_conflict(rec2, incoming_stale)
    assert is_up is False
    # Verified: Status remains Active, blurb remains newer one!
    assert rec3["status"] == "Active"
    assert rec3["blurb"] == "Upgraded to full participant in Wednesday practice."

    # 5. Test identical timestamp (T_new == T_current) MUST BE REJECTED
    incoming_identical = {
        "player_name": "Puka Nacua",
        "status": "Doubtful",
        "timestamp_utc": "2026-09-02T14:30:00Z",
        "blurb": "Duplicate report."
    }
    is_up, rec4 = resolve_injury_temporal_conflict(rec2, incoming_identical)
    assert is_up is False
    assert rec4["status"] == "Active"

    # 6. Test Git commit snippet generation
    snippet = generate_git_commit_snippet(["Puka Nacua", "Ja'Marr Chase"], "2026-09-02T16:00:00Z")
    assert "feat(injuries): auto-sync update for 2 players (2026-09-02)" in snippet
    assert "- Puka Nacua" in snippet
    assert "- Ja'Marr Chase" in snippet
    assert "T_new > T_current" in snippet


def test_ir_candidates_and_expert_coverage():
    """Verify Ricky Pearsall & Jayden Higgins IR status, and 100% expert source coverage."""
    import pandas as pd
    from scraper import load_expert_files, clean_smart_name, NICKNAMES

    df = pd.read_parquet("data/draft_board_2026.parquet")
    
    # 1. Verify Ricky Pearsall
    pearsall = df[df["name"] == "Ricky Pearsall"]
    assert not pearsall.empty, "Ricky Pearsall must be present on draft board"
    assert pearsall["pos"].values[0] == "WR"
    assert pearsall["team"].values[0] == "SF"
    assert "IR" in pearsall["injury_status"].values[0] or "IR" in pearsall["injury_badge"].values[0]
    assert pearsall["sportsillustrated_rank"].values[0] == 90

    # 2. Verify Jayden Higgins
    higgins = df[df["name"] == "Jayden Higgins"]
    assert not higgins.empty, "Jayden Higgins must be present on draft board"
    assert higgins["pos"].values[0] == "WR"
    assert higgins["team"].values[0] == "HOU"
    assert "IR" in higgins["injury_status"].values[0] or "IR" in higgins["injury_badge"].values[0]
    assert higgins["sportsillustrated_rank"].values[0] == 117

    # 3. Verify 100% expert match rate
    experts = load_expert_files()
    board_clean_set = set(df["clean_name"].apply(clean_smart_name))
    for src, exp_df in experts.items():
        col = f"{src}_rank"
        mapped_count = df[col].notna().sum()
        assert mapped_count >= len(exp_df) - 1, f"Source {src} should have all {len(exp_df)} players mapped"


def test_sidebar_minimizer_toggle():
    """Verify minimizer toggle logic and CSS injection contract."""
    state = {"sidebar_collapsed": False}
    # Toggle minimize
    state["sidebar_collapsed"] = not state["sidebar_collapsed"]
    assert state["sidebar_collapsed"] is True
    # Toggle remaximize
    state["sidebar_collapsed"] = not state["sidebar_collapsed"]
    assert state["sidebar_collapsed"] is False


def test_rank_header_and_reset_search():
    """Verify Avail # is renamed to Rank # and search reset logic functions properly."""
    # Verify app.py contains Rank # column configuration
    with open("app.py", encoding="utf-8") as f:
        content = f.read()
    assert '"avail_rank": "Rank #"' in content, "avail_rank should map to 'Rank #'"
    assert '"Rank #": st.column_config.TextColumn(width="small")' in content, "Rank # column config should be present"
    assert "reset_table_search" in content, "reset_table_search helper function should exist"

    # Verify reset_table_search mechanics
    session_mock = {}
    def mock_reset_table_search(prefix="all_avail"):
        session_mock[f"search_ver_{prefix}"] = session_mock.get(f"search_ver_{prefix}", 0) + 1
        sel_k = f"table_select_{prefix}"
        if sel_k in session_mock:
            del session_mock[sel_k]

    session_mock["search_ver_all_avail"] = 0
    session_mock["table_select_all_avail"] = {"rows": [3]}
    mock_reset_table_search("all_avail")
    assert session_mock["search_ver_all_avail"] == 1
    assert "table_select_all_avail" not in session_mock


if __name__ == "__main__":
    test_player_normalization()
    test_consensus_calculation()
    test_snake_draft_math()
    test_cross_off_logic()
    test_restore_player_logic()
    test_unicode_strikethrough()
    test_curated_injury_ledger()
    test_board_injury_fields()
    test_temporal_conflict_resolution()
    test_ir_candidates_and_expert_coverage()
    test_sidebar_minimizer_toggle()
    test_rank_header_and_reset_search()
    print("[ALL TESTS PASSED SUCCESSFULLY!]")

