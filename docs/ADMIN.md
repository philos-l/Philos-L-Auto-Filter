# Guida per l'amministratore

Questa guida spiega come gestire il progetto **Philos-L Notification Bot** giorno per giorno. È pensata per chi non ha competenze tecniche: ogni operazione è descritta passo per passo. Se segui le istruzioni alla lettera non puoi sbagliare.

---

## A. Cos'è e come funziona

Il bot monitora la mailing list **PHILOS-L** ogni ora circa minuti. Per ogni utente iscritto, controlla se nelle nuove mail compaiono le sue parole chiave; se sì, gli manda una notifica su Telegram.

Tutto gira automaticamente su **GitHub Actions**, un servizio gratuito di GitHub che esegue piccoli programmi a intervalli regolari senza bisogno di tenere acceso un computer. 
In pratica è come una sveglia che ogni ora controlla la posta e fa partire il bot al posto tuo. 
Anche che le operazioni di gestione (aggiungere/rimuovere utenti, ecc.) si fanno tutte dalla pagina web del repo, cliccando dei pulsanti — non serve installare niente sul tuo computer.

Il tuo compito è solo:

- aggiungere nuovi utenti quando te lo chiedono
- modificare/rimuovere utenti su richiesta
- controllare di tanto in tanto che non ci siano errori
- aggiornare le credenziali se Gmail o Telegram lo richiedono

---

## B. Operazioni quotidiane

Tutte le operazioni si fanno dalla pagina **Actions** del repo:
https://github.com/philos-l/Philos-L-Auto-Filter/actions

![Pagina Actions evidenziata in blu](/docs/images/image-1.png)
*Pagina Actions evidenziata in blu*

Il flusso è sempre lo stesso:
1. Apri il link del workflow giusto (li trovi qui sotto)
2. Clicca il pulsante **Run workflow** in alto a destra
3. Compila i campi che appaiono
4. Clicca di nuovo **Run workflow**
5. Aspetta 30-60 secondi e controlla che il pallino diventi verde ✅

![Schermata di esecuzione un workflow](/docs/images/image-2.png)
*Schermata di esecuzione un workflow*

![Schermata di fine esecuzione di un workflow](/docs/images/image-3.png)
*Schermata di fine esecuzione di un workflow*


---

### B.1 — Aggiungere un utente

Quando qualcuno ti manda nome, Chat ID e parole chiave:

1. Apri il workflow [Add User](https://github.com/philos-l/Philos-L-Auto-Filter/actions/workflows/add_user.yml)
2. Clicca **Run workflow** (in alto a destra)
3. Compila i tre campi:
   - **Nome del profilo**: il nome che ti ha dato (es. `mario`) — solo lettere minuscole, senza spazi
   - **Chat ID**: il numero che ti ha mandato (es. `684963912`)
   - **Parole chiave**: le keyword separate da virgola (es. `phd, postdoc, metaphysics`)
4. Clicca **Run workflow**
5. Aspetta che la run finisca (pallino verde ✅)

Da quel momento l'utente riceverà notifiche alla prossima esecuzione.

---

### B.2 — Modificare le keyword di un utente

Quando un utente vuole cambiare le sue parole chiave:

1. Apri il workflow [Modify User](https://github.com/philos-l/Philos-L-Auto-Filter/actions/workflows/modify_user.yml)
2. Clicca **Run workflow**
3. Compila:
   - **Nome del profilo**: il suo nome (es. `mario`)
   - **Nuove parole chiave**: le nuove keyword separate da virgola (sostituiscono le vecchie)
4. Clicca **Run workflow**

Il Chat ID resta invariato, cambiano solo le keyword.

> **Nota bene:** solo le **nuove** mail che contengono le nuove keyword vengono processate. Se si vuole riprocessare anche le vecchie mail con la nuova keyword, conviene eliminare il profilo e ricrearlo con lo stesso nome e Chat ID.

---

### B.3 — Rimuovere un utente

Quando qualcuno vuole disiscriversi:

1. Apri il workflow [Remove User](https://github.com/philos-l/Philos-L-Auto-Filter/actions/workflows/remove_user.yml)
2. Clicca **Run workflow**
3. Scrivi il **Nome del profilo** da rimuovere
4. Clicca **Run workflow**

Profilo e storico vengono eliminati.

---

### B.4 — Resettare lo stato (riscansione mail)

Quando serve: se un utente segnala "non ho ricevuto una notifica per una mail vecchia che doveva farmi match" — succede ad esempio se ha aggiunto delle keyword nuove e vuole che il bot riguardi le mail già processate.

1. Apri il workflow [Reset State](https://github.com/philos-l/Philos-L-Auto-Filter/actions/workflows/reset_state.yml)
2. Clicca **Run workflow**
3. Compila:
   - **Nome del profilo**: lascia vuoto per resettare tutti, oppure scrivi un nome specifico
4. Clicca **Run workflow**

Alla prossima esecuzione il bot riprocesserà **tutte** le mail dall'inizio (può mandare molte notifiche tutte insieme — avvisa l'utente).

---

## C. Verificare che tutto funzioni

### C.1 — Controllo periodico

Per fare un controllo della corretta esecuzione apri la pagina [Actions](https://github.com/philos-l/Philos-L-Auto-Filter/actions)

Vedrai una lista di run con dei pallini:
- ✅ **Verde** = tutto bene
- ❌ **Rosso** = qualcosa non ha funzionato

![Pagina Principale di Github Actions](/docs/images/image-4.png)
*Pagina Principale di Github Actions*

Se vedi pallini rossi recenti, vai al punto C.2.

### C.2 — Cosa fare se un workflow fallisce

1. Clicca sulla esecuzione con il pallino rosso
2. Clicca sul job che è fallito (di solito è uno solo)
3. Scorri i passaggi (steps) — quello fallito ha la X rossa
4. Clicca sul passaggio rosso per espanderlo
5. Copia tutto il testo dell'errore
6. Manda allo sviluppatore il messaggio + il link della run

![Esempio di esecuzione fallita](/docs/images/image-5.png)
*Esempio di esecuzione fallita*

![Singolo job fallito](/docs/images/image-6.png)
*Singolo job fallito*

![Log di errore del job fallito](/docs/images/image-7.png)
*Log di errore del job fallito*

### C.3 — Un utente segnala "non ricevo notifiche"

Controlla in ordine:

1. Vai su **Actions** e verifica che le ultime run siano verdi
2. Se sono tutte verdi: probabilmente nessuna mail ha matchato le sue keyword. Chiedigli le keyword e fai una ricerca manuale sul sito.
3. Verifica che il suo profilo esista nella sezione [Profiles](https://github.com/philos-l/Philos-L-Auto-Filter/tree/main/profiles)
4. Se c'è qualcosa che non torna, contatta sviluppatore

---

## D. Gestione delle credenziali (Secrets)

I "Secrets" sono le credenziali (password e token) che il workflow usa per autenticarsi con Gmail (per leggere le mail) e con Telegram (per mandare i messaggi tramite il bot).

Non possono stare scritte in chiaro nel codice del repository: il codice è pubblico su GitHub, quindi chiunque visiti il repo potrebbe leggerle e usarle per accedere alla casella Gmail o impersonare il bot Telegram. 
Per questo GitHub le tiene in una "cassaforte" apposita ("Secrets and variables"): il bot le usa solo nel momento in cui gira, nessuno le può leggere — nemmeno tu. Se serve cambiarle, l'unica cosa che puoi fare è sovrascriverle con un nuovo valore.

Vanno aggiornati raramente (in pratica solo se Gmail revoca l'App Password o se il token Telegram viene rigenerato), ma devi sapere come fare.

**Dove si trovano:**
https://github.com/philos-l/Philos-L-Auto-Filter/settings/secrets/actions

Per aggiornarne uno: clicca sul nome del Secret → **Update** → incolla il nuovo valore → **Update secret**.

### D.1 — `IMAP_PASS` (App Password Gmail)

L'**App Password** è una password "usa e getta" che Gmail genera per far accedere alla casella un programma esterno (in questo caso il bot), senza dovergli dare la password vera dell'account.
Va aggiornata se Gmail la revoca (succede raramente, di solito quando si cambia la password principale dell'account).

Per generarne una nuova:
1. Accedi all'account Gmail `philos.l.list@gmail.com`
2. Vai su https://myaccount.google.com/security
3. Sezione **Verifica in due passaggi** → in fondo trovi **App Password** (oppure cercalo nella barra di ricerca)
4. Genera una nuova password (16 caratteri)
5. Copiala e incollala nel Secret `IMAP_PASS` su GitHub

### D.2 — `TELEGRAM_BOT_TOKEN`

Il bot Telegram è gestito da sviluppatore. Se serve rigenerare il token:
1. Contatta sviluppatore
2. Lui ti manda il nuovo token
3. Tu lo incolli nel Secret `TELEGRAM_BOT_TOKEN` su GitHub

### D.3 — `IMAP_USER`

E' la mail dell'account.
Va sostituita solo se cambia l'indirizzo email Gmail dell'account.

### D.4 — `IMAP_HOST`

Non cambia mai. È sempre `imap.gmail.com`. 

---

## E. Cose da NON fare

Per evitare di rompere qualcosa:

- ❌ **Non modificare i file `.toml` direttamente** dalla pagina del repo. Usa sempre i workflow `Add User` / `Modify User` / `Remove User`.
- ❌ **Non cancellare la cartella `state/` a mano**. Se devi resettare, usa il workflow `Reset State`.
- ❌ **Non disabilitare i workflow** dal tab Actions.
- ❌ **Non modificare il codice Python** (`mail_monitor_multi.py`) né i file YAML dei workflow.
- ❌ **Non condividere i Secrets** con nessuno (sono come password).

Se qualcosa di tutto questo serve davvero, chiedi a sviluppatore.

---

## F. Quando contattare sviluppatore

- Un workflow è fallito (mandagli il log copiato come spiegato in C.2)
- Va rigenerato il token Telegram
- Vuoi cambiare qualcosa nel funzionamento del bot
- Vuoi una nuova feature
- Qualcosa non capisci o ti spaventa — meglio chiedere che rompere
