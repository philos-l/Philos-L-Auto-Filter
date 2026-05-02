#!/usr/bin/env python3
"""
Mail Keyword Monitor — multi-profilo
Si connette a una casella Gmail via IMAP, legge le mail nuove,
e per ogni profilo definito in profiles.json cerca le keyword
nel soggetto e nel corpo, mandando notifiche Telegram separate.

Uso:
    python3 mail_monitor.py                        # esecuzione normale
    python3 mail_monitor.py --dry-run              # stampa i match senza mandare Telegram
    python3 mail_monitor.py --reset                # azzera tutti gli storici
    python3 mail_monitor.py --reset --profile foo  # azzera solo il profilo "foo"
"""

import argparse
import email
import email.header
import html
import imaplib
import json
import os
import re
import sys
import tomllib
import urllib.request
from datetime import datetime
from email import policy

# ---------------------------------------------------------------------------
# CONFIGURAZIONE IMAP — unica per tutti i profili
# ---------------------------------------------------------------------------

IMAP_HOST  = "imap.gmail.com"
IMAP_USER  = "philos.l.list@gmail.com"
IMAP_PASS  = os.environ.get("IMAP_PASS", "citb ekjo lnik kwqt ")   # App Password Gmail

# Label IMAP da monitorare
IMAP_LABEL = "INBOX"

# Base URL archivio LISTSERV — usata per l'indice mensile dei messaggi
LISTSERV_BASE = "https://listserv.liv.ac.uk/cgi-bin/wa"

# Bot Telegram condiviso da tutti i profili
# Crealo con @BotFather su Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8712823263:AAEG8sjPEeqvshplpJR04-EiqjQJnSAMmzM")

# ---------------------------------------------------------------------------
# PATH FILE
# ---------------------------------------------------------------------------

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR  = os.path.join(BASE_DIR, "profiles")
STATE_DIR     = os.path.join(BASE_DIR, "state")

# ---------------------------------------------------------------------------

CAUTION_RE = re.compile(
    r"CAUTION:\s*This email originated.*?safe\.",
    re.IGNORECASE | re.DOTALL,
)
FOOTER_RE = re.compile(
    r'Philos-L\s+"The Liverpool List".*',
    re.IGNORECASE | re.DOTALL,
)


SUBJECT_PREFIX_RE = re.compile(r"^\[PHILOS-L\]\s*", re.IGNORECASE)
ARCHIVE_LINK_RE   = re.compile(
    r'href="(https://listserv\.liv\.ac\.uk/cgi-bin/wa\?A2=\d+&amp;L=PHILOS-L&amp;P=\d+)"'
    r'[^>]*>\s*([^<]+?)\s*</a>',
    re.IGNORECASE,
)


def normalize_subject(subject):
    """Rimuove prefissi tipo [PHILOS-L] e normalizza spazi per il confronto."""
    return SUBJECT_PREFIX_RE.sub("", subject).strip().lower()


def fetch_archive_links():
    """
    Fetcha l'indice mensile LISTSERV e ritorna dict normalized_subject -> link.
    Copre tutti i messaggi del mese corrente (e del precedente se siamo
    nei primi 3 giorni del mese, per email a cavallo di mese).
    """
    from datetime import datetime, timedelta
    links = {}
    dates = [datetime.now()]
    if datetime.now().day <= 3:
        dates.append(datetime.now() - timedelta(days=3))
    for dt in dates:
        yymm = dt.strftime("%y%m")
        url = f"{LISTSERV_BASE}?A1=ind{yymm}&L=PHILOS-L"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            for href, title in ARCHIVE_LINK_RE.findall(html):
                key = normalize_subject(title.strip().strip("'\""))
                if key:
                    links[key] = href.replace("&amp;", "&")
        except Exception as e:
            print(f"WARN archivio {yymm} non disponibile: {e}", file=sys.stderr)
    print(f"Archivio LISTSERV: {len(links)} messaggi caricati.")
    return links


def load_profiles():
    if not os.path.exists(PROFILES_DIR):
        print(f"ERRORE: directory '{PROFILES_DIR}' non trovata.", file=sys.stderr)
        sys.exit(1)
    profiles = []
    for fname in sorted(os.listdir(PROFILES_DIR)):
        if not fname.endswith(".toml"):
            continue
        with open(os.path.join(PROFILES_DIR, fname), "rb") as f:
            p = tomllib.load(f)
        p["name"] = fname.removesuffix(".toml")
        profiles.append(p)
    if not profiles:
        print(f"ERRORE: nessun profilo in '{PROFILES_DIR}'.", file=sys.stderr)
        sys.exit(1)
    return profiles


def state_file(profile_name):
    os.makedirs(STATE_DIR, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", profile_name)
    return os.path.join(STATE_DIR, f"{safe}.json")


def load_state(profile_name):
    path = state_file(profile_name)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {"seen_uids": []}


def save_state(profile_name, state):
    with open(state_file(profile_name), "w") as f:
        json.dump(state, f, indent=2)


def decode_header_str(value):
    parts = email.header.decode_header(value or "")
    out = []
    for part, charset in parts:
        if isinstance(part, bytes):
            out.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out).strip()


def get_body(msg):
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
    text = CAUTION_RE.sub("", text)
    text = FOOTER_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def matches(subject, body, keywords):
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
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise Exception(f"{e.code} {e.reason}: {e.read().decode()}") from e


def format_message(subject, sender, date_str, body, matched_kw, archive_link=""):
    kw_list  = ", ".join(f"<code>{k}</code>" for k in matched_kw)
    preview  = html.escape(body[:400] + "…" if len(body) > 400 else body)
    date_str = f"\n📅 {html.escape(date_str)}" if date_str else ""
    link_str = f"\n🔗 <a href=\"{archive_link}\">Leggi l'annuncio</a>" if archive_link else ""
    return (
        f"🔔 <b>PHILOS-L Monitor</b>\n"
        f"🔑 Keyword: {kw_list}{date_str}{link_str}\n"
        f"👤 {html.escape(sender)}\n\n"
        f"<b>{html.escape(subject)}</b>\n\n"
        f"{preview}"
    )


def main():
    parser = argparse.ArgumentParser(description="Mail Keyword Monitor multi-profilo")
    parser.add_argument("--dry-run", action="store_true",
                        help="Stampa i match senza mandare Telegram")
    parser.add_argument("--reset", action="store_true",
                        help="Azzera lo storico (tutti i profili o solo --profile)")
    parser.add_argument("--profile", metavar="NAME",
                        help="Limita l'esecuzione (o il reset) a un singolo profilo")
    args = parser.parse_args()

    profiles = load_profiles()

    if args.profile:
        profiles = [p for p in profiles if p["name"] == args.profile]
        if not profiles:
            print(f"ERRORE: profilo '{args.profile}' non trovato.", file=sys.stderr)
            sys.exit(1)

    if args.reset:
        for p in profiles:
            save_state(p["name"], {"seen_uids": []})
            print(f"Storico azzerato: {p['name']}")
        return

    # --- Connessione IMAP ---
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Connessione a {IMAP_HOST}...")
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

    status, data = imap.uid("search", None, "ALL")
    if status != "OK":
        print("ERRORE search IMAP.", file=sys.stderr)
        imap.logout()
        sys.exit(1)

    all_uids = data[0].split()
    print(f"Mail nella label: {len(all_uids)}")

    # Carica gli stati di tutti i profili
    all_seen = {}
    for p in profiles:
        st = load_state(p["name"])
        all_seen[p["name"]] = set(st.get("seen_uids", []))

    # Determina quali UID fetchare (almeno un profilo non li ha ancora visti)
    uids_to_fetch = set()
    for uid_bytes in all_uids:
        uid = uid_bytes.decode()
        for p in profiles:
            if uid not in all_seen[p["name"]]:
                uids_to_fetch.add(uid)
                break

    print(f"Mail nuove da processare: {len(uids_to_fetch)}")

    # Fetch e parsing — una volta sola per tutte le mail
    parsed = {}
    for uid in uids_to_fetch:
        status, msg_data = imap.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not msg_data or msg_data[0] is None:
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw, policy=policy.compat32)
        subject = decode_header_str(msg.get("Subject", ""))
        if "[PHILOS-L]" not in subject:
            continue
        parsed[uid] = {
            "subject":      subject,
            "sender":       decode_header_str(msg.get("From", "")),
            "date":         decode_header_str(msg.get("Date", "")),
            "body":         clean_body(get_body(msg)),
            "archive_link": "",   # popolato dopo con RSS
        }

    imap.logout()

    # Arricchisce i parsed item con i link dall'RSS
    archive_links = fetch_archive_links()
    for uid, m in parsed.items():
        key = normalize_subject(m["subject"])
        m["archive_link"] = archive_links.get(key, "")

    for p in profiles:
        print(f"\n── Profilo: {p['name']} ──")
        seen     = all_seen[p["name"]]
        keywords = p.get("keywords", [])
        tg_chat  = p.get("telegram_chat_id", "")
        notified = 0

        for uid_bytes in all_uids:
            uid = uid_bytes.decode()
            if uid in seen:
                continue
            if uid not in parsed:
                seen.add(uid)
                continue

            m = parsed[uid]
            matched_kw = matches(m["subject"], m["body"], keywords)
            if not matched_kw:
                seen.add(uid)
                continue

            print(f"  MATCH [{', '.join(matched_kw)}]: {m['subject']}")

            if not args.dry_run:
                if TELEGRAM_BOT_TOKEN == "IL_TUO_BOT_TOKEN":
                    print("  Telegram non configurato (imposta TELEGRAM_BOT_TOKEN).")
                else:
                    try:
                        send_telegram(
                            TELEGRAM_BOT_TOKEN, tg_chat,
                            format_message(m["subject"], m["sender"],
                                           m["date"], m["body"], matched_kw,
                                           m.get("archive_link", "")),
                        )
                        print("  Notifica inviata.")
                    except Exception as e:
                        print(f"  ERRORE Telegram: {e}", file=sys.stderr)
            else:
                print(f"  [dry-run] Messaggio:\n")
                print(format_message(m["subject"], m["sender"],
                                     m["date"], m["body"], matched_kw,
                                     m.get("archive_link", "")))
                print()

            seen.add(uid)
            notified += 1

        save_state(p["name"], {"seen_uids": list(seen)[-5000:]})
        print(f"  Notificati: {notified}")


if __name__ == "__main__":
    main()