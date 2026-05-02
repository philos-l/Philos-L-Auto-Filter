# TODO

## Documentazione per nuovi utenti
- Guida pratica step-by-step: come unirsi al bot, creare il proprio profilo `.toml`, configurare le keyword
- Istruzioni per ottenere il `telegram_chat_id` tramite API /getUpdates
- Nessuna spiegazione del codice — solo setup e utilizzo

## Documentazione tecnica del codice
- Spiegazione funzione per funzione di `mail_monitor_multi.py`
- Flusso dati end-to-end (IMAP → parsing → archivio → Telegram)
- Note sulle scelte implementative non ovvie

## Ricontrollo completo del codice
- Review generale di `mail_monitor_multi.py` dopo tutte le modifiche incrementali
- Verificare gestione errori, edge case, pulizia codice inutilizzato

## GitHub Actions
- Workflow che esegue `mail_monitor_multi.py` ogni 15 minuti
- Gestione sicura delle credenziali via GitHub Secrets (IMAP_PASS, TELEGRAM_BOT_TOKEN)
- Logging degli output nel runner
