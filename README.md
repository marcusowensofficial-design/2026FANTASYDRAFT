# ⚡ 2026 Fantasy Football PPR Draft Assistant

A production-grade, ultra-fast 8-Team PPR Draft Board and Live War Room built with **Python**, **Streamlit**, **Pandas**, and **BeautifulSoup/Playwright** to dominate 90-second pick clock drafts.

---

## 🚀 Key Features

### 1. Multi-Expert Consensus & Value Spread Engine (`scraper.py`)
- **Consolidates 5 Expert Feeds**: ESPN Top 300 PPR, FantasyPros Consensus ECR, Yahoo, Sleeper, and CBS.
- **Deterministic Player Normalization**: Strips suffixes (`Jr.`, `III`, `II`, `Sr.`), punctuation, and team aliases to generate deterministic `player_id`s (e.g., `jahmyr_gibbs_det`, `bijan_robinson_atl`).
- **Value vs ESPN Spread**:
  $$\text{Value Diff} = \text{ESPN Rank} - \text{Consensus Rank}$$
  - **$\ge +5$ (Steal)**: Undervalued on ESPN default rankings. Exploit these against your ESPN league-mates.
  - **$\le -5$ (Reach Trap)**: Overvalued on ESPN default rankings. Let opponents reach for these traps.
- **Instant Parquet & SQLite Cache**: Loads in under 10ms from `data/draft_board_2026.parquet` and `data/draft_board.db`.
- **Custom CSV Fallback Reader**: Automatically parses any custom CSV ranking files dropped into `data/`.

### 2. High-Speed Live Draft UI (`app.py`)
- **Fast-Action Quick-Search Bar**: Top-of-screen autocomplete matching player names, teams (e.g. `KC`, `DET`), and positions with real-time injury alert banners.
- **Instant 1-Click Draft Actions**:
  - 🟩 **Draft (My Team)**: Assigns player to your starting roster/bench and advances the snake draft.
  - ⬛ **Cross Off (Other)**: Strikes player off the board for opponents.
  - ↩️ **Undo**: 1-click instant rollback for mistaken picks.
  - ⏱️ **90s Clock Controls**: Reset, +15s, and timer sync.
- **Clean Main Board (Zero Horizontal Scroll)**:
  - 8 Core Columns: `Avail #`, `Player Name`, `Pos`, `Team`, `Injury / Risk`, `Bye`, `Tier`, `Consensus`, `Value Diff`, `ESPN`.
  - **Native Unicode Strikethroughs**: Out-for-season IR players (e.g. `T̶r̶e̶y̶ ̶B̶e̶n̶s̶o̶n̶ 🛑`) are clearly struck through while remaining on the board for reference.
  - **🚫 Hide Season IR Toggle**: Quick 1-click filter to hide season-ending players while keeping viable multi-week stashes.
  - **Granular Expert Toggle**: Check `Show Expert Breakdowns` to reveal FantasyPros, Yahoo, Sleeper, CBS, Best/Worst ranges, and Auction Values without cluttering the default table.
- **Real-Time Injury & Suspension Intelligence Engine**:
  - Multi-source live feed querying ESPN 32-team injury API and Sleeper NFL API hourly.
  - 4 standardized tiers:
    - 🛑 **Out for Season**: Season-ending IR with strikethrough typography & "DO NOT DRAFT" tags.
    - ⛔ **Suspensions**: League disciplinary games missed with return timelines (e.g. Rashee Rice).
    - ⚠️ **Multi-Week / PUP**: Out minimum first 4 weeks (e.g. Nick Chubb, Jonathon Brooks, T.J. Hockenson).
    - 🟡 **Week 1 Risk**: Day-to-day, soft-tissue, and practice monitoring notes.
  - **High-Visibility Selection Banners**: Clicking any player reveals full clinical diagnosis, recovery target dates, and draft advice.
- **Position & Strategy Filter Tabs**:
  - `⚡ All Available`
  - `🏃 Running Backs`
  - `🎯 Wide Receivers`
  - `🏈 Quarterbacks`
  - `🛡️ Tight Ends`
  - `⭐ FLEX Targets`
  - `🛡️ DST & Kickers`
  - `🔥 Value Steals` (Highest positive value spreads)
  - `⚠️ Reach Traps` (Highest negative value spreads)
  - `🚑 Injury & Suspension Report` (Dedicated scouting dashboard with KPI counts and timeline filters)
  - `❌ Crossed Off / Drafted`
  - `📜 8-Team Grid & Log` (Full 16-round snake draft matrix and chronological pick log)
- **8-Team Starting Lineup Tracker**:
  - Real-time starting slot tracker (QB, 2 RB, 2 WR, TE, 2 FLEX, DST, K, 6 Bench).
  - Positional need indicators and bye week stack alerts.
  - Live snake pick calculator tracking whose turn it is across all 8 teams.
  - CSV Export of final draft results.

---

## 📦 Launch Options

### Option 1: 1-Click Launch (Windows)
Double-click [`app.bat`](file:///c:/Users/marco/OneDrive/Desktop/FANTASYDRAFT/app.bat) in this folder. It will automatically:
1. Open your browser to `http://localhost:8501`.
2. Start the local Streamlit server.

### Option 2: Command Line
```bash
# 1. Install dependencies (first time only)
pip install -r requirements.txt

# 2. Launch the Live Streamlit War Room
python -m streamlit run app.py
```

---

## 📁 Project Structure

```
FANTASYDRAFT/
├── app.bat                        # 1-Click Windows launcher (starts server & opens browser)
├── app.py                         # Production Streamlit live draft war room
├── scraper.py                     # Scraper, synthetic 2026 generator, consensus calculator
├── test_draft.py                  # Unit and integration test suite
├── requirements.txt               # Dependencies
├── README.md                      # Documentation
└── data/
    ├── draft_board_2026.parquet   # High-speed binary ranking cache
    ├── draft_board.db             # SQLite database cache
    └── sample_rankings_template.csv # User drop-in CSV template
```
