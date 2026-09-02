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

# -----------------------------------------------------------------------------
# 1. STREAMLIT PAGE CONFIGURATION & CUSTOM DARK THEME CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="2026 PPR Draft Assistant | 8-Team Live War Room",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

if "draft_board" not in st.session_state:
    st.session_state.draft_board = load_or_generate_draft_board(force_refresh=False)

if "draft_history" not in st.session_state:
    st.session_state.draft_history = []  # Stack of picks for undo

if "current_pick" not in st.session_state:
    st.session_state.current_pick = 1

if "user_slot" not in st.session_state:
    st.session_state.user_slot = 1  # User draft position (1 to 8)

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


def execute_pick(player_id: str, drafted_by_user: bool = False, team_label: Optional[str] = None):
    """
    Drafts a player, updates DataFrame in session state, and advances draft state.
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
    rd, rpick, team_num, is_user_turn = get_snake_pick_info(pick_num)
    
    if team_label is None:
        if drafted_by_user:
            team_label = f"User (Team {st.session_state.user_slot})"
            is_user = True
        else:
            # Explicitly drafted by another team / crossed off
            if is_user_turn:
                # If crossed off during user turn, assign to opponent
                team_label = f"Opponent (Pick #{pick_num})"
            else:
                team_label = f"Team {team_num}"
            is_user = False
    else:
        is_user = ("User" in team_label)

    # Update row
    df.at[i, "is_drafted"] = True
    df.at[i, "draft_round"] = rd
    df.at[i, "pick_number"] = pick_num
    df.at[i, "drafted_by"] = team_label

    # Save to history stack for instant undo
    st.session_state.draft_history.append({
        "player_id": player_id,
        "name": df.at[i, "name"],
        "pos": df.at[i, "pos"],
        "team": df.at[i, "team"],
        "pick_number": pick_num,
        "draft_round": rd,
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
        df.at[i, "drafted_by"] = ""

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
    df.at[i, "drafted_by"] = ""

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
    df["drafted_by"] = ""
    st.session_state.draft_board = df
    st.session_state.draft_history = []
    st.session_state.current_pick = 1
    st.session_state.clock_seconds = 90
    st.toast("Draft board successfully reset!", icon="🔄")


def get_player_injury_links_html(player_name: str, report_time: Optional[str] = None) -> str:
    """Generates direct profile and real-time injury tracking links for FantasyPros and RotoWire with timestamp."""
    clean_n = player_name.lower().replace("'", "").replace(".", "").strip()
    for sfx in [" jr", " sr", " ii", " iii", " iv", " v"]:
        if clean_n.endswith(sfx):
            clean_n = clean_n[:-len(sfx)].strip()
    slug = "-".join([w for w in re.split(r'[^a-z0-9]+', clean_n) if w])
    
    fp_url = f"https://www.fantasypros.com/nfl/players/{slug}.php"
    rw_q = urllib.parse.quote_plus(f"rotowire {player_name} nfl injury news")
    rw_url = f"https://www.google.com/search?q={rw_q}"
    
    time_html = ""
    if report_time:
        time_html = f'<span style="color:#94a3b8; font-size:0.75rem; margin-left:auto;">🕒 <strong>Updated:</strong> {report_time}</span>'
    
    return (
        f'<div style="margin-top:8px; padding-top:6px; border-top:1px dashed rgba(255,255,255,0.18); display:flex; flex-wrap:wrap; gap:8px; align-items:center;">'
        f'<span style="color:#cbd5e1; font-size:0.8rem; font-weight:700;">📡 Live Injury Wire & Beat History:</span>'
        f'<a href="{fp_url}" target="_blank" rel="noopener noreferrer" style="background:#1e293b; color:#38bdf8; text-decoration:none; padding:3px 10px; border-radius:5px; font-size:0.78rem; font-weight:700; border:1px solid #38bdf850; display:inline-flex; align-items:center; gap:4px;">'
        f'⚡ FantasyPros Live Profile ↗'
        f'</a>'
        f'<a href="{rw_url}" target="_blank" rel="noopener noreferrer" style="background:#1e293b; color:#fb923c; text-decoration:none; padding:3px 10px; border-radius:5px; font-size:0.78rem; font-weight:700; border:1px solid #fb923c50; display:inline-flex; align-items:center; gap:4px;">'
        f'📰 RotoWire Latest Beat News ↗'
        f'</a>'
        f'{time_html}'
        f'</div>'
    )


def get_user_roster() -> Dict[str, List[Dict[str, Any]]]:
    """
    Computes user's 8-team PPR starting lineup (9 starters: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 D/ST, 1 K),
    7 bench slots, and 1 dedicated IR stash slot for injured/suspended players.
    """
    user_picks = [p for p in st.session_state.draft_history if p.get("is_user", False)]
    
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
    
    for p in user_picks:
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
        {f'<div class="status-badge-ontheclock">🚨 YOU ARE ON THE CLOCK!</div>' if is_user_turn and st.session_state.current_pick <= TOTAL_PICKS else f'<div class="status-badge-clock">⏳ Team {cur_team} On Clock</div>'}
        <div class="status-badge-clock">
            <span>Round {cur_rd}</span> &bull; <span>Pick {cur_rpick}</span> &bull; <span style="color:#38bdf8;">Overall #{min(st.session_state.current_pick, TOTAL_PICKS)}</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 5. BEST AVAILABLE QUICK RADAR
# -----------------------------------------------------------------------------
df_board = st.session_state.draft_board
available_df = df_board[~df_board["is_drafted"]].copy().reset_index(drop=True)
available_df["avail_rank"] = available_df.index + 1

# Exclude season-ending IR from BPA quick radar recommendations
radar_avail_df = available_df[~available_df["is_season_out"]].reset_index(drop=True)

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
    disp_n = f"{to_unicode_strikethrough(row['name'])} 🛑" if row.get("is_season_out") else row["name"]
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
                {get_player_injury_links_html(tsp['name'], tsp.get('injury_updated_formatted'))}
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
                {get_player_injury_links_html(tsp['name'], tsp.get('injury_updated_formatted'))}
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
                {get_player_injury_links_html(tsp['name'], tsp.get('injury_updated_formatted'))}
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
                {get_player_injury_links_html(tsp['name'], tsp.get('injury_updated_formatted'))}
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
                {get_player_injury_links_html(tsp['name'], tsp.get('injury_updated_formatted'))}
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
    
    # User Slot Picker
    user_slot_input = st.selectbox(
        "Your Draft Slot (8-Team)",
        options=list(range(1, 9)),
        index=st.session_state.user_slot - 1,
        format_func=lambda x: f"Slot #{x} {'(Current Turn 🔥)' if x == cur_team else ''}"
    )
    if user_slot_input != st.session_state.user_slot:
        st.session_state.user_slot = user_slot_input
        st.rerun()

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
    st.markdown("### 📋 My Starting Lineup (PPR)")

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
tab_all, tab_drafted, tab_rb, tab_wr, tab_qb, tab_te, tab_flex, tab_dstk, tab_steals, tab_reaches, tab_injuries, tab_grid, tab_depth = st.tabs([
    "⚡ All Available",
    "❌ Drafted Players",
    "🏃 Running Backs",
    "🎯 Wide Receivers",
    "🏈 Quarterbacks",
    "🛡️ Tight Ends",
    "⭐ FLEX Targets",
    "🛡️ DST & Kickers",
    "🔥 Value Steals",
    "⚠️ Reach Traps",
    "🚑 Injury & Suspension Report",
    "📜 8-Team Grid & Log",
    "📋 2026 Depth Chart Cheat Sheet"
])


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

    # In-table search & filtering bar
    f_c1, f_c2, f_c3, f_c4, f_c5 = st.columns([2.0, 1.1, 1.6, 1.4, 1.5])
    with f_c1:
        tbl_search = st.text_input(
            f"Filter table ({len(df_display)} players)",
            key=f"search_{key_prefix}",
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
        granular_toggle = st.checkbox(
            "📊 Show All Expert Sources (9 Ranks)",
            value=st.session_state.get(f"toggle_granular_{key_prefix}", True),
            key=f"toggle_granular_{key_prefix}",
            help="Checked by default. Displays all 9 expert ranking sources ordered from most reliable to mainstream. Note: Outlets with published cutoff lists (Footballguys/NBC/SI Top 200, Draft Sharks Top 250, B/R Top 314) display None for players outside their evaluated range."
        )
    with f_c4:
        default_hide_ir = (key_prefix != "inj_report")
        hide_ir_toggle = st.checkbox(
            "🚫 Hide Season IR",
            value=st.session_state.get(f"hide_ir_{key_prefix}", default_hide_ir),
            key=f"hide_ir_{key_prefix}",
            help="Checked by default on draft boards. Hides players on season-ending IR (with strikethrough names) while keeping active players and viable multi-week stashes. Uncheck to view all players."
        )
    with f_c5:
        keep_drafted_toggle = st.checkbox(
            "🔴 Keep Drafted (Redded Out)",
            value=True,
            key=f"keep_drafted_{key_prefix}",
            help="When checked, drafted players remain visible in the table with full red strikethrough styling and 1-click undo. Uncheck to view only remaining available players."
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

    col_rename = {
        "avail_rank": "Avail #",
        "player_display_name": "Player Name",
        "pos": "Pos",
        "team": "Team",
        "injury_badge_display": "Injury / Risk",
        "bye": "Bye",
        "tier": "Tier",
        "consensus_rank": "Consensus",
        "value_diff": "Value Diff",
        "espn_rank": "ESPN",
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
            "Avail #": st.column_config.TextColumn(width="small"),
            "Player Name": st.column_config.TextColumn(width="medium"),
            "Pos": st.column_config.TextColumn(width="small"),
            "Team": st.column_config.TextColumn(width="small"),
            "Injury / Risk": st.column_config.TextColumn(
                width="medium",
                help="Live NFL Injury, Suspension, & Return Timeline. Click any row in the table to display full beat-reporter injury notes and surgical updates below."
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
                    
                    u_c1, u_c2, u_c3 = st.columns([1.5, 2, 0.8])
                    with u_c1:
                        if st.button(f"🔄 Undo Pick / Restore {p_name}", key=f"btn_undo_sel_{p_id}_{key_prefix}", type="primary", use_container_width=True):
                            restore_player(p_id)
                            st.rerun()
                    with u_c2:
                        st.caption(f"Click above to undo this pick and return {p_name} back onto the active draft board as available.")
                    with u_c3:
                        if st.button("✖ Close", key=f"btn_close_undo_{p_id}_{key_prefix}", use_container_width=True, help="Dismiss card"):
                            if f"table_select_{key_prefix}" in st.session_state:
                                del st.session_state[f"table_select_{key_prefix}"]
                            st.rerun()
                else:
                    report_ts = sel_player.get("injury_updated_formatted") or "Sep 2, 2026 at 10:30 AM UTC"
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
                            {get_player_injury_links_html(p_name, report_ts)}
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
                            {get_player_injury_links_html(p_name, report_ts)}
                        </div>
                        """, unsafe_allow_html=True)
                    elif inj_tier == "PUP_MULTI_WEEK":
                        st.markdown(f"""
                        <div style="background:#431407; border:2px solid #f97316; border-radius:8px; padding:12px 16px; margin-top:8px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong style="color:#fed7aa; font-size:1.05rem;">⚠️ RESERVE / PUP ALERT (OUT FIRST 4+ WEEKS) &bull; {p_name} ({p_pos} - {p_team})</strong>
                                <span style="background:#f97316; color:#fff; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;">MULTI-WEEK STASH</span>
                            </div>
                            <div style="margin-top:6px; color:#ffedd5; font-size:0.9rem;">
                                <strong>Timeline:</strong> {sel_player.get('injury_timeline', 'Out minimum 4 weeks')} &bull; <strong>Diagnosis:</strong> {sel_player.get('injury_type', 'PUP List')} &bull; <strong>Target Return:</strong> {sel_player.get('injury_return_date', 'Week 5')}
                            </div>
                            <div style="margin-top:4px; color:#f1f5f9; font-size:0.85rem;">
                                {sel_player.get('injury_blurb', '')}
                            </div>
                            <div style="margin-top:4px; color:#fdba74; font-size:0.85rem; font-weight:600;">
                                💡 Stash Strategy: {sel_player.get('draft_advice', 'Target as late-round stash.')}
                            </div>
                            {get_player_injury_links_html(p_name, report_ts)}
                        </div>
                        """, unsafe_allow_html=True)
                    elif inj_tier == "OUT_WEEK_1":
                        st.markdown(f"""
                        <div style="background:#431407; border:2px solid #ea580c; border-radius:8px; padding:12px 16px; margin-top:8px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong style="color:#fdba74; font-size:1.05rem;">🟠 OUT WEEK 1 (EXPECTED BACK WEEK 2) &bull; {p_name} ({p_pos} - {p_team})</strong>
                                <span style="background:#ea580c; color:#fff; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;">OUT WK 1 ONLY</span>
                            </div>
                            <div style="margin-top:6px; color:#fed7aa; font-size:0.9rem;">
                                <strong>Timeline:</strong> {sel_player.get('injury_timeline', 'Out Wk 1 • Target Return: Week 2')} &bull; <strong>Diagnosis:</strong> {sel_player.get('injury_type', 'Short-term')} &bull; <strong>Target Return:</strong> {sel_player.get('injury_return_date', 'Week 2')}
                            </div>
                            <div style="margin-top:4px; color:#f1f5f9; font-size:0.85rem;">
                                {sel_player.get('injury_blurb', '')}
                            </div>
                            <div style="margin-top:4px; color:#fb923c; font-size:0.85rem; font-weight:600;">
                                💡 Strategy: {sel_player.get('draft_advice', 'Confirmed out for Week 1 only; expected ready for Week 2.')}
                            </div>
                            {get_player_injury_links_html(p_name, report_ts)}
                        </div>
                        """, unsafe_allow_html=True)
                    elif inj_tier == "WEEK_1_RISK":
                        st.markdown(f"""
                        <div style="background:#422006; border:2px solid #eab308; border-radius:8px; padding:12px 16px; margin-top:8px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong style="color:#fef08a; font-size:1.05rem;">🟡 WEEK 1 MONITORING / QUESTIONABLE &bull; {p_name} ({p_pos} - {p_team})</strong>
                                <span style="background:#eab308; color:#000; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:4px;">DAY-TO-DAY</span>
                            </div>
                            <div style="margin-top:6px; color:#fef9c3; font-size:0.9rem;">
                                <strong>Timeline:</strong> {sel_player.get('injury_timeline', 'Week 1')} &bull; <strong>Status:</strong> {sel_player.get('injury_type', 'Questionable')} &bull; <strong>Target Return:</strong> {sel_player.get('injury_return_date', 'Week 1')}
                            </div>
                            <div style="margin-top:4px; color:#f1f5f9; font-size:0.85rem;">
                                {sel_player.get('injury_blurb', '')}
                            </div>
                            <div style="margin-top:4px; color:#fef08a; font-size:0.85rem; font-weight:600;">
                                💡 Advice: {sel_player.get('draft_advice', 'Monitor practice reports.')}
                            </div>
                            {get_player_injury_links_html(p_name, report_ts)}
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
                        {get_player_injury_links_html(p_name, report_ts)}
                        """, unsafe_allow_html=True)
                    
                    b_c1, b_c2, b_c3 = st.columns([1.5, 1.5, 0.8])
                    with b_c1:
                        btn_label = f"🟩 Draft {p_name} (My Roster)"
                        if inj_tier == "SEASON_IR":
                            btn_label += " ⚠️[IR RISK]"
                        if st.button(btn_label, key=f"btn_user_{p_id}_{key_prefix}", type="primary", use_container_width=True):
                            execute_pick(p_id, drafted_by_user=True)
                            st.rerun()
                    with b_c2:
                        if st.button(f"⬛ Cross Off {p_name} (Other)", key=f"btn_opp_{p_id}_{key_prefix}", use_container_width=True):
                            execute_pick(p_id, drafted_by_user=False)
                            st.rerun()
                    with b_c3:
                        if st.button("✖ Close", key=f"btn_close_sel_{p_id}_{key_prefix}", use_container_width=True, help="Dismiss card"):
                            if f"table_select_{key_prefix}" in st.session_state:
                                del st.session_state[f"table_select_{key_prefix}"]
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
            st.metric("On My Roster", user_drafted_count)
        with mc3:
            st.metric("Taken by Opponents / Crossed Off", opp_drafted_count)

        # Filters for crossed off view
        c_f1, c_f2, c_f3 = st.columns([3, 1.5, 1.5])
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
            drafter_filter = st.selectbox(
                "Drafted By",
                options=["All Removed", "My Roster Only", "Opponents Only"],
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

        if drafter_filter == "My Roster Only":
            filtered_history = [h for h in filtered_history if h.get("is_user", False)]
        elif drafter_filter == "Opponents Only":
            filtered_history = [h for h in filtered_history if not h.get("is_user", False)]

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

# --- Tab 3: Running Backs ---
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

# --- Tab 8: Value Steals ---
with tab_steals:
    st.markdown("#### 🔥 Undervalued on ESPN (Consensus Steals)")
    st.caption("Players where Expert Consensus Rank is significantly higher than ESPN Default Rank. Exploit these against ESPN league-mates!")
    steals_df = df_board[df_board["value_diff"] >= 4].sort_values(by="value_diff", ascending=False).reset_index(drop=True)
    render_draft_table(steals_df, key_prefix="steals")

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
                    f'{get_player_injury_links_html(ir["name"], ir.get("injury_updated_formatted"))}'
                    f'</div>'
                )
                st.markdown(wire_card, unsafe_allow_html=True)



# --- Tab 11: 8-Team Draft Grid & Log ---
with tab_grid:
    st.markdown("### 📊 8-Team Live Draft Matrix")
    
    # Construct 8-team grid
    grid_rows = []
    for rd in range(1, ROSTER_ROUNDS + 1):
        row_data = {"Round": f"Rd {rd}"}
        for team_idx in range(1, TOTAL_TEAMS + 1):
            if rd % 2 == 1:
                p_num = (rd - 1) * TOTAL_TEAMS + team_idx
            else:
                p_num = (rd - 1) * TOTAL_TEAMS + (TOTAL_TEAMS - team_idx + 1)
            
            picked = [h for h in st.session_state.draft_history if h["pick_number"] == p_num]
            if picked:
                p = picked[0]
                row_data[f"Team {team_idx}"] = f"{p['name']} ({p['pos']})"
            elif p_num == st.session_state.current_pick:
                row_data[f"Team {team_idx}"] = "⏳ ON CLOCK"
            else:
                row_data[f"Team {team_idx}"] = f"#{p_num}"
        grid_rows.append(row_data)

    grid_df = pd.DataFrame(grid_rows)
    st.dataframe(grid_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("### 📜 Chronological Draft Log")
    if st.session_state.draft_history:
        log_df = pd.DataFrame(st.session_state.draft_history)[["pick_number", "draft_round", "name", "pos", "team", "drafted_by"]]
        log_df = log_df.rename(columns={
            "pick_number": "Overall #",
            "draft_round": "Round",
            "name": "Player",
            "pos": "Pos",
            "team": "Team",
            "drafted_by": "Drafted By"
        })
        st.dataframe(log_df.iloc[::-1], use_container_width=True, hide_index=True)
    else:
        st.caption("No picks made yet. Draft is at Pick #1.")

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

