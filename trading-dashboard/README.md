# 📊 Trading Signal Dashboard

A full-stack algorithmic trading signal web app — same strategy engine as the Telegram bot, now with a beautiful web dashboard, real-time signal streaming, interactive TradingView charts, and performance analytics.

## How It Works

1. The backend scanner runs **every 5 minutes**, checking all pairs
2. Each pair is scored using a **5-component confluence model** (max 8 pts)
3. Only setups scoring **≥ 5/8** are published as signals
4. Signals stream to your browser **instantly** via WebSocket
5. Every 30 minutes the engine checks if SL or TP was hit → **WIN / LOSS**
6. Click any signal card to see its **TradingView chart** with entry/SL/TP levels

---

## Signal Scoring Model

| Component | Condition | Points |
|---|---|---|
| **Trend Confirmation** | EMA50/200 aligned on BOTH timeframes (15min + 1h) | +2 |
| **RSI Pullback** | RSI < 40 (BUY) or > 60 (SELL) | +1 |
| **Market Structure** | Price within 0.3% of recent swing low/high | +2 |
| **ATR Volatility** | Current ATR above 50-bar average | +1 |
| **Liquidity Sweep** | Price swept recent H/L then reversed | +2 |
| **Minimum to trade** | | **5/8** |

**Risk Management:** SL = 1.5× ATR · TP = 2.5× ATR · Min RR = 1:1.5

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python · FastAPI · APScheduler |
| Real-time | WebSocket (built into FastAPI) |
| Market data | TwelveData REST API (free tier) |
| Charts | TradingView free embed widget (no API key needed) |
| Database | SQLite (persisted on Render disk) |
| Frontend | React · Vite · Tailwind CSS · Recharts · Zustand |

---

## Project Structure

```
trading-dashboard/
├── render.yaml                  ← Render deployment config
├── backend/
│   ├── main.py                  ← FastAPI app + WebSocket endpoint
│   ├── config.py                ← All tunable parameters
│   ├── requirements.txt
│   ├── .env.example
│   └── modules/
│       ├── database.py          ← SQLite persistence
│       ├── market_data.py       ← TwelveData API client
│       ├── strategy.py          ← Signal scoring engine
│       └── scanner.py           ← Background scheduler + WS broadcast
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── index.html
    └── src/
        ├── App.tsx              ← Main dashboard layout
        ├── store/useStore.ts    ← Zustand state
        ├── hooks/useWebSocket.ts← WebSocket client hook
        └── components/
            ├── signals/SignalCard.tsx    ← Clickable signal card
            ├── signals/SignalDetail.tsx  ← Chart + trade levels
            └── signals/StatsPanel.tsx   ← Charts + win rate
```

---

## Local Development

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env and add your TWELVEDATA_API_KEY

# Run backend
python main.py
# → API available at http://localhost:8000
```

### 2. Frontend setup (separate terminal)

```bash
cd frontend
npm install
npm run dev
# → Dashboard at http://localhost:5173
```

Open http://localhost:5173, click **▶ Start** to begin scanning.

---

## Deploy to Render

### Option A — Automatic (recommended)

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → **New** → **Blueprint**
3. Connect your repo — Render reads `render.yaml` automatically
4. Add environment variable: `TWELVEDATA_API_KEY` = your key
5. Deploy — done ✅

### Option B — Manual

1. Create a **Web Service** on Render
2. Connect your GitHub repo
3. Set:
   - **Root Directory**: `backend`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt && cd ../frontend && npm install && npm run build && cp -r dist ../backend/dist
     ```
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add a **Disk** (1 GB) mounted at `/data`
5. Add environment variable: `TWELVEDATA_API_KEY`
6. Deploy

### Environment Variables on Render

| Variable | Required | Description |
|---|---|---|
| `TWELVEDATA_API_KEY` | ✅ | Free at twelvedata.com |
| `LOG_LEVEL` | ❌ | Default: `INFO` |

---

## TwelveData Free Tier

The free tier provides **800 API credits/day**.

Each scan cycle: 2 timeframes × 12 pairs = **24 credits per scan**

At 5-minute intervals: 24 × 288 scans/day = **6,912 credits** needed for continuous scanning.

**To stay within free tier**: reduce `WATCHLIST` to 4–6 pairs in `config.py`, or increase `SCAN_INTERVAL_SECONDS` to 1800 (30 min).

---

## Configuring the Bot

All settings are in `backend/config.py`:

```python
SCAN_INTERVAL_SECONDS = 300      # Scan every 5 min
MIN_SCORE_TO_TRADE = 5           # Min confluence score
ATR_SL_MULTIPLIER = 1.5          # Stop loss distance
ATR_TP_MULTIPLIER = 2.5          # Take profit distance
MIN_RISK_REWARD = 1.5            # Reject if RR below this
MIN_SIGNAL_GAP_SECONDS = 3600    # 1-hour cooldown per pair
MAX_SIGNALS_PER_HOUR = 5         # Hard hourly cap

# Set to None to scan 24/7:
ACTIVE_SESSION_HOURS = [(7, 16), (12, 21)]  # London + New York UTC

WATCHLIST = [
    "EUR/USD", "GBP/USD", "USD/JPY", ...  # Add/remove pairs here
]
```

---

## API Endpoints

The backend also exposes REST endpoints if you want to query directly:

| Endpoint | Description |
|---|---|
| `GET /api/signals` | All signals (last 100) |
| `GET /api/signals/{id}` | Single signal by ID |
| `GET /api/stats` | Performance statistics |
| `GET /api/scanner/status` | Scanner on/off |
| `POST /api/scanner/start` | Start scanner |
| `POST /api/scanner/stop` | Stop scanner |
| `WS /ws` | Real-time WebSocket stream |

---

## Disclaimer

This tool is for **educational and research purposes only**. Not financial advice. Trading involves significant risk. Past signal performance does not guarantee future results.
