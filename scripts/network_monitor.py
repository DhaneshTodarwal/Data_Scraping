"""
Network Health Monitor for Data Collection
============================================
Monitors network connectivity during market hours.
Sends Telegram alerts when network issues are detected.

Features:
- Checks internet connectivity (DNS, ping)
- Checks AngelOne API reachability
- Checks Telegram API reachability
- Alerts on failure and restoration
- Cooldown to prevent alert spam

Usage:
    python3 network_monitor.py --test     # Test connectivity
    python3 network_monitor.py --run      # Run continuous monitoring
    python3 network_monitor.py --once     # Single check
"""

import socket
import time
import subprocess
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

# Add project paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "analysis"))

# Import notifications
try:
    from notifications import send_telegram_message, send_desktop_notification
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    def send_telegram_message(msg): print(f"[TELEGRAM] {msg}")
    def send_desktop_notification(title, msg, urgency="normal"): print(f"[DESKTOP] {title}: {msg}")

# Timezone
IST = timezone(timedelta(hours=5, minutes=30))

# Configuration
CHECK_INTERVAL = 60  # seconds
ALERT_COOLDOWN = 300  # 5 minutes - don't spam alerts
LOG_FILE = Path(__file__).parent.parent / "logs" / "network_health.log"

# Endpoints to check
ENDPOINTS = {
    "internet": ("8.8.8.8", 53),  # Google DNS
    "angelone_api": ("apiconnect.angelone.in", 443),
    "telegram": ("api.telegram.org", 443),
}


def log(message: str):
    """Log message to file and console"""
    timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(log_msg + "\n")
    except Exception as e:
        print(f"Failed to write log: {e}")


def check_socket(host: str, port: int, timeout: float = 5.0) -> bool:
    """Check if host:port is reachable via socket connection"""
    try:
        socket.setdefaulttimeout(timeout)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except socket.gaierror:
        # DNS resolution failed
        return False
    except socket.timeout:
        return False
    except Exception:
        return False


def check_dns_resolution(hostname: str) -> bool:
    """Check if hostname can be resolved via DNS"""
    try:
        socket.gethostbyname(hostname)
        return True
    except socket.gaierror:
        return False


def check_ping(host: str = "8.8.8.8", count: int = 2) -> bool:
    """Check if host responds to ping"""
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", "3", host],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def check_internet() -> tuple[bool, str]:
    """Check basic internet connectivity"""
    # Method 1: Try socket to Google DNS
    if check_socket("8.8.8.8", 53, timeout=3):
        return True, "Google DNS reachable"
    
    # Method 2: Try ping
    if check_ping("8.8.8.8", count=2):
        return True, "Ping to 8.8.8.8 successful"
    
    # Method 3: Try another DNS
    if check_socket("1.1.1.1", 53, timeout=3):
        return True, "Cloudflare DNS reachable"
    
    return False, "No internet connectivity"


def check_api_reachable() -> tuple[bool, str]:
    """Check if AngelOne API is reachable"""
    hostname = "apiconnect.angelone.in"
    
    # Check DNS resolution
    if not check_dns_resolution(hostname):
        return False, f"DNS resolution failed for {hostname}"
    
    # Check socket connection
    if check_socket(hostname, 443, timeout=5):
        return True, "AngelOne API reachable"
    
    return False, "AngelOne API not reachable"


def check_telegram_reachable() -> tuple[bool, str]:
    """Check if Telegram API is reachable"""
    hostname = "api.telegram.org"
    
    if not check_dns_resolution(hostname):
        return False, f"DNS resolution failed for {hostname}"
    
    if check_socket(hostname, 443, timeout=5):
        return True, "Telegram API reachable"
    
    return False, "Telegram API not reachable"


def check_all() -> dict:
    """Run all connectivity checks"""
    results = {}
    
    internet_ok, internet_msg = check_internet()
    results['internet'] = {'ok': internet_ok, 'message': internet_msg}
    
    api_ok, api_msg = check_api_reachable()
    results['angelone_api'] = {'ok': api_ok, 'message': api_msg}
    
    telegram_ok, telegram_msg = check_telegram_reachable()
    results['telegram'] = {'ok': telegram_ok, 'message': telegram_msg}
    
    results['all_ok'] = internet_ok and api_ok and telegram_ok
    
    return results


def is_market_hours() -> bool:
    """Check if current time is within market hours (9:15 AM - 3:35 PM, Mon-Fri)"""
    now = datetime.now(IST)
    
    # Weekend check
    if now.weekday() >= 5:
        return False
    
    # Time check
    current_time = now.hour * 60 + now.minute
    market_start = 9 * 60 + 15   # 9:15 AM
    market_end = 15 * 60 + 35    # 3:35 PM
    
    return market_start <= current_time <= market_end


class NetworkHealthMonitor:
    """
    Continuous network health monitoring during market hours.
    Sends alerts on failure and when connection is restored.
    """
    
    def __init__(self, check_interval: int = CHECK_INTERVAL):
        self.check_interval = check_interval
        self.last_alert_time = 0
        self.network_was_down = False
        self.failure_count = 0
        self.last_failure_reason = ""
    
    def _can_send_alert(self) -> bool:
        """Check if we can send an alert (cooldown)"""
        return time.time() - self.last_alert_time > ALERT_COOLDOWN
    
    def _send_failure_alert(self, results: dict):
        """Send alert when network fails"""
        now = datetime.now(IST).strftime("%H:%M:%S")
        
        issues = []
        if not results['internet']['ok']:
            issues.append(f"🌐 Internet: ❌ {results['internet']['message']}")
        if not results['angelone_api']['ok']:
            issues.append(f"📊 AngelOne API: ❌ {results['angelone_api']['message']}")
        if not results['telegram']['ok']:
            issues.append(f"📱 Telegram: ❌ {results['telegram']['message']}")
        
        issues_text = "\n".join(issues)
        
        msg = f"""
🚨 <b>NETWORK CONNECTIVITY ALERT</b>

⏰ <b>Time:</b> {now}
⚠️ <b>Status:</b> CONNECTION ISSUES DETECTED

━━━━━ ISSUES ━━━━━

{issues_text}

━━━━━━━━━━━━━━━━━━

⚠️ <b>WARNING:</b> Data collection may fail!
🔄 Will auto-alert when restored.

<i>Check your internet connection</i>
"""
        
        # Only send if telegram is reachable
        if results['telegram']['ok']:
            send_telegram_message(msg)
            self.last_alert_time = time.time()
        
        # Always try desktop notification
        send_desktop_notification(
            "🚨 Network Down!",
            "Data collection at risk - check internet",
            "critical"
        )
        
        log(f"⚠️ Network failure alert sent: {issues_text}")
    
    def _send_restoration_alert(self):
        """Send alert when network is restored"""
        now = datetime.now(IST).strftime("%H:%M:%S")
        
        msg = f"""
✅ <b>NETWORK RESTORED</b>

⏰ <b>Time:</b> {now}
✅ <b>Status:</b> All connections working

━━━━━━━━━━━━━━━━━━

✅ Internet: OK
✅ AngelOne API: OK
✅ Telegram: OK

━━━━━━━━━━━━━━━━━━

📊 Data collection should resume normally.
"""
        
        send_telegram_message(msg)
        send_desktop_notification(
            "✅ Network Restored",
            "All connections working again",
            "normal"
        )
        
        self.last_alert_time = time.time()
        log("✅ Network restoration alert sent")
    
    def check_once(self) -> dict:
        """Perform a single health check"""
        results = check_all()
        
        if results['all_ok']:
            if self.network_was_down:
                # Network was down but now restored
                self._send_restoration_alert()
                self.network_was_down = False
                self.failure_count = 0
            log("✅ Network health check: All OK")
        else:
            self.failure_count += 1
            
            if not self.network_was_down and self._can_send_alert():
                # First failure detection
                self._send_failure_alert(results)
                self.network_was_down = True
            elif self.failure_count % 10 == 0 and self._can_send_alert():
                # Periodic reminder (every 10 failures ~10 minutes)
                self._send_failure_alert(results)
            
            log(f"❌ Network health check: FAILED (count: {self.failure_count})")
        
        return results
    
    def run(self):
        """Run continuous monitoring during market hours"""
        log("=" * 60)
        log("Starting Network Health Monitor")
        log(f"Check interval: {self.check_interval}s")
        log("=" * 60)
        
        # Initial check
        results = self.check_once()
        
        if not results['all_ok']:
            log("⚠️ Starting with network issues!")
        else:
            log("✅ Initial check passed")
        
        # Main loop
        while True:
            try:
                if is_market_hours():
                    self.check_once()
                else:
                    log("Outside market hours - skipping check")
                
                time.sleep(self.check_interval)
            
            except KeyboardInterrupt:
                log("Monitor stopped by user")
                break
            except Exception as e:
                log(f"Error in monitoring loop: {e}")
                time.sleep(self.check_interval)


def run_test():
    """Run a test of all network checks"""
    print("\n" + "=" * 60)
    print("       NETWORK CONNECTIVITY TEST")
    print("=" * 60)
    
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"⏰ Time: {now}\n")
    
    # Run all checks
    results = check_all()
    
    print("📡 Internet Connectivity:")
    print(f"   {'✅' if results['internet']['ok'] else '❌'} {results['internet']['message']}")
    
    print("\n📊 AngelOne API:")
    print(f"   {'✅' if results['angelone_api']['ok'] else '❌'} {results['angelone_api']['message']}")
    
    print("\n📱 Telegram API:")
    print(f"   {'✅' if results['telegram']['ok'] else '❌'} {results['telegram']['message']}")
    
    print("\n" + "=" * 60)
    
    if results['all_ok']:
        print("✅ ALL SYSTEMS OPERATIONAL")
        
        # Send test message
        if TELEGRAM_AVAILABLE:
            print("\n📤 Sending test Telegram message...")
            msg = f"""
🧪 <b>Network Monitor Test</b>

⏰ Time: {now}

✅ Internet: OK
✅ AngelOne API: OK  
✅ Telegram: OK

<i>Network monitoring is working!</i>
"""
            if send_telegram_message(msg):
                print("✅ Test message sent successfully!")
            else:
                print("⚠️ Failed to send test message")
    else:
        print("❌ CONNECTIVITY ISSUES DETECTED")
        print("   Please check your internet connection")
    
    print("=" * 60 + "\n")
    
    return results['all_ok']


def main():
    parser = argparse.ArgumentParser(description="Network Health Monitor")
    parser.add_argument("--test", action="store_true", help="Run connectivity test")
    parser.add_argument("--run", action="store_true", help="Run continuous monitoring")
    parser.add_argument("--once", action="store_true", help="Run single check")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    
    args = parser.parse_args()
    
    if args.test:
        run_test()
    elif args.run:
        monitor = NetworkHealthMonitor(check_interval=args.interval)
        monitor.run()
    elif args.once:
        monitor = NetworkHealthMonitor()
        results = monitor.check_once()
        print(f"Network OK: {results['all_ok']}")
    else:
        # Default: run test
        run_test()


if __name__ == "__main__":
    main()
