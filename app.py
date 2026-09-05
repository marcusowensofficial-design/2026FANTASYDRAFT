"""
2026 Fantasy Football PPR Draft Assistant - Production Streamlit App
Ultra-fast, dark-mode 8-Team PPR Draft Board with live 90-second pick clock,
instant player striking, multi-expert consensus metrics, 8-team roster tracking,
and zero horizontal scrolling.
"""

import time
import json
import re
import urllib.parse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import streamlit as st
import pandas as pd
import numpy as np

from scraper import (
    load_or_generate_draft_board,
    clean_player_name,
    normalize_position,
    to_unicode_strikethrough,
    enrich_board_with_injuries,
    get_rotowire_url,
    get_fantasypros_url,
    TEAM_BYE_WEEKS_2026,
    PARQUET_FILE,
    DATA_DIR
)
from injury_sync import (
    sync_injury_pipeline,
    load_injury_database,
    save_injury_database,
    mark_database_committed,
    generate_git_commit_snippet,
    format_display_timestamp
)
from sleeper_sync import (
    sync_sleeper_pipeline,
    load_sleeper_database,
    save_sleeper_database,
    enrich_board_with_sleepers,
    format_user_friendly_utc
)
from espn_cheatsheet import (
    load_espn_cheatsheet,
    build_player_espn_index,
    enrich_board_with_espn_cheatsheet,
    clean_name_key,
    RAW_ESPN_CHEAT_SHEET_DATA
)

# -----------------------------------------------------------------------------
# 1. STREAMLIT PAGE CONFIGURATION & CUSTOM DARK THEME CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="2026 PPR Draft Assistant | 8-Team Live War Room",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 0. STREAMLIT MARKDOWN HTML CODE-BLOCK PREVENTER
# -----------------------------------------------------------------------------
# Guarantees HTML cards, badges, alerts, and dossiers NEVER render as raw indented code blocks.
# In CommonMark/markdown-it, lines with 4+ spaces of indentation are parsed as <pre><code>.
# Stripping leading whitespace per line ensures all HTML elements start at column 0.
_orig_st_markdown = st.markdown

def _safe_st_markdown(body, *args, **kwargs):
    if isinstance(body, str):
        s_body = body.strip()
        # Preserve genuine fenced code blocks
        if s_body.startswith("```") or s_body.startswith("~~~"):
            return _orig_st_markdown(body, *args, **kwargs)
        
        # If string contains HTML tags, strip leading indentation so markdown never treats it as code block
        if ("<div" in body or "<span" in body or "<style" in body or "<table" in body or 
            "<ul" in body or "<li" in body or "<p" in body or "<br" in body or "<strong" in body or 
            "<hr" in body or "<a " in body):
            lines = [l.lstrip() for l in body.splitlines()]
            if s_body.startswith("<") and s_body.endswith(">"):
                lines = [l for l in lines if l]
            body = "\n".join(lines)
            kwargs["unsafe_allow_html"] = True
    return _orig_st_markdown(body, *args, **kwargs)

st.markdown = _safe_st_markdown

# Injected CSS for ultra-dense, responsive dark UI
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

    html, body, [class*="css"], .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
        -webkit-font-smoothing: antialiased !important;
        -moz-osx-font-smoothing: grayscale !important;
        text-rendering: optimizeLegibility !important;
        background-color: #0a0d14 !important;
        color: #f8fafc !important;
    }

    /* Force dark background on all Streamlit layout wrappers */
    .stApp, 
    [data-testid="stAppViewContainer"], 
    [data-testid="stHeader"], 
    [data-testid="stToolbar"],
    section.main {
        background-color: #0a0d14 !important;
        color: #f8fafc !important;
    }

    [data-testid="stSidebar"], 
    [data-testid="stSidebarContent"],
    section[data-testid="stSidebar"] {
        background-color: #111827 !important;
        border-right: 1px solid #1e293b !important;
    }

    header[data-testid="stHeader"] {
        background-color: transparent !important;
    }

    /* Custom sleek dark scrollbars for Chrome / WebKit */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #0a0d14;
    }
    ::-webkit-scrollbar-thumb {
        background: #1e293b;
        border-radius: 4px;
        border: 1px solid #0f172a;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #334155;
    }

    /* Dark cyber-athletic palette */
    :root {
        --bg-primary: #0a0d14;
        --bg-card: #111827;
        --bg-card-hover: #1f2937;
        --border-color: #1e293b;
        --text-main: #f8fafc;
        --text-muted: #94a3b8;
        --accent-blue: #38bdf8;
        --accent-green: #10b981;
        --accent-gold: #f59e0b;
        --accent-red: #ef4444;
        --accent-purple: #a855f7;
    }

    /* Container padding and tight layout */
    .block-container {
        padding-top: 0.75rem !important;
        padding-bottom: 1.5rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
        max-width: 100% !important;
    }

    /* Header banner */
    .war-room-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
        border: 1px solid #3730a3;
        border-radius: 10px;
        padding: 10px 18px;
        margin-bottom: 10px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    }
    
    .war-room-title {
        font-size: 1.35rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        background: linear-gradient(90deg, #38bdf8, #818cf8, #c084fc);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }

    /* Status and clock pill */
    .status-badge-clock {
        background: #1e1b4b;
        border: 1px solid #6366f1;
        color: #e0e7ff;
        padding: 4px 12px;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.85rem;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }

    .status-badge-ontheclock {
        background: linear-gradient(90deg, #991b1b, #dc2626);
        color: #ffffff;
        padding: 5px 14px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 0.9rem;
        animation: pulse 1.5s infinite;
        border: 1px solid #f87171;
        box-shadow: 0 0 15px rgba(220, 38, 38, 0.5);
    }

    @keyframes pulse {
        0%, 100% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.02); opacity: 0.92; }
    }

    /* Recommendation bar */
    .best-avail-bar {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 6px 14px;
        margin-bottom: 10px;
        display: flex;
        gap: 16px;
        align-items: center;
        font-size: 0.8rem;
        overflow-x: auto;
    }

    /* Position badges */
    .pos-badge {
        display: inline-block;
        padding: 2px 7px;
        border-radius: 5px;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.4px;
        text-align: center;
    }
    .pos-RB { background-color: #064e3b; color: #34d399; border: 1px solid #059669; }
    .pos-WR { background-color: #1e3a8a; color: #60a5fa; border: 1px solid #2563eb; }
    .pos-QB { background-color: #7f1d1d; color: #f87171; border: 1px solid #dc2626; }
    .pos-TE { background-color: #78350f; color: #fbbf24; border: 1px solid #d97706; }
    .pos-DST { background-color: #581c87; color: #c084fc; border: 1px solid #9333ea; }
    .pos-K { background-color: #134e4a; color: #2dd4bf; border: 1px solid #0d9488; }

    /* Roster tracker cards */
    .roster-card {
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 6px;
        padding: 6px 10px;
        margin-bottom: 5px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .roster-card-empty {
        border: 1px dashed #374151;
        background: #0b0f19;
        color: #6b7280;
    }
    .roster-slot-title {
        font-size: 0.72rem;
        font-weight: 700;
        color: #9ca3af;
        text-transform: uppercase;
        width: 55px;
    }
    .roster-player-name {
        font-size: 0.82rem;
        font-weight: 600;
        color: #f9fafb;
    }

    /* Executive Cyber-Athletic Strategy Card Styles */
    .strategy-card {
        background: linear-gradient(135deg, rgba(17, 24, 39, 0.85) 0%, rgba(15, 23, 42, 0.85) 100%);
        border: 1px solid #1e293b;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 16px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        backdrop-filter: blur(8px);
    }
    .strategy-card-accent-blue {
        border-left: 4px solid #38bdf8;
    }
    .strategy-card-accent-green {
        border-left: 4px solid #10b981;
    }
    .strategy-card-accent-purple {
        border-left: 4px solid #a855f7;
    }
    .strategy-card-accent-gold {
        border-left: 4px solid #f59e0b;
    }
    .strategy-card-accent-red {
        border-left: 4px solid #ef4444;
    }
    .strategy-header-title {
        font-size: 1.15rem;
        font-weight: 800;
        color: #f8fafc;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
    }
    .advisor-callout {
        background: linear-gradient(90deg, rgba(30, 27, 75, 0.7) 0%, rgba(15, 23, 42, 0.7) 100%);
        border: 1px solid #4338ca;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 14px;
    }
    .recom-card {
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 8px;
        transition: all 0.15s ease-in-out;
    }
    .recom-card:hover {
        border-color: #38bdf8;
        background: #172033;
    }

    /* Compact Streamlit button overrides */
    div.stButton > button {
        border-radius: 7px;
        font-weight: 700;
        padding: 0.25rem 0.6rem;
        transition: all 0.15s ease-in-out;
    }
    div.stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    }

    /* Metrics compact */
    [data-testid="stMetricValue"] {
        font-size: 1.25rem !important;
        font-weight: 800 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.72rem !important;
        color: #94a3b8 !important;
    }

    /* Clean tab headers */
    [data-testid="stTab"] {
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        padding: 4px 12px !important;
    }
    [data-testid="stTab"][aria-selected="true"] {
        color: #38bdf8 !important;
        border-bottom-color: #38bdf8 !important;
        font-weight: 700 !important;
    }

    /* Checkbox labels */
    [data-testid="stCheckbox"] label span {
        font-size: 0.8rem !important;
        color: #cbd5e1 !important;
        font-weight: 500 !important;
    }

    /* Form input fields & selects */
    [data-testid="stTextInput"] input, [data-testid="stSelectbox"] div {
        font-size: 0.84rem !important;
    }

    /* Mobile & iPad / Tablet Responsive Enhancements (auto-detected on phones & iPads) */
    @media (max-width: 1024px) {
        .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
            padding-top: 0.5rem !important;
        }
        .war-room-header {
            flex-direction: column !important;
            align-items: flex-start !important;
            gap: 8px !important;
            padding: 8px 12px !important;
        }
        .war-room-title {
            font-size: 1.2rem !important;
        }
        .best-avail-bar {
            flex-wrap: wrap !important;
            gap: 6px !important;
            font-size: 0.76rem !important;
            padding: 6px 10px !important;
        }
        div.stButton > button {
            padding: 0.35rem 0.35rem !important;
            font-size: 0.78rem !important;
            white-space: nowrap !important;
        }
        [data-testid="column"] {
            min-width: 0 !important;
        }
        [data-testid="stTab"] {
            font-size: 0.78rem !important;
            padding: 3px 8px !important;
        }
        [data-testid="stDataFrame"] {
            -webkit-overflow-scrolling: touch !important;
        }
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 2. STATE INITIALIZATION & CONSTANTS
# -----------------------------------------------------------------------------
TOTAL_TEAMS = 8
ROSTER_ROUNDS = 16  # 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 DST, 1 K, 7 Bench = 16
TOTAL_PICKS = TOTAL_TEAMS * ROSTER_ROUNDS

# -----------------------------------------------------------------------------
# 2026 LEAGUE TEAMS & SNAKE PICK SCHEDULE (8 TEAMS, 16 ROUNDS)
# -----------------------------------------------------------------------------
LEAGUE_TEAMS_2026 = {
    1: {
        "slot": 1,
        "team_name": "Chiefs Kingdom",
        "picks": ["1.1", "2.8", "3.1", "4.8", "5.1", "6.8", "7.1", "8.8", "9.1", "10.8", "11.1", "12.8", "13.1", "14.8", "15.1", "16.8"],
        "overall_picks": [1, 16, 17, 32, 33, 48, 49, 64, 65, 80, 81, 96, 97, 112, 113, 128],
    },
    2: {
        "slot": 2,
        "team_name": "Blind Horse Named Dank",
        "picks": ["1.2", "2.7", "3.2", "4.7", "5.2", "6.7", "7.2", "8.7", "9.2", "10.7", "11.2", "12.7", "13.2", "14.7", "15.2", "16.7"],
        "overall_picks": [2, 15, 18, 31, 34, 47, 50, 63, 66, 79, 82, 95, 98, 111, 114, 127],
    },
    3: {
        "slot": 3,
        "team_name": "Mickey's Team",
        "picks": ["1.3", "2.6", "3.3", "4.6", "5.3", "6.6", "7.3", "8.6", "9.3", "10.6", "11.3", "12.6", "13.3", "14.6", "15.3", "16.6"],
        "overall_picks": [3, 14, 19, 30, 35, 46, 51, 62, 67, 78, 83, 94, 99, 110, 115, 126],
    },
    4: {
        "slot": 4,
        "team_name": "Ivey League",
        "picks": ["1.4", "2.5", "3.4", "4.5", "5.4", "6.5", "7.4", "8.5", "9.4", "10.5", "11.4", "12.5", "13.4", "14.5", "15.4", "16.5"],
        "overall_picks": [4, 13, 20, 29, 36, 45, 52, 61, 68, 77, 84, 93, 100, 109, 116, 125],
    },
    5: {
        "slot": 5,
        "team_name": "Ja'marr You Not Entertained?",
        "picks": ["1.5", "2.4", "3.5", "4.4", "5.5", "6.4", "7.5", "8.4", "9.5", "10.4", "11.5", "12.4", "13.5", "14.4", "15.5", "16.4"],
        "overall_picks": [5, 12, 21, 28, 37, 44, 53, 60, 69, 76, 85, 92, 101, 108, 117, 124],
    },
    6: {
        "slot": 6,
        "team_name": "Mara's Monstrous Team",
        "picks": ["1.6", "2.3", "3.6", "4.3", "5.6", "6.3", "7.6", "8.3", "9.6", "10.3", "11.6", "12.3", "13.6", "14.3", "15.6", "16.3"],
        "overall_picks": [6, 11, 22, 27, 38, 43, 54, 59, 70, 75, 86, 91, 102, 107, 118, 123],
    },
    7: {
        "slot": 7,
        "team_name": "Joe Brrrr-utality",
        "picks": ["1.7", "2.2", "3.7", "4.2", "5.7", "6.2", "7.7", "8.2", "9.7", "10.2", "11.7", "12.2", "13.7", "14.2", "15.7", "16.2"],
        "overall_picks": [7, 10, 23, 26, 39, 42, 55, 58, 71, 74, 87, 90, 103, 106, 119, 122],
    },
    8: {
        "slot": 8,
        "team_name": "Double Brown",
        "picks": ["1.8", "2.1", "3.8", "4.1", "5.8", "6.1", "7.8", "8.1", "9.8", "10.1", "11.8", "12.1", "13.8", "14.1", "15.8", "16.1"],
        "overall_picks": [8, 9, 24, 25, 40, 41, 56, 57, 72, 73, 88, 89, 104, 105, 120, 121],
    },
}

def get_league_team_name(slot: int) -> str:
    """Returns the official fantasy team name for an 8-team draft slot."""
    return LEAGUE_TEAMS_2026.get(slot, {}).get("team_name", f"Team {slot}")


def get_league_team_picks(slot: int) -> List[str]:
    """Returns the list of 16 round picks for an 8-team draft slot."""
    return LEAGUE_TEAMS_2026.get(slot, {}).get("picks", [])


def format_username_dropdown(slot: int, cur_on_clock_slot: Optional[int] = None) -> str:
    """Formats the username for dropdown with attached round picks (NO real owner names)."""
    team_info = LEAGUE_TEAMS_2026.get(slot, {})
    name = team_info.get("team_name", f"Team {slot}")
    picks = team_info.get("picks", [])
    # Display attached picks in dropdown: e.g. Chiefs Kingdom (Slot 1 • Picks: 1.1, 2.8, 3.1, 4.8, 5.1...)
    picks_str = ", ".join(picks[:5]) + "..." if len(picks) > 5 else ", ".join(picks)
    clock_tag = " 🔥 ON CLOCK" if cur_on_clock_slot is not None and slot == cur_on_clock_slot else ""
    return f"{name} (Slot #{slot} • Picks: {picks_str}){clock_tag}"


def set_active_username_slot(new_slot: int):
    """
    Updates the active draft user slot and aligns persona & is_user flags
    across the entire draft board, draft history, and UI metrics.
    """
    if new_slot != st.session_state.get("user_slot"):
        st.session_state.user_slot = new_slot
        st.session_state["top_bar_team_picker"] = new_slot
        st.session_state["sidebar_team_picker"] = new_slot
        # Re-align is_user flag in history
        for h in st.session_state.get("draft_history", []):
            h["is_user"] = (h.get("team_slot") == new_slot)
        # Re-align is_user flag in active DataFrame
        if "draft_board" in st.session_state:
            df = st.session_state.draft_board
            if "team_slot" in df.columns:
                df["is_user"] = (df["team_slot"] == new_slot)
            st.session_state.draft_board = df


if "draft_board" not in st.session_state:
    st.session_state.draft_board = load_or_generate_draft_board(force_refresh=False)

if "is_rookie" not in st.session_state.draft_board.columns:
    st.session_state.draft_board = enrich_board_with_sleepers(st.session_state.draft_board)

if "espn_heat_index" not in st.session_state.draft_board.columns:
    st.session_state.draft_board = enrich_board_with_espn_cheatsheet(st.session_state.draft_board)

if "team_slot" not in st.session_state.draft_board.columns:
    st.session_state.draft_board["team_slot"] = None

if "draft_history" not in st.session_state:
    st.session_state.draft_history = []  # Stack of picks for undo

if "current_pick" not in st.session_state:
    st.session_state.current_pick = 1

if "user_slot" not in st.session_state:
    st.session_state.user_slot = 1  # User draft position (1 to 8, default: Chiefs Kingdom)

if "clock_seconds" not in st.session_state:
    st.session_state.clock_seconds = 90

if "sidebar_collapsed" not in st.session_state:
    st.session_state.sidebar_collapsed = False


# -----------------------------------------------------------------------------
# 3. HELPER FUNCTIONS: DRAFT MECHANICS & SNAKE LOGIC
# -----------------------------------------------------------------------------
def get_snake_pick_info(pick_num: int, total_teams: int = TOTAL_TEAMS) -> Tuple[int, int, int, bool]:
    """
    Returns (round_num, round_pick, team_num, is_user)
    """
    if pick_num > TOTAL_PICKS:
        return (ROSTER_ROUNDS, total_teams, total_teams, False)
    
    round_num = (pick_num - 1) // total_teams + 1
    round_pick = (pick_num - 1) % total_teams + 1
    
    # Snake order: Odd rounds = 1 -> 8, Even rounds = 8 -> 1
    if round_num % 2 == 1:
        team_num = round_pick
    else:
        team_num = total_teams - round_pick + 1
        
    is_user = (team_num == st.session_state.user_slot)
    return round_num, round_pick, team_num, is_user


def execute_pick(
    player_id: str, 
    drafted_by_user: bool = False, 
    team_slot_override: Optional[int] = None,
    team_label: Optional[str] = None
):
    """
    Drafts a player, updates DataFrame in session state, and advances draft state.
    Records the exact team slot and username who made the pick.
    """
    df = st.session_state.draft_board
    idx = df.index[df["player_id"] == player_id].tolist()
    if not idx:
        return
    
    i = idx[0]
    if df.at[i, "is_drafted"]:
        st.warning(f"Player {df.at[i, 'name']} is already drafted.")
        return

    pick_num = st.session_state.current_pick
    rd, rpick, cur_snake_team, is_user_turn = get_snake_pick_info(pick_num)
    
    if drafted_by_user:
        assigned_slot = st.session_state.user_slot
        is_user = True
    elif team_slot_override is not None:
        assigned_slot = team_slot_override
        is_user = (assigned_slot == st.session_state.user_slot)
    else:
        # Default to team whose turn it is on the snake pick clock
        assigned_slot = cur_snake_team
        is_user = (assigned_slot == st.session_state.user_slot)

    assigned_team_name = get_league_team_name(assigned_slot)
    if team_label is None:
        team_label = assigned_team_name

    # Update row
    df.at[i, "is_drafted"] = True
    df.at[i, "draft_round"] = rd
    df.at[i, "pick_number"] = pick_num
    df.at[i, "team_slot"] = assigned_slot
    df.at[i, "drafted_by"] = team_label
    df.at[i, "is_user"] = is_user

    # Save to history stack for instant undo
    st.session_state.draft_history.append({
        "player_id": player_id,
        "name": df.at[i, "name"],
        "pos": df.at[i, "pos"],
        "team": df.at[i, "team"],
        "pick_number": pick_num,
        "draft_round": rd,
        "round_pick": rpick,
        "team_slot": assigned_slot,
        "drafted_by": team_label,
        "is_user": is_user
    })

    # Advance pick & reset clock
    st.session_state.current_pick = min(TOTAL_PICKS + 1, pick_num + 1)
    st.session_state.clock_seconds = 90
    st.session_state.draft_board = df


def undo_last_pick():
    """Rolls back the most recent pick."""
    if not st.session_state.draft_history:
        st.toast("No picks to undo!", icon="⚠️")
        return

    last_action = st.session_state.draft_history.pop()
    player_id = last_action["player_id"]

    df = st.session_state.draft_board
    idx = df.index[df["player_id"] == player_id].tolist()
    if idx:
        i = idx[0]
        df.at[i, "is_drafted"] = False
        df.at[i, "draft_round"] = 0
        df.at[i, "pick_number"] = 0
        df.at[i, "team_slot"] = None
        df.at[i, "drafted_by"] = ""
        df.at[i, "is_user"] = False

    st.session_state.current_pick = max(1, len(st.session_state.draft_history) + 1)
    st.session_state.draft_board = df
    st.toast(f"Undid pick: {last_action['name']}", icon="↩️")


def restore_player(player_id: str):
    """
    Restores any specific drafted/crossed-off player back to the available queue at their original rank.
    """
    df = st.session_state.draft_board
    idx = df.index[df["player_id"] == player_id].tolist()
    if not idx:
        return

    i = idx[0]
    p_name = df.at[i, "name"]
    p_rank = df.at[i, "consensus_rank"]

    # Reset player row
    df.at[i, "is_drafted"] = False
    df.at[i, "draft_round"] = 0
    df.at[i, "pick_number"] = 0
    df.at[i, "team_slot"] = None
    df.at[i, "drafted_by"] = ""
    df.at[i, "is_user"] = False

    # Remove from history
    st.session_state.draft_history = [
        h for h in st.session_state.draft_history if h["player_id"] != player_id
    ]

    # Recalculate current pick
    st.session_state.current_pick = max(1, len(st.session_state.draft_history) + 1)
    st.session_state.draft_board = df
    st.toast(f"Restored {p_name} (Consensus #{p_rank}) back to the draft board!", icon="🔄")


def reset_draft_board():
    """Resets entire draft board to pristine state."""
    df = st.session_state.draft_board
    df["is_drafted"] = False
    df["draft_round"] = 0
    df["pick_number"] = 0
    df["team_slot"] = None
    df["drafted_by"] = ""
    df["is_user"] = False
    st.session_state.draft_board = df
    st.session_state.draft_history = []
    st.session_state.current_pick = 1
    st.session_state.clock_seconds = 90
    st.toast("Draft board successfully reset!", icon="🔄")


def get_player_injury_links_html(player_name: str, report_time: Optional[str] = None, source_url: Optional[str] = None) -> str:
    """Generates direct profile and real-time injury tracking links for FantasyPros and RotoWire with timestamp."""
    fp_url = get_fantasypros_url(player_name, source_url)
    rw_url = get_rotowire_url(player_name, source_url)
    
    time_html = ""
    if report_time:
        time_html = f'<span style="color:#94a3b8; font-size:0.75rem; margin-left:auto;">🕒 <strong>Updated:</strong> {report_time}</span>'
    
    return (
        f'<div style="margin-top:8px; padding-top:6px; border-top:1px dashed rgba(255,255,255,0.18); display:flex; flex-wrap:wrap; gap:8px; align-items:center;">'
        f'<span style="color:#cbd5e1; font-size:0.8rem; font-weight:700;">📡 Live Injury Wire & Beat History:</span>'
        f'<a href="{fp_url}" target="_blank" rel="noopener noreferrer" style="background:#1e293b; color:#38bdf8; text-decoration:none; padding:3px 10px; border-radius:5px; font-size:0.78rem; font-weight:700; border:1px solid #38bdf850; display:inline-flex; align-items:center; gap:4px;">'
        f'⚡ FantasyPros Live News ↗'
        f'</a>'
        f'<a href="{rw_url}" target="_blank" rel="noopener noreferrer" style="background:#1e293b; color:#fb923c; text-decoration:none; padding:3px 10px; border-radius:5px; font-size:0.78rem; font-weight:700; border:1px solid #fb923c50; display:inline-flex; align-items:center; gap:4px;">'
        f'📰 RotoWire Player Profile ↗'
        f'</a>'
        f'{time_html}'
        f'</div>'
    )


def get_team_roster(team_slot: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Computes any 8-team league member's PPR starting lineup (9 starters: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 D/ST, 1 K),
    7 bench slots, and 1 dedicated IR stash slot for injured/suspended players.
    """
    team_picks = [p for p in st.session_state.draft_history if p.get("team_slot") == team_slot]
    
    roster: Dict[str, List[Dict[str, Any]]] = {
        "QB": [],
        "RB": [],
        "WR": [],
        "TE": [],
        "FLEX": [],
        "DST": [],
        "K": [],
        "BENCH": [],
        "IR": []
    }

    df_b = st.session_state.draft_board
    ir_eligible = []
    active_pool = []
    
    for p in team_picks:
        p_id = p["player_id"]
        p_row = df_b[df_b["player_id"] == p_id]
        inj_tier = p_row.iloc[0].get("injury_tier", "") if not p_row.empty else ""
        is_ir = p_row.iloc[0].get("is_season_out", False) if not p_row.empty else False
        
        # Eligible for IR stash if player is on PUP, Season IR, Suspension, or Out
        if inj_tier in ["PUP_MULTI_WEEK", "SEASON_IR", "SUSPENSION", "OUT_WEEK_1"] or is_ir:
            p_copy = dict(p)
            p_copy["injury_badge"] = p_row.iloc[0].get("injury_badge", "⚠️ IR")
            p_copy["injury_tier"] = inj_tier
            ir_eligible.append(p_copy)
        else:
            active_pool.append(p)
            
    # Step 1: Assign healthy/active players to 9 starting slots first
    remaining_pool = []
    for p in active_pool:
        pos = p["pos"]
        if pos == "QB" and len(roster["QB"]) < 1:
            roster["QB"].append(p)
        elif pos == "RB" and len(roster["RB"]) < 2:
            roster["RB"].append(p)
        elif pos == "WR" and len(roster["WR"]) < 2:
            roster["WR"].append(p)
        elif pos == "TE" and len(roster["TE"]) < 1:
            roster["TE"].append(p)
        elif pos in ["RB", "WR", "TE"] and len(roster["FLEX"]) < 1:
            roster["FLEX"].append(p)
        elif pos == "DST" and len(roster["DST"]) < 1:
            roster["DST"].append(p)
        elif pos == "K" and len(roster["K"]) < 1:
            roster["K"].append(p)
        else:
            remaining_pool.append(p)
            
    # Step 2: Dedicated 1 IR stash slot (first eligible stash player goes here)
    if ir_eligible:
        roster["IR"].append(ir_eligible[0])
        for p in ir_eligible[1:]:
            remaining_pool.append(p)
            
    # Step 3: Fill any remaining starting slot voids from remaining pool
    final_bench = []
    for p in remaining_pool:
        pos = p["pos"]
        if pos == "QB" and len(roster["QB"]) < 1:
            roster["QB"].append(p)
        elif pos == "RB" and len(roster["RB"]) < 2:
            roster["RB"].append(p)
        elif pos == "WR" and len(roster["WR"]) < 2:
            roster["WR"].append(p)
        elif pos == "TE" and len(roster["TE"]) < 1:
            roster["TE"].append(p)
        elif pos in ["RB", "WR", "TE"] and len(roster["FLEX"]) < 1:
            roster["FLEX"].append(p)
        elif pos == "DST" and len(roster["DST"]) < 1:
            roster["DST"].append(p)
        elif pos == "K" and len(roster["K"]) < 1:
            roster["K"].append(p)
        else:
            final_bench.append(p)
            
    roster["BENCH"] = final_bench
    return roster


def get_user_roster() -> Dict[str, List[Dict[str, Any]]]:
    """
    Computes active chosen user's 8-team PPR starting lineup (9 starters: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 D/ST, 1 K),
    7 bench slots, and 1 dedicated IR stash slot for injured/suspended players.
    """
    return get_team_roster(st.session_state.user_slot)


# -----------------------------------------------------------------------------
# 4. TOP BAR: STATUS, CLOCK, ON-THE-CLOCK INDICATOR
# -----------------------------------------------------------------------------
cur_rd, cur_rpick, cur_team, is_user_turn = get_snake_pick_info(st.session_state.current_pick)

# Calculate next pick for user
next_picks = []
for p_idx in range(st.session_state.current_pick, TOTAL_PICKS + 1):
    _, _, t_num, is_u = get_snake_pick_info(p_idx)
    if is_u:
        next_picks.append(p_idx)
        if len(next_picks) >= 3:
            break

picks_until_user = (next_picks[0] - st.session_state.current_pick) if next_picks else 0

# Minimizer logic & CSS override when Live Draft Control is minimized
if st.session_state.get("sidebar_collapsed", False):
    st.markdown("""
    <style>
        [data-testid="stSidebar"], 
        section[data-testid="stSidebar"],
        [data-testid="stSidebarContent"] {
            display: none !important;
            width: 0px !important;
            min-width: 0px !important;
            max-width: 0px !important;
            transform: translateX(-100%) !important;
        }
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
        .stApp [data-testid="stAppViewContainer"] > section.main {
            margin-left: 0 !important;
            width: 100vw !important;
            max-width: 100vw !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        .block-container {
            max-width: 100% !important;
            width: 100% !important;
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # High-visibility remaximize bar at top of page
    c_rem1, c_rem2 = st.columns([3.5, 6.5])
    with c_rem1:
        if st.button("▶ 🏆 Show Draft Control & Roster", key="btn_remaximize_banner", type="primary", use_container_width=True, help="Click to restore the Live Draft Control and starting lineup sidebar"):
            st.session_state.sidebar_collapsed = False
            st.rerun()
    with c_rem2:
        st.markdown("""
        <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 8px; padding: 7px 14px; color: #38bdf8; font-size: 0.83rem; display: flex; align-items: center; gap: 8px; height: 100%;">
            <span>📱</span> <span><strong>Full Screen Mode Active:</strong> Live Draft Control is minimized so tables and expert rankings take up 100% of your screen on Mobile & iPad. Click button to restore.</span>
        </div>
        """, unsafe_allow_html=True)

st.markdown(f"""
<div class="war-room-header">
    <div>
        <h1 class="war-room-title">⚡ 2026 FANTASY FOOTBALL PPR DRAFT WAR ROOM</h1>
        <div style="color: #94a3b8; font-size: 0.8rem; margin-top: 2px;">
            8-Team PPR League &bull; Multi-Expert Consensus &bull; 90-Sec Clock &bull; Zero Lag Engine
        </div>
    </div>
    <div style="display: flex; gap: 10px; align-items: center;">
        {f'<div class="status-badge-ontheclock">🚨 YOU ARE ON THE CLOCK!</div>' if is_user_turn and st.session_state.current_pick <= TOTAL_PICKS else f'<div class="status-badge-clock">⏳ {get_league_team_name(cur_team)} On Clock (Pick {cur_rd}.{cur_rpick})</div>'}
        <div class="status-badge-clock">
            <span>Round {cur_rd}</span> &bull; <span>Pick {cur_rpick}</span> &bull; <span style="color:#38bdf8;">Overall #{min(st.session_state.current_pick, TOTAL_PICKS)}</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4B. TOP WAR ROOM CHOOSE USERNAME DROPDOWN & ATTACHED ROUND PICK SCHEDULE
# -----------------------------------------------------------------------------
top_team_col1, top_team_col2 = st.columns([4.2, 5.8])
with top_team_col1:
    top_user_slot = st.selectbox(
        "👤 Choose Username",
        options=list(range(1, TOTAL_TEAMS + 1)),
        index=st.session_state.user_slot - 1,
        format_func=lambda s: format_username_dropdown(s, cur_team),
        key="top_bar_team_picker",
        help="Choose your username to configure your draft slot, attach your 16-round picks, and guide your live draft."
    )
    if top_user_slot != st.session_state.user_slot:
        set_active_username_slot(top_user_slot)
        st.rerun()

with top_team_col2:
    cur_team_info = LEAGUE_TEAMS_2026.get(st.session_state.user_slot, {})
    all_team_picks = cur_team_info.get("picks", [])
    all_team_ovr = cur_team_info.get("overall_picks", [])
    remaining_picks = [
        (p, ovr, rd)
        for rd, (p, ovr) in enumerate(zip(all_team_picks, all_team_ovr), start=1)
        if ovr >= st.session_state.current_pick
    ]

    if remaining_picks:
        next_p_label, next_ovr, next_rd = remaining_picks[0]
        p_diff = next_ovr - st.session_state.current_pick
        diff_str = "NOW! 🔥" if p_diff == 0 else f"in {p_diff} picks (Pick #{next_ovr})"
        chips_str = " &bull; ".join(
            [f"<strong>Rd {rd} ({p})</strong>: #{ovr}" for p, ovr, rd in remaining_picks[:5]]
        )
        st.markdown(f"""
        <div style="background: rgba(15, 23, 42, 0.85); border: 1px solid #38bdf8; border-radius: 8px; padding: 6px 12px; margin-top: 1px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:700; color:#38bdf8;">🏈 Active Drafter: {cur_team_info.get('team_name')} (Slot #{st.session_state.user_slot})</span>
                <span style="font-size:0.75rem; color:{'#f59e0b' if p_diff == 0 else '#e2e8f0'}; font-weight:700;">Next Turn: {diff_str}</span>
            </div>
            <div style="color: #94a3b8; font-size: 0.74rem; margin-top: 2px;">
                Upcoming Picks: {chips_str}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background: rgba(15, 23, 42, 0.85); border: 1px solid #10b981; border-radius: 8px; padding: 6px 12px; margin-top: 1px;">
            <span style="font-weight:700; color:#10b981;">✓ {cur_team_info.get('team_name')}</span> &bull; All 16 Draft Rounds Completed!
        </div>
        """, unsafe_allow_html=True)

    with st.expander(f"📋 View Attached 16-Round Picks & Pick Guide for {cur_team_info.get('team_name')}", expanded=False):
        sched_chips = []
        for rd_idx, (p_str, ovr) in enumerate(zip(all_team_picks, all_team_ovr), start=1):
            past_pick = [h for h in st.session_state.draft_history if h.get("team_slot") == st.session_state.user_slot and h.get("draft_round") == rd_idx]
            if past_pick:
                p_item = past_pick[0]
                status_txt = f"<span style='color:#10b981; font-weight:700;'>✓ {p_item['name']} ({p_item['pos']})</span>"
                bg_c = "rgba(16, 185, 129, 0.15)"
                border_c = "#059669"
            elif ovr == st.session_state.current_pick:
                status_txt = "<span style='color:#f59e0b; font-weight:800;'>🔥 ON CLOCK</span>"
                bg_c = "rgba(245, 158, 11, 0.25)"
                border_c = "#f59e0b"
            elif ovr > st.session_state.current_pick:
                diff = ovr - st.session_state.current_pick
                status_txt = f"<span style='color:#94a3b8;'>In {diff} picks (#{ovr})</span>"
                bg_c = "#0f172a"
                border_c = "#334155"
            else:
                status_txt = "<span style='color:#64748b;'>Passed</span>"
                bg_c = "#0f172a"
                border_c = "#1e293b"

            sched_chips.append(f"""
            <div style="background:{bg_c}; border:1px solid {border_c}; border-radius:6px; padding:4px 8px; font-size:0.75rem;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <strong style="color:#f8fafc;">Rd {rd_idx} ({p_str})</strong>
                    {status_txt}
                </div>
            </div>
            """)

        st.markdown(f'<div style="display:grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-bottom: 6px;">{"".join(sched_chips)}</div>', unsafe_allow_html=True)
        st.caption("Snake Pick Logic: Odd rounds pick 1st to 8th • Even rounds reverse 8th to 1st. Use Tab 11 for the full league matrix.")




# -----------------------------------------------------------------------------
# 5. BEST AVAILABLE QUICK RADAR
# -----------------------------------------------------------------------------
df_board = st.session_state.draft_board
available_df = df_board[~df_board["is_drafted"]].copy().reset_index(drop=True)
available_df["avail_rank"] = available_df.index + 1

# Exclude season-ending IR and algorithmic injury traps from BPA quick radar recommendations
radar_avail_df = available_df[
    (~available_df["is_season_out"]) & 
    (available_df.get("injury_tier", "") != "SEASON_IR") & 
    (~available_df.get("is_injury_trap", False))
].reset_index(drop=True)

top_overall = radar_avail_df.iloc[0] if not radar_avail_df.empty else None
top_rb = radar_avail_df[radar_avail_df["pos"] == "RB"].iloc[0] if not radar_avail_df[radar_avail_df["pos"] == "RB"].empty else None
top_wr = radar_avail_df[radar_avail_df["pos"] == "WR"].iloc[0] if not radar_avail_df[radar_avail_df["pos"] == "WR"].empty else None
top_qb = radar_avail_df[radar_avail_df["pos"] == "QB"].iloc[0] if not radar_avail_df[radar_avail_df["pos"] == "QB"].empty else None
top_te = radar_avail_df[radar_avail_df["pos"] == "TE"].iloc[0] if not radar_avail_df[radar_avail_df["pos"] == "TE"].empty else None

st.markdown(f"""
<div class="best-avail-bar">
    <span style="font-weight:800; color:#38bdf8;">⚡ Top Available:</span>
    <span><strong>BPA:</strong> {top_overall['name'] if top_overall is not None else 'None'} ({top_overall['pos_tag'] if top_overall is not None else ''})</span>
    <span><span class="pos-badge pos-RB">RB</span> {top_rb['name'] if top_rb is not None else 'None'} (#{top_rb['consensus_rank'] if top_rb is not None else '-'})</span>
    <span><span class="pos-badge pos-WR">WR</span> {top_wr['name'] if top_wr is not None else 'None'} (#{top_wr['consensus_rank'] if top_wr is not None else '-'})</span>
    <span><span class="pos-badge pos-QB">QB</span> {top_qb['name'] if top_qb is not None else 'None'} (#{top_qb['consensus_rank'] if top_qb is not None else '-'})</span>
    <span><span class="pos-badge pos-TE">TE</span> {top_te['name'] if top_te is not None else 'None'} (#{top_te['consensus_rank'] if top_te is not None else '-'})</span>
</div>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 6. FAST ACTION QUICK-SEARCH BAR & LIVE CLOCK (TOP OF SCREEN)
# -----------------------------------------------------------------------------
search_col1, search_col2, search_col3, search_col4, search_col5, search_col6 = st.columns([3.6, 1.2, 1.2, 0.7, 1.3, 1.2])

# Format player choices for instant autocomplete
player_options = {}
for _, row in available_df.iterrows():
    val_str = f"+{row['value_diff']}" if row['value_diff'] > 0 else f"{row['value_diff']}"
    is_season_out_player = row.get("is_season_out") or row.get("injury_tier") == "SEASON_IR" or row.get("is_injury_trap")
    disp_n = f"🛑 [OUT FOR SEASON] {to_unicode_strikethrough(row['name'])}" if is_season_out_player else row["name"]
    badge_str = ""
    if row.get("injury_badge"):
        tl = row.get("injury_timeline", "")
        tl_str = f" [{tl}]" if tl else ""
        badge_str = f" {row['injury_badge']}{tl_str}"
    lbl = f"#{row['consensus_rank']} {disp_n}{badge_str} ({row['pos']} - {row['team']}, Bye {row['bye']}) | Tier {row['tier']} | Val: {val_str}"
    player_options[row["player_id"]] = lbl

with search_col1:
    selected_player_id = st.selectbox(
        "🔍 Quick Search & Fast Action Bar",
        options=list(player_options.keys()),
        format_func=lambda x: player_options.get(x, x),
        label_visibility="collapsed",
        placeholder="Type to search player name, team (KC, DET), or position (RB, WR)..."
    )

with search_col2:
    if st.button("🟩 Draft (My Team)", use_container_width=True, type="primary"):
        if selected_player_id:
            execute_pick(selected_player_id, drafted_by_user=True)
            st.rerun()

with search_col3:
    if st.button("⬛ Cross Off (Other)", use_container_width=True):
        if selected_player_id:
            execute_pick(selected_player_id, drafted_by_user=False)
            st.rerun()

with search_col4:
    if st.button("↩️ Undo", use_container_width=True, help="Undo the last drafted pick"):
        undo_last_pick()
        st.rerun()

with search_col5:
    # 90-Second Clock controls
    t_c1, t_c2, t_c3 = st.columns([1, 1, 1])
    with t_c1:
        if st.button("⏱️ 90s", use_container_width=True):
            st.session_state.clock_seconds = 90
            st.rerun()
    with t_c2:
        if st.button("+15s", use_container_width=True):
            st.session_state.clock_seconds += 15
            st.rerun()
    with t_c3:
        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.clock_seconds = 90
            st.rerun()

with search_col6:
    is_min = st.session_state.get("sidebar_collapsed", False)
    btn_label = "▶ 🏆 Control" if is_min else "📱 Fullscreen"
    btn_help = "Show Live Draft Control sidebar" if is_min else "Minimize Live Draft Control to view consensus tables fullscreen on Mobile/iPad"
    if st.button(btn_label, key="btn_toggle_sidebar_fastbar", help=btn_help, use_container_width=True):
        st.session_state.sidebar_collapsed = not is_min
        st.rerun()

# If top selected player has an active injury/suspension warning, display immediate alert banner
if selected_player_id:
    top_sel_matches = available_df[available_df["player_id"] == selected_player_id]
    if not top_sel_matches.empty:
        tsp = top_sel_matches.iloc[0]
        if tsp.get("injury_tier") == "SEASON_IR":
            st.markdown(f"""
            <div style="background:#450a0a; border:2px solid #ef4444; border-radius:8px; padding:8px 14px; margin-top:6px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="color:#f87171; font-weight:800; font-size:0.95rem;">🛑 INJURY ALERT: OUT FOR SEASON (IR) &bull; {tsp['name']} ({tsp['pos']} - {tsp['team']})</span>
                    <span style="background:#ef4444; color:#fff; font-size:0.7rem; font-weight:700; padding:2px 8px; border-radius:4px;">DO NOT DRAFT</span>
                </div>
                <div style="color:#fecaca; font-size:0.85rem; margin-top:2px;">
                    <strong>Timeline:</strong> {tsp.get('injury_timeline', 'Out for Season')} &bull; <strong>Diagnosis:</strong> {tsp.get('injury_type', 'Severe Injury')}
                </div>
                <div style="color:#f3f4f6; font-size:0.8rem; margin-top:2px;">
                    {tsp.get('injury_blurb', '')}
                </div>
                {get_player_injury_links_html(tsp['name'], tsp.get('injury_updated_formatted'), tsp.get('source_url'))}
            </div>
            """, unsafe_allow_html=True)
        elif tsp.get("injury_tier") == "SUSPENSION":
            st.markdown(f"""
            <div style="background:#3b0764; border:2px solid #c084fc; border-radius:8px; padding:8px 14px; margin-top:6px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="color:#e9d5ff; font-weight:800; font-size:0.95rem;">⛔ DISCIPLINE ALERT: SUSPENDED &bull; {tsp['name']} ({tsp['pos']} - {tsp['team']})</span>
                    <span style="background:#a855f7; color:#fff; font-size:0.7rem; font-weight:700; padding:2px 8px; border-radius:4px;">SUSPENDED</span>
                </div>
                <div style="color:#f3e8ff; font-size:0.85rem; margin-top:2px;">
                    <strong>Timeline:</strong> {tsp.get('injury_timeline', 'Suspended')} &bull; <strong>Reason:</strong> {tsp.get('injury_type', 'League Policy')}
                </div>
                <div style="color:#f3f4f6; font-size:0.8rem; margin-top:2px;">
                    {tsp.get('injury_blurb', '')} &bull; <em>Draft Strategy: {tsp.get('draft_advice', 'Mid-round stash')}</em>
                </div>
                {get_player_injury_links_html(tsp['name'], tsp.get('injury_updated_formatted'), tsp.get('source_url'))}
            </div>
            """, unsafe_allow_html=True)
        elif tsp.get("injury_tier") == "PUP_MULTI_WEEK":
            st.markdown(f"""
            <div style="background:#431407; border:2px solid #f97316; border-radius:8px; padding:8px 14px; margin-top:6px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="color:#fed7aa; font-weight:800; font-size:0.95rem;">⚠️ RESERVE / PUP ALERT: OUT 4+ WEEKS &bull; {tsp['name']} ({tsp['pos']} - {tsp['team']})</span>
                    <span style="background:#f97316; color:#fff; font-size:0.7rem; font-weight:700; padding:2px 8px; border-radius:4px;">MULTI-WEEK STASH</span>
                </div>
                <div style="color:#ffedd5; font-size:0.85rem; margin-top:2px;">
                    <strong>Timeline:</strong> {tsp.get('injury_timeline', 'Out min 4 weeks')} &bull; <strong>Injury:</strong> {tsp.get('injury_type', 'Rehab')}
                </div>
                <div style="color:#f3f4f6; font-size:0.8rem; margin-top:2px;">
                    {tsp.get('injury_blurb', '')} &bull; <em>Strategy: {tsp.get('draft_advice', 'Target in later rounds')}</em>
                </div>
                {get_player_injury_links_html(tsp['name'], tsp.get('injury_updated_formatted'), tsp.get('source_url'))}
            </div>
            """, unsafe_allow_html=True)
        elif tsp.get("injury_tier") == "OUT_WEEK_1":
            st.markdown(f"""
            <div style="background:#431407; border:2px solid #ea580c; border-radius:8px; padding:8px 14px; margin-top:6px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="color:#fdba74; font-weight:800; font-size:0.95rem;">🟠 OUT WEEK 1 (EXPECTED BACK WEEK 2) &bull; {tsp['name']} ({tsp['pos']} - {tsp['team']})</span>
                    <span style="background:#ea580c; color:#fff; font-size:0.7rem; font-weight:700; padding:2px 8px; border-radius:4px;">OUT WK 1 ONLY</span>
                </div>
                <div style="color:#fed7aa; font-size:0.85rem; margin-top:2px;">
                    <strong>Timeline:</strong> {tsp.get('injury_timeline', 'Out Wk 1 • Expected back Wk 2')} &bull; <strong>Status:</strong> Ruled Out Week 1 &bull; <strong>Condition:</strong> {tsp.get('injury_type', 'Short-term')}
                </div>
                <div style="color:#f3f4f6; font-size:0.8rem; margin-top:2px;">
                    {tsp.get('injury_blurb', '')} &bull; <em>Draft Strategy: {tsp.get('draft_advice', 'Safe to draft; will only miss opening game.')}</em>
                </div>
                {get_player_injury_links_html(tsp['name'], tsp.get('injury_updated_formatted'), tsp.get('source_url'))}
            </div>
            """, unsafe_allow_html=True)
        elif tsp.get("injury_tier") == "WEEK_1_RISK":
            st.markdown(f"""
            <div style="background:#422006; border:2px solid #eab308; border-radius:8px; padding:8px 14px; margin-top:6px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="color:#fef08a; font-weight:800; font-size:0.95rem;">🟡 QUESTIONABLE / WEEK 1 NOTE &bull; {tsp['name']} ({tsp['pos']} - {tsp['team']})</span>
                    <span style="background:#eab308; color:#000; font-size:0.7rem; font-weight:700; padding:2px 8px; border-radius:4px;">DAY-TO-DAY</span>
                </div>
                <div style="color:#fef9c3; font-size:0.85rem; margin-top:2px;">
                    <strong>Timeline:</strong> {tsp.get('injury_timeline', 'Target Week 1')} &bull; <strong>Condition:</strong> {tsp.get('injury_type', 'Day-to-day')}
                </div>
                <div style="color:#f3f4f6; font-size:0.8rem; margin-top:2px;">
                    {tsp.get('injury_blurb', '')}
                </div>
                {get_player_injury_links_html(tsp['name'], tsp.get('injury_updated_formatted'), tsp.get('source_url'))}
            </div>
            """, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 7. SIDEBAR: 8-TEAM ROSTER TRACKER, DRAFT POSITION & NEEDS
# -----------------------------------------------------------------------------
with st.sidebar:
    sb_c1, sb_c2 = st.columns([3, 1.2])
    with sb_c1:
        st.markdown("### 🏆 Live Draft Control")
    with sb_c2:
        if st.button("◀ Hide", key="btn_hide_sidebar_top", help="Minimize Live Draft Control to expand table view on Mobile/iPad/Desktop", use_container_width=True):
            st.session_state.sidebar_collapsed = True
            st.rerun()
    
    # User Team & Draft Slot Picker ("Choose Username")
    user_slot_input = st.selectbox(
        "👤 Choose Username",
        options=list(range(1, TOTAL_TEAMS + 1)),
        index=st.session_state.user_slot - 1,
        format_func=lambda s: format_username_dropdown(s, cur_team),
        key="sidebar_team_picker",
        help="Choose your username to configure your draft slot, attach your 16-round picks, and guide your live draft."
    )
    if user_slot_input != st.session_state.user_slot:
        set_active_username_slot(user_slot_input)
        st.rerun()

    # Attached 16-Round Pick Schedule Card
    sel_team_info = LEAGUE_TEAMS_2026.get(st.session_state.user_slot, {})
    with st.expander(f"📋 {sel_team_info.get('team_name', 'Your Team')} Pick Schedule (16 Rounds)", expanded=False):
        picks_list = sel_team_info.get("picks", [])
        overall_list = sel_team_info.get("overall_picks", [])

        schedule_html = '<div style="display:grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 0.76rem;">'
        for rd_idx, (p_str, ovr) in enumerate(zip(picks_list, overall_list), start=1):
            is_past = ovr < st.session_state.current_pick
            is_cur = ovr == st.session_state.current_pick

            if is_cur:
                card_bg = "rgba(56, 189, 248, 0.25)"
                border_c = "#38bdf8"
                status_icon = "<span style='color:#f59e0b; font-weight:800;'>🔥 NOW</span>"
            elif is_past:
                card_bg = "rgba(15, 23, 42, 0.6)"
                border_c = "#1e293b"
                past_p = [h for h in st.session_state.draft_history if h.get("team_slot") == st.session_state.user_slot and h.get("draft_round") == rd_idx]
                if past_p:
                    status_icon = f"<span style='color:#10b981; font-weight:700;' title='{past_p[0]['name']}'>✓ {past_p[0]['name'][:12]} ({past_p[0]['pos']})</span>"
                else:
                    status_icon = "<span style='color:#10b981;'>✓ Done</span>"
            else:
                card_bg = "#0f172a"
                border_c = "#334155"
                status_icon = f"<span style='color:#64748b;'>#{ovr}</span>"

            schedule_html += f'''
            <div style="background:{card_bg}; border:1px solid {border_c}; border-radius:5px; padding:3px 6px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-weight:700; color:#f8fafc;">Rd {rd_idx}: {p_str}</span>
                    <span style="font-size:0.7rem;">{status_icon}</span>
                </div>
            </div>
            '''
        schedule_html += '</div>'
        st.markdown(schedule_html, unsafe_allow_html=True)

    # Draft Progress Summary Metrics
    m1, m2 = st.columns(2)
    with m1:
        st.metric("Total Pick", f"#{min(st.session_state.current_pick, TOTAL_PICKS)} / {TOTAL_PICKS}")
    with m2:
        if is_user_turn:
            st.metric("Next Turn", "NOW! 🔥", delta="Your Pick", delta_color="normal")
        else:
            st.metric("Next Turn", f"in {picks_until_user} picks", delta=f"Pick #{next_picks[0]}" if next_picks else "Done")

    # Mobile / iPad 1-click full screen tables button
    if st.button("📱 Fullscreen Tables (Minimize)", key="btn_minimize_sidebar_mid", use_container_width=True, help="Hide sidebar to give maximum horizontal width to consensus ranking tables on iPad & Mobile"):
        st.session_state.sidebar_collapsed = True
        st.rerun()

    st.markdown("---")
    st.markdown(f"### 📋 {sel_team_info.get('team_name', 'My Team')} Lineup (PPR)")

    user_roster = get_user_roster()
    
    slots_def = [
        ("QB", 1),
        ("RB", 2),
        ("WR", 2),
        ("TE", 1),
        ("FLEX", 1),
        ("DST", 1),
        ("K", 1),
    ]

    total_starters_needed = 9
    total_starters_filled = 0
    all_user_byes = []

    for slot_name, count in slots_def:
        filled_list = user_roster.get(slot_name, [])
        for i in range(count):
            if i < len(filled_list):
                p = filled_list[i]
                total_starters_filled += 1
                bye_w = TEAM_BYE_WEEKS_2026.get(p.get("team", ""), 0)
                if bye_w > 0:
                    all_user_byes.append(bye_w)
                st.markdown(f"""
                <div class="roster-card">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span class="pos-badge pos-{p['pos']}">{p['pos']}</span>
                        <span class="roster-player-name">{p['name']}</span>
                    </div>
                    <div style="font-size:0.75rem; color:#94a3b8; font-weight:700;">
                        {p['team']} (Wk {bye_w})
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                label = slot_name if count == 1 else f"{slot_name} {i+1}"
                st.markdown(f"""
                <div class="roster-card roster-card-empty">
                    <span class="roster-slot-title">{label}</span>
                    <span style="font-size:0.8rem; font-style:italic;">Empty</span>
                </div>
                """, unsafe_allow_html=True)

    # Bench Slots (7 slots total as shown in ESPN image)
    TOTAL_BENCH_SLOTS = 7
    bench_list = user_roster.get("BENCH", [])
    st.markdown(f"**🪑 Bench ({len(bench_list)}/{TOTAL_BENCH_SLOTS} slots):**")
    for i in range(TOTAL_BENCH_SLOTS):
        if i < len(bench_list):
            b = bench_list[i]
            bye_w = TEAM_BYE_WEEKS_2026.get(b.get("team", ""), 0)
            if bye_w > 0:
                all_user_byes.append(bye_w)
            st.markdown(f"""
            <div class="roster-card">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span class="pos-badge pos-{b['pos']}">{b['pos']}</span>
                    <span class="roster-player-name">{b['name']}</span>
                </div>
                <div style="font-size:0.75rem; color:#94a3b8; font-weight:700;">
                    {b['team']} (Wk {bye_w})
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="roster-card roster-card-empty">
                <span class="roster-slot-title">Bench {i+1}</span>
                <span style="font-size:0.8rem; font-style:italic;">Empty</span>
            </div>
            """, unsafe_allow_html=True)

    # Dedicated 1 IR Slot (for injured/suspended stashes)
    ir_list = user_roster.get("IR", [])
    st.markdown(f"**🚑 IR / Stash ({len(ir_list)}/1 slot):**")
    if ir_list:
        ir_p = ir_list[0]
        bye_w = TEAM_BYE_WEEKS_2026.get(ir_p.get("team", ""), 0)
        badge = ir_p.get("injury_badge", "⚠️ IR")
        st.markdown(f"""
        <div class="roster-card" style="border:1px solid #ea580c; background:#2d1205;">
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="background:#ea580c; color:#fff; font-size:0.68rem; font-weight:800; padding:2px 6px; border-radius:4px;">IR</span>
                <span class="roster-player-name" style="color:#fdba74;">{ir_p['name']}</span>
            </div>
            <div style="font-size:0.72rem; color:#f97316; font-weight:700;">
                {badge}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="roster-card roster-card-empty" style="border: 1px dashed #64748b;">
            <span class="roster-slot-title" style="color:#f59e0b;">IR</span>
            <span style="font-size:0.8rem; font-style:italic; color:#94a3b8;">Empty (Stash Slot)</span>
        </div>
        """, unsafe_allow_html=True)

    # Bye Week Conflict Check
    if all_user_byes:
        bye_counts = pd.Series(all_user_byes).value_counts()
        conflicts = bye_counts[bye_counts >= 3].to_dict()
        if conflicts:
            st.warning(f"⚠️ Bye Week Stack: Weeks {list(conflicts.keys())} have {list(conflicts.values())} starters off!")

    st.markdown("---")
    
    # Export & Reset Options
    with st.expander("⚙️ Export & Board Options"):
        if st.session_state.draft_history:
            export_df = pd.DataFrame(st.session_state.draft_history)
            csv_data = export_df.to_csv(index=False)
            st.download_button(
                "📥 Export Draft Log (CSV)",
                data=csv_data,
                file_name="my_2026_draft_log.csv",
                mime="text/csv",
                use_container_width=True
            )
        if st.button("🚨 Reset Entire Draft Board", type="secondary", use_container_width=True):
            reset_draft_board()
            st.rerun()
        if st.button("📥 Force Re-Scrape / Refresh", use_container_width=True):
            st.session_state.draft_board = load_or_generate_draft_board(force_refresh=True)
            st.toast("Draft pool re-scraped and updated!", icon="⚡")
            st.rerun()


# -----------------------------------------------------------------------------
# 8. MAIN VIEW TABS & MULTI-EXPERT DRAFT BOARD
# -----------------------------------------------------------------------------
tab_all, tab_drafted, tab_strategy, tab_espn_cs, tab_rb, tab_wr, tab_qb, tab_te, tab_flex, tab_dstk, tab_steals, tab_reaches, tab_injuries, tab_grid, tab_depth = st.tabs([
    "⚡ All Available",
    "❌ Drafted Players",
    "🧠 Draft Strategy & Playbook",
    "📋 ESPN Expert Cheat Sheet",
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
])


def reset_table_search(key_prefix: str = "all_avail"):
    """Safely increments the search and sort version counters to clear text inputs and deselect rows without StreamlitAPIException."""
    st.session_state[f"search_ver_{key_prefix}"] = st.session_state.get(f"search_ver_{key_prefix}", 0) + 1
    st.session_state[f"sort_ver_{key_prefix}"] = st.session_state.get(f"sort_ver_{key_prefix}", 0) + 1
    sel_k = f"table_select_{key_prefix}"
    if sel_k in st.session_state:
        del st.session_state[sel_k]


def reset_table_sort(key_prefix: str = "all_avail"):
    """Safely increments the sort version counter to reset sorting to default without StreamlitAPIException."""
    st.session_state[f"sort_ver_{key_prefix}"] = st.session_state.get(f"sort_ver_{key_prefix}", 0) + 1


def render_draft_table(df_subset: pd.DataFrame, key_prefix: str = "main", show_granular: bool = True):
    """
    Renders an ultra-clean, high-density, interactive draft board with full multi-expert rankings,
    unicode strikethrough on out-for-season IR players, red-out styling on drafted players,
    and live injury/suspension badges with 1-click undo.
    """
    if df_subset.empty:
        st.info("No players matching the current filter.")
        return

    df_display = df_subset.copy().reset_index(drop=True)

    search_ver = st.session_state.get(f"search_ver_{key_prefix}", 0)
    search_key = f"search_input_{key_prefix}_{search_ver}"

    sort_ver = st.session_state.get(f"sort_ver_{key_prefix}", 0)
    sort_by_key = f"sort_by_{key_prefix}_{sort_ver}"
    sort_dir_key = f"sort_dir_{key_prefix}_{sort_ver}"
    hide_unranked_key = f"hide_unranked_{key_prefix}_{sort_ver}"

    # In-table search, sorting & filtering bar
    f_c1, f_c2, f_c3, f_c4, f_c5 = st.columns([1.8, 0.9, 1.4, 1.3, 1.1])
    with f_c1:
        curr_q = st.session_state.get(search_key, "")
        if curr_q:
            s_c1, s_c2 = st.columns([3.0, 1.1])
            with s_c1:
                tbl_search = st.text_input(
                    f"Filter table ({len(df_display)} players)",
                    key=search_key,
                    placeholder="Type player, team, or position..."
                )
            with s_c2:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("✖ Clear", key=f"btn_clr_filter_{key_prefix}", use_container_width=True, help="Clear search and return to all available"):
                    reset_table_search(key_prefix)
                    st.rerun()
        else:
            tbl_search = st.text_input(
                f"Filter table ({len(df_display)} players)",
                key=search_key,
                placeholder="Type player, team, or position..."
            )
    with f_c2:
        tier_filter = st.multiselect(
            "Filter Tiers",
            options=sorted(df_display["tier"].unique()),
            default=[],
            key=f"tier_{key_prefix}",
            placeholder="All Tiers"
        )
    with f_c3:
        espn_filter = st.selectbox(
            "ESPN Cheat Sheet Filter",
            options=[
                "All Players",
                "⭐ ESPN Heat (2+ Experts)",
                "🎯 Karabell Do Draft",
                "🛑 Karabell Fade (Overvalued)",
                "📋 Clay Blueprint Target",
                "⭐ Schefter Target",
                "🏆 Florio League Winner",
                "💎 Field Favorite",
                "🏹 Bowen Top Target",
                "🚀 Loza Flier",
                "🛡️ Moody Handcuff RB",
                "🔥 Moody Value",
                "💤 Cockcroft Deep Sleeper"
            ],
            index=0,
            key=f"espn_filter_{key_prefix}_{sort_ver}",
            help="Filter players by official ESPN Ultimate Cheat Sheet expert endorsements and fade tags."
        )
    with f_c4:
        sort_options = [
            "Consensus (Default)",
            "ESPN (Top 300)",
            "ESPN Heat Index (Experts)",
            "Draft Sharks (#1)",
            "Footballguys (#2)",
            "FantasyPros (#3)",
            "RotoBaller (#4)",
            "CBS Sports (#5)",
            "NBC Sports (#6)",
            "Bleacher Report (#7)",
            "Sports Illustrated (#8)",
            "Value Steals (ESPN Diff)",
            "Auction Value ($)"
        ]
        sort_by = st.selectbox(
            "Sort by Ranking",
            options=sort_options,
            index=0,
            key=sort_by_key,
            help="Choose an expert ranking source to sort by. Guarantees ranks start cleanly at 1 or 300, never at None."
        )
    with f_c5:
        sort_dir_options = [
            "Lowest to High (1 → 300)",
            "High to Lowest (300 → 1)"
        ]
        sort_direction = st.selectbox(
            "Sort Order",
            options=sort_dir_options,
            index=0,
            key=sort_dir_key,
            help="Sort from lowest rank to highest (e.g. 1, 2, 3...) or highest to lowest (e.g. 300, 299, 298...)."
        )

    # Secondary display & filtering toggles row
    t_c1, t_c2, t_c3, t_c4 = st.columns([1.5, 1.1, 1.2, 1.6])
    with t_c1:
        granular_toggle = st.checkbox(
            "📊 Show All Expert Sources (9 Ranks)",
            value=st.session_state.get(f"toggle_granular_{key_prefix}", True),
            key=f"toggle_granular_{key_prefix}",
            help="Checked by default. Displays all 9 expert ranking sources ordered from most reliable to mainstream."
        )
    with t_c2:
        default_hide_ir = (key_prefix != "inj_report")
        hide_ir_toggle = st.checkbox(
            "🚫 Hide Season IR",
            value=st.session_state.get(f"hide_ir_{key_prefix}", default_hide_ir),
            key=f"hide_ir_{key_prefix}",
            help="Checked by default on draft boards. Hides players on season-ending IR while keeping active players."
        )
    with t_c3:
        keep_drafted_toggle = st.checkbox(
            "🔴 Keep Drafted",
            value=True,
            key=f"keep_drafted_{key_prefix}",
            help="When checked, drafted players remain visible in the table with full red strikethrough styling and 1-click undo."
        )
    with t_c4:
        hide_unranked = False
        if sort_by != "Consensus (Default)" and sort_by not in ["Value Steals (ESPN Diff)", "Auction Value ($)"]:
            short_name = sort_by.split(" ")[0]
            hide_unranked = st.checkbox(
                f"🎯 Only Ranked on {short_name}",
                value=st.session_state.get(f"hide_unranked_{key_prefix}", False),
                key=hide_unranked_key,
                help=f"Filter the board to only players evaluated and ranked by {sort_by}, hiding unranked players entirely."
            )

    # Visual Injury Status Legend / Key (below filter controls)
    st.markdown("""
    <div style="background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 6px 14px; margin: 4px 0 10px 0; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-size: 0.77rem; box-shadow: inset 0 1px 3px rgba(0,0,0,0.3);">
        <span style="font-weight: 800; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.5px; display: flex; align-items: center; gap: 4px;">
            📋 Injury Key:
        </span>
        <span style="background: #1e1b4b; padding: 2px 8px; border-radius: 4px; border: 1px solid #3730a3;">
            <strong style="color: #eab308;">🟡 Q</strong> <span style="color: #cbd5e1;">= Questionable / Day-to-Day (Could play Wk 1)</span>
        </span>
        <span style="background: #431407; padding: 2px 8px; border-radius: 4px; border: 1px solid #ea580c;">
            <strong style="color: #fb923c;">🟠 OUT (W1)</strong> <span style="color: #fed7aa;">= Out Week 1 Only (Expected back Wk 2)</span>
        </span>
        <span style="background: #2d1a04; padding: 2px 8px; border-radius: 4px; border: 1px solid #d97706;">
            <strong style="color: #f59e0b;">⚠️ PUP / IR</strong> <span style="color: #fde68a;">= Multi-Wk Stash (Out min first 4 wks, returns Wk 5+)</span>
        </span>
        <span style="background: #3b0764; padding: 2px 8px; border-radius: 4px; border: 1px solid #7e22ce;">
            <strong style="color: #c084fc;">⛔ SUSP</strong> <span style="color: #e9d5ff;">= Suspended (Returns when reinstated)</span>
        </span>
        <span style="background: #450a0a; padding: 2px 8px; border-radius: 4px; border: 1px solid #991b1b;">
            <strong style="color: #f87171;">🛑 IR (Season)</strong> <span style="color: #fecaca;">= Season-Ending (Do not draft)</span>
        </span>
    </div>
    """, unsafe_allow_html=True)

    # Apply in-table filters
    if not keep_drafted_toggle and "is_drafted" in df_display.columns:
        df_display = df_display[~df_display["is_drafted"]].reset_index(drop=True)

    if hide_ir_toggle and "is_season_out" in df_display.columns:
        df_display = df_display[~df_display["is_season_out"]].reset_index(drop=True)

    if tbl_search:
        s_low = tbl_search.lower().strip()
        df_display = df_display[
            df_display["name"].str.lower().str.contains(s_low, na=False) |
            df_display["team"].str.lower().str.contains(s_low, na=False) |
            df_display["pos"].str.lower().str.contains(s_low, na=False) |
            df_display.get("injury_type", pd.Series([""] * len(df_display))).str.lower().str.contains(s_low, na=False)
        ].reset_index(drop=True)

    if tier_filter:
        df_display = df_display[df_display["tier"].isin(tier_filter)].reset_index(drop=True)

    # Apply ESPN Cheat Sheet Expert Filter
    if espn_filter == "⭐ ESPN Heat (2+ Experts)" and "espn_heat_index" in df_display.columns:
        df_display = df_display[df_display["espn_heat_index"] >= 2].reset_index(drop=True)
    elif espn_filter == "🎯 Karabell Do Draft" and "espn_expert_badges" in df_display.columns:
        df_display = df_display[df_display["espn_expert_badges"].str.contains("Karabell Target", na=False)].reset_index(drop=True)
    elif espn_filter == "🛑 Karabell Fade (Overvalued)" and "is_espn_fade" in df_display.columns:
        df_display = df_display[df_display["is_espn_fade"]].reset_index(drop=True)
    elif espn_filter == "📋 Clay Blueprint Target" and "clay_round" in df_display.columns:
        df_display = df_display[df_display["clay_round"].notna()].reset_index(drop=True)
    elif espn_filter == "⭐ Schefter Target" and "espn_expert_badges" in df_display.columns:
        df_display = df_display[df_display["espn_expert_badges"].str.contains("Schefter", na=False)].reset_index(drop=True)
    elif espn_filter == "🏆 Florio League Winner" and "espn_expert_badges" in df_display.columns:
        df_display = df_display[df_display["espn_expert_badges"].str.contains("Florio", na=False)].reset_index(drop=True)
    elif espn_filter == "💎 Field Favorite" and "espn_expert_badges" in df_display.columns:
        df_display = df_display[df_display["espn_expert_badges"].str.contains("Field", na=False)].reset_index(drop=True)
    elif espn_filter == "🏹 Bowen Top Target" and "espn_expert_badges" in df_display.columns:
        df_display = df_display[df_display["espn_expert_badges"].str.contains("Bowen", na=False)].reset_index(drop=True)
    elif espn_filter == "🚀 Loza Flier" and "espn_expert_badges" in df_display.columns:
        df_display = df_display[df_display["espn_expert_badges"].str.contains("Loza", na=False)].reset_index(drop=True)
    elif espn_filter == "🛡️ Moody Handcuff RB" and "espn_expert_badges" in df_display.columns:
        df_display = df_display[df_display["espn_expert_badges"].str.contains("Moody Handcuff", na=False)].reset_index(drop=True)
    elif espn_filter == "🔥 Moody Value" and "espn_expert_badges" in df_display.columns:
        df_display = df_display[df_display["espn_expert_badges"].str.contains("Moody Value", na=False)].reset_index(drop=True)
    elif espn_filter == "💤 Cockcroft Deep Sleeper" and "espn_expert_badges" in df_display.columns:
        df_display = df_display[df_display["espn_expert_badges"].str.contains("Cockcroft", na=False)].reset_index(drop=True)

    # Dictionary mapping user-friendly names to dataframe columns
    SORT_COL_MAP = {
        "Consensus (Default)": "consensus_rank",
        "ESPN (Top 300)": "espn_rank",
        "ESPN Heat Index (Experts)": "espn_heat_index",
        "Draft Sharks (#1)": "draftsharks_rank",
        "Footballguys (#2)": "footballguys_rank",
        "FantasyPros (#3)": "fantasypros_rank",
        "RotoBaller (#4)": "rotoballer_rank",
        "CBS Sports (#5)": "cbs_rank",
        "NBC Sports (#6)": "nbcsports_rank",
        "Bleacher Report (#7)": "bleacherreport_rank",
        "Sports Illustrated (#8)": "sportsillustrated_rank",
        "Value Steals (ESPN Diff)": "value_diff",
        "Auction Value ($)": "auction_value"
    }

    sort_col = SORT_COL_MAP.get(sort_by, "consensus_rank")
    is_ascending = (sort_direction == "Lowest to High (1 → 300)")

    # If user wants to see only players ranked by that specific expert
    if hide_unranked and sort_col in df_display.columns:
        df_display = df_display[df_display[sort_col].notna()].reset_index(drop=True)

    # GUARANTEE: na_position='last' ensures that:
    # 1. Lowest to High (1 -> 300): Starts cleanly at 1, 2, 3, 4 ... up to 300!
    # 2. High to Lowest (300 -> 1): Starts cleanly at 300, 299, 298 ... down to 1!
    # 3. In BOTH directions, unranked players (NaN / None) are placed at the BOTTOM, NEVER at the top!
    if sort_col in df_display.columns:
        if sort_by == "Value Steals (ESPN Diff)":
            df_display = df_display.sort_values(
                by=[sort_col, "consensus_rank"],
                ascending=[not is_ascending if sort_direction == "Lowest to High (1 → 300)" else is_ascending, True],
                na_position="last"
            ).reset_index(drop=True)
        elif sort_by == "ESPN Heat Index (Experts)":
            df_display = df_display.sort_values(
                by=[sort_col, "consensus_rank"],
                ascending=[not is_ascending if sort_direction == "Lowest to High (1 → 300)" else is_ascending, True],
                na_position="last"
            ).reset_index(drop=True)
        else:
            df_display = df_display.sort_values(
                by=[sort_col, "consensus_rank"],
                ascending=[is_ascending, True],
                na_position="last"
            ).reset_index(drop=True)

    # Active sort banner with 1-click Reset to Consensus
    if sort_by != "Consensus (Default)" or sort_direction != "Lowest to High (1 → 300)":
        non_null_ranks = df_display[sort_col].dropna()
        if not non_null_ranks.empty:
            start_rank_val = int(non_null_ranks.iloc[0])
        else:
            start_rank_val = "1" if is_ascending else "300"
        c_sort_info, c_sort_btn = st.columns([7.8, 2.2])
        with c_sort_info:
            st.info(f"📊 Table sorted by **{sort_by}** &bull; **{sort_direction}** (Starts at rank **#{start_rank_val}**, unranked players placed at bottom)")
        with c_sort_btn:
            if st.button("🔄 Reset to Consensus", key=f"btn_reset_sort_{key_prefix}_{sort_ver}", use_container_width=True, help="Reset sorting back to Consensus Median Rank #1-300"):
                reset_table_sort(key_prefix)
                st.rerun()

    # Dedicated active search alert bar with 1-click Return to Available
    if tbl_search:
        c_act_info, c_act_btn = st.columns([7.8, 2.2])
        with c_act_info:
            st.info(f"🔍 Currently filtered by **'{tbl_search}'** ({len(df_display)} matching player{'s' if len(df_display) != 1 else ''} found)")
        with c_act_btn:
            if st.button("🔙 Return to All Available", key=f"btn_ret_avail_{key_prefix}", type="primary", use_container_width=True, help="Clear search and return to full draft board"):
                reset_table_search(key_prefix)
                st.rerun()

    if df_display.empty:
        st.info("No players matching the active filters.")
        return

    # Calculate Avail # ranks: numeric for available, red pick number for drafted
    avail_ranks = []
    rank_counter = 1
    for _, r in df_display.iterrows():
        if r.get("is_drafted"):
            pick_num = r.get("pick_number", "-")
            avail_ranks.append(f"🔴 #{pick_num}")
        else:
            avail_ranks.append(str(rank_counter))
            rank_counter += 1
    df_display["avail_rank"] = avail_ranks

    # Format presentation columns with native unicode strikethrough
    def format_player_name(r):
        name = r["name"]
        if r.get("is_drafted"):
            pick_num = r.get("pick_number", "?")
            tag = "MY ROSTER" if r.get("is_user") else f"{r.get('drafted_by', 'TAKEN')}"
            return f"🔴 [PICK #{pick_num} - {tag}] {to_unicode_strikethrough(name)}"
        if r.get("is_season_out"):
            return f"{to_unicode_strikethrough(name)} 🛑"
        return name

    df_display["player_display_name"] = df_display.apply(format_player_name, axis=1)

    # Format injury badge / drafted indicator
    def format_badge(r):
        if r.get("is_drafted"):
            return "🟩 MY ROSTER" if r.get("is_user") else f"🔴 DRAFTED (#{r.get('pick_number', '')})"
        badge = r.get("injury_badge", "")
        if not badge:
            return ""
        # On dedicated injury tab, display the full timeline alongside badge
        if key_prefix == "inj_report":
            timeline = r.get("injury_timeline", "")
            if timeline:
                tl_clean = (
                    timeline.replace("Target Return: ~", "Back ~")
                    .replace("Out minimum first 4 games", "Out min 4 wks")
                    .replace("Suspended until ~", "Susp. to ~")
                )
                return f"{badge} • {tl_clean}"
            return badge
        # On all regular draft boards, show just the clean icon, tag, and specific injury (e.g. 🟡 Q (Knee), 🟠 OUT (Ankle))
        return badge

    df_display["injury_badge_display"] = df_display.apply(format_badge, axis=1)

    if key_prefix == "steals" and "sleeper_badge" in df_display.columns:
        display_cols = [
            "avail_rank",
            "player_display_name",
            "pos",
            "team",
            "sleeper_badge",
            "preseason_grade",
            "value_diff",
            "consensus_rank",
            "espn_rank",
            "tier",
            "bye",
        ]
    else:
        display_cols = [
            "avail_rank",
            "player_display_name",
            "pos",
            "team",
            "injury_badge_display",
            "bye",
            "tier",
            "consensus_rank",
            "value_diff",
            "espn_rank",
        ]

    if granular_toggle:
        expert_sources_order = [
            "draftsharks_rank", "footballguys_rank", "fantasypros_rank", "rotoballer_rank",
            "cbs_rank", "nbcsports_rank", "bleacherreport_rank", "sportsillustrated_rank",
            "consensus_best", "consensus_worst", "consensus_std", "auction_value"
        ]
        for col in expert_sources_order:
            if col in df_display.columns:
                display_cols.append(col)

    if "espn_expert_badges" in df_display.columns:
        display_cols.append("espn_expert_badges")

    col_rename = {
        "avail_rank": "Rank #",
        "player_display_name": "Player Name",
        "pos": "Pos",
        "team": "Team",
        "injury_badge_display": "Injury / Risk",
        "sleeper_badge": "Sleeper / Rookie Intel",
        "preseason_grade": "Preseason Grade",
        "bye": "Bye",
        "tier": "Tier",
        "consensus_rank": "Consensus",
        "value_diff": "Value Diff",
        "espn_rank": "ESPN",
        "espn_expert_badges": "ESPN Badges",
        "draftsharks_rank": "Draft Sharks (#1)",
        "footballguys_rank": "Footballguys (#2)",
        "fantasypros_rank": "FantasyPros (#3)",
        "rotoballer_rank": "RotoBaller (#4)",
        "cbs_rank": "CBS Sports (#5)",
        "nbcsports_rank": "NBC Sports (#6)",
        "bleacherreport_rank": "Bleacher Report (#7)",
        "sportsillustrated_rank": "Sports Illustrated (#8)",
        "consensus_best": "Best",
        "consensus_worst": "Worst",
        "consensus_std": "Std Dev",
        "auction_value": "Auction $"
    }

    sub_view = df_display[display_cols].rename(columns=col_rename)

    # Style drafted rows with dark red background and strikethrough
    drafted_indices = set(df_display[df_display.get("is_drafted", False)].index)

    def style_drafted_rows(row):
        if row.name in drafted_indices:
            return [
                "background-color: rgba(185, 28, 28, 0.35); color: #fca5a5; text-decoration: line-through; opacity: 0.85;"
            ] * len(row)
        return [""] * len(row)

    styled_view = sub_view.style.apply(style_drafted_rows, axis=1)

    # Container placed ABOVE the table to ensure selected player card renders above the table
    selected_card_container = st.container()

    # Prominent, high-visibility draft room tip banner
    st.markdown("""
    <div style="background: linear-gradient(90deg, #1e1b4b 0%, #0f172a 100%); border: 1.5px solid #6366f1; border-radius: 8px; padding: 10px 16px; margin: 8px 0 10px 0; display: flex; align-items: center; gap: 12px; box-shadow: 0 3px 12px rgba(99, 102, 241, 0.22);">
        <span style="font-size: 1.4rem; line-height: 1;">💡</span>
        <div style="font-size: 0.92rem; color: #f1f5f9; line-height: 1.45;">
            <strong style="color: #a5b4fc; text-transform: uppercase; letter-spacing: 0.5px;">Crucial Draft Room Feature:</strong>
            Click any player's <span style="background:#3730a3; padding:1px 6px; border-radius:4px; font-weight:700; color:#fff;">checkbox or row</span> in the table to immediately open their <strong>full beat-reporter injury notes, return timeline, live medical profile links, and 1-click draft buttons</strong> above the table.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Interactive Table with Direct Selection and Smooth Horizontal Scrolling
    selection = st.dataframe(
        styled_view,
        use_container_width=True,
        hide_index=True,
        height=480,
        selection_mode="single-row",
        on_select="rerun",
        key=f"table_select_{key_prefix}",
        column_config={
            "Rank #": st.column_config.TextColumn(width="small"),
            "Player Name": st.column_config.TextColumn(width="medium"),
            "Pos": st.column_config.TextColumn(width="small"),
            "Team": st.column_config.TextColumn(width="small"),
            "Injury / Risk": st.column_config.TextColumn(
                width="medium",
                help="Live NFL Injury, Suspension, & Return Timeline. Click any row in the table to display full beat-reporter injury notes and surgical updates below."
            ),
            "Sleeper / Rookie Intel": st.column_config.TextColumn(
                width="medium",
                help="2026 Preseason Breakout Status, Rookie Tags, and Camp Buzz"
            ),
            "Preseason Grade": st.column_config.TextColumn(
                width="small",
                help="Scouting evaluation grade based on 2026 preseason game film and efficiency"
            ),
            "Bye": st.column_config.NumberColumn(width="small", format="%d"),
            "Tier": st.column_config.NumberColumn(width="small", format="%d"),
            "Consensus": st.column_config.NumberColumn(width="small", format="%.1f", help="Consensus Median Rank across all 9 expert sources"),
            "Value Diff": st.column_config.NumberColumn(
                width="small",
                format="%+d",
                help="Positive = ESPN undervalues player (STEAL). Negative = ESPN overvalues player (REACH)."
            ),
            "ESPN": st.column_config.NumberColumn(width="small", format="%d", help="Official ESPN 2026 API Draft Rank"),
            "ESPN Badges": st.column_config.TextColumn(
                width="medium",
                help="Official ESPN Ultimate Cheat Sheet Expert Endorsements (Karabell, Schefter, Florio, Clay, Bowen, Moody, Loza, Cockcroft, Yates)"
            ),
            "Draft Sharks (#1)": st.column_config.NumberColumn(width="small", format="%d", help="Draft Sharks (#1 Accuracy Champion). Published Top 250 (cells display None for players outside Top 250)."),
            "Footballguys (#2)": st.column_config.NumberColumn(width="small", format="%d", help="Footballguys (#2 Accuracy Champion). Published Top 200 (cells display None for players outside Top 200)."),
            "FantasyPros (#3)": st.column_config.NumberColumn(width="small", format="%d", help="FantasyPros 50+ Expert Consensus Rank (ECR)."),
            "RotoBaller (#4)": st.column_config.NumberColumn(width="small", format="%d", help="RotoBaller Top 400 PPR Rankings."),
            "CBS Sports (#5)": st.column_config.NumberColumn(width="small", format="%d", help="CBS Sports Fantasy Consensus (Eisenberg / Richard / Cummings)."),
            "NBC Sports (#6)": st.column_config.NumberColumn(width="small", format="%d", help="NBC Sports / Rotoworld Top 200 (offensive skill positions; cells display None for players outside Top 200)."),
            "Bleacher Report (#7)": st.column_config.NumberColumn(width="small", format="%d", help="Bleacher Report Top 314 PPR Rankings."),
            "Sports Illustrated (#8)": st.column_config.NumberColumn(width="small", format="%d", help="Sports Illustrated / Michael Fabiano Top 200 (cells display None for players outside Top 200)."),
            "Best": st.column_config.NumberColumn(width="small", format="%d"),
            "Worst": st.column_config.NumberColumn(width="small", format="%d"),
            "Std Dev": st.column_config.NumberColumn(width="small", format="%.1f", help="Variance/disagreement among experts"),
            "Auction $": st.column_config.NumberColumn(width="small", format="$%d"),
        }
    )

    # If row clicked, show instant draft banner or undo banner with comprehensive alerts ABOVE the table
    selected_rows = selection.selection.rows if selection and hasattr(selection, "selection") else []
    if selected_rows:
        with selected_card_container:
            sel_idx = selected_rows[0]
            if sel_idx < len(df_display):
                sel_player = df_display.iloc[sel_idx]
                p_id = sel_player["player_id"]
                p_name = sel_player["name"]
                p_pos = sel_player["pos"]
                p_team = sel_player["team"]
                p_val = sel_player["value_diff"]
                inj_tier = sel_player.get("injury_tier", "")
                is_drafted = sel_player.get("is_drafted", False)
                
                # If drafted, display red drafted banner with 1-click Undo button
                if is_drafted:
                    drafted_by_label = "Your Roster" if sel_player.get("is_user") else sel_player.get("drafted_by", "Opponent")
                    pick_num = sel_player.get("pick_number", "?")
                    draft_round = sel_player.get("draft_round", "?")
                    st.markdown(f"""
                    <div style="background:#450a0a; border:2px solid #ef4444; border-radius:8px; padding:12px 16px; margin-top:8px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <strong style="color:#f87171; font-size:1.05rem;">🔴 DRAFTED: {p_name} ({p_pos} - {p_team}) &bull; Taken at Pick #{pick_num} by {drafted_by_label}</strong>
                            <span style="background:#ef4444; color:#fff; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;">OFF THE BOARD</span>
                        </div>
                        <div style="margin-top:6px; color:#fecaca; font-size:0.9rem;">
                            <strong>Round:</strong> {draft_round} &bull; <strong>Consensus:</strong> #{sel_player['consensus_rank']} &bull; <strong>Value Spread:</strong> {'+' if p_val > 0 else ''}{p_val}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    u_c1, u_c2, u_c3 = st.columns([1.5, 1.5, 0.8])
                    with u_c1:
                        if st.button(f"🔄 Undo Pick / Restore {p_name}", key=f"btn_undo_sel_{p_id}_{key_prefix}", type="primary", use_container_width=True):
                            restore_player(p_id)
                            st.rerun()
                    with u_c2:
                        if st.button("🔙 Return to Available", key=f"btn_return_undo_{p_id}_{key_prefix}", use_container_width=True, help="Clear search bar and return to all available players"):
                            reset_table_search(key_prefix)
                            st.rerun()
                    with u_c3:
                        if st.button("✖ Close", key=f"btn_close_undo_{p_id}_{key_prefix}", use_container_width=True, help="Dismiss card"):
                            if f"table_select_{key_prefix}" in st.session_state:
                                del st.session_state[f"table_select_{key_prefix}"]
                            st.rerun()
                else:
                    report_ts = sel_player.get("injury_updated_formatted") or "Sep 5, 2026 at 08:00 AM UTC"
                    # Available player: High-visibility injury / suspension alerts based on tier
                    if inj_tier == "SEASON_IR":
                        st.markdown(f"""
                        <div style="background:#450a0a; border:2px solid #ef4444; border-radius:8px; padding:12px 16px; margin-top:8px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong style="color:#f87171; font-size:1.05rem;">🛑 INJURY WARNING: OUT FOR SEASON (IR) &bull; {p_name} ({p_pos} - {p_team})</strong>
                                <span style="background:#ef4444; color:#fff; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;">DO NOT DRAFT</span>
                            </div>
                            <div style="margin-top:6px; color:#fecaca; font-size:0.9rem;">
                                <strong>Timeline:</strong> {sel_player.get('injury_timeline', 'Out for Season')} &bull; <strong>Diagnosis:</strong> {sel_player.get('injury_type', 'Season-Ending')} &bull; <strong>Consensus #{sel_player['consensus_rank']}</strong>
                            </div>
                            <div style="margin-top:4px; color:#f1f5f9; font-size:0.85rem;">
                                {sel_player.get('injury_blurb', '')}
                            </div>
                            <div style="margin-top:4px; color:#fca5a5; font-size:0.85rem; font-weight:600;">
                                ⚠️ Draft Guidance: {sel_player.get('draft_advice', 'Do not draft in standard redraft leagues.')}
                            </div>
                            {get_player_injury_links_html(p_name, report_ts, sel_player.get('source_url'))}
                        </div>
                        """, unsafe_allow_html=True)
                    elif inj_tier == "SUSPENSION":
                        st.markdown(f"""
                        <div style="background:#3b0764; border:2px solid #c084fc; border-radius:8px; padding:12px 16px; margin-top:8px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong style="color:#e9d5ff; font-size:1.05rem;">⛔ LEAGUE SUSPENSION ALERT &bull; {p_name} ({p_pos} - {p_team})</strong>
                                <span style="background:#a855f7; color:#fff; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;">MULTI-GAME SUSPENSION</span>
                            </div>
                            <div style="margin-top:6px; color:#f3e8ff; font-size:0.9rem;">
                                <strong>Timeline:</strong> {sel_player.get('injury_timeline', 'Suspended')} &bull; <strong>Reason:</strong> {sel_player.get('injury_type', 'League Policy')} &bull; <strong>Consensus #{sel_player['consensus_rank']}</strong>
                            </div>
                            <div style="margin-top:4px; color:#f1f5f9; font-size:0.85rem;">
                                {sel_player.get('injury_blurb', '')}
                            </div>
                            <div style="margin-top:4px; color:#d8b4fe; font-size:0.85rem; font-weight:600;">
                                💡 Stash Strategy: {sel_player.get('draft_advice', 'Target as mid-round stash.')}
                            </div>
                            {get_player_injury_links_html(p_name, report_ts, sel_player.get('source_url'))}
                        </div>
                        """, unsafe_allow_html=True)
                    elif inj_tier == "PUP_MULTI_WEEK":
                        ret_dt = str(sel_player.get('injury_return_date', '') or '').strip()
                        ret_disp = ret_dt if ret_dt and ret_dt.lower() != 'nan' and ret_dt.lower() != 'none' else 'Week 5'
                        st.markdown(f"""
                        <div style="background:#431407; border:2px solid #f97316; border-radius:8px; padding:12px 16px; margin-top:8px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong style="color:#fed7aa; font-size:1.05rem;">⚠️ RESERVE / PUP ALERT (OUT FIRST 4+ WEEKS) &bull; {p_name} ({p_pos} - {p_team})</strong>
                                <span style="background:#f97316; color:#fff; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;">MULTI-WEEK STASH</span>
                            </div>
                            <div style="margin-top:6px; color:#ffedd5; font-size:0.9rem;">
                                <strong>Timeline:</strong> Out minimum first 4 games &bull; <strong>Diagnosis:</strong> {sel_player.get('injury_type', 'PUP List')} &bull; <strong>Target Return:</strong> {ret_disp} &bull; <strong>Consensus #{sel_player['consensus_rank']}</strong>
                            </div>
                            <div style="margin-top:4px; color:#f1f5f9; font-size:0.85rem;">
                                {sel_player.get('injury_blurb', '')}
                            </div>
                            <div style="margin-top:4px; color:#fdba74; font-size:0.85rem; font-weight:600;">
                                💡 Stash Strategy: {sel_player.get('draft_advice', 'Target as late-round stash.')}
                            </div>
                            {get_player_injury_links_html(p_name, report_ts, sel_player.get('source_url'))}
                        </div>
                        """, unsafe_allow_html=True)
                    elif inj_tier == "OUT_WEEK_1":
                        ret_dt = str(sel_player.get('injury_return_date', '') or '').strip()
                        ret_disp = ret_dt if ret_dt and ret_dt.lower() != 'nan' and ret_dt.lower() != 'none' else 'Week 2'
                        st.markdown(f"""
                        <div style="background:#431407; border:2px solid #ea580c; border-radius:8px; padding:12px 16px; margin-top:8px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong style="color:#fdba74; font-size:1.05rem;">🟠 OUT WEEK 1 (EXPECTED BACK WEEK 2) &bull; {p_name} ({p_pos} - {p_team})</strong>
                                <span style="background:#ea580c; color:#fff; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;">OUT WK 1 ONLY</span>
                            </div>
                            <div style="margin-top:6px; color:#fed7aa; font-size:0.9rem;">
                                <strong>Timeline:</strong> Out Week 1 Only &bull; <strong>Diagnosis:</strong> {sel_player.get('injury_type', 'Short-term')} &bull; <strong>Target Return:</strong> {ret_disp} &bull; <strong>Consensus #{sel_player['consensus_rank']}</strong>
                            </div>
                            <div style="margin-top:4px; color:#f1f5f9; font-size:0.85rem;">
                                {sel_player.get('injury_blurb', '')}
                            </div>
                            <div style="margin-top:4px; color:#fb923c; font-size:0.85rem; font-weight:600;">
                                💡 Strategy: {sel_player.get('draft_advice', 'Confirmed out for Week 1 only; expected ready for Week 2.')}
                            </div>
                            {get_player_injury_links_html(p_name, report_ts, sel_player.get('source_url'))}
                        </div>
                        """, unsafe_allow_html=True)
                    elif inj_tier == "WEEK_1_RISK":
                        ret_dt = str(sel_player.get('injury_return_date', '') or '').strip()
                        ret_disp = ret_dt if ret_dt and ret_dt.lower() != 'nan' and ret_dt.lower() != 'none' else 'Week 1'
                        st.markdown(f"""
                        <div style="background:#422006; border:2px solid #eab308; border-radius:8px; padding:12px 16px; margin-top:8px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong style="color:#fef08a; font-size:1.05rem;">🟡 WEEK 1 MONITORING / QUESTIONABLE &bull; {p_name} ({p_pos} - {p_team})</strong>
                                <span style="background:#eab308; color:#000; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;">DAY-TO-DAY</span>
                            </div>
                            <div style="margin-top:6px; color:#fef9c3; font-size:0.9rem;">
                                <strong>Timeline:</strong> Day-to-Day &bull; <strong>Status:</strong> {sel_player.get('injury_type', 'Questionable')} &bull; <strong>Target Return:</strong> {ret_disp} &bull; <strong>Consensus #{sel_player['consensus_rank']}</strong>
                            </div>
                            <div style="margin-top:4px; color:#f1f5f9; font-size:0.85rem;">
                                {sel_player.get('injury_blurb', '')}
                            </div>
                            <div style="margin-top:4px; color:#fef08a; font-size:0.85rem; font-weight:600;">
                                💡 Advice: {sel_player.get('draft_advice', 'Monitor practice reports.')}
                            </div>
                            {get_player_injury_links_html(p_name, report_ts, sel_player.get('source_url'))}
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div style="background:#1e293b; border:1px solid #38bdf8; border-radius:8px; padding:10px 16px; margin-top:8px; display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <strong style="color:#f8fafc; font-size:1.05rem;">🟩 ACTIVE &bull; {p_name} ({p_pos} - {p_team})</strong> | <strong>Consensus #{sel_player['consensus_rank']}</strong> | <strong>Value Diff: {'+' if p_val > 0 else ''}{p_val}</strong>
                            </div>
                            <span style="background:#064e3b; color:#34d399; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px; border:1px solid #059669;">HEALTHY</span>
                        </div>
                        {get_player_injury_links_html(p_name, report_ts, sel_player.get('source_url'))}
                        """, unsafe_allow_html=True)
                    
                    # High-visibility Karabell Fade Warning
                    if sel_player.get("is_espn_fade", False):
                        st.markdown(f"""
                        <div style="background:#451a03; border:1.5px solid #f59e0b; border-radius:6px; padding:9px 14px; margin-top:8px; font-size:0.86rem; color:#fef3c7; box-shadow:0 2px 8px rgba(245,158,11,0.25);">
                            <strong style="color:#fbbf24; text-transform:uppercase; letter-spacing:0.5px;">🛑 KARABELL FADE ALERT:</strong> Erik Karabell rates <strong>{p_name}</strong> as <em>NOT worth current ADP ({sel_player.get('espn_adp_cheat_sheet', 'N/A')})</em>. {sel_player.get('karabell_fade_note', 'Target ONLY if they slide significantly past ADP.')}
                        </div>
                        """, unsafe_allow_html=True)

                    # Official ESPN Expert Dossier (All endorsements, notes, and tiers)
                    if sel_player.get("espn_dossier_html"):
                        st.markdown(sel_player["espn_dossier_html"], unsafe_allow_html=True)
                    
                    # Determine team on the clock and active chosen username
                    active_user_team = get_league_team_name(st.session_state.user_slot)
                    _, _, on_clock_slot, _ = get_snake_pick_info(st.session_state.current_pick)
                    on_clock_team = get_league_team_name(on_clock_slot)

                    b_c1, b_c2, b_c3, b_c4 = st.columns([1.6, 1.6, 1.3, 0.7])
                    with b_c1:
                        btn_label = f"🟩 Draft for {active_user_team}"
                        if inj_tier == "SEASON_IR":
                            btn_label += " ⚠️[IR RISK]"
                        if st.button(btn_label, key=f"btn_user_{p_id}_{key_prefix}", type="primary", use_container_width=True):
                            execute_pick(p_id, drafted_by_user=True)
                            st.rerun()
                    with b_c2:
                        btn_opp_label = f"⬛ Draft for {on_clock_team} (#{min(st.session_state.current_pick, TOTAL_PICKS)})"
                        if st.button(btn_opp_label, key=f"btn_opp_{p_id}_{key_prefix}", use_container_width=True, help=f"Assign pick #{st.session_state.current_pick} to {on_clock_team}"):
                            execute_pick(p_id, drafted_by_user=False, team_slot_override=on_clock_slot)
                            st.rerun()
                    with b_c3:
                        if st.button("🔙 Return to Available", key=f"btn_return_sel_{p_id}_{key_prefix}", use_container_width=True, help="Clear search bar and return to all available players"):
                            reset_table_search(key_prefix)
                            st.rerun()
                    with b_c4:
                        if st.button("✖ Close", key=f"btn_close_sel_{p_id}_{key_prefix}", use_container_width=True, help="Dismiss card"):
                            if f"table_select_{key_prefix}" in st.session_state:
                                del st.session_state[f"table_select_{key_prefix}"]
                            st.rerun()

                    # Out-of-order team assignment expander
                    with st.expander("🎯 Assign pick to a different team (out-of-order draft):", expanded=False):
                        oc1, oc2 = st.columns([3, 1.5])
                        with oc1:
                            target_override_slot = st.selectbox(
                                "Select Drafting Team:",
                                options=list(range(1, TOTAL_TEAMS + 1)),
                                index=on_clock_slot - 1,
                                format_func=lambda s: f"{get_league_team_name(s)} (Slot #{s})",
                                key=f"sel_override_team_{p_id}_{key_prefix}"
                            )
                        with oc2:
                            st.write("")
                            if st.button("Draft for Team", key=f"btn_draft_override_{p_id}_{key_prefix}", use_container_width=True):
                                execute_pick(p_id, drafted_by_user=(target_override_slot == st.session_state.user_slot), team_slot_override=target_override_slot)
                                st.rerun()


# --- Tab 1: All Available ---
with tab_all:
    render_draft_table(df_board, key_prefix="all_avail")

# --- Tab 2: Drafted Players ---
with tab_drafted:
    st.markdown("### ❌ Drafted Players")
    st.caption("Review all players removed from the board. Click **'🔄 Restore to Board'** next to any player to immediately return them to the available queue at their original rank.")

    drafted_df = df_board[df_board["is_drafted"]].copy()

    if drafted_df.empty:
        st.info("No players have been drafted or crossed off yet. When players are selected, they will appear here with instant restore buttons.")
    else:
        # Summary metrics
        user_drafted_count = len([h for h in st.session_state.draft_history if h.get("is_user", False)])
        opp_drafted_count = len([h for h in st.session_state.draft_history if not h.get("is_user", False)])

        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.metric("Total Removed", len(drafted_df))
        with mc2:
            st.metric(f"On {get_league_team_name(st.session_state.user_slot)}", user_drafted_count)
        with mc3:
            st.metric("Taken by Other Teams", opp_drafted_count)

        # Filters for crossed off view
        c_f1, c_f2, c_f3 = st.columns([3, 1.5, 1.8])
        with c_f1:
            search_crossed = st.text_input(
                "Filter removed players",
                placeholder="Search by player name, team, or position...",
                key="search_crossed_off"
            )
        with c_f2:
            pos_crossed = st.multiselect(
                "Position",
                options=["QB", "RB", "WR", "TE", "DST", "K"],
                default=[],
                placeholder="All Positions",
                key="pos_crossed_off"
            )
        with c_f3:
            drafter_options = ["All Removed", "My Team Only", "Other Teams Only"] + [get_league_team_name(s) for s in range(1, TOTAL_TEAMS + 1)]
            drafter_filter = st.selectbox(
                "Drafted By Team",
                options=drafter_options,
                key="drafter_crossed_off"
            )

        # Apply filters to history
        filtered_history = list(reversed(st.session_state.draft_history))

        if search_crossed:
            s_low = search_crossed.lower().strip()
            filtered_history = [
                h for h in filtered_history
                if s_low in h["name"].lower() or s_low in h["team"].lower() or s_low in h["pos"].lower()
            ]

        if pos_crossed:
            filtered_history = [h for h in filtered_history if h["pos"] in pos_crossed]

        if drafter_filter == "My Team Only":
            filtered_history = [h for h in filtered_history if h.get("is_user", False)]
        elif drafter_filter == "Other Teams Only":
            filtered_history = [h for h in filtered_history if not h.get("is_user", False)]
        elif drafter_filter != "All Removed":
            filtered_history = [h for h in filtered_history if h.get("drafted_by") == drafter_filter or get_league_team_name(h.get("team_slot", 0)) == drafter_filter]

        if not filtered_history:
            st.info("No removed players match the selected filters.")
        else:
            st.markdown("---")
            # Render list of removed players with reverse/restore button next to each
            for p in filtered_history:
                pid = p["player_id"]
                is_u = p.get("is_user", False)
                
                # Fetch fresh consensus rank
                p_match = df_board[df_board["player_id"] == pid]
                c_rank = p_match["consensus_rank"].values[0] if not p_match.empty else "?"
                p_tier = p_match["tier"].values[0] if not p_match.empty else "?"
                p_bye = p_match["bye"].values[0] if not p_match.empty else "?"

                card_c1, card_c2, card_c3, card_c4, card_c5 = st.columns([1.2, 3.5, 2, 2.5, 2])
                
                with card_c1:
                    st.markdown(f"**Pick #{p['pick_number']}**<br><span style='color:#94a3b8; font-size:0.75rem;'>Rd {p.get('draft_round', 1)}</span>", unsafe_allow_html=True)

                with card_c2:
                    st.markdown(f"""
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span class="pos-badge pos-{p['pos']}">{p['pos']}</span>
                        <strong style="font-size:0.95rem; text-decoration: line-through; opacity:0.85;">{p['name']}</strong>
                        <span style="color:#94a3b8; font-size:0.8rem;">{p['team']} (Wk {p_bye})</span>
                    </div>
                    """, unsafe_allow_html=True)

                with card_c3:
                    st.markdown(f"<span style='color:#94a3b8;'>Consensus:</span> <strong>#{c_rank}</strong> &bull; <span style='color:#94a3b8;'>Tier:</span> <strong>{p_tier}</strong>", unsafe_allow_html=True)

                with card_c4:
                    if is_u:
                        st.markdown("<span style='background:#064e3b; color:#34d399; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;'>🟩 My Roster</span>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<span style='background:#1e293b; color:#94a3b8; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;'>⬛ {p['drafted_by']}</span>", unsafe_allow_html=True)

                with card_c5:
                    if st.button(f"🔄 Restore to Board", key=f"restore_btn_{pid}_{p['pick_number']}", use_container_width=True):
                        restore_player(pid)
                        st.rerun()

                st.markdown("<div style='border-bottom: 1px solid #1e293b; margin: 4px 0 8px 0;'></div>", unsafe_allow_html=True)

# --- Tab 3: Draft Strategy & Playbook ---
with tab_strategy:
    st.markdown("### 🧠 8-Team PPR War Room Strategy & Playbook")
    st.caption(
        "Master the ESPN 8-Team PPR format (**9 Starters: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 DST, 1 K, 7 Bench, 1 IR Stash**). "
        "Real-time tactical directives, dynamic target recommendations with 1-click draft actions, 5 cardinal strategic shifts, and ESPN ADP arbitrage exploits."
    )

    # 1. LIVE DRAFT CONTEXT & SMART ADVISOR
    cur_pick = st.session_state.current_pick
    cur_rd, cur_rpick, cur_team_on_clock, is_my_turn = get_snake_pick_info(cur_pick)
    user_roster = get_user_roster()

    # Calculate starter needs
    starter_requirements = [
        ("QB", 1, len(user_roster.get("QB", []))),
        ("RB", 2, len(user_roster.get("RB", []))),
        ("WR", 2, len(user_roster.get("WR", []))),
        ("TE", 1, len(user_roster.get("TE", []))),
        ("FLEX", 1, len(user_roster.get("FLEX", []))),
        ("DST", 1, len(user_roster.get("DST", []))),
        ("K", 1, len(user_roster.get("K", [])))
    ]
    unfilled_starters = [slot for slot, req, filled in starter_requirements if filled < req]
    bench_filled = len(user_roster.get("BENCH", []))
    ir_filled = len(user_roster.get("IR", []))

    # Top Live Status Bar
    ad_col1, ad_col2, ad_col3, ad_col4 = st.columns([2, 2, 2.5, 2])
    with ad_col1:
        st.metric("Draft Status", f"Round {min(cur_rd, 16)}", delta=f"Pick #{min(cur_pick, TOTAL_PICKS)} / {TOTAL_PICKS}")
    with ad_col2:
        if is_my_turn:
            st.metric("Turn Status", "YOUR PICK NOW! 🔥", delta=f"{get_league_team_name(st.session_state.user_slot)} (Slot #{st.session_state.user_slot})", delta_color="normal")
        else:
            user_s = st.session_state.user_slot
            next_user_picks = [p for p in range(cur_pick, TOTAL_PICKS + 1) if get_snake_pick_info(p)[2] == user_s]
            if next_user_picks:
                st.metric("Next Turn", f"In {next_user_picks[0] - cur_pick} picks", delta=f"Pick #{next_user_picks[0]}")
            else:
                st.metric("Draft Status", "Complete", delta="All Rounds Done")
    with ad_col3:
        needed_str = ", ".join(unfilled_starters) if unfilled_starters else "Starters Full! (Fill Bench)"
        st.metric("Unfilled Starters", f"{len(unfilled_starters)} Left", delta=needed_str, delta_color="inverse" if unfilled_starters else "normal")
    with ad_col4:
        st.metric("Bench & IR Capacity", f"Bench: {bench_filled}/7", delta=f"IR: {ir_filled}/1 Stash", delta_color="normal")

    st.markdown("---")

    # 2. DYNAMIC SCENARIO SELECTOR & TACTICAL DIRECTIVE
    st.markdown("#### 🎯 Live Tactical Advisor & Opponent Behavior Counter")

    sc_c1, sc_c2 = st.columns([2.5, 3.5])
    with sc_c1:
        scenario = st.selectbox(
            "What are your opponents doing right now?",
            options=[
                "🎯 Balanced / Normal Draft Flow",
                "🚨 Early QB Panic / Run (Opponents drafting QBs in R2-3)",
                "🚜 Heavy RB Hoard / Run (Opponents taking 10+ RBs in top 20)",
                "📉 Blindly Following ESPN ADP (Opponents strictly following ESPN order)"
            ],
            key="strategy_scenario_select"
        )

    # Formulate tactical advice and target positions based on round and scenario
    target_positions = []
    directive_title = ""
    directive_body = ""
    directive_color = "strategy-card-accent-blue"

    if scenario == "🚨 Early QB Panic / Run (Opponents drafting QBs in R2-3)":
        directive_title = "🛑 DO NOT PANIC: Exploit Falling Alpha WRs & Bellcow RBs"
        directive_body = (
            "Opponents drafting QBs in R2–3 means 25% of the league is punting skill positions for a round! "
            "Every QB reached for pushes an elite Tier-1 skill player directly down the board to you. In an 8-team room where only 16 WRs "
            "are drafted across the starting WR slots, you can easily secure three top-15 WRs or two top-15 WRs + two top-12 RBs by Round 5. "
            "Completely fade QB for now—hoover up elite WR1s and RB1s (CeeDee Lamb [DAL], Justin Jefferson [MIN], Drake London [ATL], Kenneth Walker III [KC]). "
            "You will still land Lamar Jackson (BAL), Jalen Hurts (PHI), or Joe Burrow (CIN) in Rounds 6–8 with zero weekly point loss."
        )
        target_positions = ["WR", "RB"]
        directive_color = "strategy-card-accent-purple"

    elif scenario == "🚜 Heavy RB Hoard / Run (Opponents taking 10+ RBs in top 20)":
        directive_title = "🌊 PIVOT TO WR AVALANCHE + ELITE TE MISMATCH"
        directive_body = (
            "Opponents are reaching for low-ceiling committee backs well above true market value. In full 1.0 PPR, top-10 WRs and elite "
            "tight ends outscore RB2s by 12–18 fantasy points per week. Lock in 3 top-10 WRs and grab Brock Bowers (LV) or Trey McBride (ARI). "
            "Fill your RB2 and bench in Rounds 6–10 with high-touch ambiguity backs and elite contingent handcuffs (Chase Brown [CIN], Blake Corum [LAR], Zach Charbonnet [SEA])."
        )
        target_positions = ["WR", "TE"]
        directive_color = "strategy-card-accent-green"

    elif scenario == "📉 Blindly Following ESPN ADP (Opponents strictly following ESPN order)":
        directive_title = "⚡ EXPLOIT ESPN SPREAD INEFFICIENCIES (STEAL ARBITRAGE)"
        directive_body = (
            "Your league-mates are drafting directly down the default ESPN queue! Exploit this by waiting 1–2 full rounds on massive "
            "consensus steals like Kenneth Walker III (KC, +10 value), Brian Thomas Jr. (JAX, +18 value), Caleb Williams (CHI, +18 value), Tucker Kraft (GB, +19 value), "
            "and Zay Flowers (BAL, +7 value). Let opponents reach for ESPN trap players like Ashton Jeanty (LV, -6 reach trap) and injured veterans."
        )
        target_positions = ["RB", "WR", "TE", "QB"]
        directive_color = "strategy-card-accent-gold"

    else:  # Balanced / Normal Draft Flow
        if cur_rd <= 2:
            directive_title = "🏛️ PHASE 1 (ROUNDS 1–2): HERO RB + ALPHA WR (CEILING OVER FLOOR)"
            directive_body = (
                "Take the ceiling, not the floor! In an 8-team league, your top 16 picks are effectively two 1st-rounders. "
                "Anchor your squad with the two highest-ceiling players available: elite dual-threat Bellcows (Jahmyr Gibbs [DET], Bijan Robinson [ATL], CMC [SF], Jonathan Taylor [IND]) "
                "and Tier-1 Target-Hog WRs (Ja'Marr Chase [CIN], Puka Nacua [LAR], Amon-Ra St. Brown [DET], CeeDee Lamb [DAL]). "
                "Do not reach for need—replacement level on waivers and the flex spot cover you."
            )
            target_positions = ["RB", "WR"]
            directive_color = "strategy-card-accent-blue"
        elif cur_rd <= 5:
            directive_title = "🔨 PHASE 2 (ROUNDS 3–5): POSITIONAL HAMMERS (ELITE TE/QB) & SKILL AVALANCHE"
            directive_body = (
                "Attack positional scarcity! In an 8-team league, Brock Bowers (LV, #22) or Trey McBride (ARI, #24) creates a +6 to +8 PPG weekly advantage "
                "over the 6 teams streaming mid-tier TEs. Taking an elite TE early or grabbing Josh Allen (BUF, #27) is highly viable because skill-position drop-off "
                "is much flatter. Otherwise, scoop falling consensus steals like Kenneth Walker III (KC, +10), Drake London (ATL, +5), and Malik Nabers (NYG, +5)."
            )
            target_positions = ["TE", "QB", "WR", "RB"]
            directive_color = "strategy-card-accent-purple"
        elif cur_rd <= 8:
            directive_title = "⚡ PHASE 3 (ROUNDS 6–8): SECURE DUAL-THREAT QB & HIGH-FLOOR FLEX"
            directive_body = (
                "If you waited on QB, this is the golden pocket: Lamar Jackson (BAL, #42), Drake Maye (NE, #51), Joe Burrow (CIN, #57, +7 steal), or Jalen Hurts (PHI, #61, +5 steal). "
                "At TE, Colston Loveland (CHI, #34, +8 steal) is an elite target. Lock down your FLEX spot with explosive WRs like Zay Flowers (BAL, +7) or DeVonta Smith (PHI, +5). "
                "Remember: never take a mid-tier QB—either lock in an elite dual threat or wait until Rounds 8–10+."
            )
            target_positions = ["QB", "TE", "WR"]
            directive_color = "strategy-card-accent-green"
        elif cur_rd <= 14:
            directive_title = "🚀 PHASE 4 (ROUNDS 9–14): 100% UPSIDE BENCH (NO SAFE FLOOR TRAPS!)"
            directive_body = (
                "Draft for upside, not depth! In an 8-team league, your bench is nearly worthless for static points. Dedicate all 7 bench slots to: "
                "1) Preseason breakout rookies (Brian Thomas Jr. [JAX, +18 steal], Caleb Williams [CHI, +18 steal]), and 2) Contingent league-winning handcuffs "
                "(Blake Corum [LAR], Zach Charbonnet [SEA], Ray Davis [BUF]) who become instant top-10 RB1s if the starter misses time. "
                "Never draft a backup QB, Kicker, or DST."
            )
            target_positions = ["WR", "RB", "QB", "TE"]
            directive_color = "strategy-card-accent-gold"
        else:
            directive_title = "🚑 PHASE 5 (ROUNDS 15–16): THE IR STASH HACK & STREAMING DST/K"
            directive_body = (
                "DO NOT draft a DST or Kicker early. Use Round 15 to draft a high-upside player on PUP/IR or suspension (Jonathon Brooks [CAR], T.J. Hockenson [MIN], Rashee Rice [KC]). "
                "Post-draft, immediately move them to your dedicated IR slot and pick up a free Week 1 waiver wire player! Draft your streaming DST and Kicker in the final round."
            )
            target_positions = ["IR", "DST", "K"]
            directive_color = "strategy-card-accent-red"

    with sc_c2:
        st.markdown(f"""
        <div class="strategy-card {directive_color}">
            <div class="strategy-header-title">{directive_title}</div>
            <div style="font-size:0.86rem; color:#cbd5e1; line-height:1.45;">
                {directive_body}
            </div>
            <div style="margin-top:10px; font-size:0.8rem; font-weight:700; color:#38bdf8;">
                🎯 Recommended Focus: <span style="color:#f8fafc;">{", ".join(target_positions)}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 3. LIVE RECOMMENDED TARGETS WITH 1-CLICK DRAFT
    # Check Mike Clay's 16-Round Blueprint target for the user's current round
    if 1 <= cur_rd <= 16:
        clay_rounds = RAW_ESPN_CHEAT_SHEET_DATA.get("clay_draft_board", {}).get("rounds", [])
        if cur_rd - 1 < len(clay_rounds):
            clay_cur = clay_rounds[cur_rd - 1]
            c_target_player = clay_cur.get("player", "")
            c_target_alt = clay_cur.get("alt_player", "")
            c_pos = clay_cur.get("pos", "")
            c_note = clay_cur.get("note", "")

            # Look up primary target in draft board
            c_match = None
            for _, p_row in df_board.iterrows():
                if clean_name_key(p_row.get("name", "")) == clean_name_key(c_target_player):
                    c_match = p_row
                    break

            if c_match is not None:
                c_drafted = c_match["is_drafted"]
                c_user = c_match.get("drafted_by_user", False)
                c_pid = c_match["player_id"]
                c_pname = c_match["name"]
                c_crank = int(c_match["consensus_rank"]) if pd.notna(c_match.get("consensus_rank")) else "N/A"
                c_espn = int(c_match["espn_rank"]) if pd.notna(c_match.get("espn_rank")) and c_match.get("espn_rank") < 900 else "N/A"

                if not c_drafted:
                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%); border: 1.5px solid #6366f1; border-radius: 8px; padding: 12px 16px; margin-bottom: 14px; box-shadow: 0 4px 12px rgba(99,102,241,0.25);">
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                            <div style="display:flex; align-items:center; gap:8px;">
                                <span style="background:#4f46e5; color:#ffffff; font-weight:800; padding:2px 8px; border-radius:4px; font-size:0.75rem; letter-spacing:0.5px;">📋 CLAY BLUEPRINT &bull; ROUND {cur_rd} TARGET</span>
                                <strong style="color:#e0e7ff; font-size:1.05rem;">{c_pname}</strong>
                                <span class="pos-badge pos-{c_match['pos']}">{c_match['pos']}</span>
                                <span style="color:#94a3b8; font-size:0.82rem;">({c_match['team']} &bull; Wk {c_match['bye']})</span>
                            </div>
                            <span style="background:#064e3b; color:#34d399; font-weight:800; padding:3px 10px; border-radius:4px; font-size:0.78rem; border:1px solid #059669;">🟢 AVAILABLE ON BOARD</span>
                        </div>
                        <div style="margin-top:6px; color:#cbd5e1; font-size:0.84rem;">
                            <strong>Consensus #{c_crank}</strong> &bull; <strong>ESPN #{c_espn}</strong> &bull; <span style="color:#a5b4fc;">Strategy:</span> <em>{c_note}</em>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    clay_c1, clay_c2, _ = st.columns([1.6, 1.4, 4.0])
                    with clay_c1:
                        if st.button(f"🟩 Draft {c_pname} (My Team)", key=f"strat_clay_draft_{c_pid}", use_container_width=True, type="primary"):
                            execute_pick(c_pid, drafted_by_user=True)
                            st.rerun()
                    with clay_c2:
                        if st.button(f"⬛ Cross Off", key=f"strat_clay_cross_{c_pid}", use_container_width=True):
                            execute_pick(c_pid, drafted_by_user=False)
                            st.rerun()
                else:
                    tag_txt = "ON YOUR ROSTER" if c_user else "TAKEN BY OPPONENT"
                    tag_bg = "#1e3a8a" if c_user else "#374151"
                    st.markdown(f"""
                    <div style="background:#0b0f19; border: 1px dashed #475569; border-radius: 8px; padding: 10px 14px; margin-bottom: 14px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <span style="color:#818cf8; font-weight:700; font-size:0.78rem;">📋 CLAY BLUEPRINT &bull; ROUND {cur_rd} TARGET:</span>
                                <span style="text-decoration:line-through; color:#94a3b8; font-size:0.95rem; margin-left:6px;">{c_pname} ({c_match['pos']} - {c_match['team']})</span>
                            </div>
                            <span style="background:{tag_bg}; color:#cbd5e1; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;">{tag_txt}</span>
                        </div>
                        <div style="margin-top:4px; color:#94a3b8; font-size:0.8rem;">
                            <em>Clay's Plan: {c_note}</em> &bull; Target is taken; pivot to top available recommendations below!
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background: #0f172a; border: 1px solid #312e81; border-radius: 8px; padding: 10px 14px; margin-bottom: 14px;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="background:#4338ca; color:#fff; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;">📋 CLAY BLUEPRINT &bull; ROUND {cur_rd} FOCUS</span>
                        <strong style="color:#e0e7ff; font-size:0.95rem;">{clay_cur.get('target', 'Best Available')}</strong>
                        <span style="color:#94a3b8; font-size:0.82rem;">({c_pos})</span>
                    </div>
                    <div style="margin-top:4px; color:#94a3b8; font-size:0.82rem;">
                        <em>Clay's Directive:</em> {c_note}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("#### ⚡ Recommended Live Targets on Active Board")
    st.caption("Top available players matching current tactical directive. Execute picks with 1-click without switching tabs.")

    avail_pool = df_board[~df_board["is_drafted"]].copy()

    # Exclude season ending IR from recommended targets
    avail_pool = avail_pool[~avail_pool["is_season_out"]].copy()

    # Filter by target positions if specified and not empty
    if target_positions and "IR" not in target_positions:
        pos_filter = [p for p in target_positions if p in ["QB", "RB", "WR", "TE", "DST", "K"]]
        if pos_filter:
            recom_df = avail_pool[avail_pool["pos"].isin(pos_filter)].copy()
        else:
            recom_df = avail_pool.copy()
    else:
        recom_df = avail_pool.copy()

    # In IR phase, surface PUP/Suspension candidates
    if "IR" in target_positions:
        ir_cands = avail_pool[avail_pool["injury_tier"].isin(["PUP_MULTI_WEEK", "SUSPENSION", "OUT_WEEK_1"])]
        if not ir_cands.empty:
            recom_df = ir_cands.copy()

    # Prioritize consensus rank
    recom_df = recom_df.sort_values(by=["consensus_rank"]).head(6)

    if recom_df.empty:
        st.info("No active players currently match the targeted position criteria.")
    else:
        for _, r_row in recom_df.iterrows():
            r_pid = r_row["player_id"]
            r_name = r_row["name"]
            r_pos = r_row["pos"]
            r_team = r_row["team"]
            r_bye = r_row["bye"]
            r_tier = r_row["tier"]
            r_crank = int(r_row["consensus_rank"])
            r_espn = int(r_row["espn_rank"]) if pd.notna(r_row["espn_rank"]) and r_row["espn_rank"] < 900 else "N/A"
            r_vdiff = int(r_row["value_diff"]) if pd.notna(r_row["value_diff"]) else 0
            r_inj_badge = r_row.get("injury_badge", "")

            # Value badge formatting
            if r_vdiff >= 10:
                v_badge_html = f"<span style='background:#064e3b; color:#34d399; font-weight:800; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>🔥 +{r_vdiff} MEGA STEAL</span>"
            elif r_vdiff >= 5:
                v_badge_html = f"<span style='background:#1e3a8a; color:#60a5fa; font-weight:800; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>⚡ +{r_vdiff} VALUE STEAL</span>"
            elif r_vdiff <= -5:
                v_badge_html = f"<span style='background:#7f1d1d; color:#f87171; font-weight:800; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>⚠️ {r_vdiff} REACH TRAP</span>"
            else:
                v_badge_html = f"<span style='color:#94a3b8; font-size:0.75rem;'>Value: {r_vdiff:+d}</span>"

            rc1, rc2, rc3, rc4, rc5 = st.columns([1, 3.5, 2.5, 1.8, 1.8])
            with rc1:
                st.markdown(f"**#{r_crank}**<br><span style='color:#94a3b8; font-size:0.72rem;'>Tier {r_tier}</span>", unsafe_allow_html=True)
            with rc2:
                inj_line = f"<div style='font-size:0.75rem; color:#f59e0b; margin-top:2px;'>{r_inj_badge}</div>" if r_inj_badge else ""
                st.markdown(f"""
                <div style="display:flex; align-items:center; gap:8px;">
                    <span class="pos-badge pos-{r_pos}">{r_pos}</span>
                    <strong style="font-size:0.95rem;">{r_name}</strong>
                    <span style="color:#94a3b8; font-size:0.8rem;">({r_team} - Wk {r_bye})</span>
                </div>
                {inj_line}
                """, unsafe_allow_html=True)
            with rc3:
                st.markdown(f"ESPN: <strong>#{r_espn}</strong> &bull; {v_badge_html}", unsafe_allow_html=True)
            with rc4:
                if st.button("🟩 Draft (My Team)", key=f"strat_draft_{r_pid}", use_container_width=True):
                    execute_pick(r_pid, drafted_by_user=True)
                    st.rerun()
            with rc5:
                if st.button("⬛ Cross Off", key=f"strat_cross_{r_pid}", use_container_width=True):
                    execute_pick(r_pid, drafted_by_user=False)
                    st.rerun()
            st.markdown("<div style='border-bottom: 1px solid #1e293b; margin: 4px 0 8px 0;'></div>", unsafe_allow_html=True)

    st.markdown("---")

    # 4. DEEP-DIVE STRATEGIC PLAYBOOK CARDS
    st.markdown("#### 📚 Executive 8-Team Strategy Playbooks & Master Guide")

    p_col1, p_col2 = st.columns(2)

    with p_col1:
        st.markdown("""
        <div class="strategy-card strategy-card-accent-blue">
            <div class="strategy-header-title">📊 1. The 8-Team Mathematical Reality: Tighter Margins & Scarcity Flip</div>
            <p style="font-size:0.85rem; color:#cbd5e1; line-height:1.5;">
                In an 8-team league with 16 rounds, only <strong>128 total players</strong> are drafted across the entire league. 
                Players who would be drafted in Rounds 11–13 of a 12-team league are sitting on your <strong>free waiver wire all season</strong>!
            </p>
            <ul style="font-size:0.82rem; color:#94a3b8; padding-left:18px; line-height:1.55;">
                <li><strong>The 'Every Team is Loaded' Paradox:</strong> If your roster looks 'pretty good,' you will finish 5th. Every opponent has Pro Bowl starters. Your margins are tighter: because opponents have a much higher chance of hitting on superstars, you are <strong>far more penalized for missing in the draft</strong>. Playing it safe guarantees mediocrity. Your edge comes strictly from maximizing <em>ceiling, not floor</em>.</li>
                <li><strong>Zero Value in 'Floor' Starters:</strong> A safe committee RB or possession WR who gets you 9–10 PPR points per game is a weekly liability when opposing starting lineups average 140–150+ PPR points. Don't draft 'safe' RB2s—swing for players with league-winning ceilings.</li>
                <li><strong>Scarcity Flips & Sky-High Replacement Level:</strong> The gap between your starters and the waiver wire is what wins championships. That gap is massive at the very top of each position (elite stars), while mid-round 'safe floor' guys are essentially identical to free agents. Your bench is strictly for bye weeks, injuries, and astronomical upside swings.</li>
                <li><strong>The Waiver Wire Is Your 'Second Draft' Every Week:</strong> In-season, be the most aggressive waiver wire operator in the league. If a high-upside draft pick busts, the waiver wire offers immediate startable replacements. Roster exactly 1 QB, 1 K, and 1 DST—use all 7 bench slots for high-ceiling RB/WR lottery tickets and contingent handcuffs.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="strategy-card strategy-card-accent-gold">
            <div class="strategy-header-title">⚡ 2. Top ESPN Arbitrage Steals & Traps</div>
            <p style="font-size:0.85rem; color:#cbd5e1; line-height:1.5;">
                Our 11-expert consensus exposes huge flaws in the default ESPN draft room rankings:
            </p>
            <div style="font-size:0.82rem; color:#cbd5e1; line-height:1.6;">
                <strong style="color:#34d399;">🔥 Top Target Steals (Draft 1–2 Rounds Late):</strong><br>
                &bull; <strong>Brian Thomas Jr. (WR, JAX, Wk 7)</strong>: Consensus #78 vs ESPN #96 (<span style="color:#34d399; font-weight:700;">+18 Steal</span>)<br>
                &bull; <strong>Caleb Williams (QB, CHI, Wk 10)</strong>: Consensus #69 vs ESPN #87 (<span style="color:#34d399; font-weight:700;">+18 Steal</span>)<br>
                &bull; <strong>Christian Watson (WR, GB, Wk 11)</strong>: Consensus #59 vs ESPN #74 (<span style="color:#34d399; font-weight:700;">+15 Steal</span>)<br>
                &bull; <strong>Luther Burden III (WR, CHI, Wk 10)</strong>: Consensus #45 vs ESPN #59 (<span style="color:#34d399; font-weight:700;">+14 Steal</span>)<br>
                &bull; <strong>Kenneth Walker III (RB, KC, Wk 5)</strong>: Consensus #18 vs ESPN #28 (<span style="color:#34d399; font-weight:700;">+10 Steal</span>)<br>
                &bull; <strong>Colston Loveland (TE, CHI, Wk 10)</strong>: Consensus #34 vs ESPN #42 (<span style="color:#34d399; font-weight:700;">+8 Steal</span>)<br>
                &bull; <strong>Drake London (WR, ATL, Wk 11)</strong>: Consensus #13 vs ESPN #18 (<span style="color:#34d399; font-weight:700;">+5 Steal</span>)<br>
                <br>
                <strong style="color:#f87171;">⚠️ Reach Traps to Avoid (Let Opponents Draft):</strong><br>
                &bull; <strong>Ashton Jeanty (RB, LV)</strong>: Consensus #23 vs ESPN #17 (<span style="color:#f87171; font-weight:700;">-6 Reach Trap</span>)<br>
                &bull; <strong>Trey Benson (RB, ARI)</strong>: Season-ending injury; do not draft!<br>
                &bull; <strong>Jayden Higgins (WR, HOU)</strong>: Torn ACL; do not draft!
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="strategy-card strategy-card-accent-green">
            <div class="strategy-header-title">🚑 3. The 17th Roster Spot 'IR Stash Hack'</div>
            <p style="font-size:0.85rem; color:#cbd5e1; line-height:1.5;">
                Your ESPN setup features <strong>1 dedicated IR / Stash slot</strong>. Here is how to exploit it on draft day:
            </p>
            <ol style="font-size:0.82rem; color:#94a3b8; padding-left:18px; line-height:1.5;">
                <li><strong>Target a PUP / Multi-Week IR Stud in Round 14–15:</strong> Intentionally draft an injured player with massive late-season ceiling who is designated on Reserve/PUP or IR to open 2026 (e.g. <em>Zach Charbonnet [SEA, Reserve/PUP], Tank Dell [HOU, Reserve/IR], or Isiah Pacheco [DET, IR]</em>).</li>
                <li><strong>Immediate Post-Draft Transfer:</strong> The second your draft concludes, move that player directly into your <strong>IR Slot</strong> in the ESPN fantasy app.</li>
                <li><strong>Claim a Free Waiver Wire Player:</strong> With an empty bench spot now open, immediately claim the top available breakout candidate or backup running back from waivers <em>before Week 1 kicks off</em>.</li>
                <li><strong>Result:</strong> You enter Week 1 with <strong>17 players</strong> on your roster while your league-mates only have 16!</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)

    with p_col2:
        st.markdown("""
        <div class="strategy-card strategy-card-accent-purple">
            <div class="strategy-header-title">🔑 4. The 5 Cardinal 8-Team Strategic Shifts</div>
            <div style="font-size:0.82rem; color:#cbd5e1; line-height:1.55;">
                <strong>1. Prioritize Studs & Upside Over Safety:</strong><br>
                <span style="color:#94a3b8;">Depth doesn't win championships in an 8-team league—superstars do. Stack your roster with high-upside players and don't be afraid to swing for the fences in every round. Safe, reliable, high-floor, low-ceiling guys are not valuable. If high-upside guys bust, the waiver wire will have far better options than you are used to in 12-team leagues. Don't draft 'safe' RB2s—swing for league-winning ceilings.</span><br><br>
                <strong>2. You CAN Be Aggressive at QB and TE Early:</strong><br>
                <span style="color:#94a3b8;">In 12-team leagues, taking Josh Allen or Brock Bowers early leaves glaring holes at RB/WR. But in 8-team leagues, there is no steep drop-off at skill positions. Drafting Brock Bowers (LV) in Round 2 and Josh Allen (BUF) in Round 4 creates an insurmountable weekly positional advantage while still allowing you to recover with top-tier starting RBs and WRs.</span><br><br>
                <strong>3. The Waiver Wire Is Your Secret Weapon:</strong><br>
                <span style="color:#94a3b8;">You can and should roster just 1 QB, 1 K, and 1 DST. Pick up bye-week coverage only for the week you need, then drop them immediately for extra skill-position depth. Do not draft a backup at any onesie position—it is a wasted roster spot that belongs on high-upside RB/WR lottery tickets.</span><br><br>
                <strong>4. Push 'Wait on QB' to the EXTREME (The Fork in the Road):</strong><br>
                <span style="color:#94a3b8;">Only 8 QBs start each week. With Allen, Daniels, Jackson, Maye, Hurts, Burrow, plus Dart, Lawrence, Prescott, Nix, Purdy, and Stafford, there are 12+ viable weekly starters. Even the last team to take a QB gets a top-12 option, and streaming is always open. <em>The Cardinal Rule:</em> Either grab an elite difference-maker early (Allen) or wait until Rounds 8–10+. <strong>Never draft a mid-tier QB in rounds 5–7!</strong></span><br><br>
                <strong>5. Tight End Is a Sneaky Priority:</strong><br>
                <span style="color:#94a3b8;">Tight end is fantasy's thinnest position, and elite options dry up fast. Even in an 8-team format, the gap between TE1/TE3 (Bowers, McBride, Loveland) and TE8 is massive. Securing a top-3 TE gives you a persistent positional edge that streaming opponents cannot match. If you miss the elite tier, wait until the very end—TE8 vs TE14 is indistinguishable noise.</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="strategy-card strategy-card-accent-blue">
            <div class="strategy-header-title">📋 5. Master 8-Team Draft-Day Checklist & Round Blueprint</div>
            <div style="font-size:0.82rem; color:#cbd5e1; line-height:1.55;">
                &bull; <strong>Rounds 1–2 (Ceiling, Not Floor):</strong> Take the two highest-ceiling players available, position-agnostic (Gibbs/Bijan/Nacua/Chase/JSN tier). In an 8-team room, you get two picks in the top 16 (basically two 1st-rounders). Do not reach for positional need—replacement level covers you.<br>
                &bull; <strong>Rounds 3–5 (Skill Avalanche + Elite TE Window):</strong> Hammer WR/RB value. When opponents draft QBs early (25% of the league punting skill players for a round), elite WR2/RB2 talent falls directly to you. You can realistically emerge with three top-15 WRs or two top-15 WRs + two top-12 RBs. Elite TE (Bowers/McBride/Loveland) is prime here.<br>
                &bull; <strong>QB Strategy (Rounds 8–10 or Early Hammer):</strong> One QB only! Either pay for Josh Allen early or wait until Rounds 8–10 for Lamar Jackson, Jalen Hurts, Drake Maye, or Joe Burrow. The waiver wire is your backup—never draft a second QB.<br>
                &bull; <strong>RB Strategy (Pass-Catchers & Contingent Handcuffs):</strong> True three-down pass-catchers are rare (~6–8 players). If you miss early, don't panic-draft 10-point committee backs. Target ambiguous backfields and elite contingent handcuffs (Blake Corum, Zach Charbonnet, Ray Davis) who become instant RB1s if the starter misses time.<br>
                &bull; <strong>Bench (Rounds 9–14 = 100% Upside):</strong> Dedicate your last 5–6 picks exclusively to lottery tickets: rookie breakouts, ambiguous situations, and backups to injury-prone starters. A boring WR4 who gets 80 targets is on waivers all year anyway.<br>
                &bull; <strong>K & DST (Rounds 15–16):</strong> Last two picks, no exceptions! Stream both weekly off waivers based on Vegas spreads and matchups.<br>
                &bull; <strong>In-Season (The Second Draft):</strong> Be the most active waiver manager in the league. With ~128 players rostered, the waiver wire is a weekly goldmine.
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="strategy-card strategy-card-accent-purple">
            <div class="strategy-header-title">🏆 6. Championship Roster Architecture</div>
            <p style="font-size:0.85rem; color:#cbd5e1; line-height:1.5;">
                What an elite 8-Team PPR roster looks like after 16 rounds of value arbitrage (with distinct team pairings and no same-team WR stacks):
            </p>
            <div style="font-size:0.8rem; background:#0b0f19; border:1px solid #1f2937; border-radius:6px; padding:10px 14px; font-family:monospace; line-height:1.5; color:#e2e8f0;">
                <strong>STARTING NINE (PPR):</strong><br>
                QB:   Lamar Jackson (BAL, Wk 13)       [R6, Pick 45] (25+ PPG rushing upside)<br>
                RB1:  Jahmyr Gibbs (DET, Wk 6)         [R1, Pick 4]  (Dual-threat bellcow)<br>
                RB2:  Kenneth Walker III (KC, Wk 5)    [R3, Pick 20] (+10 ESPN Steal)<br>
                WR1:  CeeDee Lamb (DAL, Wk 14)         [R2, Pick 13] (150+ target alpha)<br>
                WR2:  Drake London (ATL, Wk 11)        [R4, Pick 29] (+5 ESPN Steal - avoids DAL WR stack)<br>
                TE:   Brock Bowers (LV, Wk 13)         [R5, Pick 36] (Positional hammer)<br>
                FLEX: Malik Nabers (NYG, Wk 8)         [R7, Pick 52] (Target-hog WR)<br>
                DST:  Denver Broncos (DEN, Wk 10)      [R15, Pick 116] (Week 1 Streamer)<br>
                K:    Harrison Butker (KC, Wk 5)       [R16, Pick 125] (High-scoring offense)<br><br>
                <strong>BENCH (7 High-Upside / League-Winner Slots):</strong><br>
                B1: Brian Thomas Jr. (JAX, Wk 7)       [R8, Pick 61] (🚀 Rookie WR1 Breakout)<br>
                B2: Zay Flowers (BAL, Wk 13)           [R9, Pick 68] (Target monster WR)<br>
                B3: Caleb Williams (CHI, Wk 10)        [R10, Pick 77] (High-ceiling dual threat)<br>
                B4: Blake Corum (LAR, Wk 11)           [R11, Pick 84] (Contingent bellcow handcuff)<br>
                B5: Colston Loveland (CHI, Wk 10)      [R12, Pick 93] (+8 TE Value Steal)<br>
                B6: Christian Watson (GB, Wk 11)       [R13, Pick 100] (+15 Steal)<br>
                B7: Keaton Mitchell (LAC, Wk 5)        [R14, Pick 109] (High-upside change-of-pace RB)<br><br>
                <strong>IR STASH (17th Roster Spot Hack):</strong><br>
                IR: Zach Charbonnet (SEA, Wk 11 - Reserve/PUP) or Tank Dell (HOU, Wk 8 - Reserve/IR) [Round 14 Stash]
            </div>
        </div>
        """, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# --- Tab: ESPN Expert Cheat Sheet War Room ---
# -----------------------------------------------------------------------------
with tab_espn_cs:
    st.markdown("### 📋 ESPN Ultimate 2026 Fantasy Cheat Sheet War Room")
    st.caption(
        "Official 2026 preseason draft intelligence and consensus directly extracted from ESPN's senior fantasy editorial team: "
        "**Erik Karabell, Matt Bowen, Mike Clay, Adam Schefter, Field Yates, Matt Florio, Eric Moody, Liz Loza, and Tristan H. Cockcroft**."
    )

    # 1. Top KPI Summary Cards
    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)
    
    total_indexed = len(build_player_espn_index())
    heat_2plus = len(df_board[df_board["espn_heat_index"] >= 2])
    
    # Calculate Clay blueprint available
    clay_named_targets = [
        r.get("player") for r in RAW_ESPN_CHEAT_SHEET_DATA.get("clay_draft_board", {}).get("rounds", [])
        if r.get("player") and "Best" not in r.get("player", "") and "Breakout" not in r.get("player", "") and "Kicker" not in r.get("player", "")
    ]
    clay_avail_count = 0
    for ct in clay_named_targets:
        match_p = df_board[df_board["name"].apply(clean_name_key) == clean_name_key(ct)]
        if not match_p.empty and not match_p.iloc[0]["is_drafted"]:
            clay_avail_count += 1

    # Calculate Karabell targets available
    karabell_targets = [p.get("name") for p in RAW_ESPN_CHEAT_SHEET_DATA.get("karabell_do_draft", {}).get("players", [])]
    karabell_avail_count = 0
    for kt in karabell_targets:
        match_p = df_board[df_board["name"].apply(clean_name_key) == clean_name_key(kt)]
        if not match_p.empty and not match_p.iloc[0]["is_drafted"]:
            karabell_avail_count += 1

    karabell_fades_count = len(df_board[df_board["is_espn_fade"]])

    with kpi_col1:
        st.markdown(f"""
        <div class="strategy-card strategy-card-accent-blue" style="padding:10px 14px; text-align:center;">
            <div style="font-size:0.75rem; color:#94a3b8; font-weight:700; text-transform:uppercase;">Cheat Sheet Pool</div>
            <div style="font-size:1.6rem; font-weight:800; color:#38bdf8;">{total_indexed}</div>
            <div style="font-size:0.75rem; color:#cbd5e1;">Players Indexed from PDF</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col2:
        st.markdown(f"""
        <div class="strategy-card strategy-card-accent-purple" style="padding:10px 14px; text-align:center;">
            <div style="font-size:0.75rem; color:#94a3b8; font-weight:700; text-transform:uppercase;">Heat Consensus (2+)</div>
            <div style="font-size:1.6rem; font-weight:800; color:#c084fc;">{heat_2plus}</div>
            <div style="font-size:0.75rem; color:#cbd5e1;">Endorsed by 2+ Analysts</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col3:
        st.markdown(f"""
        <div class="strategy-card strategy-card-accent-green" style="padding:10px 14px; text-align:center;">
            <div style="font-size:0.75rem; color:#94a3b8; font-weight:700; text-transform:uppercase;">Clay Blueprint Avail</div>
            <div style="font-size:1.6rem; font-weight:800; color:#34d399;">{clay_avail_count} / {len(clay_named_targets)}</div>
            <div style="font-size:0.75rem; color:#cbd5e1;">Available on Active Board</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col4:
        st.markdown(f"""
        <div class="strategy-card strategy-card-accent-gold" style="padding:10px 14px; text-align:center;">
            <div style="font-size:0.75rem; color:#94a3b8; font-weight:700; text-transform:uppercase;">Karabell Targets</div>
            <div style="font-size:1.6rem; font-weight:800; color:#fbbf24;">{karabell_avail_count} / {len(karabell_targets)}</div>
            <div style="font-size:0.75rem; color:#cbd5e1;">Do Draft Targets Avail</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col5:
        st.markdown(f"""
        <div class="strategy-card strategy-card-accent-red" style="padding:10px 14px; text-align:center;">
            <div style="font-size:0.75rem; color:#94a3b8; font-weight:700; text-transform:uppercase;">Karabell Fades</div>
            <div style="font-size:1.6rem; font-weight:800; color:#f87171;">{karabell_fades_count}</div>
            <div style="font-size:0.75rem; color:#cbd5e1;">Flagged Overvalued Traps</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

    # 2. Subview Selection
    cs_subview = st.radio(
        "Select ESPN Intelligence Module:",
        [
            "📋 Mike Clay's 16-Round Blueprint",
            "🔥 ESPN Consensus Heat Radar",
            "📊 Positional Tiers Matrix (Bowen & Karabell)",
            "👥 Analyst Rolodex & Specialized Target Lists"
        ],
        horizontal=True,
        key="espn_cs_subview_radio"
    )

    st.markdown("<div style='border-bottom: 1px solid #1e293b; margin: 10px 0 16px 0;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # MODULE 1: MIKE CLAY'S 16-ROUND BLUEPRINT
    # =========================================================================
    if cs_subview == "📋 Mike Clay's 16-Round Blueprint":
        st.markdown("#### 📋 Mike Clay's Round-by-Round 16-Round Draft Blueprint")
        st.caption(
            "Mike Clay's recommended blueprint for navigating all 16 rounds of a PPR draft. "
            "Picks synchronize with your active draft board in real time."
        )

        clay_data = RAW_ESPN_CHEAT_SHEET_DATA.get("clay_draft_board", {})
        c_rounds = clay_data.get("rounds", [])

        # Round status summary
        total_rounds = len(c_rounds)
        rounds_user_drafted = 0
        rounds_taken = 0
        rounds_avail = 0

        for r_item in c_rounds:
            p_name = r_item.get("player", "")
            if "Best" not in p_name and "Breakout" not in p_name and "Kicker" not in p_name:
                m = df_board[df_board["name"].apply(clean_name_key) == clean_name_key(p_name)]
                if not m.empty:
                    row_m = m.iloc[0]
                    if row_m["is_drafted"]:
                        if row_m.get("drafted_by_user", False):
                            rounds_user_drafted += 1
                        else:
                            rounds_taken += 1
                    else:
                        rounds_avail += 1

        b_sc1, b_sc2, b_sc3 = st.columns(3)
        with b_sc1:
            st.metric("Blueprint Targets Available", f"{rounds_avail} / {len(clay_named_targets)}")
        with b_sc2:
            st.metric("Secured on Your Roster", f"{rounds_user_drafted}")
        with b_sc3:
            st.metric("Taken by Opponents", f"{rounds_taken}")

        st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

        for r_item in c_rounds:
            r_num = r_item["round"]
            r_target = r_item["target"]
            r_player = r_item.get("player", "")
            r_alt = r_item.get("alt_player", "")
            r_pos = r_item.get("pos", "")
            r_team = r_item.get("team", "")
            r_note = r_item.get("note", "")

            # Highlight current round
            is_current_round = (r_num == cur_rd)
            card_border = "2px solid #6366f1" if is_current_round else "1px solid #1e293b"
            card_bg = "linear-gradient(90deg, #1e1b4b 0%, #0b0f19 100%)" if is_current_round else "#0b0f19"
            round_badge_color = "#4f46e5" if is_current_round else "#1e293b"
            cur_tag = "<span style='background:#4f46e5; color:#ffffff; font-size:0.72rem; font-weight:800; padding:2px 8px; border-radius:4px; margin-left:8px;'>👈 ACTIVE ROUND</span>" if is_current_round else ""

            # Check if this round targets a specific named player
            p_match = None
            if r_player and "Best" not in r_player and "Breakout" not in r_player and "Kicker" not in r_player:
                found = df_board[df_board["name"].apply(clean_name_key) == clean_name_key(r_player)]
                if not found.empty:
                    p_match = found.iloc[0]

            col_r1, col_r2, col_r3, col_r4 = st.columns([1.2, 4.5, 2.5, 2.5])

            with col_r1:
                st.markdown(f"""
                <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; background:{round_badge_color}; border-radius:8px; padding:10px; height:100%;">
                    <div style="font-size:0.72rem; color:#94a3b8; font-weight:700;">ROUND</div>
                    <div style="font-size:1.6rem; font-weight:900; color:#ffffff;">{r_num}</div>
                </div>
                """, unsafe_allow_html=True)

            with col_r2:
                pos_pill = f"<span class='pos-badge pos-{r_pos}'>{r_pos}</span>" if r_pos in ["QB", "RB", "WR", "TE", "DST", "K"] else f"<span style='background:#334155; color:#cbd5e1; font-weight:700; padding:2px 6px; border-radius:4px; font-size:0.75rem;'>{r_pos}</span>"
                st.markdown(f"""
                <div style="display:flex; align-items:center; gap:8px;">
                    {pos_pill}
                    <strong style="font-size:1.05rem; color:#f8fafc;">{r_target}</strong>
                    {cur_tag}
                </div>
                <div style="margin-top:4px; font-size:0.84rem; color:#cbd5e1; line-height:1.4;">
                    <strong style="color:#a5b4fc;">Clay's Blueprint:</strong> {r_note}
                </div>
                """, unsafe_allow_html=True)

            if p_match is not None:
                p_id = p_match["player_id"]
                p_drafted = p_match["is_drafted"]
                p_user = p_match.get("drafted_by_user", False)
                p_crank = int(p_match["consensus_rank"]) if pd.notna(p_match.get("consensus_rank")) else "N/A"
                p_espn = int(p_match["espn_rank"]) if pd.notna(p_match.get("espn_rank")) and p_match.get("espn_rank") < 900 else "N/A"
                p_val = int(p_match.get("value_diff", 0)) if pd.notna(p_match.get("value_diff")) else 0

                val_pill = f"<span style='color:#34d399; font-weight:700;'>+{p_val}</span>" if p_val > 0 else (f"<span style='color:#f87171; font-weight:700;'>{p_val}</span>" if p_val < 0 else "0")

                with col_r3:
                    if not p_drafted:
                        st.markdown(f"""
                        <div style="font-size:0.82rem; color:#cbd5e1;">
                            <div>Status: <span style="background:#064e3b; color:#34d399; font-weight:800; padding:2px 8px; border-radius:4px; font-size:0.75rem;">🟢 AVAILABLE</span></div>
                            <div style="margin-top:4px;">Consensus: <strong>#{p_crank}</strong> &bull; ESPN: <strong>#{p_espn}</strong> (Diff: {val_pill})</div>
                        </div>
                        """, unsafe_allow_html=True)
                    elif p_user:
                        st.markdown(f"""
                        <div style="font-size:0.82rem; color:#cbd5e1;">
                            <span style="background:#1e3a8a; color:#93c5fd; font-weight:800; padding:2px 8px; border-radius:4px; font-size:0.75rem;">🏆 ON YOUR ROSTER</span>
                            <div style="margin-top:4px; color:#94a3b8;">Consensus #{p_crank}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div style="font-size:0.82rem; color:#94a3b8;">
                            <span style="background:#374151; color:#d1d5db; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;">❌ TAKEN BY OPPONENT</span>
                            <div style="margin-top:4px;">Consensus #{p_crank}</div>
                        </div>
                        """, unsafe_allow_html=True)

                with col_r4:
                    if not p_drafted:
                        btn_c1, btn_c2 = st.columns([1.2, 1.0])
                        with btn_c1:
                            if st.button("🟩 Draft", key=f"clay_board_draft_{p_id}_{r_num}", use_container_width=True, type="primary"):
                                execute_pick(p_id, drafted_by_user=True)
                                st.rerun()
                        with btn_c2:
                            if st.button("⬛ Cross", key=f"clay_board_cross_{p_id}_{r_num}", use_container_width=True):
                                execute_pick(p_id, drafted_by_user=False)
                                st.rerun()
                    else:
                        if st.button("🔄 Restore", key=f"clay_board_restore_{p_id}_{r_num}", use_container_width=True):
                            restore_player(p_id)
                            st.rerun()
            else:
                with col_r3:
                    st.markdown("""
                    <div style="font-size:0.82rem; color:#94a3b8;">
                        <span style="background:#1e293b; color:#94a3b8; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;">🎯 SITUATIONAL DIRECTIVE</span>
                        <div style="margin-top:4px;">Draft best value matching directive</div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_r4:
                    st.caption("See Live Recommendations")

            st.markdown("<div style='border-bottom: 1px solid #1e293b; margin: 8px 0 12px 0;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # MODULE 2: ESPN CONSENSUS HEAT RADAR
    # =========================================================================
    elif cs_subview == "🔥 ESPN Consensus Heat Radar":
        st.markdown("#### 🔥 ESPN Consensus Heat Radar (Ranked by Endorsement Count)")
        st.caption(
            "Identifies players who received multiple independent endorsements across the 9 ESPN analysts. "
            "High heat signifies unanimous draft-day conviction."
        )

        hr_f1, hr_f2, hr_f3, hr_f4 = st.columns([2.2, 1.5, 1.8, 2.5])
        with hr_f1:
            heat_min = st.selectbox(
                "Minimum Heat Level",
                options=[
                    "All Endorsed (1+ Analysts)",
                    "🔥 2+ Analysts (Consensus Smash)",
                    "🔥🔥 3+ Analysts (Super-Consensus)",
                    "🔥🔥🔥 4+ Analysts (Elite Target)"
                ],
                index=1,
                key="hr_heat_min"
            )
        with hr_f2:
            hr_pos = st.selectbox(
                "Position",
                options=["All Positions", "QB", "RB", "WR", "TE", "DST", "K"],
                index=0,
                key="hr_pos_filter"
            )
        with hr_f3:
            hr_avail_only = st.checkbox("Available on Board Only", value=True, key="hr_avail_only")
        with hr_f4:
            hr_search = st.text_input("Search Player or Team", placeholder="Type name or team...", key="hr_search")

        # Parse minimum heat
        min_h = 1
        if "2+" in heat_min:
            min_h = 2
        elif "3+" in heat_min:
            min_h = 3
        elif "4+" in heat_min:
            min_h = 4

        df_heat = df_board[df_board["espn_heat_index"] >= min_h].copy()

        if hr_pos != "All Positions":
            df_heat = df_heat[df_heat["pos"] == hr_pos]

        if hr_avail_only:
            df_heat = df_heat[~df_heat["is_drafted"]]

        if hr_search:
            s_q = hr_search.lower().strip()
            df_heat = df_heat[
                df_heat["name"].str.lower().str.contains(s_q, na=False) |
                df_heat["team"].str.lower().str.contains(s_q, na=False)
            ]

        df_heat = df_heat.sort_values(by=["espn_heat_index", "consensus_rank"], ascending=[False, True]).reset_index(drop=True)

        st.markdown(f"**Found {len(df_heat)} players matching Heat Index &ge; {min_h}**")

        if df_heat.empty:
            st.info("No players match the selected heat and position filters.")
        else:
            for _, h_row in df_heat.iterrows():
                h_id = h_row["player_id"]
                h_name = h_row["name"]
                h_pos = h_row["pos"]
                h_team = h_row["team"]
                h_bye = h_row["bye"]
                h_heat = int(h_row["espn_heat_index"])
                h_badges = h_row.get("espn_expert_badges", "")
                h_crank = int(h_row["consensus_rank"]) if pd.notna(h_row.get("consensus_rank")) else "N/A"
                h_espn = int(h_row["espn_rank"]) if pd.notna(h_row.get("espn_rank")) and h_row.get("espn_rank") < 900 else "N/A"
                h_drafted = h_row["is_drafted"]
                h_user = h_row.get("drafted_by_user", False)
                h_dossier = h_row.get("espn_dossier_html", "")

                heat_stars = "🔥" * min(h_heat, 5)
                heat_pill_color = "#f59e0b" if h_heat >= 3 else "#38bdf8"

                hc1, hc2, hc3, hc4 = st.columns([1.2, 4.0, 2.5, 2.3])
                with hc1:
                    st.markdown(f"""
                    <div style="background:#111827; border:1px solid {heat_pill_color}; border-radius:6px; padding:6px; text-align:center;">
                        <div style="font-size:1.1rem; font-weight:800; color:{heat_pill_color};">{h_heat} Analysts</div>
                        <div style="font-size:0.75rem; letter-spacing:1px;">{heat_stars}</div>
                    </div>
                    """, unsafe_allow_html=True)

                with hc2:
                    st.markdown(f"""
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span class="pos-badge pos-{h_pos}">{h_pos}</span>
                        <strong style="font-size:1.05rem; color:#f8fafc;">{h_name}</strong>
                        <span style="color:#94a3b8; font-size:0.82rem;">({h_team} &bull; Wk {h_bye})</span>
                    </div>
                    <div style="margin-top:3px; font-size:0.76rem; color:#cbd5e1;">
                        {h_badges}
                    </div>
                    """, unsafe_allow_html=True)

                with hc3:
                    st.markdown(f"""
                    <div style="font-size:0.82rem; color:#cbd5e1;">
                        Consensus: <strong>#{h_crank}</strong> &bull; ESPN: <strong>#{h_espn}</strong>
                    </div>
                    """, unsafe_allow_html=True)

                with hc4:
                    if not h_drafted:
                        bc1, bc2 = st.columns([1.2, 1.0])
                        with bc1:
                            if st.button("🟩 Draft", key=f"hr_draft_{h_id}", use_container_width=True, type="primary"):
                                execute_pick(h_id, drafted_by_user=True)
                                st.rerun()
                        with bc2:
                            if st.button("⬛ Cross", key=f"hr_cross_{h_id}", use_container_width=True):
                                execute_pick(h_id, drafted_by_user=False)
                                st.rerun()
                    else:
                        d_lbl = "ON ROSTER" if h_user else "TAKEN"
                        st.markdown(f"<span style='color:#94a3b8; font-size:0.8rem; font-weight:700;'>[{d_lbl}]</span>", unsafe_allow_html=True)

                # Show expandable official dossier
                if h_dossier:
                    with st.expander(f"📖 Analyst Breakdown & Notes for {h_name} ({h_heat} Analysts)", expanded=False):
                        st.markdown(h_dossier, unsafe_allow_html=True)

                st.markdown("<div style='border-bottom: 1px solid #1e293b; margin: 6px 0 10px 0;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # MODULE 3: POSITIONAL TIERS MATRIX (BOWEN & KARABELL)
    # =========================================================================
    elif cs_subview == "📊 Positional Tiers Matrix (Bowen & Karabell)":
        st.markdown("#### 📊 Official ESPN Positional Tiers Matrix")
        st.caption(
            "Authoritative tiers established in NFL26_CS_ULTIMATE.pdf by **Erik Karabell** (Running Backs & Wide Receivers) "
            "and **Matt Bowen** (Quarterbacks & Tight Ends). Monitor tier cliff alerts to draft ahead of drop-offs."
        )

        tier_pos_choice = st.radio(
            "Select Position Tier Matrix:",
            [
                "🏃 Running Backs (Erik Karabell - 13 Tiers)",
                "🎯 Wide Receivers (Erik Karabell - 11 Tiers)",
                "🏈 Quarterbacks (Matt Bowen - 5 Tiers)",
                "🛡️ Tight Ends (Matt Bowen - 3 Tiers)"
            ],
            horizontal=True,
            key="tier_pos_choice"
        )

        tier_config = {}
        if "Running Backs" in tier_pos_choice:
            tier_config = RAW_ESPN_CHEAT_SHEET_DATA.get("karabell_rb_tiers", {})
        elif "Wide Receivers" in tier_pos_choice:
            tier_config = RAW_ESPN_CHEAT_SHEET_DATA.get("karabell_wr_tiers", {})
        elif "Quarterbacks" in tier_pos_choice:
            tier_config = RAW_ESPN_CHEAT_SHEET_DATA.get("bowen_qb_tiers", {})
        elif "Tight Ends" in tier_pos_choice:
            tier_config = RAW_ESPN_CHEAT_SHEET_DATA.get("bowen_te_tiers", {})

        tiers_dict = tier_config.get("tiers", {})
        analyst_author = tier_config.get("analyst", "ESPN Expert")
        pos_target = tier_config.get("position", "")

        for t_num, p_names in tiers_dict.items():
            # Count available players in this tier
            tier_total = len(p_names)
            tier_avail_players = []
            tier_drafted_players = []

            for p_name in p_names:
                m = df_board[df_board["name"].apply(clean_name_key) == clean_name_key(p_name)]
                if not m.empty:
                    p_data = m.iloc[0]
                    if p_data["is_drafted"]:
                        tier_drafted_players.append(p_data)
                    else:
                        tier_avail_players.append(p_data)
                else:
                    # Player not in top 300 / unranked
                    tier_drafted_players.append({"name": p_name, "is_drafted": True, "drafted_by_user": False, "consensus_rank": 999, "player_id": p_name})

            avail_count = len(tier_avail_players)
            is_depleted = (avail_count == 0)
            is_cliff = (avail_count == 1)

            # Tier Header Banner
            header_bg = "#3b0764" if t_num == 1 else ("#1e293b" if avail_count > 1 else ("#451a03" if is_cliff else "#0f172a"))
            header_border = "#c084fc" if t_num == 1 else ("#eab308" if is_cliff else ("#475569" if not is_depleted else "#334155"))
            badge_status = f"<span style='background:#064e3b; color:#34d399; font-weight:800; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>{avail_count} / {tier_total} AVAILABLE</span>" if not is_depleted else "<span style='background:#374151; color:#94a3b8; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>TIER DEPLETED</span>"

            cliff_msg = f"<span style='color:#fbbf24; font-weight:700; font-size:0.8rem; margin-left:10px;'>⚠️ TIER CLIFF: Only 1 player remaining!</span>" if is_cliff else ""

            st.markdown(f"""
            <div style="background:{header_bg}; border:1.5px solid {header_border}; border-radius:8px; padding:10px 14px; margin:14px 0 8px 0; display:flex; justify-content:space-between; align-items:center;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <strong style="color:#ffffff; font-size:1.05rem;">Tier {t_num}</strong>
                    <span style="color:#94a3b8; font-size:0.82rem;">({analyst_author})</span>
                    {cliff_msg}
                </div>
                <div>
                    {badge_status}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Render Available Players First
            if tier_avail_players:
                cols = st.columns(min(len(tier_avail_players), 3))
                for idx, p_row in enumerate(tier_avail_players):
                    p_id = p_row["player_id"]
                    p_n = p_row["name"]
                    p_t = p_row["team"]
                    p_b = p_row["bye"]
                    p_cr = int(p_row["consensus_rank"]) if pd.notna(p_row.get("consensus_rank")) else "N/A"
                    p_espn = int(p_row["espn_rank"]) if pd.notna(p_row.get("espn_rank")) and p_row.get("espn_rank") < 900 else "N/A"
                    p_heat = int(p_row.get("espn_heat_index", 0))
                    p_heat_str = f" &bull; 🔥 {p_heat} Experts" if p_heat >= 2 else ""

                    with cols[idx % len(cols)]:
                        st.markdown(f"""
                        <div style="background:#111827; border:1px solid #1e293b; border-radius:6px; padding:8px 10px; margin-bottom:6px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong style="color:#f8fafc; font-size:0.95rem;">{p_n}</strong>
                                <span style="color:#94a3b8; font-size:0.78rem;">{p_t} (Wk {p_b})</span>
                            </div>
                            <div style="font-size:0.78rem; color:#cbd5e1; margin-top:2px;">
                                Consensus: <strong>#{p_cr}</strong> &bull; ESPN: <strong>#{p_espn}</strong>{p_heat_str}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        b1, b2 = st.columns([1.2, 1.0])
                        with b1:
                            if st.button("🟩 Draft", key=f"tier_draft_{p_id}_{t_num}", use_container_width=True, type="primary"):
                                execute_pick(p_id, drafted_by_user=True)
                                st.rerun()
                        with b2:
                            if st.button("⬛ Cross", key=f"tier_cross_{p_id}_{t_num}", use_container_width=True):
                                execute_pick(p_id, drafted_by_user=False)
                                st.rerun()

            # Render Drafted / Taken Players (Strikethrough)
            if tier_drafted_players:
                drafted_names_html = []
                for p_d in tier_drafted_players:
                    is_u = p_d.get("drafted_by_user", False)
                    u_lbl = "(My Team)" if is_u else "(Opponent)"
                    u_col = "#93c5fd" if is_u else "#64748b"
                    drafted_names_html.append(f"<span style='text-decoration:line-through; color:#64748b;'>{p_d['name']}</span> <span style='font-size:0.75rem; color:{u_col};'>{u_lbl}</span>")

                st.markdown(f"""
                <div style="font-size:0.8rem; color:#64748b; margin-top:4px; padding-left:4px;">
                    <strong>Drafted:</strong> {" &bull; ".join(drafted_names_html)}
                </div>
                """, unsafe_allow_html=True)

    # =========================================================================
    # MODULE 4: ANALYST ROLODEX & SPECIALIZED TARGET LISTS
    # =========================================================================
    elif cs_subview == "👥 Analyst Rolodex & Specialized Target Lists":
        st.markdown("#### 👥 Analyst Rolodex & Specialized Target Lists")
        st.caption(
            "Browse each ESPN expert's individual draft board, priority sleepers, league winners, and warning fades."
        )

        LIST_MAPPING = {
            "🎯 Erik Karabell: 'Do Draft' List": "karabell_do_draft",
            "🛑 Erik Karabell: 'Do Not Draft' Fades": "karabell_do_not_draft",
            "🏹 Matt Bowen: Top Targets": "bowen_top_targets",
            "⭐ Adam Schefter: Picks to Target": "schefter_picks_to_target",
            "🏆 Matt Florio: League Winners": "florio_league_winners",
            "💎 Field Yates: Field's Favorites": "field_favorites",
            "🚀 Liz Loza: Late-Round Fliers": "loza_late_round_fliers",
            "🛡️ Eric Moody: Top Insurance RBs (Handcuffs)": "moody_top_insurance_rbs",
            "🔥 Eric Moody: Top Draft-Day Values": "moody_top_draft_values",
            "💤 Tristan H. Cockcroft: Deep Sleepers": "cockcroft_deep_sleepers",
            "⚡ ESPN Staff: Have Skills, Need Opportunity": "have_skills_need_opportunity"
        }

        sel_list_name = st.selectbox(
            "Select Expert List:",
            options=list(LIST_MAPPING.keys()),
            index=0,
            key="espn_cs_list_select"
        )

        list_key = LIST_MAPPING[sel_list_name]
        list_obj = RAW_ESPN_CHEAT_SHEET_DATA.get(list_key, {})

        l_title = list_obj.get("title", "")
        l_analyst = list_obj.get("analyst", "")
        l_desc = list_obj.get("description", "")
        l_badge = list_obj.get("badge", "")
        l_players = list_obj.get("players", [])

        # Special Alert for Karabell Fades
        if list_key == "karabell_do_not_draft":
            st.markdown(f"""
            <div style="background:#451a03; border:2px solid #ef4444; border-radius:8px; padding:12px 16px; margin-bottom:14px;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <strong style="color:#f87171; font-size:1.05rem;">🛑 KARABELL'S OFFICIAL DRAFT-DAY WARNING</strong>
                </div>
                <div style="margin-top:4px; font-size:0.86rem; color:#fef2f2; line-height:1.45;">
                    Erik Karabell rates these 18 players as <strong>NOT worth their current ESPN ADP</strong> due to excessive injury mileage, split-backfield timeshares, or unproven passing situations.
                    <strong>Key Advice:</strong> Do NOT reach for them at cost. However, Karabell notes they are <em>OK to draft if they slide 2+ full rounds past their ADP</em>!
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:#111827; border:1px solid #3730a3; border-radius:8px; padding:12px 16px; margin-bottom:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <strong style="color:#c084fc; font-size:1.05rem;">{l_title}</strong>
                    <span style="background:#1e1b4b; color:#818cf8; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.78rem;">{l_analyst}</span>
                </div>
                <div style="margin-top:4px; font-size:0.84rem; color:#cbd5e1;">
                    {l_desc}
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Render players in this list
        st.markdown(f"**Total Players in List: {len(l_players)}**")

        for p_item in l_players:
            p_n = p_item.get("name", "")
            p_pos = p_item.get("pos", "")
            p_team = p_item.get("team", "")
            p_adp = p_item.get("adp", "N/A")
            p_note = p_item.get("note", "")

            # Match against df_board
            m_found = df_board[df_board["name"].apply(clean_name_key) == clean_name_key(p_n)]
            m_row = m_found.iloc[0] if not m_found.empty else None

            p_id = m_row["player_id"] if m_row is not None else p_n
            is_drafted = m_row["is_drafted"] if m_row is not None else False
            is_user = m_row.get("drafted_by_user", False) if m_row is not None else False
            crank = int(m_row["consensus_rank"]) if m_row is not None and pd.notna(m_row.get("consensus_rank")) else "N/A"

            lc1, lc2, lc3, lc4 = st.columns([1.0, 4.5, 2.5, 2.0])

            with lc1:
                pos_badge_class = f"pos-badge pos-{p_pos}" if p_pos in ["QB", "RB", "WR", "TE", "DST", "K"] else ""
                st.markdown(f"<span class='{pos_badge_class}'>{p_pos}</span>", unsafe_allow_html=True)

            with lc2:
                name_style = "text-decoration:line-through; color:#94a3b8;" if is_drafted else "color:#f8fafc; font-weight:700;"
                st.markdown(f"""
                <div>
                    <span style="{name_style} font-size:1.0rem;">{p_n}</span>
                    <span style="color:#94a3b8; font-size:0.82rem; margin-left:6px;">({p_team})</span>
                </div>
                <div style="font-size:0.83rem; color:#cbd5e1; margin-top:2px;">
                    <strong style="color:#38bdf8;">Note:</strong> {p_note}
                </div>
                """, unsafe_allow_html=True)

            with lc3:
                adp_info = f"ADP: <strong>{p_adp}</strong>" if p_adp != "N/A" else ""
                st.markdown(f"""
                <div style="font-size:0.82rem; color:#cbd5e1;">
                    Consensus: <strong>#{crank}</strong> &bull; {adp_info}
                </div>
                """, unsafe_allow_html=True)

            with lc4:
                if not is_drafted and m_row is not None:
                    bc1, bc2 = st.columns([1.2, 1.0])
                    with bc1:
                        if st.button("🟩 Draft", key=f"rolodex_draft_{p_id}_{list_key}", use_container_width=True, type="primary"):
                            execute_pick(p_id, drafted_by_user=True)
                            st.rerun()
                    with bc2:
                        if st.button("⬛ Cross", key=f"rolodex_cross_{p_id}_{list_key}", use_container_width=True):
                            execute_pick(p_id, drafted_by_user=False)
                            st.rerun()
                elif is_drafted and m_row is not None:
                    d_tag = "ON ROSTER" if is_user else "TAKEN"
                    st.markdown(f"<span style='color:#94a3b8; font-size:0.8rem; font-weight:700;'>[{d_tag}]</span>", unsafe_allow_html=True)
                else:
                    st.caption("Deep Player")

            st.markdown("<div style='border-bottom: 1px solid #1e293b; margin: 4px 0 8px 0;'></div>", unsafe_allow_html=True)


# --- Tab 4: Running Backs ---
with tab_rb:
    rb_df = df_board[df_board["pos"] == "RB"].copy().reset_index(drop=True)
    render_draft_table(rb_df, key_prefix="rb")

# --- Tab 3: Wide Receivers ---
with tab_wr:
    wr_df = df_board[df_board["pos"] == "WR"].copy().reset_index(drop=True)
    render_draft_table(wr_df, key_prefix="wr")

# --- Tab 4: Quarterbacks ---
with tab_qb:
    qb_df = df_board[df_board["pos"] == "QB"].copy().reset_index(drop=True)
    render_draft_table(qb_df, key_prefix="qb")

# --- Tab 5: Tight Ends ---
with tab_te:
    te_df = df_board[df_board["pos"] == "TE"].copy().reset_index(drop=True)
    render_draft_table(te_df, key_prefix="te")

# --- Tab 6: FLEX Targets ---
with tab_flex:
    flex_df = df_board[df_board["pos"].isin(["RB", "WR", "TE"])].copy().reset_index(drop=True)
    render_draft_table(flex_df, key_prefix="flex")

# --- Tab 7: DST & Kickers ---
with tab_dstk:
    dstk_df = df_board[df_board["pos"].isin(["DST", "K"])].copy().reset_index(drop=True)
    render_draft_table(dstk_df, key_prefix="dstk")

# --- Tab 8: Value Steals & Sleepers ---
with tab_steals:
    st.markdown("### 🔥 2026 Consensus Value Steals & Preseason Rookie Breakouts")
    st.caption("Exploit ESPN's algorithmic ADP lag with live expert consensus steals, dominating preseason rookies, and high-upside sleeper intelligence. Monotonic temporal synchronization ensures reports reflect the latest August/September game film.")

    # -------------------------------------------------------------------------
    # 1. MANUAL SYNC, TEMPORAL RESOLUTION & DB CHANGE TRACKER
    # -------------------------------------------------------------------------
    sl_db = load_sleeper_database()
    sl_meta = sl_db.get("metadata", {})
    sl_last_synced_str = sl_meta.get("last_synced_formatted", "Not yet synced")
    sl_uncommitted_cnt = sl_meta.get("uncommitted_changes", 0)

    sl_sync_col1, sl_sync_col2, sl_sync_col3 = st.columns([1.8, 2.4, 1.8])
    with sl_sync_col1:
        if st.button("🔄 Sync & Refresh Sleeper News", type="primary", use_container_width=True, key="btn_sync_sleepers", help="Synchronizes latest preseason film, coach quotes, and touch share reports with strict temporal precedence (T_new > T_current)"):
            with st.spinner("Scraping live preseason feeds & validating temporal precedence..."):
                up_cnt, up_names, updated_db = sync_sleeper_pipeline()
                st.session_state.draft_board = enrich_board_with_sleepers(st.session_state.draft_board)
                if up_cnt > 0:
                    st.toast(f"⚡ {up_cnt} player(s) updated with newer preseason reports!", icon="⚡")
                else:
                    st.toast("✅ Sleeper intelligence is up to date. Latest temporal reports active.", icon="✅")
                st.rerun()

    with sl_sync_col2:
        if sl_uncommitted_cnt > 0:
            st.markdown(f"""
            <div style="background:#431407; border:1.5px solid #ea580c; border-radius:6px; padding:6px 12px; display:flex; align-items:center; gap:8px;">
                <span style="font-size:1.1rem;">⚠️</span>
                <div style="font-size:0.82rem; line-height:1.3;">
                    <strong style="color:#fdba74;">Database Status:</strong> <span style="color:#f97316; font-weight:800;">{sl_uncommitted_cnt} Uncommitted Updates</span><br/>
                    <span style="color:#cbd5e1; font-size:0.75rem;">Last Synced: {sl_last_synced_str}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:#064e3b25; border:1.5px solid #05966980; border-radius:6px; padding:6px 12px; display:flex; align-items:center; gap:8px;">
                <span style="font-size:1.1rem;">🟢</span>
                <div style="font-size:0.82rem; line-height:1.3;">
                    <strong style="color:#34d399;">Database Status:</strong> <span style="color:#6ee7b7; font-weight:700;">100% Up to Date</span><br/>
                    <span style="color:#cbd5e1; font-size:0.75rem;">Last Synced: {sl_last_synced_str}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with sl_sync_col3:
        sl_json_str = json.dumps(sl_db, indent=2, ensure_ascii=False)
        st.download_button(
            label="📥 Export Sleeper DB (JSON)",
            data=sl_json_str,
            file_name="sleeper_database_2026.json",
            mime="application/json",
            use_container_width=True,
            key="btn_dl_sleepers"
        )

    # -------------------------------------------------------------------------
    # 2. HIGH-LEVEL KPI METRICS
    # -------------------------------------------------------------------------
    # GUARANTEE: Exclude players on season-ending IR or flagged as algorithmic injury traps
    all_steals_df = df_board[
        (df_board["value_diff"] >= 4) &
        (~df_board.get("is_season_out", False)) &
        (df_board.get("injury_tier", "") != "SEASON_IR") &
        (~df_board.get("is_injury_trap", False))
    ].copy()
    rookie_count = len(all_steals_df[all_steals_df.get("is_rookie", False)])
    max_val = all_steals_df["value_diff"].max() if not all_steals_df.empty else 0
    avg_val = round(all_steals_df["value_diff"].mean(), 1) if not all_steals_df.empty else 0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric("🔥 Total Value Steals", f"{len(all_steals_df)} Players", help="Healthy players where Consensus Rank is at least 4 spots ahead of ESPN default")
    with kpi2:
        st.metric("🚀 Preseason Rookies", f"{rookie_count} Phenoms", help="2026 healthy rookies dominating preseason snaps and camp reps")
    with kpi3:
        st.metric("💎 Max Value Discrepancy", f"+{max_val} Picks", help="Largest algorithmic blindspot on ESPN")
    with kpi4:
        st.metric("📈 Avg Steal Advantage", f"+{avg_val} Spots", help="Average draft value captured over ESPN ADP")

    # -------------------------------------------------------------------------
    # 3. INTERACTIVE CATEGORY & POSITION FILTERS
    # -------------------------------------------------------------------------
    sl_f1, sl_f2 = st.columns([3.8, 1.2])
    with sl_f1:
        steals_category = st.radio(
            "Filter Scouting Category:",
            options=[
                "All Steals & Sleepers",
                "🚀 Preseason Rookie Breakouts (Film & Touch Leaders)",
                "💎 High-Upside Value Gems (Val Diff >= 15)",
                "⚡ Top 100 Consensus Steals (Starting Caliber)",
                "🎯 Deep Sleepers & League Winners (Late Rounds)"
            ],
            horizontal=True,
            key="steals_cat_filter"
        )
    with sl_f2:
        steals_pos = st.multiselect(
            "Filter Position:",
            options=["RB", "WR", "QB", "TE"],
            default=[],
            placeholder="All Positions",
            key="steals_pos_filter"
        )

    filtered_steals = all_steals_df.copy()
    if steals_category == "🚀 Preseason Rookie Breakouts (Film & Touch Leaders)":
        filtered_steals = filtered_steals[filtered_steals.get("is_rookie", False)].reset_index(drop=True)
    elif steals_category == "💎 High-Upside Value Gems (Val Diff >= 15)":
        filtered_steals = filtered_steals[filtered_steals["value_diff"] >= 15].reset_index(drop=True)
    elif steals_category == "⚡ Top 100 Consensus Steals (Starting Caliber)":
        filtered_steals = filtered_steals[filtered_steals["consensus_rank"] <= 100].reset_index(drop=True)
    elif steals_category == "🎯 Deep Sleepers & League Winners (Late Rounds)":
        filtered_steals = filtered_steals[filtered_steals["consensus_rank"] > 100].reset_index(drop=True)

    if steals_pos:
        filtered_steals = filtered_steals[filtered_steals["pos"].isin(steals_pos)].reset_index(drop=True)

    filtered_steals = filtered_steals.sort_values(by="value_diff", ascending=False).reset_index(drop=True)

    render_draft_table(filtered_steals, key_prefix="steals")

    # -------------------------------------------------------------------------
    # 4. PRESEASON ROOKIE DOMINANCE & SLEEPER SCOUTING WIRE
    # -------------------------------------------------------------------------
    wire_players = [
        r for _, r in filtered_steals.iterrows() 
        if r.get("preseason_stats") 
        and not r.get("is_season_out", False) 
        and r.get("injury_tier", "") != "SEASON_IR" 
        and not r.get("is_injury_trap", False)
    ]
    if not wire_players:
        wire_players = [
            r for _, r in all_steals_df.iterrows() 
            if r.get("preseason_stats") 
            and not r.get("is_season_out", False) 
            and r.get("injury_tier", "") != "SEASON_IR" 
            and not r.get("is_injury_trap", False)
        ]

    with st.expander(f"📰 2026 Preseason Rookie Dominance & Sleeper Scouting Wire ({len(wire_players)} Scouting Cards)", expanded=True):
        st.caption("Deep-dive scouting reports, preseason game metrics, temporal beat reports, and actionable draft strategies.")
        for p in wire_players[:25]:
            p_name = p["name"]
            p_pos = p["pos"]
            p_team = p["team"]
            val = p["value_diff"]
            cons = p["consensus_rank"]
            espn = p["espn_rank"]
            badge = p.get("sleeper_badge") or "💎 VALUE STEAL"
            grade = p.get("preseason_grade") or "A"
            stats = p.get("preseason_stats") or "Preseason starter reps"
            trend = p.get("preseason_snap_trend") or "Rising"
            blurb = p.get("sleeper_blurb") or ""
            strategy = p.get("sleeper_strategy") or ""
            ts_str = p.get("sleeper_updated_formatted") or "Sep 5, 2026 at 08:00 AM UTC"
            source = p.get("sleeper_source") or "Beat Wire"
            rotowire_url = get_rotowire_url(p_name, p.get("source_url"))

            wire_card = (
                f'<div style="background:#111827; border-left:4px solid #38bdf8; border-radius:6px; padding:12px 16px; margin-bottom:12px; border-top:1px solid #1f2937; border-right:1px solid #1f2937; border-bottom:1px solid #1f2937;">'
                f'<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">'
                f'<div>'
                f'<strong style="color:#f8fafc; font-size:1.02rem;">{p_name} ({p_pos} - {p_team})</strong>'
                f'<span style="color:#94a3b8; font-size:0.82rem; margin-left:8px;">Consensus #{cons} &bull; ESPN #{espn}</span>'
                f'<span style="background:#065f46; color:#34d399; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px; margin-left:8px;">+{val} ESPN Steal</span>'
                f'</div>'
                f'<div style="display:flex; gap:6px; align-items:center;">'
                f'<span style="background:#1e293b; color:#38bdf8; font-size:0.75rem; font-weight:800; padding:3px 8px; border-radius:4px; border:1px solid #0284c740;">{badge}</span>'
                f'<span style="background:#312e81; color:#c7d2fe; font-size:0.75rem; font-weight:800; padding:3px 8px; border-radius:4px;">Grade: {grade}</span>'
                f'</div>'
                f'</div>'
                f'<div style="color:#cbd5e1; font-size:0.84rem; margin-top:6px;">'
                f'<strong>Preseason Production:</strong> <span style="color:#f1f5f9;">{stats}</span> &bull; <strong>Trend:</strong> <span style="color:#38bdf8;">{trend}</span>'
                f'</div>'
                f'<div style="color:#94a3b8; font-size:0.83rem; margin-top:6px; line-height:1.45; background:#0b0f19; padding:8px 12px; border-radius:5px; border:1px solid #1e293b;">'
                f'{blurb}'
                f'</div>'
                f'<div style="color:#fbbf24; font-size:0.8rem; font-weight:600; margin-top:6px;">'
                f'💡 Draft Strategy: {strategy}'
                f'</div>'
                f'<div style="display:flex; justify-content:space-between; align-items:center; margin-top:6px; font-size:0.75rem; color:#64748b;">'
                f'<span>🕒 Updated: {ts_str} &bull; Source: {source}</span>'
                f'<a href="{rotowire_url}" target="_blank" style="color:#38bdf8; text-decoration:none; font-weight:600;">Rotowire Preseason Profile ↗</a>'
                f'</div>'
                f'</div>'
            )
            st.markdown(wire_card, unsafe_allow_html=True)

# --- Tab 9: Reach Traps ---
with tab_reaches:
    st.markdown("#### ⚠️ Overvalued on ESPN (Reach Traps)")
    st.caption("Players where ESPN default rank is much higher than expert consensus. Let your opponents reach for these traps!")
    reaches_df = df_board[df_board["value_diff"] <= -4].sort_values(by="value_diff", ascending=True).reset_index(drop=True)
    render_draft_table(reaches_df, key_prefix="reaches")

# --- Tab 10: Injury & Suspension Scouting Report ---
with tab_injuries:
    st.markdown("### 🚑 2026 Live NFL Injury & Suspension Scouting Intelligence")
    st.caption("Real-time aggregated medical and disciplinary intelligence from ESPN, Sleeper, and NFL beat sources. Track return timelines, surgical notes, and draft stash guidance.")

    # -------------------------------------------------------------------------
    # 1. MANUAL SYNC, TEMPORAL RESOLUTION & DB CHANGE TRACKER
    # -------------------------------------------------------------------------
    inj_db = load_injury_database()
    meta = inj_db.get("metadata", {})
    last_synced_str = meta.get("last_synced_formatted", "Not yet synced")
    uncommitted_cnt = meta.get("uncommitted_changes", 0)
    uncommitted_players = meta.get("uncommitted_players", [])
    
    sync_col1, sync_col2, sync_col3 = st.columns([1.8, 2.4, 1.8])
    with sync_col1:
        if st.button("🔄 Sync & Refresh Injury News", type="primary", use_container_width=True, help="Scrapes latest ESPN, Sleeper, and NFL beat reports using monotonic temporal precedence (T_new > T_current)"):
            with st.spinner("Scraping live injury feeds & executing temporal conflict resolution..."):
                up_cnt, up_names, updated_db = sync_injury_pipeline()
                st.session_state.draft_board = enrich_board_with_injuries(st.session_state.draft_board)
                if up_cnt > 0:
                    st.toast(f"⚠️ {up_cnt} player(s) updated with newer reports!", icon="⚠️")
                else:
                    st.toast("✅ Database is up to date. No older reports overwrote newer ones.", icon="✅")
                st.rerun()
                
    with sync_col2:
        if uncommitted_cnt > 0:
            st.markdown(f"""
            <div style="background:#431407; border:1.5px solid #ea580c; border-radius:6px; padding:6px 12px; display:flex; align-items:center; gap:8px;">
                <span style="font-size:1.1rem;">⚠️</span>
                <div style="font-size:0.82rem; line-height:1.3;">
                    <strong style="color:#fdba74;">Database Status:</strong> <span style="color:#f97316; font-weight:800;">{uncommitted_cnt} Uncommitted Changes</span><br/>
                    <span style="color:#cbd5e1; font-size:0.75rem;">Last Synced: {last_synced_str}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:#064e3b25; border:1.5px solid #05966980; border-radius:6px; padding:6px 12px; display:flex; align-items:center; gap:8px;">
                <span style="font-size:1.1rem;">🟢</span>
                <div style="font-size:0.82rem; line-height:1.3;">
                    <strong style="color:#34d399;">Database Status:</strong> <span style="color:#6ee7b7; font-weight:700;">Up to Date</span><br/>
                    <span style="color:#cbd5e1; font-size:0.75rem;">Last Synced: {last_synced_str}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
    with sync_col3:
        db_json_str = json.dumps(inj_db, indent=2, ensure_ascii=False)
        st.download_button(
            label="📥 Export Updated DB / Download JSON",
            data=db_json_str,
            file_name="injury_database_2026.json",
            mime="application/json",
            use_container_width=True,
            help="Download the merged JSON database to commit into the git repository"
        )
        
    # Uncommitted Changes Alert Banner & Git Commit Snippet
    if uncommitted_cnt > 0:
        st.markdown(f"""
        <div style="background:#2d1205; border-left:4px solid #ea580c; border-radius:6px; padding:10px 14px; margin:8px 0 12px 0;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <strong style="color:#fdba74; font-size:0.92rem;">⚠️ {uncommitted_cnt} players have newer injury news than your last repo commit:</strong>
                <span style="background:#ea580c; color:#fff; font-size:0.7rem; font-weight:700; padding:2px 8px; border-radius:4px;">GIT COMMIT NEEDED</span>
            </div>
            <div style="color:#fed7aa; font-size:0.82rem; margin-top:4px;">
                <strong>Updated players:</strong> {', '.join(uncommitted_players[:8])}{f' (+{uncommitted_cnt - 8} more)' if uncommitted_cnt > 8 else ''}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        with st.expander("📋 Auto-Generated Git Commit Message Snippet", expanded=False):
            st.caption("Copy this message when committing the updated `data/injury_database_2026.json` file to GitHub:")
            commit_snippet = generate_git_commit_snippet(uncommitted_players, meta.get("last_synced"))
            st.code(commit_snippet, language="bash")
            if st.button("✅ Mark as Committed to Git (Reset Status)", key="btn_mark_db_clean", use_container_width=True):
                mark_database_committed()
                st.toast("Database status marked as committed to Git!", icon="✅")
                st.rerun()

    all_inj_df = df_board[df_board["injury_tier"].isin(["SEASON_IR", "SUSPENSION", "PUP_MULTI_WEEK", "OUT_WEEK_1", "WEEK_1_RISK"])].copy().reset_index(drop=True)

    if all_inj_df.empty:
        st.success("No active players currently flagged with injuries or suspensions.")
    else:
        # KPI Overview
        kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
        with kpi1:
            st.metric("Total Flagged", len(all_inj_df))
        with kpi2:
            st.metric("🛑 Season IR", len(all_inj_df[all_inj_df["injury_tier"] == "SEASON_IR"]))
        with kpi3:
            st.metric("⛔ Suspensions", len(all_inj_df[all_inj_df["injury_tier"] == "SUSPENSION"]))
        with kpi4:
            st.metric("⚠️ PUP / 4+ Wks", len(all_inj_df[all_inj_df["injury_tier"] == "PUP_MULTI_WEEK"]))
        with kpi5:
            st.metric("🟠 Out Wk 1 Only", len(all_inj_df[all_inj_df["injury_tier"] == "OUT_WEEK_1"]))
        with kpi6:
            st.metric("🟡 Week 1 / Q", len(all_inj_df[all_inj_df["injury_tier"] == "WEEK_1_RISK"]))

        # Filter controls
        inj_f1, inj_f2 = st.columns([3, 2])
        with inj_f1:
            inj_search = st.text_input(
                "Search injured/suspended player",
                placeholder="Search by player name, injury diagnosis, or team...",
                key="inj_tab_search"
            )
        with inj_f2:
            inj_tier_filter = st.multiselect(
                "Filter Severity Tiers",
                options=[
                    "🛑 Out for Season (IR)",
                    "⛔ Suspensions",
                    "⚠️ PUP / Multi-Week (Out 4+ Wks)",
                    "🟠 Out Week 1 Only (Back W2)",
                    "🟡 Week 1 Risk / Questionable"
                ],
                default=[
                    "🛑 Out for Season (IR)",
                    "⛔ Suspensions",
                    "⚠️ PUP / Multi-Week (Out 4+ Wks)",
                    "🟠 Out Week 1 Only (Back W2)",
                    "🟡 Week 1 Risk / Questionable"
                ],
                key="inj_tab_tier_filter"
            )

        tier_name_map = {
            "🛑 Out for Season (IR)": "SEASON_IR",
            "⛔ Suspensions": "SUSPENSION",
            "⚠️ PUP / Multi-Week (Out 4+ Wks)": "PUP_MULTI_WEEK",
            "🟠 Out Week 1 Only (Back W2)": "OUT_WEEK_1",
            "🟡 Week 1 Risk / Questionable": "WEEK_1_RISK"
        }
        selected_tiers = [tier_name_map[t] for t in inj_tier_filter if t in tier_name_map]

        filtered_inj_df = all_inj_df[all_inj_df["injury_tier"].isin(selected_tiers)].copy().reset_index(drop=True)
        if inj_search:
            s_low = inj_search.lower().strip()
            filtered_inj_df = filtered_inj_df[
                filtered_inj_df["name"].str.lower().str.contains(s_low, na=False) |
                filtered_inj_df["team"].str.lower().str.contains(s_low, na=False) |
                filtered_inj_df["pos"].str.lower().str.contains(s_low, na=False) |
                filtered_inj_df["injury_type"].str.lower().str.contains(s_low, na=False) |
                filtered_inj_df["injury_blurb"].str.lower().str.contains(s_low, na=False)
            ].reset_index(drop=True)

        filtered_inj_df["avail_rank"] = filtered_inj_df.index + 1
        render_draft_table(filtered_inj_df, key_prefix="inj_report")

        # Detailed beat-reporter wire feed
        with st.expander("📰 Live Beat-Reporter Wire & Scouting Medical Blurbs", expanded=False):
            st.caption("Direct beat-reporter updates, practice participation, and return estimates from official NFL beat writers & ESPN wire.")
            for _, ir in filtered_inj_df.iterrows():
                tier_color = "#ef4444" if ir["injury_tier"] == "SEASON_IR" else ("#c084fc" if ir["injury_tier"] == "SUSPENSION" else ("#f97316" if ir["injury_tier"] == "PUP_MULTI_WEEK" else ("#ea580c" if ir["injury_tier"] == "OUT_WEEK_1" else "#eab308")))
                wire_card = (
                    f'<div style="background:#111827; border-left:4px solid {tier_color}; border-radius:6px; padding:10px 14px; margin-bottom:10px; border-top:1px solid #1f2937; border-right:1px solid #1f2937; border-bottom:1px solid #1f2937;">'
                    f'<div style="display:flex; justify-content:space-between; align-items:center;">'
                    f'<div>'
                    f'<strong style="color:#f8fafc; font-size:0.95rem;">{ir["name"]} ({ir["pos"]} - {ir["team"]})</strong>'
                    f'<span style="color:#94a3b8; font-size:0.8rem; margin-left:8px;">Consensus #{ir["consensus_rank"]} &bull; Bye {ir["bye"]}</span>'
                    f'</div>'
                    f'<span style="background:#1e293b; color:{tier_color}; font-size:0.75rem; font-weight:800; padding:3px 8px; border-radius:4px; border:1px solid {tier_color}40;">'
                    f'{ir["injury_badge"]}'
                    f'</span>'
                    f'</div>'
                    f'<div style="color:#cbd5e1; font-size:0.82rem; margin-top:4px;">'
                    f'<strong>Timeline:</strong> {ir.get("injury_timeline", "TBD")} &bull; <strong>Diagnosis:</strong> {ir.get("injury_type", "Undisclosed")}'
                    f'</div>'
                    f'<div style="color:#94a3b8; font-size:0.82rem; margin-top:4px; line-height:1.4; background:#0b0f19; padding:8px 10px; border-radius:5px; border:1px solid #1e293b;">'
                    f'{ir.get("injury_blurb", "No detailed blurb available.")}'
                    f'</div>'
                    f'<div style="color:#38bdf8; font-size:0.75rem; font-weight:600; margin-top:4px;">'
                    f'💡 Strategy: {ir.get("draft_advice", "Monitor practice reports.")}'
                    f'</div>'
                    f'{get_player_injury_links_html(ir["name"], ir.get("injury_updated_formatted"), ir.get("source_url"))}'
                    f'</div>'
                )
                st.markdown(wire_card, unsafe_allow_html=True)



# --- Tab 11: 8-Team League Dashboard & Rosters ---
with tab_grid:
    st.markdown("## 📊 8-Team League Dashboard & Draft Command Center")
    st.caption("Live multi-team command center tracking **Who Picked Who**, roster hierarchies for all 8 fantasy teams, round-by-round snake pick guides, and live board matrix.")

    subtab_who, subtab_matrix, subtab_schedule, subtab_log = st.tabs([
        "👥 Who Picked Who (8-Team Rosters)",
        "📋 8-Team Live Draft Matrix",
        "🔄 Who's Picking Each Round (16-Round Guide)",
        "📜 Chronological Draft Feed & Log"
    ])

    # -------------------------------------------------------------------------
    # SUBTAB 1: WHO PICKED WHO (8-TEAM ROSTER INSPECTOR)
    # -------------------------------------------------------------------------
    with subtab_who:
        st.markdown("### 👥 8-Team Roster Inspector & Team Needs")
        st.caption("Select any team below to inspect their full 16-player roster, starting lineup, bench, bye week coverage, and round picks.")

        insp_c1, insp_c2 = st.columns([4, 2.5])
        with insp_c1:
            chosen_inspect_slot = st.selectbox(
                "🔍 Select Team to Inspect Full Lineup:",
                options=list(range(1, TOTAL_TEAMS + 1)),
                index=st.session_state.user_slot - 1,
                format_func=lambda s: f"{get_league_team_name(s)} (Slot #{s}){' ⭐ YOUR ACTIVE TEAM' if s == st.session_state.user_slot else ''}{' 🔥 ON CLOCK' if s == cur_team else ''}",
                key="dashboard_inspect_team_select"
            )
        with insp_c2:
            st.write("")
            if chosen_inspect_slot != st.session_state.user_slot:
                if st.button(f"👉 Set {get_league_team_name(chosen_inspect_slot)} as My Persona", key="btn_switch_persona_insp", use_container_width=True, help="Switch active persona to this team so draft countdowns and board highlights follow them"):
                    set_active_username_slot(chosen_inspect_slot)
                    st.rerun()

        insp_team_info = LEAGUE_TEAMS_2026.get(chosen_inspect_slot, {})
        insp_team_name = insp_team_info.get("team_name", f"Team {chosen_inspect_slot}")
        insp_picks = insp_team_info.get("picks", [])
        insp_roster = get_team_roster(chosen_inspect_slot)
        
        # Calculate roster statistics for this team
        insp_starters = [
            p for slot_k in ["QB", "RB", "WR", "TE", "FLEX", "DST", "K"] 
            for p in insp_roster.get(slot_k, [])
        ]
        insp_bench = insp_roster.get("BENCH", [])
        insp_ir = insp_roster.get("IR", [])
        insp_total_drafted = len(insp_starters) + len(insp_bench) + len(insp_ir)

        # Team Header Banner
        is_active_user_team = (chosen_inspect_slot == st.session_state.user_slot)
        header_border = "#38bdf8" if is_active_user_team else "#3730a3"
        header_bg = "rgba(56, 189, 248, 0.08)" if is_active_user_team else "rgba(15, 23, 42, 0.75)"
        st.markdown(f"""
        <div style="background:{header_bg}; border:1.5px solid {header_border}; border-radius:8px; padding:10px 16px; margin-bottom:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:1.15rem; font-weight:800; color:{'#38bdf8' if is_active_user_team else '#f8fafc'};">
                    🏈 {insp_team_name} (Draft Slot #{chosen_inspect_slot}) {'⭐ YOUR ACTIVE TEAM' if is_active_user_team else ''}
                </span>
                <span style="font-size:0.85rem; font-weight:700; color:#10b981;">
                    Draft Progress: {insp_total_drafted} / 16 Picks
                </span>
            </div>
            <div style="font-size:0.76rem; color:#94a3b8; margin-top:4px;">
                <strong>Attached 16-Round Schedule:</strong> {', '.join(insp_picks)}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 2-Column Roster Layout: Starters & Bench
        r_col1, r_col2 = st.columns([5, 5])
        with r_col1:
            st.markdown("#### 🏆 Starting Lineup (9 Starters)")
            starter_slot_configs = [
                ("QB", 1),
                ("RB", 2),
                ("WR", 2),
                ("TE", 1),
                ("FLEX", 1),
                ("DST", 1),
                ("K", 1)
            ]
            for s_name, req_count in starter_slot_configs:
                players_in_slot = insp_roster.get(s_name, [])
                for idx in range(req_count):
                    s_label = s_name if req_count == 1 else f"{s_name} {idx+1}"
                    if idx < len(players_in_slot):
                        pl = players_in_slot[idx]
                        p_bye = TEAM_BYE_WEEKS_2026.get(pl.get("team", ""), 0)
                        st.markdown(f"""
                        <div class="roster-card">
                            <div style="display:flex; align-items:center; gap:8px;">
                                <span class="pos-badge pos-{pl['pos']}">{pl['pos']}</span>
                                <span class="roster-player-name">{pl['name']}</span>
                                <span style="font-size:0.72rem; color:#94a3b8;">({pl['team']} • Wk {p_bye})</span>
                            </div>
                            <div style="font-size:0.72rem; color:#38bdf8; font-weight:700;">
                                Pick #{pl.get('pick_number', '?')} (Rd {pl.get('draft_round', '?')})
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="roster-card roster-card-empty">
                            <span class="roster-slot-title">{s_label}</span>
                            <span style="font-size:0.76rem; color:#64748b; font-style:italic;">Empty</span>
                        </div>
                        """, unsafe_allow_html=True)

        with r_col2:
            st.markdown("#### 🪑 Bench (7 Slots) & 🚑 IR Stash")
            for b_idx in range(7):
                if b_idx < len(insp_bench):
                    bp = insp_bench[b_idx]
                    b_bye = TEAM_BYE_WEEKS_2026.get(bp.get("team", ""), 0)
                    st.markdown(f"""
                    <div class="roster-card">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span class="pos-badge pos-{bp['pos']}">{bp['pos']}</span>
                            <span class="roster-player-name">{bp['name']}</span>
                            <span style="font-size:0.72rem; color:#94a3b8;">({bp['team']} • Wk {b_bye})</span>
                        </div>
                        <div style="font-size:0.72rem; color:#38bdf8; font-weight:700;">
                            Pick #{bp.get('pick_number', '?')} (Rd {bp.get('draft_round', '?')})
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="roster-card roster-card-empty">
                        <span class="roster-slot-title">Bench {b_idx+1}</span>
                        <span style="font-size:0.76rem; color:#64748b; font-style:italic;">Empty</span>
                    </div>
                    """, unsafe_allow_html=True)

            # IR Stash Card
            if insp_ir:
                irp = insp_ir[0]
                st.markdown(f"""
                <div class="roster-card" style="border:1px solid #ea580c; background:#2d1205;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="background:#ea580c; color:#fff; font-size:0.68rem; font-weight:800; padding:2px 6px; border-radius:4px;">IR STASH</span>
                        <span class="roster-player-name" style="color:#fdba74;">{irp['name']}</span>
                        <span style="font-size:0.72rem; color:#fed7aa;">({irp['pos']} - {irp['team']})</span>
                    </div>
                    <div style="font-size:0.72rem; color:#f97316; font-weight:700;">
                        {irp.get('injury_badge', '⚠️ IR')} &bull; Pick #{irp.get('pick_number', '?')}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="roster-card roster-card-empty" style="border:1px dashed #64748b;">
                    <span class="roster-slot-title" style="color:#f59e0b;">IR Stash</span>
                    <span style="font-size:0.76rem; color:#64748b; font-style:italic;">Empty (PUP / IR Stash Slot)</span>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        # Comparative 8-Team Rosters at a Glance
        with st.expander("📋 Compare All 8 Teams' Drafted Players Side-by-Side", expanded=False):
            comp_cols = st.columns(4)
            for s_idx in range(1, TOTAL_TEAMS + 1):
                col_target = comp_cols[(s_idx - 1) % 4]
                t_name = get_league_team_name(s_idx)
                t_picks_made = [h for h in st.session_state.draft_history if h.get("team_slot") == s_idx]
                with col_target:
                    is_cur_user = (s_idx == st.session_state.user_slot)
                    card_border = "#38bdf8" if is_cur_user else "#1e293b"
                    card_title_color = "#38bdf8" if is_cur_user else "#f8fafc"
                    
                    st.markdown(f"""
                    <div style="background:#0f172a; border:1px solid {card_border}; border-radius:6px; padding:8px 10px; margin-bottom:8px;">
                        <strong style="color:{card_title_color}; font-size:0.85rem;">{t_name} (S#{s_idx})</strong>
                        <div style="font-size:0.72rem; color:#94a3b8;">{len(t_picks_made)}/16 drafted</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if t_picks_made:
                        for tp in t_picks_made:
                            st.markdown(f"<div style='font-size:0.76rem; margin-bottom:2px;'><span class='pos-badge pos-{tp['pos']}'>{tp['pos']}</span> <strong>{tp['name']}</strong> <span style='color:#64748b;'>#{tp['pick_number']}</span></div>", unsafe_allow_html=True)
                    else:
                        st.caption("No picks made yet.")

    # -------------------------------------------------------------------------
    # SUBTAB 2: 8-TEAM LIVE DRAFT MATRIX
    # -------------------------------------------------------------------------
    with subtab_matrix:
        st.markdown("### 📋 8-Team Live Draft Matrix Grid")
        st.caption("Complete round-by-round draft grid showing who was picked at every draft slot. Your team column is marked with ⭐.")

        grid_rows = []
        for rd in range(1, ROSTER_ROUNDS + 1):
            row_data = {"Round": f"Rd {rd}"}
            for team_idx in range(1, TOTAL_TEAMS + 1):
                if rd % 2 == 1:
                    p_num = (rd - 1) * TOTAL_TEAMS + team_idx
                else:
                    p_num = (rd - 1) * TOTAL_TEAMS + (TOTAL_TEAMS - team_idx + 1)
                
                is_user_col = (team_idx == st.session_state.user_slot)
                team_col_label = f"{get_league_team_name(team_idx)} (S{team_idx}){' ⭐' if is_user_col else ''}"
                picked = [h for h in st.session_state.draft_history if h["pick_number"] == p_num]
                if picked:
                    p = picked[0]
                    row_data[team_col_label] = f"{p['name']} ({p['pos']})"
                elif p_num == st.session_state.current_pick:
                    row_data[team_col_label] = "⏳ ON CLOCK"
                else:
                    row_data[team_col_label] = f"#{p_num}"
            grid_rows.append(row_data)

        grid_df = pd.DataFrame(grid_rows)
        st.dataframe(grid_df, use_container_width=True, hide_index=True)

        st.info("💡 **Snake Order Guide**: Odd rounds run 1 to 8 • Even rounds reverse 8 to 1. In rounds 1-2 turnarounds, Slot 8 drafts back-to-back at #8 and #9, while Slot 1 drafts back-to-back at #16 and #17.")

    # -------------------------------------------------------------------------
    # SUBTAB 3: WHO'S PICKING EACH ROUND (16-ROUND SNAKE GUIDE)
    # -------------------------------------------------------------------------
    with subtab_schedule:
        st.markdown("### 🔄 Who's Picking Each Round • 16-Round Snake Pick Order")
        st.caption("Complete breakdown showing the exact pick order of all 8 fantasy teams for every single round of the draft.")

        sched_rows = []
        for rd in range(1, ROSTER_ROUNDS + 1):
            is_odd = (rd % 2 == 1)
            start_pick = (rd - 1) * TOTAL_TEAMS + 1
            end_pick = rd * TOTAL_TEAMS
            direction_str = "1 ➔ 8 (Normal)" if is_odd else "8 ➔ 1 (Reverse)"

            # Pick sequence for this round
            order_slots = list(range(1, TOTAL_TEAMS + 1)) if is_odd else list(range(TOTAL_TEAMS, 0, -1))
            order_team_names = [get_league_team_name(s) for s in order_slots]

            # Find when active user picks in this round
            user_idx_in_round = order_slots.index(st.session_state.user_slot) + 1
            user_ovr_pick = start_pick + user_idx_in_round - 1
            user_pick_label = f"{rd}.{user_idx_in_round}"

            if user_ovr_pick < st.session_state.current_pick:
                user_status = "✓ Done"
            elif user_ovr_pick == st.session_state.current_pick:
                user_status = "🔥 ON CLOCK NOW"
            else:
                user_status = f"In {user_ovr_pick - st.session_state.current_pick} picks"

            sched_rows.append({
                "Round": f"Round {rd}",
                "Direction": direction_str,
                "Pick Range": f"#{start_pick} - #{end_pick}",
                "1st Pick": order_team_names[0],
                "2nd Pick": order_team_names[1],
                "3rd Pick": order_team_names[2],
                "4th Pick": order_team_names[3],
                "5th Pick": order_team_names[4],
                "6th Pick": order_team_names[5],
                "7th Pick": order_team_names[6],
                "8th Pick": order_team_names[7],
                f"Your Turn ({get_league_team_name(st.session_state.user_slot)})": f"Pick #{user_ovr_pick} ({user_pick_label}) &bull; {user_status}"
            })

        sched_df = pd.DataFrame(sched_rows)
        st.dataframe(sched_df, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # SUBTAB 4: CHRONOLOGICAL DRAFT FEED & LOG
    # -------------------------------------------------------------------------
    with subtab_log:
        st.markdown("### 📜 Chronological Draft Feed & Pick Audit Log")
        if st.session_state.draft_history:
            log_c1, log_c2, log_c3 = st.columns([3, 1.5, 1.5])
            with log_c1:
                log_search = st.text_input("Search Draft Feed", placeholder="Search player, drafter team, or position...", key="log_search_feed")
            with log_c2:
                log_team_filter = st.selectbox(
                    "Filter by Team",
                    options=["All Teams"] + [get_league_team_name(s) for s in range(1, TOTAL_TEAMS + 1)],
                    key="log_filter_team"
                )
            with log_c3:
                log_pos_filter = st.multiselect("Position", options=["QB", "RB", "WR", "TE", "DST", "K"], default=[], key="log_filter_pos")

            filtered_log = list(reversed(st.session_state.draft_history))
            if log_search:
                ls = log_search.lower().strip()
                filtered_log = [
                    h for h in filtered_log
                    if ls in h["name"].lower() or ls in h["team"].lower() or ls in h["pos"].lower() or ls in h.get("drafted_by", "").lower()
                ]
            if log_team_filter != "All Teams":
                filtered_log = [
                    h for h in filtered_log
                    if h.get("drafted_by") == log_team_filter or get_league_team_name(h.get("team_slot", 0)) == log_team_filter
                ]
            if log_pos_filter:
                filtered_log = [h for h in filtered_log if h["pos"] in log_pos_filter]

            if not filtered_log:
                st.info("No picks match the selected filters.")
            else:
                for lp in filtered_log:
                    l_pid = lp["player_id"]
                    l_slot = lp.get("team_slot", 0)
                    is_my_pick = (l_slot == st.session_state.user_slot)
                    badge_bg = "#064e3b" if is_my_pick else "#1e293b"
                    badge_col = "#34d399" if is_my_pick else "#94a3b8"

                    lc1, lc2, lc3, lc4, lc5 = st.columns([1.2, 3.5, 2.5, 2, 1.5])
                    with lc1:
                        st.markdown(f"**Pick #{lp['pick_number']}**<br><span style='color:#94a3b8; font-size:0.75rem;'>Rd {lp.get('draft_round', 1)}</span>", unsafe_allow_html=True)
                    with lc2:
                        st.markdown(f"""
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span class="pos-badge pos-{lp['pos']}">{lp['pos']}</span>
                            <strong>{lp['name']}</strong>
                            <span style="color:#94a3b8; font-size:0.8rem;">({lp['team']})</span>
                        </div>
                        """, unsafe_allow_html=True)
                    with lc3:
                        st.markdown(f"<span style='background:{badge_bg}; color:{badge_col}; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;'>{lp.get('drafted_by', get_league_team_name(l_slot))}</span>", unsafe_allow_html=True)
                    with lc4:
                        st.markdown(f"<span style='color:#94a3b8; font-size:0.8rem;'>Round Pick #{lp.get('round_pick', '?')}</span>", unsafe_allow_html=True)
                    with lc5:
                        if st.button("🔄 Undo Pick", key=f"undo_log_btn_{l_pid}_{lp['pick_number']}", use_container_width=True):
                            restore_player(l_pid)
                            st.rerun()
        else:
            st.info("No picks made yet. Draft is currently at Pick #1.")

# --- Tab 12: 2026 Depth Chart Cheat Sheet ---
with tab_depth:
    st.markdown("### 📋 Official 2026 ESPN NFL Depth Chart & Cheat Sheet")
    st.caption("Official ESPN 2026 Depth Chart cheat sheet (Updated August 31, 2026). Use this during your live draft to check starter hierarchies (QB1, RB1, RB2, WR1, WR2, WR3, TE1), verify depth chart status, and target high-value handcuffs!")

    depth_img_path = DATA_DIR / "depthchart.jpg"
    if depth_img_path.exists():
        st.image(
            str(depth_img_path),
            use_container_width=True,
            caption="ESPN Official 2026 NFL Depth Chart Cheat Sheet (Updated August 31, 2026)"
        )
    else:
        st.warning("Depth chart image not found at data/depthchart.jpg")

