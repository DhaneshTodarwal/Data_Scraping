#!/usr/bin/env python3
"""
Predictor Engine
================
Runs daily at 09:07 AM IST (immediately after pre-market clues are collected).
Combines:
1. Pre-market global clues (S&P 500, Nasdaq, VIX, Crude, USD/INR)
2. Previous day institutional cash flows (FII / DII net cash)
3. Previous day participant-wise open interest trends
4. Previous day option chain PCR trends

Calculates a daily bias score (-10 to +10) and recommends option trading strategies.
Sends a premium terminal-style daily bias report to Telegram.
"""
import os
import sys
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to sys.path to access config
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = Path("/home/dhanesh-todarwal/nifty_options_scanner")
sys.path.insert(0, str(PROJECT_ROOT))

# Import config credentials
try:
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    TELEGRAM_BOT_TOKEN = "8435399514:AAExJBLy-Qouu7ousURDDDmZwHxHskNJHLg"
    TELEGRAM_CHAT_ID = "-1004420106626"

import requests

# IST Timezone
IST = timezone(timedelta(hours=5, minutes=30))

# Directories
DATA_DIR = BASE_DIR / "data"
PRE_MARKET_DIR = DATA_DIR / "pre_market_clues"
FII_DII_DIR = DATA_DIR / "fii_dii"
PARTICIPANT_OI_DIR = DATA_DIR / "participant_oi"
INTRADAY_DIR = DATA_DIR / "intraday_indicators"

# Log configuration
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "predictor_engine.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("PredictorEngine")

def send_telegram_message(message: str) -> bool:
    """Send formatted message to Telegram channel."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram token or Chat ID not configured.")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        res = requests.post(url, data=data, timeout=10)
        return res.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False

def get_sorted_dates_in_dir(directory: Path):
    """Scan directory recursively and return sorted list of dates (datetime objects) from filenames."""
    dates = []
    if not directory.exists():
        return dates
    for p in directory.glob("**/*.json"):
        try:
            # Filename is YYYY-MM-DD.json
            dt = datetime.strptime(p.stem, "%Y-%m-%d")
            dates.append((dt, p))
        except ValueError:
            continue
    for p in directory.glob("**/*.csv"):
        try:
            # Filename is YYYY-MM-DD.csv
            dt = datetime.strptime(p.stem, "%Y-%m-%d")
            dates.append((dt, p))
        except ValueError:
            continue
    dates.sort(key=lambda x: x[0])
    return dates

def get_latest_file_before(directory: Path, target_date: datetime):
    """Get the path to the latest file in directory dated strictly before target_date."""
    sorted_files = get_sorted_dates_in_dir(directory)
    latest_file = None
    for dt, path in sorted_files:
        if dt.date() < target_date.date():
            latest_file = path
        else:
            break
    return latest_file

def load_json(path: Path):
    """Load JSON file safely."""
    if not path or not path.exists():
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
        return None

def load_last_line_csv(path: Path):
    """Load the last non-empty line of a CSV file (useful for daily closing indicators)."""
    if not path or not path.exists():
        return None
    try:
        with open(path, "r") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
            if len(lines) < 2:
                return None
            headers = [h.strip() for h in lines[0].split(',')]
            values = [v.strip() for v in lines[-1].split(',')]
            return dict(zip(headers, values))
    except Exception as e:
        logger.error(f"Error reading CSV {path}: {e}")
        return None

def compute_bias(target_date_str):
    """Compute market bias score and generate predictions."""
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    
    # 1. Load Pre-Market Clues (For target date / Today)
    year = target_dt.strftime("%Y")
    month = target_dt.strftime("%B")
    today_pre_market_file = PRE_MARKET_DIR / year / month / f"{target_date_str}.json"
    pre_market = load_json(today_pre_market_file)
    
    # 2. Get Previous Trading Day files
    prev_fii_dii_file = get_latest_file_before(FII_DII_DIR, target_dt)
    prev_participant_file = get_latest_file_before(PARTICIPANT_OI_DIR, target_dt)
    prev_intraday_file = get_latest_file_before(INTRADAY_DIR, target_dt)
    
    # Get previous to previous day participant file to calculate OI changes
    prev_prev_participant_file = None
    if prev_participant_file:
        prev_dt = datetime.strptime(prev_participant_file.stem, "%Y-%m-%d")
        prev_prev_participant_file = get_latest_file_before(PARTICIPANT_OI_DIR, prev_dt)
        
    fii_dii = load_json(prev_fii_dii_file)
    participant_oi = load_json(prev_participant_file)
    prev_participant_oi = load_json(prev_prev_participant_file)
    intraday_close = load_last_line_csv(prev_intraday_file)
    
    logger.info(f"Loaded Pre-market: {'✅' if pre_market else '❌'}")
    logger.info(f"Loaded FII/DII Cash: {'✅' if fii_dii else '❌'} (Date: {prev_fii_dii_file.stem if prev_fii_dii_file else 'N/A'})")
    logger.info(f"Loaded Participant OI: {'✅' if participant_oi else '❌'} (Date: {prev_participant_file.stem if prev_participant_file else 'N/A'})")
    logger.info(f"Loaded Previous Intraday: {'✅' if intraday_close else '❌'} (Date: {prev_intraday_file.stem if prev_intraday_file else 'N/A'})")
    
    # Scoring calculation
    score = 0.0
    details = []
    
    # --- SECTION A: GLOBAL MARKET SETUP (Max +/- 3.0) ---
    if pre_market and "clues" in pre_market:
        clues = pre_market["clues"]
        
        # S&P 500
        sp = clues.get("SP500", {})
        if sp:
            sp_change = sp.get("pct_change", 0.0)
            if sp_change > 0.75:
                score += 1.0
                details.append(("S&P 500 Strong Close", +1.0, f"+{sp_change:.2f}%"))
            elif sp_change > 0.25:
                score += 0.5
                details.append(("S&P 500 Positive Close", +0.5, f"+{sp_change:.2f}%"))
            elif sp_change < -0.75:
                score -= 1.0
                details.append(("S&P 500 Weak Close", -1.0, f"{sp_change:.2f}%"))
            elif sp_change < -0.25:
                score -= 0.5
                details.append(("S&P 500 Negative Close", -0.5, f"{sp_change:.2f}%"))
                
        # Nasdaq
        nas = clues.get("Nasdaq", {})
        if nas:
            nas_change = nas.get("pct_change", 0.0)
            if nas_change > 0.75:
                score += 0.5
                details.append(("Nasdaq Strong Close", +0.5, f"+{nas_change:.2f}%"))
            elif nas_change < -0.75:
                score -= 0.5
                details.append(("Nasdaq Weak Close", -0.5, f"{nas_change:.2f}%"))
                
        # US VIX
        us_vix = clues.get("US_VIX", {})
        if us_vix:
            vix_change = us_vix.get("pct_change", 0.0)
            if vix_change > 5.0:
                score -= 0.5
                details.append(("US VIX Spike", -0.5, f"+{vix_change:.2f}%"))
            elif vix_change < -5.0:
                score += 0.5
                details.append(("US VIX Decline", +0.5, f"{vix_change:.2f}%"))
                
        # Brent Crude
        crude = clues.get("Brent_Crude", {})
        if crude:
            crude_change = crude.get("pct_change", 0.0)
            if crude_change > 1.5:
                score -= 0.5
                details.append(("Brent Crude Spike", -0.5, f"+{crude_change:.2f}%"))
            elif crude_change < -1.5:
                score += 0.5
                details.append(("Brent Crude Decline", +0.5, f"{crude_change:.2f}%"))
                
        # USD / INR
        inr = clues.get("USD_INR", {})
        if inr:
            inr_change = inr.get("pct_change", 0.0)
            if inr_change > 0.20:
                score -= 0.5
                details.append(("USD/INR Rupee Deprec", -0.5, f"+{inr_change:.2f}%"))
            elif inr_change < -0.20:
                score += 0.5
                details.append(("USD/INR Rupee Apprec", +0.5, f"{inr_change:.2f}%"))
    else:
        details.append(("Global Market Setup (No data)", 0.0, "N/A"))
        
    # --- SECTION B: INSTITUTIONAL FLOWS (Max +/- 4.0) ---
    if fii_dii:
        fii_cash = fii_dii.get("FII", {}).get("net_value_crores", 0.0)
        dii_cash = fii_dii.get("DII", {}).get("net_value_crores", 0.0)
        
        # FII Cash Flow
        if fii_cash > 1500.0:
            score += 1.0
            details.append(("FII Cash Heavy Buying", +1.0, f"+{fii_cash:,.1f} Cr"))
        elif fii_cash > 500.0:
            score += 0.5
            details.append(("FII Cash Net Buying", +0.5, f"+{fii_cash:,.1f} Cr"))
        elif fii_cash < -1500.0:
            score -= 1.0
            details.append(("FII Cash Heavy Selling", -1.0, f"{fii_cash:,.1f} Cr"))
        elif fii_cash < -500.0:
            score -= 0.5
            details.append(("FII Cash Net Selling", -0.5, f"{fii_cash:,.1f} Cr"))
            
        # DII Cash Flow
        if dii_cash > 1500.0:
            score += 0.5
            details.append(("DII Cash Strong Buying", +0.5, f"+{dii_cash:,.1f} Cr"))
        elif dii_cash < -1500.0:
            score -= 0.5
            details.append(("DII Cash Net Selling", -0.5, f"{dii_cash:,.1f} Cr"))
    else:
        details.append(("FII/DII Cash Flow (No data)", 0.0, "N/A"))
        
    # FII Index Futures Net Position & Change
    if participant_oi and "data" in participant_oi:
        fii_oi = participant_oi["data"].get("FII", {})
        fii_long = fii_oi.get("future_index_long", 0)
        fii_short = fii_oi.get("future_index_short", 0)
        net_fii_idx = fii_long - fii_short
        
        # Net Contracts
        if net_fii_idx > 50000:
            score += 1.0
            details.append(("FII Net Index Fut Long", +1.0, f"+{net_fii_idx:,}"))
        elif net_fii_idx > 0:
            score += 0.5
            details.append(("FII Net Index Fut Positive", +0.5, f"+{net_fii_idx:,}"))
        elif net_fii_idx < -100000:
            score -= 1.0
            details.append(("FII Net Index Fut Heavy Short", -1.0, f"{net_fii_idx:,}"))
        elif net_fii_idx < 0:
            score -= 0.5
            details.append(("FII Net Index Fut Net Short", -0.5, f"{net_fii_idx:,}"))
            
        # OI Change from previous day
        if prev_participant_oi and "data" in prev_participant_oi:
            prev_fii_oi = prev_participant_oi["data"].get("FII", {})
            prev_net = prev_fii_oi.get("future_index_long", 0) - prev_fii_oi.get("future_index_short", 0)
            oi_change = net_fii_idx - prev_net
            
            if oi_change > 15000:
                score += 1.0
                details.append(("FII Index Fut Long Addition", +1.0, f"+{oi_change:,}"))
            elif oi_change < -15000:
                score -= 1.0
                details.append(("FII Index Fut Short Addition", -1.0, f"{oi_change:,}"))
    else:
        details.append(("FII Index Futures OI (No data)", 0.0, "N/A"))
        
    # --- SECTION C: OPTION CHAIN PCR (Max +/- 3.0) ---
    if intraday_close:
        # Get Nifty PCR
        try:
            nifty_pcr = float(intraday_close.get("nifty_pcr", 1.0))
            if nifty_pcr > 1.25:
                score += 1.0
                details.append(("High Nifty PCR Close", +1.0, f"{nifty_pcr:.2f}"))
            elif nifty_pcr > 1.05:
                score += 0.5
                details.append(("Positive Nifty PCR Close", +0.5, f"{nifty_pcr:.2f}"))
            elif nifty_pcr < 0.75:
                score -= 1.0
                details.append(("Low Nifty PCR Close", -1.0, f"{nifty_pcr:.2f}"))
            elif nifty_pcr < 0.90:
                score -= 0.5
                details.append(("Weak Nifty PCR Close", -0.5, f"{nifty_pcr:.2f}"))
        except Exception:
            pass
            
        # Nifty Spot change / India VIX Close
        try:
            vix = float(intraday_close.get("india_vix", 15.0))
            if vix > 18.0:
                score -= 0.5
                details.append(("High India VIX Regime", -0.5, f"{vix:.2f}"))
            elif vix < 12.0:
                score += 0.5
                details.append(("Low India VIX Regime", +0.5, f"{vix:.2f}"))
        except Exception:
            pass
    else:
        details.append(("PCR & VIX Trend (No data)", 0.0, "N/A"))
        
    # Bound the score between -10.0 and +10.0
    score = max(-10.0, min(10.0, score))
    
    # Determine Bias and strategy recommendation
    if score >= 3.0:
        bias = "🟢 BULLISH BIAS"
        strat = "🐂 Bull Put Spreads (Selling Puts) / Buy Call Spreads. Avoid naked short puts unless protected."
    elif score <= -3.0:
        bias = "🔴 BEARISH BIAS"
        strat = "🐻 Bear Call Spreads (Selling Calls) / Buy Put Spreads. Avoid naked short calls unless protected."
    else:
        bias = "🟡 RANGEBOUND / NEUTRAL BIAS"
        strat = "⚖️ Short Straddle / Short Strangle. Ideal for 9:20 AM Straddle Strategy to collect premium decay."
        
    return {
        "date": target_date_str,
        "score": score,
        "bias": bias,
        "recommended_strategy": strat,
        "score_details": details,
        "pre_market_avail": bool(pre_market),
        "post_market_avail": bool(fii_dii),
        "prev_day": prev_fii_dii_file.stem if prev_fii_dii_file else "N/A"
    }

def format_telegram_report(res):
    """Format bias details into a premium terminal report."""
    formatted_date = datetime.strptime(res["date"], "%Y-%m-%d").strftime("%d-%b-%Y")
    
    report = f"🔮 <b>DAILY MARKET FORECAST ({formatted_date})</b>\n"
    report += "==================================\n\n"
    
    report += f"🎯 <b>BIAS: {res['bias']}</b>\n"
    report += f"Bias Score: <code>{res['score']:+.2f} / 10.0</code>\n\n"
    
    report += "🛠️ <b>RECOMMENDED STRATEGY:</b>\n"
    report += f"<code>{res['recommended_strategy']}</code>\n\n"
    
    report += "📊 <b>SCORE CONSTITUENTS:</b>\n"
    report += "----------------------------------\n"
    for label, pts, val in res["score_details"]:
        sign = "+" if pts > 0 else ""
        pts_str = f"{sign}{pts:.1f}" if pts != 0.0 else " 0.0"
        # Pad label for monospacing
        label_padded = label.ljust(25)
        report += f"• <code>{pts_str}</code> | {label_padded} (<code>{val}</code>)\n"
    report += "\n"
    
    report += f"ℹ️ <i>Global cues updated. Previous session data fetched from {res['prev_day']}.</i>"
    return report

def main():
    parser = argparse.ArgumentParser(description="Nifty Options Scanner Predictor Engine")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD format (Default: Today)", default=None)
    args = parser.parse_args()
    
    # Calculate target date
    if args.date:
        target_date_str = args.date
        logger.info(f"Target date set via CLI: {target_date_str}")
    else:
        # Today in IST
        now_ist = datetime.now(IST)
        target_date_str = now_ist.strftime("%Y-%m-%d")
        
        # Verify if weekend
        if now_ist.weekday() >= 5:
            logger.info("Today is a weekend. Predictions are not computed on weekends.")
            sys.exit(0)
            
    logger.info(f"Running prediction calculations for {target_date_str}...")
    
    # Compute bias and recommendations
    res = compute_bias(target_date_str)
    
    # Save the output prediction JSON
    year = datetime.strptime(target_date_str, "%Y-%m-%d").strftime("%Y")
    month = datetime.strptime(target_date_str, "%Y-%m-%d").strftime("%B")
    
    pred_dir = DATA_DIR / "predictions" / year / month
    pred_dir.mkdir(parents=True, exist_ok=True)
    
    pred_file = pred_dir / f"{target_date_str}.json"
    with open(pred_file, "w") as f:
        json.dump(res, f, indent=4)
    logger.info(f"Saved prediction results to {pred_file}")
    
    # Send Telegram alert
    msg = format_telegram_report(res)
    logger.info("Sending prediction report to Telegram...")
    success = send_telegram_message(msg)
    if success:
        logger.info("✅ Telegram bias alert sent successfully.")
    else:
        logger.error("❌ Failed to send Telegram bias alert.")

if __name__ == "__main__":
    main()
