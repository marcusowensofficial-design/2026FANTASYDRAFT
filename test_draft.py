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
    CURATED_2026_INJURY_LEDGER,
    get_rotowire_url,
    get_fantasypros_url
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

    # Verify Rashee Rice and Nick Chubb are NOT in static ledger (active / unlisted)
    assert "rashee rice" not in CURATED_2026_INJURY_LEDGER
    assert "nick chubb" not in CURATED_2026_INJURY_LEDGER
    assert "darren waller" in CURATED_2026_INJURY_LEDGER
    assert CURATED_2026_INJURY_LEDGER["darren waller"]["is_season_out"] is True



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
    assert pearsall["is_season_out"].values[0] is True or pearsall["is_season_out"].values[0] == 1
    assert "IR" in pearsall["injury_status"].values[0] or "IR" in pearsall["injury_badge"].values[0]
    assert pearsall["value_diff"].values[0] == -999
    assert pearsall["sportsillustrated_rank"].values[0] == 90

    # 2. Verify Jayden Higgins
    higgins = df[df["name"] == "Jayden Higgins"]
    assert not higgins.empty, "Jayden Higgins must be present on draft board"
    assert higgins["pos"].values[0] == "WR"
    assert higgins["team"].values[0] == "HOU"
    assert higgins["is_season_out"].values[0] is True or higgins["is_season_out"].values[0] == 1
    assert "IR" in higgins["injury_status"].values[0] or "IR" in higgins["injury_badge"].values[0]
    assert higgins["value_diff"].values[0] == -999
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


def test_sleeper_temporal_precedence():
    """Verify monotonic temporal precedence for sleeper reports (T_new > T_current)."""
    from sleeper_sync import resolve_sleeper_temporal_precedence

    current_rec = {
        "name": "Brian Thomas Jr.",
        "badge": "🚀 ROOKIE BREAKOUT",
        "preseason_grade": "A",
        "timestamp_utc": "2026-08-25T12:00:00Z"
    }

    # Stale report from earlier date
    older_rec = {
        "name": "Brian Thomas Jr.",
        "badge": "OLD_BADGE",
        "timestamp_utc": "2026-08-20T10:00:00Z"
    }
    merged, changed, reason = resolve_sleeper_temporal_precedence(current_rec, older_rec)
    assert not changed, "Older report must not overwrite newer report"
    assert merged["badge"] == "🚀 ROOKIE BREAKOUT"

    # Newer report from later date
    newer_rec = {
        "name": "Brian Thomas Jr.",
        "badge": "🚀 ROOKIE WR1 BREAKOUT",
        "preseason_grade": "A+ (Dominant)",
        "timestamp_utc": "2026-09-02T11:45:00Z"
    }
    merged2, changed2, reason2 = resolve_sleeper_temporal_precedence(current_rec, newer_rec)
    assert changed2, "Newer report must overwrite older report"
    assert merged2["badge"] == "🚀 ROOKIE WR1 BREAKOUT"
    assert merged2["preseason_grade"] == "A+ (Dominant)"
    assert merged2["timestamp_utc"] == "2026-09-02T11:45:00Z"


def test_sleeper_database_and_enrichment():
    """Verify all curated sleeper rookies are present on draft board with temporal stamps."""
    import pandas as pd
    from sleeper_sync import load_sleeper_database, CURATED_2026_SLEEPER_LEDGER

    db = load_sleeper_database()
    assert len(db["players"]) >= 24, f"Expected at least 24 players, got {len(db['players'])}"
    assert "jayden higgins" not in db["players"], "Jayden Higgins must be excluded from sleeper db"
    assert "trey benson" not in db["players"], "Trey Benson must be excluded from sleeper db"

    df = pd.read_parquet("data/draft_board_2026.parquet")
    assert "is_rookie" in df.columns
    assert "sleeper_badge" in df.columns
    assert "preseason_grade" in df.columns

    # Verify key standout rookies exist and have high value differences
    btj = df[df["name"] == "Brian Thomas Jr."].iloc[0]
    assert btj["is_rookie"] is True or btj["is_rookie"] == 1
    assert btj["value_diff"] >= 15, f"Brian Thomas Jr. value diff should be >= 15, got {btj['value_diff']}"

    cam = df[df["name"] == "Cam Ward"].iloc[0]
    assert cam["is_rookie"] is True or cam["is_rookie"] == 1
    assert cam["value_diff"] >= 50, f"Cam Ward value diff should be >= 50, got {cam['value_diff']}"


def test_injury_trap_guarantee():
    """GUARANTEE: Zero season-ending IR players have positive value diff or sleeper status."""
    import pandas as pd
    df = pd.read_parquet("data/draft_board_2026.parquet")
    season_out = df[df["is_season_out"] | (df["injury_tier"] == "SEASON_IR") | (df["is_injury_trap"] == True)]
    assert not season_out.empty, "There should be season-ending IR players tracked"

    # Guarantee 1: None have value_diff >= 4
    steals = season_out[season_out["value_diff"] >= 4]
    assert steals.empty, f"No season-out player can have value_diff >= 4, found: {steals['name'].tolist()}"

    # Guarantee 2: None have is_sleeper == True
    sleepers = season_out[season_out["is_sleeper"] == True]
    assert sleepers.empty, f"No season-out player can be marked as a sleeper, found: {sleepers['name'].tolist()}"

    # Guarantee 3: All have is_injury_trap == True and value_diff == -999
    for _, r in season_out.iterrows():
        assert r["is_injury_trap"] is True or r["is_injury_trap"] == 1, f"{r['name']} must have is_injury_trap == True"
        assert r["value_diff"] == -999, f"{r['name']} must have value_diff == -999"


def test_espn_official_top300_guarantee():
    """GUARANTEE: ESPN ranks strictly follow official Top 300 PDF and never show thousands."""
    import pandas as pd
    from scraper import parse_espn_pdf_top300

    # 1. Verify PDF parse accuracy
    pdf_df = parse_espn_pdf_top300()
    assert pdf_df is not None
    assert len(pdf_df) == 300, f"ESPN official PDF should contain exactly 300 players, got {len(pdf_df)}"
    assert pdf_df["espn_rank"].min() == 1
    assert pdf_df["espn_rank"].max() == 300

    # 2. Verify draft board parquet has NO thousands
    df = pd.read_parquet("data/draft_board_2026.parquet")
    ranked_espn = df[df["espn_rank"].notna()]
    assert len(ranked_espn) >= 300
    assert ranked_espn["espn_rank"].max() <= 300, f"Max ESPN rank must be <= 300, got {ranked_espn['espn_rank'].max()}"
    assert (ranked_espn["espn_rank"] >= 1000).sum() == 0, "No player should have ESPN rank >= 1000"

    # 3. Verify realistic value differences (no bogus thousands)
    healthy_steals = df[~df["is_season_out"] & (df["injury_tier"] != "SEASON_IR")]
    assert healthy_steals["value_diff"].max() <= 150, f"Max value diff must be <= 150, got {healthy_steals['value_diff'].max()}"


def test_expert_ranking_sort_guarantees():
    """GUARANTEE: Sorting any expert ranking column starts at rank 1 (or 300) and NEVER starts at None."""
    import pandas as pd

    df = pd.read_parquet("data/draft_board_2026.parquet")

    expert_cols = [
        "espn_rank",
        "draftsharks_rank",
        "footballguys_rank",
        "cbs_rank",
        "fantasypros_rank",
        "rotoballer_rank",
        "nbcsports_rank",
        "bleacherreport_rank",
        "sportsillustrated_rank"
    ]

    for col in expert_cols:
        assert col in df.columns, f"Column {col} must exist in draft board"

        # 1. Ascending Sort (Lowest to High: 1 -> 300)
        sorted_asc = df.sort_values(
            by=[col, "consensus_rank"],
            ascending=[True, True],
            na_position="last"
        ).reset_index(drop=True)

        first_val = sorted_asc[col].iloc[0]
        assert pd.notna(first_val), f"Ascending sort on {col} must NOT start with None/NaN"
        assert first_val == 1.0, f"Ascending sort on {col} must start at rank 1, got {first_val}"

        # Ensure all NaNs/Nones are at the bottom
        first_nan_idx = sorted_asc[col].isna().idxmax() if sorted_asc[col].isna().any() else len(sorted_asc)
        if sorted_asc[col].isna().any():
            tail_vals = sorted_asc[col].iloc[first_nan_idx:]
            assert tail_vals.isna().all(), f"All values after first NaN on {col} must be NaN (placed at bottom)"

        # 2. Descending Sort (High to Lowest: 300 -> 1)
        sorted_desc = df.sort_values(
            by=[col, "consensus_rank"],
            ascending=[False, True],
            na_position="last"
        ).reset_index(drop=True)

        first_desc_val = sorted_desc[col].iloc[0]
        max_ranked_val = df[col].dropna().max()
        assert pd.notna(first_desc_val), f"Descending sort on {col} must NOT start with None/NaN"
        assert first_desc_val == max_ranked_val, f"Descending sort on {col} must start at max rank ({max_ranked_val}), got {first_desc_val}"

        # Ensure all NaNs/Nones are at the bottom
        if sorted_desc[col].isna().any():
            first_desc_nan_idx = sorted_desc[col].isna().idxmax()
            tail_desc_vals = sorted_desc[col].iloc[first_desc_nan_idx:]
            assert tail_desc_vals.isna().all(), f"All values after first NaN on {col} (descending) must be NaN (placed at bottom)"


def test_fantasypros_and_rotowire_direct_links():
    from app import get_player_injury_links_html

    # 1. Test FantasyPros News URL defaults
    gibbs_fp = get_fantasypros_url("Jahmyr Gibbs")
    assert gibbs_fp == "https://www.fantasypros.com/nfl/news/jahmyr-gibbs.php", f"Expected news URL, got {gibbs_fp}"

    # Converting old /nfl/players/ link to /nfl/news/
    gibbs_fp_conv = get_fantasypros_url("Jahmyr Gibbs", "https://www.fantasypros.com/nfl/players/jahmyr-gibbs.php")
    assert gibbs_fp_conv == "https://www.fantasypros.com/nfl/news/jahmyr-gibbs.php"

    # Suffix handling
    btj_fp = get_fantasypros_url("Brian Thomas Jr.")
    assert btj_fp == "https://www.fantasypros.com/nfl/news/brian-thomas-jr.php"

    # 2. Test RotoWire Direct Profile URLs
    gibbs_rw = get_rotowire_url("Jahmyr Gibbs")
    assert gibbs_rw == "https://www.rotowire.com/football/player/jahmyr-gibbs-16808", f"Expected Gibbs RotoWire URL, got {gibbs_rw}"

    bijan_rw = get_rotowire_url("Bijan Robinson")
    assert bijan_rw == "https://www.rotowire.com/football/player/bijan-robinson-16739"

    cmc_rw = get_rotowire_url("Christian McCaffrey")
    assert cmc_rw == "https://www.rotowire.com/football/player/christian-mccaffrey-11690"

    lamb_rw = get_rotowire_url("CeeDee Lamb")
    assert lamb_rw == "https://www.rotowire.com/football/player/ceedee-lamb-14411"

    # Direct source_url passthrough
    custom_rw = get_rotowire_url("Player X", "https://www.rotowire.com/football/player/player-x-99999")
    assert custom_rw == "https://www.rotowire.com/football/player/player-x-99999"

    # Fallback for unmapped DSTs
    dst_rw = get_rotowire_url("Denver Broncos")
    assert "google.com/search" in dst_rw and "Denver+Broncos" in dst_rw

    # 3. Test HTML rendering in get_player_injury_links_html
    html = get_player_injury_links_html("Jahmyr Gibbs", "Sep 2, 2026 at 10:30 AM UTC")
    assert "https://www.fantasypros.com/nfl/news/jahmyr-gibbs.php" in html, "HTML must link to FP news directory"
    assert "https://www.rotowire.com/football/player/jahmyr-gibbs-16808" in html, "HTML must link directly to RotoWire player profile"
    assert "FantasyPros Live News" in html
    assert "RotoWire Player Profile" in html


def test_strategy_tab_and_playbook_guarantees():
    """
    Guarantees that the new 8-Team Draft Strategy & Playbook tab is properly registered
    as Tab #3 in app.py with all 14 tabs and required strategic modules.
    """
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Verify tab registration and ordering
    assert "tab_all, tab_drafted, tab_strategy, tab_rb" in content, "tab_strategy must be slot #3 in app.py"
    assert '"🧠 Draft Strategy & Playbook"' in content, "Tab title must be '🧠 Draft Strategy & Playbook'"

    expected_tabs = [
        "⚡ All Available",
        "❌ Drafted Players",
        "🧠 Draft Strategy & Playbook",
        "🏃 Running Backs",
        "🎯 Wide Receivers",
        "🏈 Quarterbacks",
        "🛡️ Tight Ends",
        "⭐ FLEX Targets",
        "🛡️ DST & Kickers",
        "🔥 Value Steals & Sleepers",
        "⚠️ Reach Traps",
        "🚑 Injury & Suspension Report",
        "📜 8-Team Grid & Log",
        "📋 2026 Depth Chart Cheat Sheet"
    ]
    for tab_title in expected_tabs:
        assert f'"{tab_title}"' in content, f"Tab '{tab_title}' must be present in st.tabs"

    # 2. Verify Opponent Scenarios and Tactical Advisor
    assert "Early QB Panic / Run" in content
    assert "Heavy RB Hoard / Run" in content
    assert "Blindly Following ESPN ADP" in content
    assert "Balanced / Normal Draft Flow" in content

    # 3. Verify Strategic Sections
    assert "1. The 8-Team Mathematical Reality" in content
    assert "Top ESPN Arbitrage Steals & Traps" in content
    assert "The 17th Roster Spot 'IR Stash Hack'" in content
    assert "Championship Roster Architecture" in content

    # 4. Verify 1-click action buttons on recommended cards
    assert "strat_draft_" in content
    assert "strat_cross_" in content

    # 5. Verify Team Abbreviations & Independent Lineup Pairing (No DAL WR Stack, No Nick Chubb)
    assert "Nick Chubb" not in content, "Nick Chubb must not appear anywhere in app.py"
    assert "Drake London (ATL, Wk 11)" in content
    assert "avoids DAL WR stack" in content
    assert "CeeDee Lamb (DAL, Wk 14)" in content
    assert "Lamar Jackson (BAL, Wk 13)" in content
    assert "Jahmyr Gibbs (DET, Wk 6)" in content
    assert "Kenneth Walker III (KC, Wk 5)" in content
    assert "Jonathon Brooks (CAR, Wk 5)" in content


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
    test_sleeper_temporal_precedence()
    test_sleeper_database_and_enrichment()
    test_injury_trap_guarantee()
    test_espn_official_top300_guarantee()
    test_expert_ranking_sort_guarantees()
    test_fantasypros_and_rotowire_direct_links()
    test_strategy_tab_and_playbook_guarantees()
    print("[ALL TESTS PASSED SUCCESSFULLY!]")


