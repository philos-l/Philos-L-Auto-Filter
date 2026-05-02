# CLAUDE.md — Mail Keyword Monitor (PHILOS-L)

## Panoramica progetto

Script Python che monitora una casella Gmail via IMAP, filtra le mail della
mailing list PHILOS-L, cerca keyword nel corpo completo, e manda notifiche
Telegram a profili configurabili via file TOML individuali.

Caso d'uso: monitorare PHILOS-L (listserv.liv.ac.uk) per annunci di dottorati,
postdoc e call for papers, con keyword differenti per utenti Telegram differenti.

---

## Struttura file

```
mail_monitor_multi.py   # script principale
profiles/
    giovanni.toml       # un file per persona — keyword + chat_id Telegram
    esempio.toml        # template da copiare per nuovi utenti
state/
    giovanni.json       # storico UID per profilo — generato automaticamente
TODO.md                 # attività future
```

---

## Funzionamento

1. Si connette a Gmail via IMAP4_SSL
2. Legge tutti gli UID nella label configurata (`IMAP_LABEL`)
3. Per ogni profilo in `profiles/` carica il proprio storico UID già visti
4. Fetcha via IMAP solo le mail non ancora viste da almeno un profilo (fetch unico)
5. **Filtra:** scarta le mail che non hanno `[PHILOS-L]` nel subject
6. Per ogni mail superstite: estrae subject, sender, date, body (text/plain, multipart-aware)
7. Pulisce il body: rimuove boilerplate CAUTION e footer Philos-L
8. Fetcha l'**indice mensile LISTSERV** e costruisce un dict `subject → link` per arricchire i match
9. Per ogni profilo: cerca le keyword (case-insensitive) in subject + body
10. Se match: manda notifica Telegram con preview 400 caratteri + mittente + data + link archivio
11. Salva lo stato per profilo in `state/<nome>.json` (max 5000 UID)

### Link all'archivio LISTSERV

L'indice mensile è fetchato da:
```
https://listserv.liv.ac.uk/cgi-bin/wa?A1=ind{YYMM}&L=PHILOS-L
```
Copre tutti i messaggi del mese corrente (~700+ per mese). Se siamo nei
primi 3 giorni del mese viene fetchato anche il mese precedente.

La correlazione avviene per subject: il titolo nell'indice è identico al
subject della mail a meno del prefisso `[PHILOS-L]`.
`normalize_subject()` rimuove il prefisso e fa confronto lowercase.
Se l'archivio non è raggiungibile o il subject non matcha, il messaggio viene
mandato comunque senza link.

---

## Configurazione

### IMAP + Telegram (in cima a mail_monitor_multi.py)

```python
IMAP_HOST  = "imap.gmail.com"
IMAP_USER  = "tua@gmail.com"
IMAP_PASS  = "xxxx xxxx xxxx xxxx"   # App Password Gmail 16 caratteri
IMAP_LABEL = "INBOX"                 # o nome label Gmail es. "PHILOS-L"

TELEGRAM_BOT_TOKEN = "..."           # token condiviso da tutti i profili
```

### Gmail — prerequisiti

- Verifica in due passaggi attiva sull'account
- App Password generata da: myaccount.google.com → Sicurezza → App Password
- Opzionale: filtro Gmail che etichetta le mail da `listserv@listserv.liv.ac.uk`
  con label `PHILOS-L`, poi impostare `IMAP_LABEL = "PHILOS-L"`

### Telegram

Un solo bot condiviso, creato con @BotFather. Il bot usato è:
**Philos-L Notification Bot** → https://t.me/philos_l_notification_bot

Ogni profilo ha il proprio `telegram_chat_id` (ID numerico della chat personale).
**Come ottenere il proprio chat_id** (passaggio obbligatorio per ogni nuovo utente):

1. Aprire https://t.me/philos_l_notification_bot e premere **Avvia** (o inviare qualsiasi messaggio)
2. Aprire nel browser questo URL (sostituire `<TOKEN>` con il token reale del bot):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. La risposta è un JSON. Cercare il campo `"chat"` → `"id"` — quel numero è il proprio chat_id
4. Incollarlo nel proprio file `.toml` come `telegram_chat_id = "123456789"`

Note: se la risposta è `{"ok":true,"result":[]}` (array vuoto), il bot non ha ricevuto
messaggi recenti — tornare su Telegram, mandare un altro messaggio al bot, e riprovare.

### profiles/<nome>.toml

```toml
# Parole chiave da cercare (case-insensitive)
keywords = [
    "phd",
    "postdoc",
    "call for papers",
    "metaphysics",
]

# ID Telegram numerico personale
telegram_chat_id = "123456789"
```

- Il nome del file (senza `.toml`) è il nome del profilo
- Per aggiungere un utente: copiare `esempio.toml`, rinominarlo, modificare keyword e chat_id
- `telegram_bot_token` è condiviso nello script, non nei profili

---

## Uso

```bash
# Esecuzione normale
python3 mail_monitor_multi.py

# Test senza mandare Telegram (IMAP attivo, credenziali necessarie)
python3 mail_monitor_multi.py --dry-run

# Azzera storico di tutti i profili (ri-processa tutte le mail)
python3 mail_monitor_multi.py --reset

# Azzera storico di un solo profilo
python3 mail_monitor_multi.py --reset --profile giovanni

# Esegui solo per un profilo
python3 mail_monitor_multi.py --profile giovanni

# Combinazioni
python3 mail_monitor_multi.py --profile giovanni --dry-run
```

---

## Deploy sulla VM (cron)

```bash
crontab -e
# ogni 15 minuti:
*/15 * * * * /usr/bin/python3 /path/to/mail_monitor_multi.py >> /var/log/mail_monitor.log 2>&1
```

---

## Dipendenze

Solo stdlib Python 3.11+ (testato su 3.13):
`imaplib`, `email`, `html`, `json`, `tomllib`, `urllib.request`, `re`, `argparse`

---

## Decisioni di progetto

| Scelta | Motivazione |
|---|---|
| IMAP invece di RSS | Il feed RSS di PHILOS-L espone solo anteprima troncata |
| Gmail + App Password | IMAP immediato, nessuna dipendenza da librerie OAuth |
| Fetch IMAP unico | Le mail vengono fetchate una sola volta per tutti i profili |
| Filtro `[PHILOS-L]` sul subject | Evita falsi positivi da mail personali o promozionali |
| Indice mensile LISTSERV | Copre tutti i messaggi del mese (~700+), vs 3 del feed RSS |
| Profili TOML separati | Ogni utente edita solo il suo file, formato leggibile con commenti |
| `telegram_bot_token` nello script | Un solo bot condiviso, più semplice da gestire |
| Stato per-profilo | Ogni profilo tiene il proprio storico UID |
| Storico max 5000 UID | Evita crescita illimitata del file JSON |
| Nessuna dipendenza esterna | Compatibilità massima, nessun pip install |
| `html.escape()` sui campi email | Evita errori 400 da Telegram per indirizzi email nel campo From |

---

## Note PHILOS-L specifiche

- Le mail contengono un prefisso boilerplate rimosso automaticamente:
  `CAUTION: This email originated outside of the University...`
- Footer rimosso: `Philos-L "The Liverpool List"...`
- Encoding frequente: `windows-1252` (gestito con `errors="replace"`)
- Iscrizione alla lista: mandare mail a `listserv@listserv.liv.ac.uk`
  con corpo `SUBSCRIBE PHILOS-L Nome Cognome`
