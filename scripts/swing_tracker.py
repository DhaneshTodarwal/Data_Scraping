#!/usr/bin/env python3
"""
Swing Trade Performance Tracker
================================
Tracks all stocks from the swing scanner, monitors daily performance,
and generates EOD reports sent to Telegram.

Modes:
  --register  : Register new stocks from today's scan into tracking database
  --update    : Update tracked stocks with today's closing price & status
  --report    : Generate & send EOD performance report to Telegram

Cron:
  7:52 PM  -> --register  (after scanner runs at 7:50 PM)
  3:32 PM  -> --update    (after market closes)
  3:33 PM  -> --report    (send summary to Telegram)
"""

import os, sys, json, csv, logging, argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import requests

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).resolve().parent
BASE_DIR    = SCRIPT_DIR.parent
PROJECT_ROOT = Path("/home/dhanesh-todarwal/nifty_options_scanner")
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    TELEGRAM_BOT_TOKEN = "8435399514:AAExJBLy-Qouu7ousURDDDmZwHxHskNJHLg"
    TELEGRAM_CHAT_ID   = "-1004420106626"

DATA_DIR      = BASE_DIR / "data"
TRACKING_DIR  = DATA_DIR / "swing_tracking"
SCANS_DIR     = DATA_DIR / "swing_intelligence" / "scans"
STOCKS_DIR    = DATA_DIR / "swing_intelligence" / "stocks"
REPORTS_DIR   = TRACKING_DIR / "reports"
MASTER_CSV    = TRACKING_DIR / "master_tracker.csv"
IST           = timezone(timedelta(hours=5, minutes=30))

# Category folder names
CATEGORY_MAP = {
    "🔥 SUPER BREAKOUT"   : "SUPER_BREAKOUT",
    "📦 HEAVY DELIVERY"   : "HEAVY DELIVERY",
    "🚀 MOMENTUM BREAKOUT": "MOMENTUM_BREAKOUT",
}
CATEGORY_FOLDER = {
    "🔥 SUPER BREAKOUT"   : "SUPER_BREAKOUT",
    "📦 HEAVY DELIVERY"   : "HEAVY_DELIVERY",
    "🚀 MOMENTUM BREAKOUT": "MOMENTUM_BREAKOUT",
}

MASTER_COLS = [
    "symbol","scan_date","category","scan_close","entry_min","entry_max",
    "target","stop_loss","rsi","vol_mult","delivery_pct","del_mult",
    "status","entry_date","entry_price","exit_date","exit_price",
    "pnl_pct","result","days_held","reason"
]

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "swing_tracker.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SwingTracker")

# ─── Telegram ─────────────────────────────────────────────────────────────────
def send_telegram(msg: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        res = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=15)
        return res.status_code == 200
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False

# ─── Master CSV helpers ───────────────────────────────────────────────────────
def load_master() -> list[dict]:
    if not MASTER_CSV.exists():
        return []
    with open(MASTER_CSV, newline="") as f:
        return list(csv.DictReader(f))

def save_master(rows: list[dict]):
    MASTER_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(MASTER_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MASTER_COLS)
        writer.writeheader()
        writer.writerows(rows)

def get_master_key(symbol: str, scan_date: str) -> str:
    return f"{symbol}_{scan_date}"

# ─── Per-stock JSON helpers ───────────────────────────────────────────────────
def stock_json_path(category_folder: str, symbol: str, scan_date: str) -> Path:
    return TRACKING_DIR / category_folder / f"{symbol}_{scan_date}.json"

def load_stock_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}

def save_stock_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))

# ─── Get latest price from daily_history CSV ──────────────────────────────────
def get_latest_price(symbol: str) -> dict | None:
    csv_path = STOCKS_DIR / symbol / "daily_history.csv"
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        if df.empty:
            return None
        row = df.iloc[-1]
        return {
            "date"          : row["date"].strftime("%Y-%m-%d"),
            "open"          : float(row["open"]),
            "high"          : float(row["high"]),
            "low"           : float(row["low"]),
            "close"         : float(row["close"]),
            "volume"        : int(row["volume"]),
            "delivery_pct"  : float(row.get("delivery_pct", 0)),
        }
    except Exception as e:
        logger.error(f"Error reading {symbol} history: {e}")
        return None

# ─── MODE 1: REGISTER ─────────────────────────────────────────────────────────
def register_new_stocks():
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    scan_file = SCANS_DIR / f"{today_str}.json"

    if not scan_file.exists():
        logger.warning(f"No scan file found for today: {scan_file}")
        return

    setups = json.loads(scan_file.read_text())
    logger.info(f"Found {len(setups)} setups to register for {today_str}")

    master = load_master()
    existing_keys = {get_master_key(r["symbol"], r["scan_date"]) for r in master}

    new_count = 0
    for s in setups:
        symbol     = s["symbol"]
        signal     = s.get("signal", "")
        cat_folder = CATEGORY_FOLDER.get(signal, "HEAVY_DELIVERY")
        key        = get_master_key(symbol, today_str)

        if key in existing_keys:
            logger.info(f"Already registered: {symbol}")
            continue

        # Parse entry range
        entry_parts = s.get("entry_range", "0 - 0").split(" - ")
        entry_min = float(entry_parts[0]) if len(entry_parts) == 2 else s["close"] * 0.99
        entry_max = float(entry_parts[1]) if len(entry_parts) == 2 else s["close"] * 1.01

        # --- Master CSV row ---
        row = {
            "symbol"      : symbol,
            "scan_date"   : today_str,
            "category"    : cat_folder,
            "scan_close"  : round(s["close"], 2),
            "entry_min"   : round(entry_min, 2),
            "entry_max"   : round(entry_max, 2),
            "target"      : round(s.get("target", s["close"] * 1.10), 2),
            "stop_loss"   : round(s.get("stop_loss", s["close"] * 0.94), 2),
            "rsi"         : round(s.get("rsi", 0), 2),
            "vol_mult"    : round(s.get("vol_mult", 0), 2),
            "delivery_pct": round(s.get("delivery_pct", 0), 2),
            "del_mult"    : round(s.get("del_mult", 0), 2),
            "status"      : "ACTIVE",
            "entry_date"  : "",
            "entry_price" : "",
            "exit_date"   : "",
            "exit_price"  : "",
            "pnl_pct"     : "",
            "result"      : "",
            "days_held"   : "",
            "reason"      : "",
        }
        master.append(row)
        existing_keys.add(key)

        # --- Per-stock JSON ---
        stock_data = {
            "symbol"       : symbol,
            "scan_date"    : today_str,
            "category"     : cat_folder,
            "signal"       : signal,
            "scan_close"   : round(s["close"], 2),
            "entry_range"  : s.get("entry_range", ""),
            "target"       : round(s.get("target", s["close"] * 1.10), 2),
            "stop_loss"    : round(s.get("stop_loss", s["close"] * 0.94), 2),
            "rsi_at_scan"  : round(s.get("rsi", 0), 2),
            "vol_mult"     : round(s.get("vol_mult", 0), 2),
            "delivery_pct" : round(s.get("delivery_pct", 0), 2),
            "del_mult"     : round(s.get("del_mult", 0), 2),
            "status"       : "ACTIVE",
            "daily_updates": [],
            "result"       : None,
            "exit_date"    : None,
            "exit_price"   : None,
            "pnl_pct"      : None,
            "reason"       : None,
        }
        path = stock_json_path(cat_folder, symbol, today_str)
        save_stock_json(path, stock_data)
        new_count += 1
        logger.info(f"Registered: {symbol} [{cat_folder}]")

    save_master(master)
    logger.info(f"✅ Registration complete. {new_count} new stocks added.")

    # Send Telegram confirmation
    msg  = f"📋 <b>Swing Tracker — {new_count} New Stocks Registered</b>\n"
    msg += f"📅 Scan Date: {today_str}\n\n"
    by_cat = {}
    for s in setups:
        cat = CATEGORY_FOLDER.get(s.get("signal",""), "OTHER")
        by_cat.setdefault(cat, []).append(s["symbol"])
    for cat, syms in by_cat.items():
        msg += f"<b>{cat.replace('_',' ')} ({len(syms)})</b>\n"
        msg += ", ".join(syms) + "\n\n"
    msg += "📊 Tracking started. Daily EOD updates will follow."
    send_telegram(msg)

# ─── MODE 2: UPDATE prices for all active stocks ─────────────────────────────
def update_prices():
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    master    = load_master()
    updated   = 0

    for row in master:
        if row.get("status") != "ACTIVE":
            continue

        symbol    = row["symbol"]
        scan_date = row["scan_date"]
        cat       = row["category"]
        target    = float(row["target"])
        sl        = float(row["stop_loss"])
        entry_min = float(row["entry_min"])
        entry_max = float(row["entry_max"])

        latest = get_latest_price(symbol)
        if not latest or latest["date"] != today_str:
            logger.warning(f"No today's price for {symbol}, skipping")
            continue

        close = latest["close"]
        scan_close = float(row["scan_close"])
        pct_vs_scan = round((close - scan_close) / scan_close * 100, 2)

        # Determine if entered (price was within entry range during the day)
        entered = (latest["low"] <= entry_max) and (not row.get("entry_price"))
        if entered and not row["entry_date"]:
            entry_px = min(entry_max, latest["open"])  # Approximate entry
            row["entry_date"]  = today_str
            row["entry_price"] = round(entry_px, 2)

        # Determine result
        new_status = "ACTIVE"
        result     = ""
        reason     = ""
        if latest["high"] >= target:
            new_status = "TARGET_HIT"
            result     = "WIN"
            reason     = f"Target ₹{target} hit"
            row["exit_date"]  = today_str
            row["exit_price"] = target
        elif latest["low"] <= sl:
            new_status = "SL_HIT"
            result     = "LOSS"
            reason     = f"Stop-loss ₹{sl} hit"
            row["exit_date"]  = today_str
            row["exit_price"] = sl

        if new_status != "ACTIVE":
            ep = float(row.get("entry_price") or scan_close)
            xp = float(row["exit_price"])
            row["pnl_pct"] = round((xp - ep) / ep * 100, 2)
            row["result"]  = result
            row["reason"]  = reason
            entry_d = datetime.strptime(row["entry_date"] or today_str, "%Y-%m-%d")
            exit_d  = datetime.strptime(today_str, "%Y-%m-%d")
            row["days_held"] = (exit_d - entry_d).days + 1

        row["status"] = new_status

        # Update per-stock JSON
        path       = stock_json_path(cat, symbol, scan_date)
        stock_data = load_stock_json(path)
        if stock_data:
            daily_update = {
                "date"        : today_str,
                "open"        : latest["open"],
                "high"        : latest["high"],
                "low"         : latest["low"],
                "close"       : close,
                "pct_vs_scan" : pct_vs_scan,
                "status"      : new_status,
                "delivery_pct": latest["delivery_pct"],
            }
            existing_dates = [u["date"] for u in stock_data.get("daily_updates", [])]
            if today_str not in existing_dates:
                stock_data["daily_updates"].append(daily_update)

            stock_data["status"]     = new_status
            if result:
                stock_data["result"]     = result
                stock_data["exit_date"]  = row["exit_date"]
                stock_data["exit_price"] = row["exit_price"]
                stock_data["pnl_pct"]    = row["pnl_pct"]
                stock_data["reason"]     = reason
            save_stock_json(path, stock_data)

        updated += 1
        logger.info(f"Updated {symbol}: Close={close}, Status={new_status}")

    save_master(master)
    logger.info(f"✅ Price update complete. {updated} stocks updated.")

# ─── MODE 3: EOD REPORT ───────────────────────────────────────────────────────
def eod_report():
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    master    = load_master()

    # Filter only active or recently closed today
    all_active   = [r for r in master if r["status"] == "ACTIVE"]
    target_hits  = [r for r in master if r["status"] == "TARGET_HIT" and r.get("exit_date") == today_str]
    sl_hits      = [r for r in master if r["status"] == "SL_HIT"     and r.get("exit_date") == today_str]
    today_scans  = [r for r in master if r["scan_date"] == today_str]

    # Build summary JSON
    summary = {
        "date"             : today_str,
        "total_active"     : len(all_active),
        "targets_hit_today": len(target_hits),
        "sl_hit_today"     : len(sl_hits),
        "new_today"        : len(today_scans),
        "target_stocks"    : [{"symbol": r["symbol"], "pnl_pct": r["pnl_pct"], "days_held": r["days_held"]} for r in target_hits],
        "sl_stocks"        : [{"symbol": r["symbol"], "pnl_pct": r["pnl_pct"], "days_held": r["days_held"]} for r in sl_hits],
        "active_watchlist" : [],
    }

    # Active stocks with current perf
    for r in all_active:
        latest = get_latest_price(r["symbol"])
        if latest:
            sc     = float(r["scan_close"])
            pct    = round((latest["close"] - sc) / sc * 100, 2)
            target = float(r["target"])
            sl     = float(r["stop_loss"])
            dist_t = round((target - latest["close"]) / latest["close"] * 100, 1)
            dist_s = round((latest["close"] - sl) / latest["close"] * 100, 1)
            summary["active_watchlist"].append({
                "symbol"    : r["symbol"],
                "category"  : r["category"].replace("_", " "),
                "scan_date" : r["scan_date"],
                "scan_close": sc,
                "today_close": latest["close"],
                "pct_vs_scan": pct,
                "dist_to_target": dist_t,
                "dist_to_sl"    : dist_s,
                "target"        : target,
                "stop_loss"     : sl,
            })

    # Save summary report JSON
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS_DIR / f"{today_str}_eod_summary.json"
    report_file.write_text(json.dumps(summary, indent=2))
    logger.info(f"Saved EOD summary: {report_file}")

    # ─── Telegram Message ───
    msg  = f"📊 <b>SWING TRACKER — EOD REPORT</b>\n"
    msg += f"📅 {today_str}\n"
    msg += "══════════════════════════════\n\n"

    # Wins today
    if target_hits:
        msg += f"✅ <b>TARGET HIT ({len(target_hits)})</b>\n"
        for r in target_hits:
            msg += f"  🏆 <b>{r['symbol']}</b>  →  <code>+{r['pnl_pct']}%</code>  ({r['days_held']} days)\n"
        msg += "\n"

    # Losses today
    if sl_hits:
        msg += f"❌ <b>STOP-LOSS HIT ({len(sl_hits)})</b>\n"
        for r in sl_hits:
            msg += f"  💔 <b>{r['symbol']}</b>  →  <code>{r['pnl_pct']}%</code>  ({r['days_held']} days)\n"
        msg += "\n"

    # Active watchlist (top 10 by pct change)
    active_sorted = sorted(summary["active_watchlist"], key=lambda x: x["pct_vs_scan"], reverse=True)
    if active_sorted:
        msg += f"👁️ <b>ACTIVE WATCHLIST ({len(active_sorted)} stocks)</b>\n"
        msg += "──────────────────────────────\n"
        for s in active_sorted[:15]:
            sign = "📈" if s["pct_vs_scan"] >= 0 else "📉"
            p    = f"+{s['pct_vs_scan']}%" if s["pct_vs_scan"] >= 0 else f"{s['pct_vs_scan']}%"
            msg += f"{sign} <b>{s['symbol']}</b>  <code>{p}</code>  | 🎯{s['dist_to_target']}% away | 🛑{s['dist_to_sl']}% cushion\n"
        if len(active_sorted) > 15:
            msg += f"  ... and {len(active_sorted)-15} more active.\n"

    msg += f"\n📁 <i>Total Active: {len(all_active)} | New Today: {len(today_scans)} | Category folders updated.</i>"

    ok = send_telegram(msg)
    logger.info("✅ EOD report sent to Telegram." if ok else "❌ Failed to send EOD report.")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Swing Trade Performance Tracker")
    parser.add_argument("--register", action="store_true", help="Register new stocks from today's scan")
    parser.add_argument("--update",   action="store_true", help="Update prices for all active stocks")
    parser.add_argument("--report",   action="store_true", help="Generate and send EOD report to Telegram")
    args = parser.parse_args()

    if args.register:
        logger.info("=== MODE: REGISTER ===")
        register_new_stocks()
    elif args.update:
        logger.info("=== MODE: UPDATE PRICES ===")
        update_prices()
    elif args.report:
        logger.info("=== MODE: EOD REPORT ===")
        eod_report()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
