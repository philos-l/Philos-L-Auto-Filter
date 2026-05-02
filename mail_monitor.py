#!/usr/bin/env python3
"""
Mail Keyword Monitor
Si connette a una casella Gmail via IMAP, legge le mail nuove in una label,
cerca keyword nel soggetto e nel corpo, manda notifiche Telegram.

Uso:
    python3 mail_monitor.py                  # esecuzione normale
    python3 mail_monitor.py --dry-run        # stampa i match senza mandare Telegram
    python3 mail_monitor.py --reset          # azzera lo storico UID già visti
"""

import argparse
import email
import email.header
import imaplib
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from email import policy

# ---------------------------------------------------------------------------
# CONFIGURAZIONE — modifica questi valori
# ---------------------------------------------------------------------------

IMAP_HOST  = "imap.gmail.com"
IMAP_USER  = "giogavbackup@gmail.com"
IMAP_PASS  = "dlsz srsw rifz gbnt"   # App Password Gmail (16 caratteri)

# Label IMAP da monitorare.
# "INBOX" per testare con mail dirette.
# Se crei un filtro Gmail che etichetta le mail PHILOS-L, metti il nome
# della label qui, es. "PHILOS-L" (Gmail usa "/" per le sublabel).
IMAP_LABEL = "INBOX"

KEYWORDS = [
    "metaphysics",
]
# Case-insensitive. Modifica liberamente.

TELEGRAM_BOT_TOKEN = "IL_TUO_BOT_TOKEN"   # es. "123456789:ABCdef..."
TELEGRAM_CHAT_ID   = "IL_TUO_CHAT_ID"     # es. "987654321"

# File dove vengono salvati gli UID già notificati
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mail_monitor_state.json")

# ---------------------------------------------------------------------------

CAUTION_RE = re.compile(
    r"CAUTION:\s*This email originated.*?safe\.",
    re.IGNORECASE | re.DOTALL,
)
FOOTER_RE = re.compile(
    r'Philos-L\s+"The Liverpool List".*',
    re.IGNORECASE | re.DOTALL,
)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"seen_uids": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def decode_header_str(value):
    """Decodifica un header email (gestisce encoded-words RFC 2047)."""
    parts = email.header.decode_header(value or "")
    out = []
    for part, charset in parts:
        if isinstance(part, bytes):
            out.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out).strip()


def get_body(msg):
    """Estrae il testo plain dal messaggio email."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = part.get("Content-Disposition", "")
            if ct == "text/plain" and "attachment" not in cd:
                charset = part.get_content_charset() or "utf-8"
                try:
                    body += part.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    pass
    else:
        charset = msg.get_content_charset() or "utf-8"
        try:
            body = msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            pass
    return body


def clean_body(text):
    """Rimuove boilerplate CAUTION, footer Philos-L, normalizza spazi."""
    text = CAUTION_RE.sub("", text)
    text = FOOTER_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def matches(subject, body, keywords):
    """Ritorna la lista di keyword trovate nel soggetto + corpo."""
    text = (subject + " " + body).lower()
    return [kw for kw in keywords if kw.lower() in text]


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def format_message(subject, sender, date_str, body, matched_kw):
    kw_list  = ", ".join(f"<code>{k}</code>" for k in matched_kw)
    preview  = body[:400] + "…" if len(body) > 400 else body
    date_str = f"\n📅 {date_str}" if date_str else ""
    return (
        f"🔔 <b>PHILOS-L Monitor</b>\n"
        f"🔑 Keyword: {kw_list}{date_str}\n"
        f"👤 {sender}\n\n"
        f"<b>{subject}</b>\n\n"
        f"{preview}"
    )


def main():
    parser = argparse.ArgumentParser(description="Mail Keyword Monitor")
    parser.add_argument("--dry-run", action="store_true",
                        help="Stampa i match senza mandare Telegram")
    parser.add_argument("--reset", action="store_true",
                        help="Azzera lo storico degli UID già visti")
    args = parser.parse_args()

    if args.reset:
        save_state({"seen_uids": []})
        print("Storico azzerato.")
        return

    state     = load_state()
    seen_uids = set(state.get("seen_uids", []))

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Connessione a {IMAP_HOST}…")

    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST)
        imap.login(IMAP_USER, IMAP_PASS)
    except imaplib.IMAP4.error as e:
        print(f"ERRORE login IMAP: {e}", file=sys.stderr)
        sys.exit(1)

    status, _ = imap.select(f'"{IMAP_LABEL}"', readonly=True)
    if status != "OK":
        print(f"ERRORE: label '{IMAP_LABEL}' non trovata.", file=sys.stderr)
        imap.logout()
        sys.exit(1)

    # Cerca tutte le mail nella label (UID)
    status, data = imap.uid("search", None, "ALL")
    if status != "OK":
        print("ERRORE search IMAP.", file=sys.stderr)
        imap.logout()
        sys.exit(1)

    all_uids = data[0].split()
    print(f"Mail nella label: {len(all_uids)}")

    notified = 0
    for uid_bytes in all_uids:
        uid = uid_bytes.decode()
        if uid in seen_uids:
            continue

        # Fetch headers + body
        status, msg_data = imap.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not msg_data or msg_data[0] is None:
            seen_uids.add(uid)
            continue

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw, policy=policy.compat32)

        subject = decode_header_str(msg.get("Subject", ""))
        sender  = decode_header_str(msg.get("From", ""))
        date    = decode_header_str(msg.get("Date", ""))
        body    = clean_body(get_body(msg))

        matched_kw = matches(subject, body, KEYWORDS)
        if not matched_kw:
            seen_uids.add(uid)
            continue

        print(f"  MATCH [{', '.join(matched_kw)}]: {subject}")

        if not args.dry_run:
            if TELEGRAM_BOT_TOKEN == "IL_TUO_BOT_TOKEN":
                print("  ⚠ Token Telegram non configurato — usa --dry-run oppure imposta il token.")
            else:
                try:
                    send_telegram(
                        TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                        format_message(subject, sender, date, body, matched_kw),
                    )
                    print("  → Notifica inviata.")
                except Exception as e:
                    print(f"  ERRORE Telegram: {e}", file=sys.stderr)
        else:
            print(f"  [dry-run] Messaggio:\n")
            print(format_message(subject, sender, date, body, matched_kw))
            print()

        seen_uids.add(uid)
        notified += 1

    imap.logout()

    # Tieni solo gli ultimi 5000 UID per non far crescere il file
    state["seen_uids"] = list(seen_uids)[-5000:]
    save_state(state)

    print(f"Nuovi match notificati: {notified}")


if __name__ == "__main__":
    main()
