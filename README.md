# Options Data Scraping

Automated NIFTY and BANKNIFTY options OHLCV data collection.

## Features
- ✅ Fully automated (no manual TOTP entry)
- ✅ NIFTY/BANKNIFTY 1-minute candles
- ✅ Options strike prices OHLCV
- ✅ Daily cron job (3:35 PM)
- ✅ Angel One SmartAPI integration

## Quick Start

**Run manual collection:**
```bash
python3 scripts/angelone_complete.py
```

**Test connection:**
```bash
python3 scripts/angelone_auto.py test
```

## Scripts

| Script | Purpose |
|--------|---------|
| `angelone_complete.py` | Full collection (index + options) |
| `angelone_auto.py` | Simple index collection |
| `angelone_collector.py` | Manual TOTP collection |

## Data Output

| Data Type | Location |
|-----------|----------|
| Index OHLCV | `data/options_ohlcv/` |
| Strike OHLCV | `data/strikes_ohlcv/` |
| Logs | `logs/` |

## Automation

Cron job runs at **3:35 PM** (Mon-Fri):
```bash
crontab -l | grep angelone
```

## Configuration

API credentials stored in `.env`:
- ANGEL_API_KEY
- ANGEL_SECRET_KEY
- ANGEL_CLIENT_ID
- ANGEL_PIN
- ANGEL_TOTP_SECRET

---
Created: 2026-01-16
