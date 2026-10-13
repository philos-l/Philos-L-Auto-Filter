#!/usr/bin/env python3
"""
Mail Keyword Monitor — multi-profilo
Si connette a una casella Gmail via IMAP, legge le mail nuove,
e per ogni profilo definito in profiles/*.toml cerca le keyword
nel soggetto e nel corpo, mandando notifiche Telegram separate.

Uso:
    python3 mail_monitor_multi.py                        # esecuzione normale
    python3 mail_monitor_multi.py --dry-run              # stampa i match senza mandare Telegram né salvare lo stato
    python3 mail_monitor_multi.py --check                # controlla la sintassi delle keyword ed esce
    python3 mail_monitor_multi.py --reset                # azzera tutti gli storici
    python3 mail_monitor_multi.py --reset --profile foo  # azzera solo il profilo "foo"

Test:
    python3 -m unittest -v
"""

import argparse
import email
import email.header
import functools
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

IMAP_HOST  = os.environ.get("IMAP_HOST", "")
IMAP_USER  = os.environ.get("IMAP_USER", "")
IMAP_PASS  = os.environ.get("IMAP_PASS", "")

# Label IMAP da monitorare
IMAP_LABEL = "INBOX"

# Base URL archivio LISTSERV — usata per l'indice mensile dei messaggi
LISTSERV_BASE = "https://listserv.liv.ac.uk/cgi-bin/wa"

# Bot Telegram condiviso da tutti i profili
# Crealo con @BotFather su Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

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
# Operatori delle espressioni di keyword: valgono solo in maiuscolo
OPERATOR_RE       = re.compile(r"(\(|\)|\bAND\b|\bOR\b|\bNOT\b)")


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
    """
    Ritorna l'ultimo UID già controllato per il profilo. Gli UID IMAP sono
    crescenti, quindi tutte le mail con UID minore o uguale sono già gestite.
    Ritorna None se il profilo non ha ancora uno stato, cioè è nuovo.
    """
    path = state_file(profile_name)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        state = json.load(f)
    if "last_uid" in state:
        return int(state["last_uid"])
    # Vecchio formato: lista di tutti gli UID visti
    return max((int(u) for u in state.get("seen_uids", [])), default=0)


def save_state(profile_name, last_uid):
    with open(state_file(profile_name), "w") as f:
        json.dump({"last_uid": last_uid}, f, indent=2)


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


@functools.lru_cache(maxsize=None)
def keyword_regex(keyword):
    """
    Regex che trova la keyword solo all'inizio di una parola, senza
    distinguere maiuscole e minuscole: "logic" trova "logical" e "position"
    trova "positions", ma "logic" non scatta su "phenomenological".
    """
    words = r"\s+".join(re.escape(w) for w in keyword.split())
    return re.compile(rf"(?<!\w){words}", re.IGNORECASE)


@functools.lru_cache(maxsize=None)
def parse_keyword(entry):
    """
    Trasforma una voce di `keywords` in un albero. Una voce è una parola o
    frase semplice, oppure un'espressione con AND, OR, NOT (solo in maiuscolo)
    e parentesi: tutto ciò che sta tra due operatori è una frase. Esempio:
        (phd OR doctoral position) AND (metaphysics OR logic) AND NOT conference
    Nodi: ("kw", frase), ("not", nodo), ("and", [nodi]), ("or", [nodi]).
    Solleva ValueError se l'espressione è malformata.
    """
    tokens = [t.strip() for t in OPERATOR_RE.split(entry)]
    tokens = [t for t in tokens if t]
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def parse_chain(operator, parse_operand):
        nonlocal pos
        nodes = [parse_operand()]
        while peek() == operator:
            pos += 1
            nodes.append(parse_operand())
        return nodes[0] if len(nodes) == 1 else (operator.lower(), nodes)

    def parse_or():
        return parse_chain("OR", parse_and)

    def parse_and():
        return parse_chain("AND", parse_not)

    def parse_not():
        nonlocal pos
        tok = peek()
        if tok is None:
            raise ValueError("manca una keyword alla fine")
        if tok in (")", "AND", "OR"):
            raise ValueError(f"manca una keyword prima di '{tok}'")
        pos += 1
        if tok == "NOT":
            return ("not", parse_not())
        if tok == "(":
            node = parse_or()
            if peek() != ")":
                raise ValueError("parentesi non chiusa")
            pos += 1
            return node
        return ("kw", tok)

    if not tokens:
        raise ValueError("keyword vuota")
    tree = parse_or()
    if peek() == ")":
        raise ValueError("parentesi chiusa senza la corrispondente aperta")
    if peek() is not None:
        raise ValueError(f"manca AND oppure OR prima di '{peek()}'")
    return tree


def evaluate(node, text):
    """Valuta l'albero sul testo. Ritorna (esito, keyword trovate)."""
    kind = node[0]
    if kind == "kw":
        hit = keyword_regex(node[1]).search(text) is not None
        return hit, [node[1]] if hit else []
    if kind == "not":
        hit, _ = evaluate(node[1], text)
        return not hit, []
    results = [evaluate(child, text) for child in node[1]]
    hits    = [hit for hit, _ in results]
    ok      = all(hits) if kind == "and" else any(hits)
    return ok, [kw for _, found in results for kw in found] if ok else []


def check_keywords(profile):
    """Ritorna la lista degli errori di sintassi nelle keyword del profilo."""
    problems = []
    for entry in profile.get("keywords", []):
        if not isinstance(entry, str):
            problems.append(f"keyword {entry!r}: deve essere un testo tra virgolette")
            continue
        try:
            parse_keyword(entry)
        except ValueError as e:
            problems.append(f"keyword '{entry}': {e}")
    return problems


def matches(subject, body, keywords):
    """
    Ritorna le keyword trovate nella mail; lista vuota se nessuna voce di
    `keywords` è soddisfatta. Le voci sono in OR tra loro.
    """
    text  = subject + " " + body
    found = []
    for entry in keywords:
        ok, kws = evaluate(parse_keyword(entry), text)
        if ok:
            # Un'espressione fatta solo di NOT non ha keyword trovate da mostrare
            found.extend(kws or [entry])
    return list(dict.fromkeys(found))


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
    kw_list  = ", ".join(f"<code>{html.escape(k)}</code>" for k in matched_kw)
    date_str = f"\n📅 {html.escape(date_str)}" if date_str else ""
    link_str = f"\n🔗 <a href=\"{archive_link}\">Leggi l'annuncio</a>" if archive_link else ""
    return (
        f"🔔 <b>PHILOS-L Monitor</b>\n"
        f"🔑 Keyword: {kw_list}{date_str}{link_str}\n"
        f"👤 {html.escape(sender)}\n\n"
        f"<b>{html.escape(subject)}</b>"
    )


def format_welcome(keywords):
    kw_list = "\n".join(f"• <code>{html.escape(k)}</code>" for k in keywords)
    return (
        f"✅ <b>PHILOS-L Monitor</b>\n"
        f"Profilo attivo. Riceverai una notifica per ogni nuova mail "
        f"che corrisponde alle tue keyword:\n{kw_list}"
    )


def welcome_profile(p, dry_run=False):
    """
    Manda il messaggio di benvenuto a un profilo nuovo. Ritorna False se
    l'invio fallisce (es. Chat ID sbagliato o bot mai avviato dall'utente).
    """
    text = format_welcome(p.get("keywords", []))
    if dry_run:
        print(f"  [dry-run] Messaggio:\n\n{text}\n")
        return True
    try:
        send_telegram(TELEGRAM_BOT_TOKEN, p.get("telegram_chat_id", ""), text)
        print("  Benvenuto inviato.")
        return True
    except Exception as e:
        print(f"  ERRORE Telegram: {e}", file=sys.stderr)
        return False


def process_profile(p, all_uids, parsed, last_uid, dry_run=False):
    """
    Cerca le keyword del profilo nelle mail con UID maggiore di `last_uid`
    (in ordine crescente) e manda le notifiche.
    Ritorna (notificate, fallito, nuovo last_uid). Se un invio fallisce il
    profilo si ferma lì: `last_uid` resta alla mail precedente, così il
    prossimo run riparte da quella non notificata.
    """
    keywords = p.get("keywords", [])
    tg_chat  = p.get("telegram_chat_id", "")
    notified = 0
    failed   = False

    for uid in all_uids:
        if uid <= last_uid:
            continue

        m = parsed.get(uid)
        matched_kw = matches(m["subject"], m["body"], keywords) if m else []
        if not matched_kw:
            last_uid = uid
            continue

        print(f"  MATCH [{', '.join(matched_kw)}]: {m['subject']}")

        if not dry_run:
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
                failed = True
                break
        else:
            print(f"  [dry-run] Messaggio:\n")
            print(format_message(m["subject"], m["sender"],
                                 m["date"], m["body"], matched_kw,
                                 m.get("archive_link", "")))
            print()

        last_uid = uid
        notified += 1

    return notified, failed, last_uid


def main():
    parser = argparse.ArgumentParser(description="Mail Keyword Monitor multi-profilo")
    parser.add_argument("--dry-run", action="store_true",
                        help="Stampa i match senza mandare Telegram")
    parser.add_argument("--reset", action="store_true",
                        help="Azzera lo storico (tutti i profili o solo --profile)")
    parser.add_argument("--check", action="store_true",
                        help="Controlla la sintassi delle keyword ed esce")
    parser.add_argument("--profile", metavar="NAME", type=str.strip,
                        help="Limita l'esecuzione (o il reset) a un singolo profilo")
    args = parser.parse_args()
    if args.profile is not None and not args.profile:
        parser.error("--profile non può essere vuoto")

    profiles = load_profiles()

    if args.profile:
        profiles = [p for p in profiles if p["name"] == args.profile]
        if not profiles:
            print(f"ERRORE: profilo '{args.profile}' non trovato.", file=sys.stderr)
            sys.exit(1)

    if args.reset:
        for p in profiles:
            save_state(p["name"], 0)
            print(f"Storico azzerato: {p['name']}")
        return

    # Un profilo con keyword non valide viene saltato: gli altri proseguono
    errors = 0
    valid  = []
    for p in profiles:
        problems = check_keywords(p)
        for problem in problems:
            print(f"ERRORE profilo '{p['name']}': {problem}", file=sys.stderr)
        if problems:
            errors += 1
        else:
            valid.append(p)
    profiles = valid

    if args.check:
        print(f"Profili con keyword valide: {len(profiles)}, con errori: {errors}")
        sys.exit(1 if errors else 0)
    if not profiles:
        sys.exit(1)

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

    all_uids = sorted(int(u) for u in data[0].split())
    print(f"Mail nella label: {len(all_uids)}")

    # Carica gli stati di tutti i profili. Un profilo senza stato è nuovo e
    # parte dall'ultima mail in casella, senza notifiche per quelle vecchie
    newest       = all_uids[-1] if all_uids else 0
    last_uids    = {}
    new_profiles = set()
    for p in profiles:
        last_uid = load_state(p["name"])
        if last_uid is None:
            new_profiles.add(p["name"])
            last_uid = newest
        last_uids[p["name"]] = last_uid

    # Determina quali UID fetchare (almeno un profilo non li ha ancora visti)
    oldest = min(last_uids.values())
    uids_to_fetch = [uid for uid in all_uids if uid > oldest]

    print(f"Mail nuove da processare: {len(uids_to_fetch)}")

    # Fetch e parsing — una volta sola per tutte le mail
    parsed = {}
    for uid in uids_to_fetch:
        status, msg_data = imap.uid("fetch", str(uid), "(RFC822)")
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
        if p["name"] in new_profiles:
            print("  Profilo nuovo: riceverà solo le mail in arrivo da ora in poi.")
            if not welcome_profile(p, args.dry_run):
                # Senza stato salvato resta "nuovo" e il benvenuto viene ritentato
                errors += 1
                continue

        notified, failed, last_uid = process_profile(
            p, all_uids, parsed, last_uids[p["name"]], args.dry_run)

        if not args.dry_run:
            save_state(p["name"], last_uid)
        print(f"  Notificati: {notified}")
        if failed:
            errors += 1
            print("  Invio fallito: il profilo riprende da quella mail al prossimo run.")

    # Esce con errore così il run risulta fallito e l'amministratore se ne accorge
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()