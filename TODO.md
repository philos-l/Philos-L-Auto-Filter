# TODO

## Esecuzione automatica GitHub Actions
- Verificare se i cron schedulati partono da soli o solo manualmente
- Al momento sembra che le run automatiche non scattino (solo quelle manuali)
- Se conferma il problema: valutare alternative (cron-job.org, Cloudflare Workers, GitLab CI, VPS)

## Revisione finale docs e workflow
- Controllo di README.md, ADMIN.md e tutti i workflow `.github/workflows/`
- Verificare correttezza, completezza e coerenza tra i documenti

## Documentazione tecnica del codice
- Spiegazione funzione per funzione di `mail_monitor_multi.py`
- Flusso dati end-to-end (IMAP → parsing → archivio → Telegram)
- Note sulle scelte implementative non ovvie

## Ricontrollo completo del codice
- Review generale di `mail_monitor_multi.py` dopo tutte le modifiche incrementali
- Verificare gestione errori, edge case, pulizia codice inutilizzato

## Completati

- [x] **GitHub Actions** — workflow ogni 15 minuti, credenziali via Secrets
- [x] **Documentazione per nuovi utenti** — README con guida step-by-step, workflow add/remove utente
- [x] **Documentazione amministratore** — ADMIN.md con operazioni quotidiane, gestione Secrets, workflow modify_user
