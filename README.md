# Philos-L Notification Bot

Philos-L Notification Bot permette di ricevere una notifica Telegram ogni volta che arriva una mail sulla mailing list **PHILOS-L** (mailing list di annunci di filosofia accademica) contenente una parola chiave (ad esempio: "ontology", "metaphysics", "call for papers") o qualsiasi altro termine.
Serve per essere notificati solo degli argomenti che interessano.

Viene eseguito una volta al giorno tramite Github Actions.

---

## Come iscriversi

### Passo 1 — Avvia il bot su Telegram

Cerca [**@philos_l_notification_bot**](https://t.me/philos_l_notification_bot) su Telegram,

Premi **Avvia**. Da questo momento il bot ti conosce.

---

### Passo 2 — Trova il tuo Chat ID

Il Chat ID è un numeretto che dice al bot dove mandarti i messaggi. Ce ne sono due modi per trovarlo — il primo è più semplice:

#### Metodo A — @WhatChatIDBot

1. Cerca [**@WhatChatIDBot**](https://t.me/WhatChatIDBot) su Telegram
2. Premi **Avvia**
3. Il bot ti risponde subito con il tuo Chat ID, tipo `484946982`
4. Copialo

#### Metodo B — Telegram Web

1. Apri [**https://web.telegram.org**](https://web.telegram.org) nel browser
2. Entra con il tuo account Telegram
3. Clicca su **Messaggi Salvati**
4. Guarda l'URL nella barra del browser — il numero dopo il `#` è il tuo Chat ID

---

### Passo 3 — Scegli le tue parole chiave

Quali argomenti ti interessano? Il bot cerca quelle parole in tutte le mail — titolo e testo completo — senza distinguere maiuscole e minuscole.

Qualche idea:

```
phd
postdoc
call for papers
metaphysics
ontology
phenomenology
philosophy of mind
kant
wittgenstein
conference
fellowship
```

Puoi aggiungerne quante vuoi, anche frasi di più parole.

---

### Passo 4 — Scrivi all'amministratore

<!-- AMMINISTRATORE: inserisci qui i tuoi contatti (es. email, Telegram) -->

Manda all'amministratore queste tre cose:

1. **Il tuo nome** (diventerà il nome del profilo)
2. **Il tuo Chat ID** (il numero del Passo 2)
3. **Le tue parole chiave**

Lui aggiunge il tuo profilo e da quel momento le notifiche partono in automatico. Non devi fare altro.

---

## Come disiscriversi

Scrivi all'amministratore chiedendo la rimozione del tuo profilo. Lui lo elimina e da quel momento non riceverai più notifiche.

---

## Domande frequenti

**Non arriva niente — è normale?**
Può essere. PHILOS-L è attivissima (centinaia di mail al mese), ma se le tue keyword sono molto specifiche può passare qualche giorno prima di un match.

**Posso cambiare le keyword?**
Certo, scrivilo all'amministratore in qualsiasi momento.

**Arriverà spam?**
No. Ricevi una notifica solo se c'è un match. Se non c'è niente di interessante, non ricevi niente.

**Cos'è PHILOS-L?**
La principale mailing list internazionale di filosofia accademica, attiva dal 1992. Ci girano annunci di dottorati, borse, postdoc, call for papers, conferenze e discussioni filosofiche. Maggiori info: https://listserv.liv.ac.uk/cgi-bin/wa?A0=PHILOS-L

---

## Per l'amministratore

La guida completa per la gestione del bot (aggiungere/rimuovere utenti, controllare gli errori, aggiornare le credenziali) si trova in [docs/ADMIN.md](docs/ADMIN.md).
