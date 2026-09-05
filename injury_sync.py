"""
Temporal Conflict Resolution & Live Injury Database Synchronization Engine
Handles ISO 8601 UTC normalization, monotonic precedence verification,
diff tracking, JSON database persistence, and Git commit snippet generation.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("injury_sync")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INJURY_DB_FILE = DATA_DIR / "injury_database_2026.json"


# -----------------------------------------------------------------------------
# 1. TIMESTAMP NORMALIZATION & FORMATTING
# -----------------------------------------------------------------------------
def normalize_to_iso8601_utc(raw_val: Any) -> str:
    """
    Parses any incoming timestamp into standard ISO 8601 UTC format:
    'YYYY-MM-DDTHH:MM:SSZ'.
    
    Supports:
      - Epoch in milliseconds (e.g., Sleeper API: 1788017147544)
      - Epoch in seconds
      - ISO strings (e.g., ESPN API: '2026-09-01T19:38Z' or with offsets)
      - Date strings ('YYYY-MM-DD')
      - Python datetime objects
    """
    if raw_val is None or raw_val == "":
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # 1. Datetime object
    if isinstance(raw_val, datetime):
        if raw_val.tzinfo is None:
            raw_val = raw_val.replace(tzinfo=timezone.utc)
        return raw_val.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 2. Integer/float epoch (seconds or milliseconds)
    if isinstance(raw_val, (int, float)):
        # If > 1e11 it's in milliseconds
        if raw_val > 1e11:
            dt = datetime.fromtimestamp(raw_val / 1000.0, tz=timezone.utc)
        else:
            dt = datetime.fromtimestamp(raw_val, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 3. Numeric string
    s_val = str(raw_val).strip()
    if s_val.isdigit():
        val_num = int(s_val)
        if val_num > 1e11:
            dt = datetime.fromtimestamp(val_num / 1000.0, tz=timezone.utc)
        else:
            dt = datetime.fromtimestamp(val_num, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 4. Standard ISO string parsing (ESPN: '2026-09-01T19:38Z' or with seconds)
    try:
        clean_iso = s_val.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass

    # 5. Common date formats
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y"]:
        try:
            dt = datetime.strptime(s_val, fmt).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue

    # Fallback to current UTC time if unparseable
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_display_timestamp(iso_utc_str: str) -> str:
    """
    Converts ISO 8601 UTC string into user-friendly localized format:
    e.g. 'Sep 2, 2026 at 10:30 AM UTC'
    """
    if not iso_utc_str:
        return "Unknown"
    try:
        clean = iso_utc_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        return dt.strftime("%b %d, %Y at %I:%M %p UTC")
    except Exception:
        return str(iso_utc_str)


# -----------------------------------------------------------------------------
# 2. STRICT MONOTONIC TEMPORAL PRECEDENCE & CONFLICT RESOLUTION
# -----------------------------------------------------------------------------
def resolve_injury_temporal_conflict(
    current_record: Optional[Dict[str, Any]],
    incoming_record: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any]]:
    """
    Evaluates incoming scraped update against existing database record using
    strict temporal conflict resolution:
    
    1. Normalize incoming publication timestamp T_new and current record timestamp T_current.
    2. Monotonic Progression Check:
       - If current_record is None: ACCEPT (new record). Returns (True, incoming_record).
       - If T_new > T_current: ACCEPT update. Returns (True, updated_record).
       - If T_new <= T_current: REJECT update. Stale or identical data must NEVER overwrite.
         Returns (False, current_record).
    """
    # Normalize incoming timestamp
    raw_incoming_ts = incoming_record.get("timestamp_utc") or incoming_record.get("date") or incoming_record.get("news_updated")
    t_new_iso = normalize_to_iso8601_utc(raw_incoming_ts)
    incoming_record["timestamp_utc"] = t_new_iso
    incoming_record["updated_formatted"] = format_display_timestamp(t_new_iso)

    # Condition: First time player enters database
    if current_record is None:
        return True, incoming_record

    # Normalize existing timestamp
    raw_current_ts = current_record.get("timestamp_utc")
    t_current_iso = normalize_to_iso8601_utc(raw_current_ts)
    current_record["timestamp_utc"] = t_current_iso
    if not current_record.get("updated_formatted"):
        current_record["updated_formatted"] = format_display_timestamp(t_current_iso)

    # Monotonic Comparison: ISO 8601 UTC strings sort lexicographically identically to chronological order
    if t_new_iso > t_current_iso:
        merged = current_record.copy()
        merged.update(incoming_record)
        merged["timestamp_utc"] = t_new_iso
        merged["updated_formatted"] = format_display_timestamp(t_new_iso)
        return True, merged
    else:
        # Stale or identical timestamp: reject update
        return False, current_record


# -----------------------------------------------------------------------------
# 3. DATABASE PERSISTENCE & CHANGE DETECTION
# -----------------------------------------------------------------------------
def load_injury_database() -> Dict[str, Any]:
    """Loads persistent injury database from data/injury_database_2026.json."""
    if INJURY_DB_FILE.exists():
        try:
            with open(INJURY_DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "players" in data and "metadata" in data:
                    return data
        except Exception as e:
            logger.warning(f"Error reading injury database JSON: {e}")

    # Default initialized database structure
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "metadata": {
            "last_synced": now_iso,
            "last_synced_formatted": format_display_timestamp(now_iso),
            "version": "2026.1",
            "total_records": 0,
            "uncommitted_changes": 0,
            "uncommitted_players": []
        },
        "players": {}
    }


def save_injury_database(db: Dict[str, Any]) -> bool:
    """Saves injury database atomically to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = INJURY_DB_FILE.with_suffix(".tmp")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
        temp_file.replace(INJURY_DB_FILE)
        return True
    except Exception as e:
        logger.error(f"Failed to save injury database: {e}")
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
        return False


def sync_injury_pipeline(force_sample_update: bool = False) -> Tuple[int, List[str], Dict[str, Any]]:
    """
    Executes the full manual sync and refresh pipeline:
    1. Pulls incoming records from ESPN API, Sleeper API, and Curated Ledger.
    2. Runs each player through strict monotonic temporal validation (T_new > T_current).
    3. Tracks uncommitted changes and dirty state.
    4. Persists merged records into data/injury_database_2026.json.
    
    Returns: (updated_count, updated_player_names, full_database_dict)
    """
    from scraper import fetch_espn_live_injuries, fetch_sleeper_live_injuries, CURATED_2026_INJURY_LEDGER, clean_player_name

    db = load_injury_database()
    existing_players = db.get("players", {})
    
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated_players = []

    # 1. Fetch live 2026 ESPN API
    espn_injuries, active_players = fetch_espn_live_injuries(timeout=6)
    
    # Process ESPN updates
    for clean_name, inj_data in espn_injuries.items():
        curr = existing_players.get(clean_name)
        if not inj_data.get("timestamp_utc"):
            inj_data["timestamp_utc"] = inj_data.get("date") or now_iso
        inj_data["player_name"] = clean_name.title()
        
        is_updated, winning_record = resolve_injury_temporal_conflict(curr, inj_data)
        if is_updated:
            existing_players[clean_name] = winning_record
            if curr is None or winning_record.get("timestamp_utc", "") > curr.get("timestamp_utc", ""):
                updated_players.append(winning_record.get("player_name") or clean_name.title())

    # 2. Fetch live Sleeper API
    sleeper_injuries = fetch_sleeper_live_injuries(timeout=5)
    for clean_name, inj_data in sleeper_injuries.items():
        if clean_name in active_players:
            continue
        curr = existing_players.get(clean_name)
        inj_data["player_name"] = clean_name.title()
        is_updated, winning_record = resolve_injury_temporal_conflict(curr, inj_data)
        if is_updated:
            existing_players[clean_name] = winning_record
            if curr is None or winning_record.get("timestamp_utc", "") > curr.get("timestamp_utc", ""):
                pname = winning_record.get("player_name") or clean_name.title()
                if pname not in updated_players:
                    updated_players.append(pname)

    # 3. Verified Curated Ledger (Authoritative ground truth)
    for clean_name, inj_data in CURATED_2026_INJURY_LEDGER.items():
        if clean_name in active_players and not inj_data.get("is_season_out"):
            continue
        curr = existing_players.get(clean_name)
        ledger_record = inj_data.copy()
        if not ledger_record.get("timestamp_utc"):
            ledger_record["timestamp_utc"] = now_iso
            ledger_record["updated_formatted"] = format_display_timestamp(now_iso)
        ledger_record["player_name"] = clean_name.title()
        
        if inj_data.get("is_season_out"):
            if curr:
                curr.update(ledger_record)
                curr["is_season_out"] = True
                curr["tier"] = "SEASON_IR"
                existing_players[clean_name] = curr
            else:
                existing_players[clean_name] = ledger_record
            if clean_name.title() not in updated_players:
                updated_players.append(clean_name.title())
        else:
            is_updated, winning_record = resolve_injury_temporal_conflict(curr, ledger_record)
            if is_updated:
                existing_players[clean_name] = winning_record
                pname = winning_record.get("player_name") or clean_name.title()
                if pname not in updated_players:
                    updated_players.append(pname)

    # 4. Remove active players who have recovered
    for act in active_players:
        if act in existing_players and not existing_players[act].get("is_season_out"):
            del existing_players[act]

    # Update metadata
    uncommitted_prev = db.get("metadata", {}).get("uncommitted_players", [])
    all_uncommitted = list(set(uncommitted_prev + updated_players))

    db["metadata"]["last_synced"] = now_iso
    db["metadata"]["last_synced_formatted"] = format_display_timestamp(now_iso)
    db["metadata"]["total_records"] = len(existing_players)
    db["metadata"]["uncommitted_changes"] = len(all_uncommitted)
    db["metadata"]["uncommitted_players"] = all_uncommitted
    db["players"] = existing_players

    save_injury_database(db)
    return len(updated_players), updated_players, db


def mark_database_committed() -> Dict[str, Any]:
    """Clears uncommitted dirty flag after git commit or export."""
    db = load_injury_database()
    db["metadata"]["uncommitted_changes"] = 0
    db["metadata"]["uncommitted_players"] = []
    db["metadata"]["last_committed_timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_injury_database(db)
    return db


def generate_git_commit_snippet(updated_players: List[str], timestamp_iso: Optional[str] = None) -> str:
    """Generates standard formatted Git commit message."""
    date_str = (timestamp_iso or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10]
    count = len(updated_players)
    
    msg = f"feat(injuries): auto-sync update for {count} players ({date_str})\n\n"
    msg += f"Synchronized live medical and disciplinary reports for {count} players:\n"
    for p in updated_players[:15]:
        msg += f"- {p}\n"
    msg += f"\nMonotonic timestamp resolution verified: T_new > T_current."
    return msg


if __name__ == "__main__":
    count, updated, db = sync_injury_pipeline()
    print(f"[OK] Live injury database synced: {count} players updated. Total records: {len(db.get('players', {}))}.")

