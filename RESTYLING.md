# RESTYLING — Front-end nuovo su Cloudflare

> Documento di lavoro per il rifacimento del front-end. Vive finché il progetto non è finito.
> Il contesto completo del progetto resta in **[CLAUDE.md](CLAUDE.md)** e **[PROJECT_LOG.md](PROJECT_LOG.md)**: vanno letti prima di toccare qualsiasi cosa.

## Obiettivo

Sostituire la dashboard Streamlit (`app.py`, 1.519 righe) con un front-end React statico su **Cloudflare Pages**, con animazioni e componenti moderni (21st.dev e simili), che Streamlit non può fare.

**Non** è una migrazione di tutto il progetto: il bot Telegram resta Python dov'è.

## La decisione architetturale, e il perché

Il piano free di Cloudflare dà **10 ms di CPU per richiesta** (anche per i Cron Trigger, massimo 5). Sono tantissimi per servire un JSON già pronto e pochissimi per leggere 6.000 righe e ricalcolare punteggi.

Da lì discende tutto:

- **Il bot calcola, Cloudflare mostra.** Dopo ogni ricalcolo il bot pubblica uno **snapshot JSON** già pronto. Il sito lo legge e basta.
- **`statistiche.py` resta Python.** Ha 58 test e logica che è costata sessioni di debug. Riportarla in TypeScript significherebbe rimetterla in gioco tutta. Il React fa solo presentazione.
- **Il sito diventa statico.** Niente backend, niente spegnimento dopo 15 minuti, niente avvio a freddo, niente budget ore.

Il carico non è un problema e non lo sarà: 16-20 persone sono tre ordini di grandezza sotto i limiti del piano free. I colli di bottiglia veri restano **Football-Data (10 richieste/minuto)** e le quote di Google Sheets, e non cambiano con l'hosting.

## Vincoli da non violare

1. **Il bot non si tocca nella logica di calcolo.** `esegui_calcolo_risultati`, `controlla_esito`, `normalizza_pronostico`, la scrittura su Sheets: fuori dallo scopo. Si aggiunge solo la pubblicazione dello snapshot.
2. **Il repo è GitLab**, `git@gitlab.com:benanti64/toto-amici1.git`. L'account GitHub è sospeso.
3. **Mai fare deploy del servizio `toto-amici-bot` su Render.** Punta ancora al repo GitHub sospeso: un *Manual Deploy* o un *Clear build cache* fallirebbe e farebbe cadere un bot che funziona.
4. **Il sito non scrive mai su Google Sheets.** Vale come prima: scrive solo il bot.
5. **Lo snapshot è pubblico** (niente login, come oggi). Non deve contenere nulla che il sito non mostri già.
6. **Si gira su dati veri prima di dichiarare fatto**: la dashboard attuale è il riferimento di confronto.

## Fasi

### Fase 0 — Decisioni da prendere prima di scrivere codice
- [ ] **Formato dello snapshot JSON.** È il contratto fra bot e sito: va deciso per primo, perché tutto il resto ci si appoggia.
- [ ] Dove si pubblica: **Cloudflare KV** o **R2**.
- [ ] Stack front-end: Vite + React, oppure Next.js su Pages.
- [ ] Cosa resta davvero live e cosa no (vedi Fase 3).

### Fase 1 — Lo snapshot (lato bot, Python)
- [ ] Definire lo schema e scriverlo qui dentro.
- [ ] Generazione dello snapshot dopo `esegui_calcolo_risultati`, riusando `statistiche.py`.
- [ ] Pubblicazione su Cloudflare (token come variabile d'ambiente su Render, mai nel repo).
- [ ] Test: lo snapshot contiene quello che le sei schede mostrano oggi.
- [ ] **Se la pubblicazione fallisce, il calcolo non deve fallire.** Stessa regola dello stato persistente: lo stato non è mai più importante del lavoro.

### Fase 2 — Front-end
- [ ] Scaffold React su Cloudflare Pages, deploy da GitLab.
- [ ] Lettura dello snapshot.
- [ ] Le sei schede attuali: **Classifica & Cassa**, **Schedine Live**, **Confronto Giocate**, **Statistiche**, **Coppa**, **Regolamento**.
- [ ] Tema chiaro/scuro: i colori attuali sono in `.streamlit/config.toml` e vanno portati come design token.
- [ ] Animazioni e componenti.
- [ ] Il timestamp "ultimo aggiornamento" deve **avvisare quando invecchia troppo**: se il bot smette di pubblicare, il sito mostrerebbe dati vecchi senza accorgersene.

### Fase 3 — Risultati live
Oggi `app.py` chiama Football-Data **da sola** (cache 3 minuti) per le partite in corso. Con uno snapshot statico quei dati sarebbero freschi quanto l'ultimo push del bot.
- [ ] Worker minuscolo che fa da ponte verso Football-Data: è solo I/O, quindi sta nei 10 ms.
- [ ] La chiave API sta nel Worker come secret, **mai nel browser**.
- [ ] Rispettare il limite di 10 richieste/minuto, che è condiviso col bot.

### Fase 4 — Passaggio
- [ ] I due siti convivono leggendo la stessa fonte: si passa al nuovo solo quando è pronto, senza mai restare senza sito.
- [ ] Comunicare il nuovo indirizzo ai giocatori (`NOVITA` in `app.py` o messaggio WhatsApp).
- [ ] Spegnere il servizio `toto-amici-sito` su Render: libera ~176 ore/mese, e a quel punto si può **rivalutare la pausa notturna del bot** (esiste solo per far quadrare le 750 ore).
- [ ] Aggiornare `CLAUDE.md`, `PROJECT_LOG.md` e la tabella del deploy.

## Modifiche in attesa del rilascio 3.0

Decisione dell'utente (04/10/2026): le correzioni non urgenti non si pubblicano una alla volta, ma tutte insieme al nuovo front-end. Si accumulano sul branch **`rilascio-3.0`** (solo locale + backup, **non** su GitLab finché non si rilascia); `main` resta pulito per eventuali correzioni urgenti, che vanno poi riportate anche qui (`git merge main` dentro `rilascio-3.0`).

| # | Sessione | Modifica | Tocca | Note per `NOVITA` 3.0 |
|---|---|---|---|---|
| 1 | 28 | Classifica letta per intero invece di `A:Z` (le Giornate 25-38 si perdevano); `archivia_stagione()` svuota righe intere | bot, `app.py`, test | «Classifica, statistiche e Coppa leggono tutte le 38 giornate» |

**⚠️ Scadenza che non aspetta il front-end: la #1 deve essere sul bot in produzione prima dei risultati della Giornata 25.** Dalla 26 il bot sovrascrive i punti della 25 senza dare errori. Se a quella data il 3.0 non è pronto, la #1 va pubblicata da sola (è solo bot + un range in `app.py`, già testata). In ogni caso serve prima **ripuntare il bot su GitLab**, che è anche un prerequisito della Fase 1 (lo snapshot lo pubblica il bot).

**Al momento del rilascio:** test + dry-run sul branch, `VERSIONE_APP = "3.0.0"` con le righe `NOVITA` raccolte qui sopra, merge in `main`, push su `gitlab`, poi aggiornare `PROJECT_LOG.md`.

## Riferimenti nel codice attuale

| Cosa | Dove |
|---|---|
| Le sei schede | `app.py:406` (`st.tabs`), poi `app.py:418, 630, 771, 939, 1307, 1458` |
| Lettura dati (una sola batchGet) | `app.py`, `carica_tutti_i_dati()` |
| Chiamate a Football-Data | `app.py:264` (risultati), `app.py:336` (squadre) |
| Logica statistiche | `statistiche.py` (376 righe, 58 test) |
| Colori e tema | `.streamlit/config.toml` |
| Versione e novità per i giocatori | `app.py`, `VERSIONE_APP` e `NOVITA` |
