"""
Test Email Notification

Simulates a signal detection and attempts to send an email.
Usage: python scripts/test_email_notification.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from backend.app.services.notification import EmailService
from backend.app.config import settings

def test_email():
    print("=" * 60)
    print("📧 Testing Email Notification System")
    print("=" * 60)

    # 1. Check Configuration
    print(f"SMTP Server: {settings.SMTP_SERVER}:{settings.SMTP_PORT}")
    print(f"User: {settings.SMTP_USERNAME or '(Not Set)'}")
    
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        print("\n⚠️  CRITICAL WARNING: SMTP Credentials are missing!")
        print("Please update 'backend/app/config.py' or set environment variables:")
        print(" - SMTP_USERNAME (your email)")
        print(" - SMTP_PASSWORD (your app password)")
        print("\nContinuing anyway (EmailService will skip sending)...")

    # 2. Mock Signals (Reflecting Squeeze Strategy and AU Time)
    mock_signals = [
        {
            "symbol": "XAG_USD",
            "strategy": "Squeeze",
            "signal": "BUY",
            "score": 92.0,
            "price": 23.4520,
            "stop_loss": 23.1050,
            "take_profit": 24.1500,
            "timestamp": "2026-01-10T02:00:00Z", # Friday night / Sat morning UTC
            "timeframe": "1h"
        },
        {
            "symbol": "AUD_USD",
            "strategy": "Squeeze",
            "signal": "SELL",
            "score": 85.5,
            "price": 0.6710,
            "stop_loss": 0.6750,
            "take_profit": 0.6650,
            "timestamp": "2026-01-10T01:15:00Z",
            "timeframe": "15m"
        }
    ]

    # 3. Target Recipient
    recipient = "naveenf@gmail.com"
    print(f"\nAttempting to send {len(mock_signals)} signals to: {recipient}")

    # 4. Send
    try:
        EmailService.send_signal_alert([recipient], mock_signals)
        print("\n✅ Email send routine completed (check logs/inbox).")
    except Exception as e:
        print(f"\n❌ Error sending email: {e}")

    # 5. Test State Saving (Diff Logic)
    print("\nTesting Diff Logic...")
    EmailService.save_last_sent_signals(mock_signals)
    print("Saved mock signals to state.")
    
    # Try filtering the SAME signals
    diff = EmailService.filter_new_signals(mock_signals)
    new_entries = diff['entries']
    print(f"Re-filtering same signals (Expected 0 entries): Found {len(new_entries)}")
    
    # Try adding a NEW signal
    new_batch = mock_signals + [{
        "symbol": "EUR_USD",
        "strategy": "TrendFollowing",
        "signal": "BUY",
        "score": 75.0, 
        "price": 1.0850,
        "stop_loss": 1.0800,
        "take_profit": 1.1000,
        "timestamp": "2026-01-11T15:00:00Z"
    }]
    
    # 6. Test Exit Logic
    print("\nTesting Exit Logic...")
    # Simulate XAG_USD dropping out (Exiting)
    current_signals = [new_batch[1], new_batch[2]] # AUD_USD (SELL) and EUR_USD (BUY). XAG_USD is gone.
    all_prices = {
        "XAG_USD": 24.5000, # This would be a PROFIT (Entry 23.4520)
        "AUD_USD": 0.6710,
        "EUR_USD": 1.0850
    }
    
    diff_exit = EmailService.filter_new_signals(current_signals, all_prices)
    exits = diff_exit['exits']
    print(f"Detected {len(exits)} exits (Expected 1: XAG_USD).")
    
    if len(exits) > 0:
        print(f"Exit Result for {exits[0]['symbol']}: {exits[0].get('result')} | PnL: {exits[0].get('pnl'):.4f} | R:R: {exits[0].get('rr_achieved'):.2f}R")
        print(f"Exit Reason: {exits[0].get('exit_reason')}")
        
        # Test sending exit email
        print(f"Sending exit alert to: {recipient}")
        EmailService.send_exit_alert([recipient], exits)
        print("✅ Exit Email send routine completed.")
    
    if len(diff_exit['entries']) == 1 and diff_exit['entries'][0]['symbol'] == "EUR_USD":
        print("✅ New Entry Detection working correctly.")
    else:
        print("❌ New Entry Detection Failed.")

if __name__ == "__main__":
    test_email()
