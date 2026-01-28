"""
Notification Service

Handles email alerts for trading signals.
"""

import smtplib
import json
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import settings

logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending email notifications."""
    
    _last_sent_file = settings.PROCESSED_DATA_DIR / "last_sent_signals.json"

    @classmethod
    def filter_new_signals(cls, current_signals: List[Dict], all_prices: Dict[str, float] = None) -> Dict[str, List[Dict]]:
        """
        Return a dict with 'entries' and 'exits'.
        - entries: signals that are brand new.
        - exits: active signals that have now met an exit condition.
        """
        last_sent = cls.load_last_sent_signals() # Symbol -> Full signal dict
        new_entries = []
        exits = []
        all_prices = all_prices or {}
        
        current_symbols = {s['symbol'] for s in current_signals}
        
        # 1. Check for EXITS and REVERSALS
        for symbol, last_sig in last_sent.items():
            # If the symbol is still in current signals, check for reversal
            if symbol in current_symbols:
                current_sig = next(s for s in current_signals if s['symbol'] == symbol)
                if current_sig['signal'] != last_sig['signal']:
                    # Reversal!
                    last_sig['exit_reason'] = f"REVERSAL ({current_sig['signal']})"
                    cls._enrich_exit_data(last_sig, current_sig['price'])
                    exits.append(last_sig)
            else:
                # Symbol dropped out of signals - might have hit SL/TP or just lost momentum
                exit_price = all_prices.get(symbol, last_sig.get('price')) # Fallback to entry if price not found
                last_sig['exit_reason'] = "SIGNAL EXPIRED / MOMENTUM LOST"
                cls._enrich_exit_data(last_sig, exit_price)
                exits.append(last_sig)

        # 2. Check for NEW ENTRIES
        for signal in current_signals:
            symbol = signal.get('symbol')
            if symbol not in last_sent:
                new_entries.append(signal)
            elif last_sent[symbol]['signal'] != signal['signal']:
                # This is a reversal entry, already handled in exit logic above for the old side
                new_entries.append(signal)
        
        return {"entries": new_entries, "exits": exits}

    @classmethod
    def _enrich_exit_data(cls, signal: Dict, exit_price: float):
        """Calculate PnL, Result and R:R for an exit."""
        # Defensive numeric checks
        try:
            entry_price = float(signal.get('price', 0.0))
            exit_price = float(exit_price) if exit_price is not None else entry_price
        except (TypeError, ValueError):
            entry_price = 0.0
            exit_price = 0.0

        direction = signal.get('signal', 'BUY')
        sl = signal.get('stop_loss')
        tp = signal.get('take_profit')
        
        pnl = 0.0
        if direction == "BUY":
            pnl = exit_price - entry_price
        else:
            pnl = entry_price - exit_price
            
        signal['exit_price'] = exit_price
        signal['pnl'] = pnl
        signal['result'] = "PROFIT" if pnl > 0 else "LOSS"
        
        # Calculate R:R achieved
        try:
            risk = abs(entry_price - float(sl)) if sl is not None and entry_price != float(sl) else None
            if risk and risk > 0:
                signal['rr_achieved'] = pnl / risk
            else:
                signal['rr_achieved'] = 0.0
        except (TypeError, ValueError):
            signal['rr_achieved'] = 0.0
            
        # Refine reason if it actually hit TP or SL
        try:
            if tp is not None:
                tp_val = float(tp)
                if (direction == "BUY" and exit_price >= tp_val) or (direction == "SELL" and exit_price <= tp_val):
                    signal['exit_reason'] = "TAKE PROFIT HIT 🎯"
            if sl is not None:
                sl_val = float(sl)
                if (direction == "BUY" and exit_price <= sl_val) or (direction == "SELL" and exit_price >= sl_val):
                    signal['exit_reason'] = "STOP LOSS HIT 🛑"
        except (TypeError, ValueError):
            pass

    @classmethod
    def save_last_sent_signals(cls, signals: List[Dict]):
        """Save the current active signals to file."""
        # Map symbol -> Full signal dict
        signal_map = {s['symbol']: s for s in signals}
        try:
            with open(cls._last_sent_file, 'w') as f:
                json.dump(signal_map, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save last sent signals: {e}")

    @classmethod
    def load_last_sent_signals(cls) -> Dict[str, Dict]:
        """Load the active signals."""
        if cls._last_sent_file.exists():
            try:
                with open(cls._last_sent_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load last sent signals: {e}")
        return {}

    @classmethod
    def send_exit_alert(cls, recipients: List[str], exits: List[Dict]):
        """Send an email for closed positions."""
        if not exits or not recipients: return
        
        subject = f"🏁 {len(exits)} Trade Signal{'s' if len(exits) > 1 else ''} Closed"
        
        html_body = f"""
        <html>
        <head>
            <style>
                table {{ border-collapse: collapse; width: 100%; font-family: sans-serif; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f8f9fa; color: #333; }}
                .profit {{ color: #28a745; font-weight: bold; }}
                .loss {{ color: #dc3545; font-weight: bold; }}
                .neutral {{ color: #6c757d; }}
            </style>
        </head>
        <body>
            <h2>Trade Exit Notifications</h2>
            <p>The following positions have been closed:</p>
            <table>
                <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>Result</th>
                    <th>R:R</th>
                    <th>Reason</th>
                    <th>Time</th>
                </tr>
        """
        for e in exits:
            res_class = e.get('result', 'LOSS').lower()
            rr = e.get('rr_achieved', 0.0)
            
            html_body += f"""
                <tr>
                    <td><b>{e['symbol']}</b></td>
                    <td>{e['signal']}</td>
                    <td>{e['price']:.4f}</td>
                    <td>{e.get('exit_price', 0.0):.4f}</td>
                    <td class="{res_class}">{e.get('result', 'LOSS')}</td>
                    <td class="{res_class}">{rr:.2f}R</td>
                    <td>{e.get('exit_reason', 'Unknown')}</td>
                    <td>{datetime.now().strftime("%H:%M %d/%m")}</td>
                </tr>
            """
        html_body += """
            </table>
            <p><a href="http://localhost:5173">View Portfolio Dashboard</a></p>
        </body>
        </html>
        """
        
        cls._send_email(recipients, subject, html_body)

    @classmethod
    def _send_email(cls, recipients: List[str], subject: str, html_body: str):
        if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD: return

        try:
            server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
            server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            
            for email in recipients:
                # Create a fresh message for each recipient to avoid multiple 'To' headers
                msg = MIMEMultipart()
                msg['From'] = settings.EMAIL_FROM
                msg['To'] = email
                msg['Subject'] = subject
                msg.attach(MIMEText(html_body, 'html'))
                
                server.sendmail(settings.EMAIL_FROM, email, msg.as_string())
            
            server.quit()
        except Exception as e:
            logger.error(f"Email error: {e}")

    @classmethod
    def send_signal_alert(cls, recipients: List[str], signals: List[Dict]):
        """
        Send an email with the signal list to the recipients.
        """
        if not signals or not recipients:
            return

        if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
            logger.warning("SMTP credentials not set. Skipping email.")
            return

        subject = f"🚀 {len(signals)} New Trading Signal{'s' if len(signals) > 1 else ''} Detected"
        
        # Build HTML Body
        html_body = f"""
        <html>
        <head>
            <style>
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f2f2f2; }}
                .bull {{ color: green; font-weight: bold; }}
                .bear {{ color: red; font-weight: bold; }}
            </style>
        </head>
        <body>
            <h2>New Trading Signals</h2>
            <p>The following opportunities were just detected:</p>
            <table>
                <tr>
                    <th>Time</th>
                    <th>Symbol</th>
                    <th>Strategy</th>
                    <th>Signal</th>
                    <th>Score</th>
                    <th>Entry</th>
                    <th>SL</th>
                    <th>TP</th>
                </tr>
        """
        
        for s in signals:
            direction_class = "bull" if "BUY" in s.get('signal', '').upper() else "bear"
            
            # Handle key variations
            price = s.get('current_price') or s.get('price', 0.0)
            sl = s.get('stop_loss')
            tp = s.get('take_profit')
            
            # Format numbers
            price_str = f"{price:.4f}" if isinstance(price, float) else str(price)
            sl_str = f"{sl:.4f}" if isinstance(sl, float) else "N/A"
            tp_str = f"{tp:.4f}" if isinstance(tp, float) else "Open"
            
            # Format timestamp (ISO string to readable AU Time)
            ts_str = s.get('timestamp', '')
            try:
                if ts_str:
                    dt_utc = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                    dt_au = dt_utc.astimezone(ZoneInfo("Australia/Sydney"))
                    ts_display = dt_au.strftime("%H:%M %d/%m")
                else:
                    ts_display = "-"
            except Exception:
                ts_display = str(ts_str)

            html_body += f"""
                <tr>
                    <td>{ts_display}</td>
                    <td><b>{s.get('symbol')}</b></td>
                    <td>{s.get('strategy')}</td>
                    <td class="{direction_class}">{s.get('signal')}</td>
                    <td>{s.get('score', 0):.1f}</td>
                    <td>{price_str}</td>
                    <td>{sl_str}</td>
                    <td>{tp_str}</td>
                </tr>
            """
            
        html_body += """
            </table>
            <p><small>Generated by ASX/Forex Screener at %s</small></p>
            <p><a href="http://localhost:5173">View Dashboard</a></p>
        </body>
        </html>
        """ % datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cls._send_email(recipients, subject, html_body)

