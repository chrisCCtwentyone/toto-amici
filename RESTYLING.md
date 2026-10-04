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
3. **Ogni push su `main` di GitLab ridistribuisce il bot.** Dal 04/10/2026 il servizio `toto-amici-bot` su Render è ricollegato a GitLab (`main`, auto-deploy a ogni commit). Il lavoro del restyling va quindi su un branch a parte e arriva su `main` solo quando è pronto e testato. Ogni deploy dà circa un minuto di `409 Conflict` mentre la vecchia istanza si spegne: è normale, ma va fatto lontano dalle partite e dagli orari del calcolo.
4. **Il sito non scrive mai su Google Sheets.** Vale come prima: scrive solo il bot.
5. **Lo snapshot è pubblico** (niente login, come oggi). Non deve contenere nulla che il sito non mostri già.
6. **Si gira su dati veri prima di dichiarare fatto**: la dashboard attuale è il riferimento di confronto.

## Fasi

### Fase 0 — Decisioni da prendere prima di scrivere codice
- [x] **Formato dello snapshot JSON.** È il contratto fra bot e sito: va deciso per primo, perché tutto il resto ci si appoggia. *Contenuto deciso (sotto); schema approvato il 04/10/2026 in [restyling/snapshot-schema.md](restyling/snapshot-schema.md).*
- [x] Dove si pubblica: **Cloudflare KV** (04/10/2026). Un JSON da ~40 KB compressi, al massimo un centinaio di scritture al giorno contro le 1.000 del piano free.
- [x] Stack front-end: **Vite + React su Cloudflare Workers con static assets** (04/10/2026), non Pages: un solo progetto serve sito, snapshot e risultati live, con deploy da GitLab.
- [x] Cosa resta davvero live: i **punteggi delle partite e gli orari di inizio**, dal Worker (vedi Fase 3). Tutto il resto viene dallo snapshot.
- [x] **Chi pubblica lo snapshot: il bot.** Sbloccato il 04/10/2026: il servizio è stato ricollegato da GitHub a GitLab dal pannello di Render (Settings → Build → Source), stesso URL e stesse variabili. Primo deploy da GitLab live alle 14:50 UTC con lo stesso codice di prima; solo i due `409` attesi della sovrapposizione.

#### Decisioni sullo snapshot (04/10/2026)
1. **I calcoli stanno in Python.** Tutto ciò che oggi `app.py` calcola da solo (ordinamento con spareggio, frecce di tendenza, podio, Cassa e grafico dei versamenti, protagonisti, giornata da incorniciare, Semper Fidelis, squadra amuleto/maledetta, statistiche per giocatore e ritirati, scelta del gruppo e totali del Confronto, normalizzazione dei nomi partita) passa in `statistiche.py` con i test. Lo snapshot porta questi risultati già pronti **più** le righe di Giocate già pulite (numeri veri, giornata come intero, nome partita ufficiale). Il React filtra per giornata e giocatore, non calcola.
2. **Quando si pubblica:** dopo ogni scrittura del bot su Sheets, più un controllo ogni 15 minuti che ripubblica solo se qualcosa è cambiato (così arrivano anche le correzioni fatte a mano sul foglio). Il controllo lascia comunque un **segnale di vita** con l'orario. Niente controlli dalle 02:00 alle 07:30.
3. **Avviso dati vecchi:** il sito mostra sempre "Aggiornato alle HH:MM del gg/mm" e avvisa se il segnale di vita manca da **più di 2 ore**, tranne di notte.
4. **Live:** il Worker abbina i risultati alle partite per **id di Football-Data**, non per nome. L'abbinamento riga del foglio → partita lo fa il Python prima di pubblicare, **solo fra le 10 partite di quella giornata** (matchday) scaricate da Football-Data, confrontando le due squadre normalizzate (minuscole, senza suffissi societari): nelle Giornate 1-2 il foglio ha nomi disordinati (29 scritture diverse per 10 partite in G1), dalla G3 coincidono con `shortName`. Se una riga non trova partita, il bot non indovina: avvisa gli admin e la pubblica come `ufficiale: false`.
5. **Timer dell'ultima schedina vinta:** l'istante di partenza lo calcola il Python e lo mette già pronto nello snapshot.
6. **Solo la stagione in corso**, con un campo `stagione` (il titolo del sito lo legge da lì). Lo storico si potrà aggiungere dopo senza cambiare formato.
7. **Pubblico come il sito di oggi:** nomi, schedine, vincite potenziali, Cassa con nomi e importi. Mai ID Telegram, chiavi, `SPREADSHEET_ID` o altri dati tecnici.
8. **Righe senza esito** (prima del primo calcolo): "Da giocare", e diventano "In corso" quando il live dice che la partita è iniziata.
9. **Correzioni rispetto al sito di oggi**, da segnare come differenze attese nel confronto sui dati veri:
   - frecce di tendenza con lo stesso criterio di spareggio per la posizione attuale e quella precedente;
   - squadra amuleto/maledetta contata per squadra ufficiale, non per nome scritto nel foglio;
   - la scheda Live conta anche RINVIATA, DA VERIFICARE e ANNULLATA;
   - Regolamento: 16 giocatori, obiettivo Cassa 3.200 €, ripartizione in percentuale 40/27/17/10/6.

   Tutto il resto si replica identico, compresi i titoli delle card delle Statistiche.
10. **Logica da migliorare, non solo da spostare** (richiesta dell'utente, 04/10/2026): spostando i calcoli da `app.py` a `statistiche.py` si correggono errori logici, lavoro inutile e implementazioni fragili, con un test per ognuno. Le modifiche alla logica di calcolo **del bot** si propongono prima all'utente e passano da test + `scripts/dry_run_non_regressione.py`.
11. **Schema approvato** il 04/10/2026: [restyling/snapshot-schema.md](restyling/snapshot-schema.md) (`versione_schema: 1`), con tutte le domande aperte chiuse. Decisioni di dominio: card a pari merito mostrano **tutti** i pari merito, senza minimo di pronostici (14); classifica con **stessa posizione** a parità di punti e pronostici vinti (15); il sostituto eredita i pronostici vinti del ritirato per lo spareggio (17); Semper Fidelis conta **giornate distinte** giocate e non annullate (19); amuleto/maledetta contano **solo la squadra scelta** dal pronostico (20); Coppa «definitiva» quando la Giornata 34 è **conclusa** (21).

#### Stile grafico scelto: **Diretta** (04/10/2026)
Grafica da telecronaca: blu notte, barre oblique proporzionali ai punti, pallino LIVE, ticker in basso. Riferimento: direzione 5 in [restyling/proposte-stili.html](restyling/proposte-stili.html). Palette: `#040a22`, `#2f7bff`, `#19e3ff`, `#ff2d87`, `#ffd400`. Font: Saira Extra Condensed (cifre e titoli) + Saira (testo).

### Fase 1 — Lo snapshot (lato bot, Python)
- [x] Definire lo schema (scritto nel file a parte [restyling/snapshot-schema.md](restyling/snapshot-schema.md), approvato il 04/10/2026).
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

**Ordine di rilascio deciso il 04/10/2026:** «Toto-Amici 3.0» è il momento in cui i giocatori ricevono il link del sito nuovo. Prima di allora, appena la Fase 1 è pronta e testata, si pubblica **solo la parte del bot** che genera e salva lo snapshot: non cambia nulla di ciò che il bot fa oggi e il sito vecchio non se ne accorge. Serve a provare il sito nuovo su un indirizzo di prova con dati veri e aggiornati, per qualche giorno e almeno una giornata di partite, prima del passaggio.

Decisione dell'utente (04/10/2026): le correzioni non urgenti non si pubblicano una alla volta, ma tutte insieme al nuovo front-end. Si accumulano sul branch **`rilascio-3.0`** (solo locale + backup, **non** su GitLab finché non si rilascia); `main` resta pulito per eventuali correzioni urgenti, che vanno poi riportate anche qui (`git merge main` dentro `rilascio-3.0`).

| # | Sessione | Modifica | Tocca | Note per `NOVITA` 3.0 |
|---|---|---|---|---|
| 1 | 28 | Classifica letta per intero invece di `A:Z` (le Giornate 25-38 si perdevano); `archivia_stagione()` svuota righe intere | bot, `app.py`, test — **già in produzione dal 04/10/2026** (commit `b992ac1`) | «Classifica, statistiche e Coppa leggono tutte le 38 giornate» |

**La #1 è stata pubblicata da sola il 04/10/2026 alle 17:00**, subito dopo aver ricollegato il bot a GitLab: era l'unica con una scadenza (Giornata 25). Test 522/522, dry-run giornate 1-6 senza differenze, deploy di bot e sito riuscito. Resta nella tabella solo per la riga di `NOVITA` del 3.0.

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
