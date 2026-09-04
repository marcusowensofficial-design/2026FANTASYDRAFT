# ⚡ 2026 Fantasy Football PPR Draft Assistant & Live War Room

A high-performance, dark-mode 8-Team PPR Draft Board and Live War Room built with **Python 3.14+**, **Streamlit**, **Pandas**, **PyArrow (Parquet)**, and **BeautifulSoup/Playwright**. Engineered for high-stakes 90-second pick clock drafts, multi-expert consensus arbitration, live injury tracking, and rookie dominance intelligence.

> **Note for AI Assistants & Developers**: This document serves as the single source of truth for the codebase architecture, file directory map, mathematical models, data contracts, and operational workflows.

---

## 🧭 Repository Directory Map

```text
FANTASYDRAFT/
│
├── app.py                         # Production Streamlit live draft war room UI (2,200+ LOC)
├── app.bat                        # 1-Click Windows launcher (starts server & opens browser)
├── scraper.py                     # Multi-expert consensus engine, normalizer, 5-layer medical safety
├── sleeper_sync.py                # Preseason rookie dominance & sleeper intelligence sync pipeline
├── injury_sync.py                 # Live NFL injury & suspension temporal sync engine
├── test_draft.py                  # Pytest unit & integration test suite (18 test suites)
├── requirements.txt               # Project dependencies
├── README.md                      # Authoritative architecture and onboarding documentation
│
├── .streamlit/
│   └── config.toml                # Global dark theme tokens (cyber-athletic #0a0d14 palette)
│
└── data/
    ├── draft_board_2026.parquet   # High-speed binary ranking cache (<10ms load time)
    ├── draft_board.db             # SQLite database cache of the consensus draft board
    ├── injury_database_2026.json  # Tracked NFL injuries, return dates, tiers, and ISO timestamps
    ├── sleeper_database_2026.json # Preseason rookie breakouts, snap trends, grades, and camp buzz
    ├── rotowire_player_map.json   # Authoritative player name -> RotoWire player profile slug/ID map
    ├── depthchart.jpg             # High-res ESPN Official 2026 NFL Depth Chart cheat sheet
    │
    ├── espnppr300.pdf             # Official 2026 ESPN Top 300 PPR rankings source document
    ├── espn_2026_top300.csv       # Extracted baseline ESPN rankings (Ranks 1–300)
    ├── doctor.txt                 # Sports medicine clinical injury notes & return-to-play timelines
    │
    ├── bleacherreporttop314ppr.txt # Bleacher Report Top 314 PPR rankings
    ├── draftsharksdatatop250ppr.txt# Draft Sharks Top 250 PPR rankings
    ├── footballguystop200ppr.txt   # Footballguys Top 200 PPR rankings
    ├── nbcsportstop200rankings.txt # NBC Sports / Rotoworld Top 200 rankings
    ├── rotoballertop400ppr.txt    # RotoBaller Top 400 PPR rankings
    ├── sportsillustratedtop200ppr.txt # Sports Illustrated Top 200 rankings
    └── sample_rankings_template.csv# Template for user drop-in custom CSV rankings
```

---

## 🏛️ System Architecture & Core Modules

### 1. High-Speed Live Draft War Room (`app.py`)
The primary interactive user interface designed to dominate 90-second pick clock drafts with zero horizontal scroll and instantaneous state updates:
- **Live 90s Pick Timer**: Synchronized timer controls (`Reset`, `+15s`, `Pause/Resume`) with pulsing critical-alert banners when clock falls under 20 seconds.
- **8-Team Snake Draft Engine**: Automatically calculates round, overall pick number, current drafting team, and next user pick count using standard snake draft arithmetic:
  $$\text{Odd Rounds (1, 3, 5\dots)}: \quad \text{Pick} = (R - 1) \times 8 + S$$
  $$\text{Even Rounds (2, 4, 6\dots)}: \quad \text{Pick} = (R - 1) \times 8 + (9 - S)$$
- **Sidebar Live Draft Control**:
  - Configurable draft slot selector (Slots 1–8) with real-time "Current Turn 🔥" status.
  - **1-Click Minimizer/Maximizer** (`◀ Hide` / `📱 Fullscreen Tables`): Minimizes sidebar to maximize screen width on iPad, mobile, and desktop.
  - **9 Starters + 7 Bench + 1 IR Stash** layout:
    - 9 Starters: `1 QB`, `2 RB`, `2 WR`, `1 TE`, `1 FLEX (RB/WR/TE)`, `1 DST`, `1 K`.
    - 7 Bench slots (16 draft rounds total = 128 picks).
    - 1 Dedicated IR/Suspension Stash slot.
  - **Bye Week Conflict Detector**: Automatically flags weeks where 3 or more starters share a bye.
  - **1-Click Draft Actions**: `🟩 Draft (My Team)`, `⬛ Cross Off (Other)`, and `↩️ Undo / Return to Available`.
  - **Export Draft Log**: Instant CSV export of chronological draft history.

### 2. Multi-View Navigation Tabs (14 Dedicated Tabs)
1. **`⚡ All Available`**: Main consensus draft board sorted cleanly 1-to-300 with unicode strikethroughs on season-ending IR players, per-tab search and sort reset controls.
2. **`❌ Drafted Players`**: Positioned directly next to All Available for instant pick auditing and 1-click player restoration.
3. **`🧠 Draft Strategy & Playbook`**:
   - **Hybrid Smart Sync Advisor**: Auto-detects current draft round and unfilled starting roster needs, paired with interactive opponent scenario counters (`Early QB Panic`, `Heavy RB Run`, `Blindly Following ESPN ADP`).
   - **Recommended Live Targets with 1-Click Draft**: Embedded `🟩 Draft (My Team)` and `⬛ Cross Off` buttons to draft immediately from the Strategy view.
   - **Executive 8-Team Playbook & Master Guide**:
     - *The 8-Team Mathematical Reality*: Why "every team is loaded", how tighter margins punish draft misses, sky-high replacement level (~128 players rostered), and why ceiling trumps safe floor.
     - *Top ESPN Arbitrage Steals & Traps*: Target consensus steals (+5 to +18 value) and let opponents take overvalued reach traps.
     - *The 17th Roster Spot "IR Stash Hack"*: Step-by-step workflow for drafting a PUP/IR stud in Round 14–15 to unlock an immediate free Week 1 waiver pickup.
     - *The 5 Cardinal 8-Team Strategic Shifts*: Prioritizing studs over safety, early aggressive QB/TE viability, waiver wire secret weapon, the QB fork-in-the-road (elite hammer vs. extreme wait), and tight end sneaky priority.
     - *Master 8-Team Draft-Day Checklist & Round Blueprint*: Phase-by-phase drafting rules from Rounds 1–2 ceiling anchors down to final-round K/DST streaming.
     - *Championship Roster Architecture*: Verified 16-round roster blueprint with zero same-team WR stacking and high-ceiling contingent handcuffs.
4. **`🏃 Running Backs`**: RB-exclusive board with tier badges, touches projection, and injury alerts.
5. **`🎯 Wide Receivers`**: Target share leaders and boundary/slot roles.
6. **`🏈 Quarterbacks`**: Rushing floor QBs vs pocket passers.
7. **`🛡️ Tight Ends`**: Elite TE tiers and late-round streaming targets.
8. **`⭐ FLEX Targets`**: Merged pool of RBs, WRs, and TEs for flex optimization.
9. **`🛡️ DST & Kickers`**: Defensive stream schedules and kicker projections.
10. **`🔥 Value Steals & Sleepers`**:
   - Exploitable value spreads ($\ge +5$ vs ESPN ADP).
   - **2026 Preseason Rookie Dominance & Sleepers**: Dynamic intelligence cards loaded from `sleeper_sync.py` featuring preseason snap trends, camp buzz, and breakout badges.
11. **`⚠️ Reach Traps`**: ESPN overvalued players ($\le -5$ value diff) to let league opponents draft early.
12. **`🚑 Injury & Suspension Report`**: Dedicated scouting dashboard with severity KPI counters, clinical blurbs, return dates, and manual live sync trigger.
13. **`📜 8-Team Grid & Log`**: 16-round snake draft matrix by team and chronological pick history log.
14. **`📋 2026 Depth Chart Cheat Sheet`**: Embedded official high-resolution 2026 NFL depth chart cheat sheet (`data/depthchart.jpg`).


---

### 3. Multi-Expert Consensus & Normalization Engine (`scraper.py`)
- **11 Expert Ranking Sources Merged**:
  1. *Official ESPN Top 300 PDF* (`espnppr300.pdf` / `espn_2026_top300.csv`) + live ESPN 1,000-player API
  2. *FantasyPros Consensus ECR*
  3. *Yahoo Sports*
  4. *Sleeper*
  5. *CBS Sports*
  6. *Draft Sharks Top 250* (`draftsharksdatatop250ppr.txt`)
  7. *Footballguys Top 200* (`footballguystop200ppr.txt`)
  8. *RotoBaller Top 400* (`rotoballertop400ppr.txt`)
  9. *NBC Sports / Rotoworld Top 200* (`nbcsportstop200rankings.txt`)
  10. *Bleacher Report Top 314* (`bleacherreporttop314ppr.txt`)
  11. *Sports Illustrated Top 200* (`sportsillustratedtop200ppr.txt`)
- **Deterministic Player Normalization**:
  - Strips generational suffixes (`Jr.`, `III`, `II`, `Sr.`, `IV`), punctuation, and team aliases.
  - Normalizes positions (`DEF`/`D/ST` $\to$ `DST`, `PK` $\to$ `K`).
  - Generates deterministic IDs (e.g., `jahmyr_gibbs_det`, `bijan_robinson_atl`).
- **Statistical Value Arbitrage**:
  $$\text{Value Diff} = \text{ESPN Rank} - \text{Consensus Median Rank}$$
  - **$\ge +5$ (Steal)**: Undervalued by ESPN default rankings. Exploit these against ESPN league opponents.
  - **$\le -5$ (Reach Trap)**: Overvalued on ESPN default rankings. Let opponents reach for them.
- **5-Layer Medical Safety Guarantee**:
  - Automatically identifies season-ending IR players (e.g., Jayden Higgins ACL, Trey Benson) and suppresses them from default active draft recommendations.
  - Applies unicode strikethrough formatting (`T̶r̶e̶y̶ ̶B̶e̶n̶s̶o̶n̶ 🛑`) while preserving row data for auditability.
- **Direct Live Scouting Links**:
  - Authoritative RotoWire player profile linking via `data/rotowire_player_map.json`.
  - Direct FantasyPros live news directory linking (`https://www.fantasypros.com/nfl/news/<slug>.php`).

---

### 4. Preseason Rookie Dominance & Sleeper Pipeline (`sleeper_sync.py`)
- Curated and synchronized ledger of breakout rookies and late-round sleepers.
- **Monotonic Temporal Conflict Resolution**:
  - Enforces $T_{\text{new}} > T_{\text{current}}$ using standardized ISO 8601 UTC timestamps (`YYYY-MM-DDTHH:MM:SSZ`). Stale updates are rejected.
- **Scouting Metrics**:
  - Preseason grades (e.g. `A+ (Dominant)`).
  - Preseason stats & snap trends (e.g. `92% 1st-Team Snaps (Locked WR1 📈)`).
  - Coach endorsements and camp buzz blurbs.
  - Custom breakout badges (`🚀 ROOKIE WR1 BREAKOUT`, `⚡ ROOKIE QB SLEEPER (+67)`).
- **Storage**: Persisted to `data/sleeper_database_2026.json` and merged into the draft board via `enrich_board_with_sleepers()`.

---

### 5. Live Injury & Suspension Sync Engine (`injury_sync.py`)
- Real-time synchronization querying ESPN 32-team injury API and Sleeper NFL API.
- **4 Standardized Severity Tiers**:
  - 🛑 **Out for Season**: Season-ending IR (strikethrough + DO NOT DRAFT warnings).
  - ⛔ **Suspensions**: Disciplinary games missed with return timelines (e.g. Rashee Rice).
  - ⚠️ **Multi-Week / PUP**: Out minimum first 4 weeks (e.g. Jonathon Brooks, T.J. Hockenson).
  - 🟡 **Week 1 Risk / Questionable**: Soft-tissue injuries, limited practice, and day-to-day status.
- **Automated Git Commit Snippets**: Calculates diffs upon sync and prints formatted git commit messages for quick auditing.
- **Storage**: Persisted to `data/injury_database_2026.json`.

---

## 📊 Data Contracts & Core Dataframe Schema

The central draft board dataframe (`draft_board_2026.parquet` / SQLite table) guarantees the following schema:

| Column Name | Type | Description |
| :--- | :--- | :--- |
| `player_id` | `str` | Normalized deterministic identifier (`<clean_name>_<team>`) |
| `name` | `str` | Display player name (clean typography) |
| `pos` | `str` | Standardized position (`QB`, `RB`, `WR`, `TE`, `DST`, `K`) |
| `team` | `str` | Standard 2-3 letter NFL team abbreviation |
| `bye` | `int` | 2026 NFL regular season bye week (Weeks 5–14) |
| `tier` | `int` | Positional value tier (1–8) |
| `consensus_rank` | `int` | Primary sorted consensus rank (1–300+) |
| `consensus_median_rank` | `float` | Median rank across all available expert sources |
| `espn_rank` | `int` | Official 2026 ESPN Top 300 default rank |
| `value_diff` | `int` | `espn_rank - consensus_median_rank` |
| `injury_tier` | `str` | `SEASON_ENDING_IR`, `SUSPENSION`, `PUP_MULTI_WEEK`, `QUESTIONABLE_DAY_TO_DAY`, `HEALTHY` |
| `injury_badge` | `str` | Visual badge with status and emojis (e.g., `🛑 OUT FOR SEASON`) |
| `injury_notes` | `str` | Clinical diagnosis and timeline blurb |
| `is_drafted` | `bool` | Draft status flag (defaults to `False`) |
| `drafted_by` | `str` | Name or team ID that drafted the player |
| `pick_number` | `int` | Overall draft pick number (1–128) |
| `expert ranking columns` | `float`/`int` | `fantasypros_rank`, `yahoo_rank`, `sleeper_rank`, `cbs_rank`, `draftsharks_rank`, `footballguys_rank`, `rotoballertop400_rank`, `nbcsports_rank`, `bleacherreport_rank`, `sportsillustrated_rank` |

---

## 🛠️ Developer & Operation Workflows

### 1. Launching the War Room
* **1-Click Launch (Windows)**:
  ```powershell
  .\app.bat
  ```
* **Command Line Launch**:
  ```powershell
  python -m streamlit run app.py
  ```
  The app runs locally on `http://localhost:8501`.

### 2. Running Automated Tests
Run the comprehensive 18-suite test pipeline:
```powershell
python -m pytest test_draft.py
```
To run a specific test suite:
```powershell
python -m pytest test_draft.py -k "test_temporal_conflict_resolution"
```

### 3. Synchronizing Live Injuries
To sync live injuries from external APIs outside the UI:
```powershell
python injury_sync.py
```
*(Or click **🔄 Sync Live NFL Injuries Now** directly inside the app under the `🚑 Injury & Suspension Report` tab).*

### 4. Synchronizing Sleeper & Rookie Intel
To refresh the preseason sleeper database:
```powershell
python sleeper_sync.py
```

### 5. Forcing a Board Re-Scrape
To rebuild `draft_board_2026.parquet` and `draft_board.db` from all expert text and CSV sources:
```powershell
python scraper.py
```
*(Or click **📥 Force Re-Scrape / Refresh** in the app's sidebar under `⚙️ Export & Board Options`).*

---

## 🎯 League Rules & Draft Settings Baseline
* **League Size**: 8 Teams (Snake Draft: 1 $\to$ 8, 8 $\to$ 1).
* **Scoring Format**: Full PPR (1.0 Point Per Reception).
* **Pick Clock**: 90 Seconds.
* **Total Rounds**: 16 Rounds (128 Total Draft Picks).
* **Roster Composition**:
  * **1 QB**
  * **2 RB**
  * **2 WR**
  * **1 TE**
  * **1 FLEX** (RB / WR / TE)
  * **1 DST**
  * **1 K**
  * **7 Bench**
  * **1 IR Stash**
