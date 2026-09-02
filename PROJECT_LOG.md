# PROJECT_LOG.md — Toto-Amici 2026
> Documento di tracciamento architettura, modifiche e decisioni tecniche del progetto.
> **Aggiornare dopo ogni sessione di sviluppo.**

---

## 🗂️ Architettura del Sistema (Stato Attuale)

### Deploy
| Componente | Piattaforma | Sorgente | Note |
|---|---|---|---|
| Web Dashboard (`app.py`) | Streamlit Community Cloud | GitHub `main` | Pubblica, sempre online |
| Bot Telegram (`bot_telegram.py`) | Render (Web Service) | GitHub `main` | Sveglio grazie a **due** fonti di keep-alive: auto-ping interno ogni 5 min + cron-job.org ogni 10 min. Render spegne dopo 15 min senza traffico **in entrata** |
| Database | Google Sheets | — | SPREADSHEET_ID: `1q0aaYXl7VYiUzEbttGaoQjNq7ta5wiHD4Qvg5Si7IvE` |

### Variabili d'Ambiente Necessarie
| Nome | Dove configurare | Descrizione |
|---|---|---|
| `TELEGRAM_TOKEN` | Render (Environment Variables) | Token del bot Telegram |
| `ADMIN_ID` | Render (Environment Variables) | ID Telegram dell'admin (unico utente autorizzato) |
| `SPREADSHEET_ID` | Render + Streamlit Secrets | ID del Google Spreadsheet centrale |
| `FOOTBALL_DATA_KEY` | Render + Streamlit Secrets | Chiave API football-data.org |
| `gcp_service_account` | Streamlit Secrets (JSON) | Credenziali service account Google Cloud |

### File Credenziali Locali (NON in git, in .gitignore)
| File | Utilizzo |
|---|---|
| `credenziali.json` | Service Account Google per Sheets API (usato dal bot in locale/Render) |
| `chiave_api.txt` | Chiave API Gemini (letta dal bot; aggiornabile via `/setkey` in Telegram) |
| `.env` | Variabili per test locali di `calcola_risultati.py` (archiviato) |

---

## 📁 Struttura File del Progetto

```
Toto_Amici_Progetto/
├── app.py                  # ✅ Web Dashboard Streamlit (produzione)
├── bot_telegram.py         # ✅ Super-Bot Telegram (produzione, Render)
├── requirements.txt        # ✅ Dipendenze per Streamlit Cloud e Render
├── .gitignore              # ✅ Esclude credenziali, .env, cache
├── .env                    # 🔒 Non in git — variabili locali
├── chiave_api.txt          # 🔒 Non in git — chiave Gemini
├── credenziali.json        # 🔒 Non in git — service account GCP
├── PROJECT_LOG.md          # 📋 Questo file — memoria del progetto
├── CLAUDE.md               # 🤖 Punto d'ingresso rapido per Claude Code, rimanda a PROJECT_LOG.md
├── _archivio/              # 📦 Script obsoleti ma recuperabili
│   ├── bot_lettore.py      # Vecchio lettore locale schedine (sostituito dal bot)
│   └── calcola_risultati.py # Vecchio calcolo manuale da CLI (sostituito dal bot)
├── .streamlit/             # 🔒 Non in git — secrets per Streamlit locale
│   └── secrets.toml
├── .claude/launch.json     # ✅ Config locale (nessun segreto) per preview Streamlit in Claude Code
├── schedine_whatsapp/      # 🔒 Non in git — cartella foto locali
├── api_utils.py            # ✅ Chiamate HTTP con retry/backoff (condiviso app+bot)
├── tests/                  # ✅ Test automatici (pytest) — 262 test
│   ├── test_logica_bot.py, test_invarianti.py, test_api_utils.py
│   ├── test_girone_di_ritorno.py, test_backup.py
│   └── test_riepilogo_whatsapp.py, test_archivio_stagione.py
├── requirements-dev.txt    # ✅ Dipendenze di sviluppo (pytest) — la produzione usa solo requirements.txt
└── temp_telegram/          # Cartella temporanea per foto ricevute via Telegram
```

---

## 🏗️ Struttura Google Sheets

| Foglio | Colonne | Descrizione |
|---|---|---|
| `Giocate` | A: Giornata, B: Giocatore, C: Partita, D: Tipologia, E: Pronostico, F: Quota, G: Esito, H: Vincita Potenziale, I: Punti Partita | Archivio analitico di ogni singola selezione giocata |
| `Classifica` | A: Giocatore, B: Punti Totali, C+: Punteggio per Giornata | Leaderboard generale con storico per giornata |
| `Cassa` | A: Giornata, B: Descrizione, C: Entrate, D: Saldo Totale | Registro movimenti del fondo montepremi |

> **Stagioni passate**: `/archiviastagione` duplica i tre fogli in `«Giocate 2026-27»`, `«Classifica 2026-27»`, `«Cassa 2026-27»` e svuota quelli di lavoro. I fogli senza suffisso sono sempre la stagione in corso.

---

## 🎮 Logica di Business (Regolamento)

### Composizione Obbligatoria Schedina (costo: 5€)
- **1 Combo** (es. 1+OVER_2.5, X+GOAL)
- **4 Fisse** (1, X, 2)
- **2 Doppie Chance** (1X, X2, 12)
- **3 Variabili** (OVER_2.5, UNDER_2.5, GOAL, NOGOAL, PARI, DISPARI)

### Punteggi
| Tipo | Punti base | Con quota ≥ 3.50 |
|---|---|---|
| Combo | 6 | 12 |
| Fisse | 4 | 8 |
| Doppie Chance | 1 | 2 |
| Variabili | 2 | 4 |
| **Bonus chiusura** | **+10** | — |

### Cassa
- Schedina vinta: 50% al giocatore, 50% al Fondo Cassa (aggiornato automaticamente)
- Obiettivo cassa: **3.200€** (soglia impostata in `app.py` → `OBIETTIVO_CASSA`)

### Regola Buona Fede
- OVER_1.5 → convertito in OVER_2.5
- UNDER_3.5 → convertito in UNDER_2.5

### Gestione Eccessi
- Se una categoria supera il limite (es. 5 Fisse invece di 4), le selezioni in eccesso vengono marcate `(ANNULLATA ECCESSO)` → 0 punti, ma la bolletta resta economicamente valida.

---

## 🔄 Changelog Sessioni

### 02/09/2026 — Sessione 15 (Caricamento schedina bloccato: Markdown e Gemini 503)

**Sintomo**: impossibile caricare le schedine di Giornata 3. Due errori diversi, entrambi mostrati come *"❌ Errore durante l'elaborazione IA"*:
1. `Can't parse entities: can't find end of the entity starting at byte offset 522`
2. `503 UNAVAILABLE ... This model is currently experiencing high demand` (due tentativi di fila)

**Causa 1 — non era l'IA, era la formattazione.** Il prompt di `analizza_schedine_multiple` impone all'IA di restituire pronostici normalizzati come `OVER_2.5`, `UNDER_2.5`, `1+OVER_2.5`: **contengono underscore per costruzione**. Il riepilogo veniva inviato con `parse_mode="Markdown"`, dove l'underscore apre il corsivo. Con un numero **dispari** di underscore nel messaggio, Telegram non trova la chiusura e **rifiuta l'intero messaggio**. Ricostruendo un riepilogo realistico (10 eventi secondo `LIMITI_SCHEDINA`, 3 pronostici con underscore) si ottengono **520 byte** con l'ultimo underscore spaiato in coda — l'errore reale indicava il byte 522. Riscontro quantitativo, non solo plausibile.
> Il danno vero: la lettura IA era **corretta**, ma il `try` di `esegui_conferma` avvolgeva anche l'invio, quindi il fallimento di formattazione veniva etichettato come errore dell'IA e `pulisci_dati()` buttava via il lavoro, costringendo a ricaricare le foto.

**Causa 2 — Gemini senza retry, e poi: il retry non bastava.** `client.models.generate_content` era l'**unica** chiamata esterna del progetto rimasta senza retry (Football-Data ha `richiedi_con_retry()`, Sheets ha `num_retries=3`). Prima correzione: 3 tentativi con backoff 2s/4s. **Non ha funzionato** — l'errore si è ripresentato identico al primo caricamento successivo.

**Perché non bastava** (misurato interrogando l'API con la chiave del progetto, non ipotizzato): `gemini-3.6-flash` non era *giù*, era **saturo in modo cronico** — ha risposto a un banale "dì solo OK" in **96 secondi**. Riprovare lo stesso modello 3 volte in 6 secondi non poteva servire a niente: la congestione dura minuti, non secondi. Misure sullo stesso identico carico (immagine + JSON):

| modello | esito |
|---|---|
| `gemini-3.8-flash` | 503 UNAVAILABLE (il più recente, sempre saturo) |
| `gemini-3.7-flash` | 38s |
| `gemini-3.6-flash` ← era il primario | 96s, oppure 503 |
| `gemini-3.5-flash` | 18s sulla schedina completa, **10/10 pronostici corretti** |
| `gemini-flash-latest` | 2s in un test, **503 dieci minuti dopo** |

Il dato decisivo è l'ultima riga: **la congestione si sposta da un modello all'altro nel giro di minuti**. Nessun singolo modello è affidabile da solo, quindi la soluzione non era cambiare modello ma avere una **catena di riserve**.

**Correzione definitiva**:
- **`chiama_gemini_con_fallback()`** su `MODELLI_GEMINI` (3.5-flash → flash-latest → 3.7-flash → 3.6-flash), con tre comportamenti distinti: errore transitorio (503/429/500/timeout) → riprova, poi cambia modello; modello ritirato (404, come `gemini-2.5-flash` che è già "no longer available") → passa oltre subito senza sprecare tentativi; errore definitivo (chiave non valida) → rilancia subito invece di far aspettare l'admin per 4 modelli.
- **Timeout di 60s per richiesta** (`http_options`): senza tetto, un modello congestionato tiene il bot occupato per 96s mentre l'admin fissa "L'IA sta analizzando le foto...". Il minimo accettato dall'API è 10s.
- **Eccezione dedicata `GeminiSovraccarico`**: se tutta la catena è satura, l'admin riceve *"Gemini è sovraccarico, non è un problema del bot né delle tue foto, riprova tra qualche minuto"* invece del JSON grezzo del 503.
- **Verifica di qualità prima del cambio di modello**: `gemini-3.5-flash` è stato scelto dopo averlo testato con il **prompt reale** su una schedina sintetica a 10 eventi contenente le insidie note (`U 2.5`, `Entrambe segnano: Sì`, `GG`, `1 + Over 2.5`): 10/10 pronostici normalizzati correttamente, vincita letta giusta. Poi verifica end-to-end sulla vera `analizza_schedine_multiple`: 15,4s, 10/10. Un modello più veloce ma che legge peggio sarebbe stato un downgrade mascherato da fix.

**Correzioni**:
- **`escape_markdown()`**: neutralizza `_`, `*`, `` ` ``, `[` in **qualsiasi** testo non scritto da noi (output IA: partita, pronostico, quota, vincita) prima di inserirlo in un messaggio Markdown. Il grassetto scritto da noi continua a funzionare.
- **Fallback in testo semplice**: se Telegram rifiuta comunque la formattazione, il riepilogo viene rimandato senza `parse_mode` invece di distruggere una lettura riuscita. Un problema di *visualizzazione* non deve più costare il lavoro dell'IA.
- **`chiama_gemini_con_retry()`**: 3 tentativi con backoff 2s/4s, ma **solo** sugli errori transitori (503/UNAVAILABLE, 429/RESOURCE_EXHAUSTED, 500/INTERNAL). Una chiave sbagliata viene rilanciata subito, senza far aspettare l'admin per un guasto che riprovare non risolve.
- **`import time`** aggiunto: c'era solo l'alias `dt_time` da `datetime`, quindi `time.sleep()` sarebbe esploso con `NameError` al primo retry.
- **42 nuovi test** in `tests/test_robustezza_ia.py` (totale: **304**), incluso il caso reale con numero dispari di underscore e la distinzione tra errore transitorio e definitivo.

**Causa 3 (la più grave) — 0 eventi riconosciuti su una schedina piena.** Dopo le correzioni sopra, la scansione è andata a buon fine ma il bot ha mostrato `0/1, 0/4, 0/2, 0/3`, **con il tasto "Conferma e Salva" attivo**: un clic distratto avrebbe scritto una schedina vuota in Giocate. Non era il modello che leggeva male: il codice pretendeva le chiavi JSON **esatte** (`dati.get("eventi", dati).get("Doppie Chance", [])`), e bastava una forma leggermente diversa per trovare 0 eventi **senza sollevare nessun errore**. Verificato interrogando l'API: lo stesso `gemini-3.5-flash` restituisce le categorie dentro `eventi` in una richiesta e al primo livello in quella successiva — **la forma non è deterministica**, e cambiando modello cambiano anche i nomi delle chiavi.

**Correzione, su tre livelli**:
- **`SCHEMA_SCHEDINA` passato come `response_schema`**: la struttura non è più una gentile concessione del modello, è imposta dall'API. Verificato su più modelli e più giri: forma sempre identica (`['vincita_potenziale', 'eventi']`), 10/10 eventi.
- **`estrai_eventi_per_categoria()`**: difesa in profondità se un modello ignorasse lo schema. Riconosce le categorie a prescindere da maiuscole, spazi e underscore ("Doppia Chance" = "doppie_chance" = "DOPPIE CHANCE"), gestisce sia il wrapper `eventi` sia le categorie al primo livello sia una lista piatta con campo `categoria`, e restituisce **sempre** tutte e quattro le chiavi. Sostituisce i **tre** punti del codice che facevano il lookup fragile (`normalizza_nomi_partite`, `scrivi_su_sheets_con_regole`, `esegui_conferma`).
- **Zero eventi = errore, non risultato**: il bot si ferma, spiega cosa può essere andato storto e **logga il JSON grezzo**. Prima un fallimento silenzioso era indistinguibile da una schedina vuota; ora è diagnosticabile al primo colpo.
- **Timeout non ritentato sullo stesso modello**: un 503 arriva in una frazione di secondo, un timeout ha già bruciato 60s — riprovare lo stesso modello congestionato ne brucerebbe altri 60 (l'utente ha aspettato oltre due minuti).

**Nota su un punto lasciato com'è**: in `esegui_calcolo_risultati` il report include il pronostico non interpretabile racchiuso tra backtick (`` `{pron}` ``), dove in Markdown legacy gli underscore sono letterali — per questo quel percorso non ha mai dato problemi nonostante contenga gli stessi `OVER_2.5`. Resta un punto da ricordare se un giorno quei backtick venissero tolti.

### 01/09/2026 — Sessione 14 (Il bot cadeva e non si rialzava: keep-alive irrobustito)
**Sintomo**: da tre giorni il bot spariva e serviva riavviarlo a mano da Render. Errore mostrato: `Exited with status 137`.

**Cosa NON era** (verificato, non ipotizzato):
- **Non la memoria**: misurata, 96 MB a riposo su 512 disponibili, e 98 MB stabili dopo 300 cicli di ricalcolo con una stagione intera di dati. Nessuna perdita.
- **Non un crash del codice**: i log di Render mostravano `Application is stopping` — lo spegnimento *ordinato* di python-telegram-bot su SIGTERM — senza alcun traceback, con `getUpdates` a 200 OK fino all'ultimo secondo. Era Render a fermarlo.
- **Non il nostro endpoint**: interrogandolo dal vivo risponde 200 OK, 69 byte, 0,25s, senza redirect.

**Causa reale** (emersa dallo screenshot di cron-job.org fornito dall'utente): **tutte** le esecuzioni del pinger fallivano con *"output troppo grande"*. Trovando il servizio già spento, il ping riceveva la pagina d'errore di Render, molto più grande dei nostri 69 byte. Da cui il **circolo vizioso**: servizio giù → ping riceve pagina d'errore → fallisce → non lo risveglia → resta giù per sempre. Ecco perché serviva sempre l'intervento manuale.
> Nota: il salvataggio delle risposte su cron-job.org era **già disattivato**, quindi non è una impostazione regolabile — la pagina d'errore di Render è grande di suo.

**Correzioni**:
- **`task_autoping`**: il bot chiama il proprio indirizzo pubblico (`RENDER_EXTERNAL_URL`, impostata da Render) generando da sé il traffico in entrata che impedisce lo spegnimento. Non resuscita un processo morto, ma toglie il **punto singolo di rottura**: finché il bot è vivo basta che funzioni una delle due fonti, invece di dipendere solo da un servizio esterno.
- **Intervallo di 5 minuti, non 10**: Render spegne dopo 15 minuti di silenzio, quindi con intervallo di 10 minuti **un solo ping perso** crea un buco di 20 minuti e uccide il servizio. A 5 minuti ne sopravvive due consecutivi.
- **Il ping usa `richiedi_con_retry`**: un blip di rete non deve valere come ping perso, perché ogni ping perso avvicina lo spegnimento.
- **Server web esplicitamente multi-thread**: una richiesta lenta non deve impedire di rispondere ai ping successivi.
- **Log dei ping in entrata** con l'intervallo dal precedente: prima la diagnosi richiedeva di dedurre il problema dall'*assenza* di righe nei log. Allarme Telegram abbassato da 30 a 15 minuti, cioè la soglia reale oltre cui Render spegne (a 30 il servizio era già morto da un pezzo).
- Il messaggio di avvio passa da `print()` a `logging`: senza flush restava nel buffer e compariva nei log solo allo spegnimento, facendo sembrare un riavvio che non c'era stato.

**Lezione**: in questa sessione ho sbagliato **due ipotesi** dette con troppa sicurezza (esaurimento delle ore mensili del piano gratuito; intervallo del ping troppo lungo — era già a 10 minuti). In entrambi i casi è stato un dato fornito dall'utente (log di Render, poi screenshot di cron-job.org) a dare la risposta vera. Davanti a un guasto di piattaforma, chiedere i dati grezzi prima di teorizzare.

### 31/08/2026 — Sessione 13 (Revisione Opus: bug critico, invarianti, multi-stagione, Coppa)
Seconda revisione completa con Opus. Ne è uscito **un bug critico con la miccia già accesa**, più quattro lavori richiesti dall'utente.

**🔴 1. La giornata veniva confrontata per SOTTOSTRINGA**
- In 5 punti il bot filtrava le righe con `str(giornata) in str(riga[0])`: cerca `"1"` *dentro* `"Giornata 1"`, ma `"1"` è contenuto anche in **"Giornata 12"**, "Giornata 13", "Giornata 21"… Ricalcolare la Giornata 1 selezionava righe di **13 giornate diverse** (la 2 idem, la 3 ne tocca 12).
- **Danno dimostrato eseguendo la funzione vera**: una riga della Giornata 12 già vinta (2 punti) veniva riscritta a **PERSA con 0 punti**, perché agganciata al risultato della Giornata 1 tramite il fallback sull'ordine invertito — andata e ritorno hanno le stesse due squadre scambiate, quindi il fallback le considera la stessa partita. In più i punti delle righe estranee finivano sommati nella colonna della giornata ricalcolata in Classifica.
- Non se n'erano accorti perché **il problema scatta dalla Giornata 10 in poi** (circa due mesi).
- **Correzione**: nuova `riga_e_della_giornata()` con confronto esatto sul numero, applicata a tutti e 5 i punti.
- **Aggravante correlata corretta**: `ottieni_giornata_corrente()` ripiegava su `1` quando l'API non risponde, ed è usata da 4 job — un singolo errore di rete avrebbe fatto ricalcolare la Giornata 1, cioè 13 giornate. Ora ritorna `None` e tutti i chiamanti saltano il giro.

**🟠 2. Partite rinviate distinte da "in corso"**
- Tutto ciò che non era `FINISHED` diventava IN CORSO, comprese POSTPONED/SUSPENDED/CANCELLED. Ma il riepilogo di fine giornata parte solo quando nessuna riga è IN CORSO: **una partita rinviata lo avrebbe bloccato indefinitamente**.
- Nuovo esito `⏸️ RINVIATA`: 0 punti, non conta come persa, impedisce di dichiarare chiusa la schedina e di pagare la Cassa finché il recupero non è giocato (regolamento: "per i punti si aspetta il recupero"). Il riepilogo ora parte lo stesso segnalando gli eventi in attesa. Badge viola in Schedine Live.

**🟠 3. Test di invariante** (`tests/test_invarianti.py`, 101 test)
- Il bug della sottostringa è passato inosservato pur con 145 test verdi, perché ogni test guardava *un* caso e nessuno chiedeva la *proprietà*: «ricalcolare la giornata N può toccare righe di un'altra giornata?».
- Invarianti coperte: isolamento delle 38 giornate (su una stagione con andata/ritorno invertiti), nessuna giornata riconosce l'etichetta di un'altra (38×38), ogni pronostico valido ha sempre un esito deciso, gli esiti complementari (1/X/2, GOAL/NOGOAL, PARI/DISPARI, OVER/UNDER) ne hanno sempre esattamente uno vincente, le doppie chance vincono esattamente quando vince uno dei due singoli, i punti restano fra 0 e 12, nessuno stato diverso da FINISHED può pagare la Cassa.
- **Validati reintroducendo il bug**: 10 test falliscono subito. Non sono verdi per caso.

**🟡 4. Cassa: saldo ricalcolato invece che ereditato**
- Prima il saldo si leggeva dall'ultima riga e ci si sommava sopra: una correzione manuale (come i 430 € di Paolo, arrotondati sui 427,85 calcolati) o una riga fuori ordine faceva divergere il saldo in silenzio, e ogni movimento successivo ereditava l'errore. Nuova `saldo_cassa()` che somma le entrate: autocorrettiva. Verificato sul foglio vero — vecchio e nuovo metodo danno entrambi 430,00.

**🏆 5. Coppa: tabellone pronto, sfidanti sfocati**
- Il tab non è più un placeholder: tabellone completo (ottavi → quarti → semifinali → finale con trofeo) con i nomi **volutamente sfocati via CSS**, su richiesta dell'utente: la struttura è decisa e visibile, il mistero resta solo su chi incontra chi.
- Formato proposto (da confermare dal creatore del torneo): tutti e 16 i giocatori, ultime 4 giornate, ogni turno è uno scontro diretto su una giornata, parità risolta dalla classifica generale, nessuna schedina extra.

**📚 6. Supporto multi-stagione**
- La Serie A va da agosto a maggio: `etichetta_stagione()` ricava "2026-27" dalla data di inizio riportata dall'API (un input malformato dà `None` invece di un'etichetta plausibile ma sbagliata — debolezza scoperta proprio da un test).
- Nuovo comando **`/archiviastagione`**: manda prima un backup di sicurezza, chiede conferma esplicita, poi duplica Giocate/Classifica/Cassa in fogli `«... 2026-27»` e svuota quelli di lavoro lasciando le intestazioni.
- **Sicurezza dell'operazione** (l'unica che cancella dati): prima duplica *tutti* i fogli, poi **verifica che le copie esistano davvero**, e solo allora cancella. Si rifiuta di partire se un foglio manca o se l'archivio di quella stagione esiste già. Testato anche il caso in cui la duplicazione fallisce: nessuna cancellazione.

**Verifiche**: suite da 145 a **262 test**, tutti verdi. Dry-run su Giornate 1-2 ripetuto dopo *ogni* modifica: 576 celle, 0 differenze ogni volta. Sito verificato dal vivo. Versione app **2.7.0**.

**Idea scartata**: pagina profilo per giocatore (l'utente non l'ha voluta).

### 31/08/2026 — Sessione 12 (Retry mancante su Google Sheets: l'utente ha beccato l'errore in flagrante)
L'utente ha catturato uno screenshot con l'errore in diretta: `HttpError 503 ... "The service is currently unavailable."` sulla `batchGet` di Google Sheets in `app.py`. A differenza degli episodi precedenti (dove i log non bastavano a essere certi della causa), qui il messaggio è inequivocabile: è un **503 di Google Sheets stesso**, non un blip generico di piattaforma.

**Causa della lacuna**: il retry con backoff aggiunto in Sessione 10 (`api_utils.richiedi_con_retry`) copre solo le chiamate a Football-Data.org via `requests.get()`. Le chiamate a Google Sheets passano da un client completamente diverso (`googleapiclient`), che non transita mai da quella funzione — quindi restavano scoperte, ed è bastato un 503 per far fallire il caricamento dell'intera pagina.

**Correzione**: `googleapiclient` ha un meccanismo di retry integrato apposta per errori 5xx, semplicemente non lo stavamo usando — basta passare `num_retries=N` a `.execute()` (retry con backoff esponenziale e jitter, gestito internamente dalla libreria). Aggiunto `num_retries=3` a **tutte** le chiamate `.execute()`: 1 in `app.py`, 16 in `bot_telegram.py`.

**Verifiche**: aggiornati i mock nei test (accettano ora `**kwargs` su `execute()`, dato che il codice reale ora passa `num_retries`) — 145 test ancora verdi. Dry-run completo su Giornate 1-2 rifatto: 576 celle, 0 differenze. Sito e bot ricontrollati dal vivo dopo la modifica.

**Nota per il futuro**: se un'altra chiamata a Sheets viene aggiunta in seguito, ricordarsi `num_retries=3` — vedi anche la regola aggiunta in `CLAUDE.md`.

### 31/08/2026 — Sessione 11 (Frontend: frecce di tendenza, riepilogo automatico per WhatsApp, skeleton di caricamento)
Su richiesta dell'utente, tre migliorie frontend/UX dopo il giro sulla robustezza backend. Prima di proporre altre idee ho fatto una ricerca web su cosa permette Streamlit 2026 a livello grafico e cosa fanno bene le app di leghe fantasy — da lì sono nate le proposte poi accettate/scartate sotto.

**1) Frecce di tendenza in classifica** (`app.py`)
- Nuova colonna "Tend." nella Classifica completa: 🟢▲N / 🔴▼N / ⚪– per il cambio di posizione rispetto alla giornata precedente. Calcolata dai dati già in `Classifica` (nessuna chiamata API in più). Verificato a mano contro i dati reali (4 giocatori, incluso il caso estremo Michele -11 posizioni) — tutti corretti. Testati i casi limite (una sola giornata, classifica vuota): nessun crash.

**2) Riepilogo automatico di fine giornata, pronto per WhatsApp** (`bot_telegram.py`)
- Ogni mattina alle 09:15 il bot controlla se la giornata corrente è completamente conclusa (nessuna riga IN CORSO in `Giocate` — si basa sui nostri dati già protetti dall'anti-regressione, non su una nuova chiamata a Football-Data che potrebbe essere di nuovo bloccata) e, se non l'ha già mandato, invia all'admin il riepilogo: classifica ordinata con punti guadagnati in giornata, chi ha chiuso la schedina, saldo Cassa.
- **Dettaglio pensato apposta**: il messaggio usa `*grassetto*` con un solo asterisco (sintassi di WhatsApp) ed è inviato su Telegram **senza** `parse_mode`, così gli asterischi restano testo letterale invece di essere "consumati" dal rendering di Telegram — copiato e incollato su WhatsApp, il grassetto funziona lì.
- Nuovo comando **`/riepilogo`** per forzarlo a mano (utile per testare, o rimandarlo), con messaggi espliciti sul perché non ha inviato nulla (partite ancora in corso, già mandato, nessun dato).
- **Bug trovato e corretto durante il test con dati finti**: se `Cassa` ha solo la riga di intestazione (nessun movimento ancora), il codice leggeva quella riga come se fosse un dato reale, mostrando "Saldo Totale" (il nome della colonna) invece di un importo — stesso tipo di guardia già presente altrove nel codice, mancava qui.
- 16 nuovi test (funzione di costruzione del messaggio + il job schedulato con Sheets/Telegram mockati).

**Suite di test**: da 129 a **145 test**, tutti verdi. Dry-run completo su Giornate 1-2 rifatto dopo tutte le modifiche: 576 celle, 0 differenze.

**3) Skeleton animato al caricamento dati** (`app.py`)
- `carica_tutti_i_dati()` (la chiamata batchGet a Google Sheets, prima di tutto il resto della pagina) ora gira dentro `with st.skeleton(height=420):` — funzionalità nativa di Streamlit 2026, nessuna libreria esterna. Mostra un placeholder animato al posto di una pagina bianca quando il caricamento richiede un attimo percepibile (cache scaduta dopo 3 minuti, o dopo aver premuto "Aggiorna"); se la cache è calda, Streamlit lo salta da solo senza sfarfallio.
- **Verificato dal vivo iniettando un ritardo artificiale** (15s, poi rimosso) per catturare lo skeleton a schermo, dato che il caricamento reale è troppo rapido per osservarlo altrimenti: confermato che appare correttamente e sparisce da solo a fine caricamento, poi ripristinato il codice originale e ricontrollato che il comportamento normale (veloce, senza flash) resti intatto.

**Idee scartate dopo discussione**: grafico andamento punti nel tempo, countdown prossima partita, notifiche push in tempo reale per ogni evento (troppo rumore per un gruppo di 16 amici che si coordina già su Telegram/WhatsApp).

### 31/08/2026 — Sessione 10 (Robustezza backend: retry, girone di ritorno, backup)
Su richiesta dell'utente, tre migliorie mirate a "irrobustire" backend e sito, dopo aver valutato e **scartato** il passaggio a un database vero (nessuno degli incidenti finora è nato da Google Sheets; il costo di migrazione sarebbe alto per 16 utenti, vedi discussione in chat).

**1) Retry con backoff su tutte le chiamate a Football-Data.org**
- Nuovo modulo condiviso `api_utils.py` (`richiedi_con_retry`), usato sia da `app.py` che da `bot_telegram.py`: fino a 3 tentativi con attesa crescente prima di rilanciare l'eccezione al chiamante — copre i blip di rete transitori (come nell'incidente del 30/08) senza mascherare un guasto vero.
- Sostituite tutte le chiamate dirette `requests.get()` a Football-Data (2 in `app.py`, 7 in `bot_telegram.py`).
- 6 nuovi test con rete mockata + verifica contro l'API reale + dry-run completo (576 celle, 0 differenze).

**2) Test dedicato al girone di ritorno** (`tests/test_girone_di_ritorno.py`)
- 4 test: andata/ritorno della stessa coppia di squadre segnate in modo indipendente senza contaminazione reciproca; il ritorno scritto con l'ordine "vecchio" (quello dell'andata) viene comunque valutato correttamente grazie al fallback sull'ordine invertito (Sessione 7); nessuna collisione tra i prefissi "Milan"/"Inter" nel matching.
- **Validati non banali**: ho iniettato deliberatamente un bug nello scambio dei gol e verificato che il test lo intercetti (fallisce come previsto), prima di ripristinare il codice corretto — non erano verdi per caso.

**3) Backup settimanale automatico** (`task_backup_periodico`)
- Ogni lunedì alle 09:00 (fuso Europe/Rome), il bot esporta Giocate/Classifica/Cassa in un JSON e lo manda come documento all'admin su Telegram — una copia dei dati fuori da Google, richiamabile anche a mano col nuovo comando **`/backup`**.
- Il file locale viene sempre cancellato dopo l'invio (anche se l'invio fallisce, grazie a un `finally`): su Render il disco è comunque effimero, Telegram è la copia che conta. `backup_toto_amici_*.json` aggiunto a `.gitignore` come rete di sicurezza.
- Verificato con dati reali (321 righe Giocate, 17 Classifica, 2 Cassa esportate correttamente) sia il percorso di successo che quello di fallimento (nessun file orfano, admin avvisato). 5 test automatici aggiunti in `tests/test_backup.py`.

**Suite di test**: da 114 a **129 test**, tutti verdi.

### 31/08/2026 — Sessione 9 (Riavvio inatteso del bot su Render)
**Segnalato dall'utente**: alle 07:18 (05:18 UTC) il bot su Render è andato in "instance failed" e si è riavviato da solo. Anche il sito ha dato "Service Unavailable" per un momento nella stessa giornata, ma senza nulla nei log di Streamlit Cloud — verosimilmente un blip infrastrutturale non riconducibile al nostro codice (non genera mai quel messaggio).

**Analisi del log Render fornito dall'utente**: l'ultima riga prima del riavvio è `file_cache is only supported with oauth2client<4.0.0` — stampata sempre da `googleapiclient` quando costruisce un client Sheets da zero — seguita subito da `==> Running 'python bot_telegram.py'` (il marcatore di Render per un riavvio del processo), **senza nessun traceback Python in mezzo**. L'assenza di un errore Python gestito è il segnale tipico di un kill esterno (OOM o riavvio forzato dalla piattaforma), non di un'eccezione nel nostro codice. Il timing coincide esattamente con `task_controlla_anomalie_partite` (schedulata ogni 2 ore) che chiama `connetti_sheets()`.

**Trovato e corretto**: `connetti_sheets()` **ricostruiva l'intero client Google Sheets da zero ad ogni chiamata** (rilettura credenziali + `build()`, che ri-scopre l'API), invece di riusare un'istanza — lo stesso problema già risolto in `app.py` con `@st.cache_resource`, mai applicato al bot. Con job schedulati fino a ~20+ volte/giorno (monitoraggio ogni 2h, calcolo risultati 5x/giorno, comandi manuali), è un carico ripetuto e non necessario su un piano Render da 512MB — una causa plausibile (non certa: non ho accesso alle metriche di memoria di Render) del riavvio.

**Correzione**: `connetti_sheets()` ora costruisce il client una sola volta e lo riusa (stesso pattern di `app.py`); il token OAuth del service account si rinnova comunque da solo quando serve, quindi è sicuro. Verificato: `build()` chiamata 1 sola volta su 3 richieste consecutive, stessa istanza riusata, connessione funzionante. Dry-run completo su Giornate 1 e 2 dopo la modifica: **576 celle ricalcolate, 0 differenze**.

**Nota per il futuro**: non ho accesso ai log/metriche di Streamlit Cloud né di Render (nessuna credenziale per quelle piattaforme in questo ambiente) — l'analisi si è basata solo sul frammento di log incollato dall'utente. Se il riavvio si ripete anche dopo questa correzione, andrebbe controllato il grafico di utilizzo memoria nel pannello Render per confermare o escludere l'OOM.

### 30/08/2026 — Sessione 8 (Revisione con Opus: due bug latenti gravi, primi test automatici)
Sessione nata da una richiesta di idee/migliorie, trasformata in revisione del codice. Sono emersi **due bug latenti mai andati in produzione ma già armati**, entrambi corretti.

**🔴 1. Il calcolo esiti assegnava VINTA a qualsiasi pronostico non riconosciuto** (`controlla_esito`)
- La funzione partiva da `vinta = True` e la smentiva solo se una regola nota falliva: se **nessuna** regola corrispondeva, l'esito restava "vinto". Quindi `SI`, `2X`, `X1`, `OVER 2.5` (con spazio), un mercato nuovo, o **un pronostico vuoto** (lettura IA fallita) diventavano punti regalati **in silenzio**.
- **I bug "SI" e "2X" delle Sessioni 6/7 non erano due incidenti separati: erano lo stesso difetto strutturale manifestatosi due volte.** Ogni volta si era aggiunto l'alias mancante, lasciando la trappola armata per il formato successivo.
- **Correzione**: logica invertita. Nuova `valuta_singolo_segno()` che ritorna `True`/`False`/`None`; `None` = segno sconosciuto → l'intero pronostico diventa `ESITO_DA_VERIFICARE` ("⚠️ DA VERIFICARE"), 0 punti, cella gialla, e il report Telegram elenca esattamente le righe da correggere.
- **Protezioni a valle** (la parte più delicata): una riga da verificare **non** conta come persa (non marcherebbe la schedina "bruciata" a torto) e **blocca la dichiarazione di schedina chiusa** — altrimenti +10 punti e un pagamento in Cassa sarebbero partiti su dati non verificati. Verificato end-to-end con uno scenario costruito apposta.

**🔴 2. Le vincite a quattro cifre finivano in Cassa divise per mille** (`estrai_numero`)
- `estrai_numero` faceva solo `replace(',', '.')`: `"1.674,56"` diventava `"1.674.56"` e il match si fermava a **1.674**. La stessa funzione legge la Vincita Potenziale da cui si calcola il 50% da versare in Cassa → alla prima schedina chiusa sopra i mille euro, in Cassa sarebbero finiti **0,84 €** invece di 837,28 €.
- Nessun dato storico intaccato: l'unica schedina chiusa finora (Paolo, 855,70) era sotto la soglia. Ma nel foglio ci sono già vincite potenziali da 1.008,29 / 1.674,56 / 2.414,56.
- **Correzione**: parsing esplicito del formato italiano (punto = migliaia, virgola = decimali). È lo stesso difetto corretto in `app.py` in Sessione 6, che era rimasto nel bot.

**🟠 3. Semper Fidelis: una chiamata API per giornata, sarebbe esplosa a metà stagione**
- La statistica iterava sulle giornate chiamando `scarica_risultati_api` per ciascuna. Con 2 giornate = 2 chiamate; dalla **giornata ~11** avrebbe superato il rate limit di **10 richieste/minuto**, e i risultati vuoti sarebbero stati messi in cache 180s degradando anche gli altri tab.
- **Correzione**: nuova `scarica_squadre_serie_a()` — endpoint `/competitions/SA/teams`, **una sola chiamata** per l'intera stagione (cache 24h), dato che i nomi squadra non cambiano. Verificato: stesso identico risultato (GIOVANNI → Juventus FC, 2×) con 1 chiamata invece di N.

**🟠 4. Primi test automatici del progetto** (`tests/test_logica_bot.py`, 114 test)
- Coprono `normalizza_pronostico`, `valuta_singolo_segno`, `controlla_esito`, `calcola_punteggio_partita`, `estrai_numero`, con test di regressione espliciti legati a ogni incidente realmente accaduto (SI, 2X, migliaia, ordine invertito).
- Aggiunto `requirements-dev.txt` (la produzione continua a usare solo `requirements.txt`). Eseguire con `python3 -m pytest tests/ -v`.

**🟡 5. Chiave Gemini resa stabile ai riavvii**
- `/setkey` scrive su `chiave_api.txt`, ma su Render il filesystem è effimero e i Secret File sono in sola lettura: la chiave nuova sarebbe tornata silenziosamente a quella vecchia al riavvio. `leggi_chiave_api()` ora legge **prima** la variabile d'ambiente `GEMINI_API_KEY` (stabile fra i riavvii) e usa il file come fallback; i messaggi di `/setkey` avvisano di questo.
- **Azione consigliata per l'utente**: impostare `GEMINI_API_KEY` come variabile d'ambiente su Render.

**Verifiche eseguite prima del push** (nessuna modifica ai dati reali):
- 114 test unitari verdi
- Dry-run completo di `esegui_calcolo_risultati` su Giornate 1 e 2 dopo *tutte* le modifiche: **512 celle ricalcolate, 0 differenze**, 0 cambiamenti in Classifica, 0 movimenti di Cassa spuri
- Scenario costruito: schedina vincente con una riga non interpretabile → confermato 0 punti, niente "chiusa", niente +10, niente pagamento in Cassa
- `applica_risultato_manuale` ancora idempotente; monitoraggio anomalie e deduplica avvisi funzionanti
- Tutti e 6 i tab del sito renderizzati senza errori in console né nei log del server

**Valutato e scartato**: tracciare le quote di partecipazione (200€ a testa) — il gruppo si vede di persona, la rigidità non serve.

### 30/08/2026 — Sessione 7 (Versionamento, changelog in-app, monitoraggio, fix ordine invertito)
- ✅ **Versione app**: aggiunto `VERSIONE_APP` + lista `NOVITA` in `app.py`, mostrati sotto al titolo in un expander pensato per i giocatori (linguaggio semplice, non tecnico). Versione attuale calcolata ripercorrendo le sessioni: **2.5.0** (2.0.0 = redesign Sessione 2, poi una minor per sessione di funzionalità). Convenzione documentata in `CLAUDE.md`: aggiornare ad ogni release.
- ✅ **Monitoraggio automatico anomalie** (`bot_telegram.py`, `task_controlla_anomalie_partite`, ogni 2 ore): avvisa l'admin se una partita è iniziata da oltre 3 ore senza risultare FINISHED, oppure se una riga di Giocate ancora IN CORSO non trova corrispondenza in nessuna partita ufficiale della giornata.
- ✅ **Fix bug ordine invertito** (`esegui_calcolo_risultati`): il matching partita controllava solo l'ordine diretto (squadra scritta per prima = casa secondo l'API) — se la normalizzazione falliva all'upload e l'ordine restava invertito, la riga restava IN CORSO per sempre senza errori. Ora si ritenta con l'ordine scambiato e si scambiano di conseguenza i gol per calcolare correttamente l'esito. **Verificato con un dry-run completo su Giornata 1 e 2** (320+192 celle ricalcolate, zero differenze rispetto ai dati già salvati) prima di pubblicare.
- ✅ Rimosse dalla TODO le statistiche avanzate non volute dall'utente.
- ✅ **Comando admin "Inserisci Risultato Manuale"** implementato: menu → giornata → partita (bottoni) → risultato in formato rigido `N-M` (regex, blocca a priori qualsiasi "formula injection" su Sheets) → conferma esplicita → `applica_risultato_manuale()` forza solo quella partita mantenendo intatte le altre della giornata, riusando `esegui_calcolo_risultati` (ora accetta `matches_api` opzionale). Verificato in dry-run: idempotente su risultati già corretti, tocca solo le righe giuste su un risultato nuovo. Il Flusso 1 (correzione di un singolo pronostico già scritto) resta solo progettato, non implementato — utile se serve in futuro.
- ✅ **Orari extra di verifica automatica**: aggiunti 01:00 e 08:00 ai tre già esistenti (17:30/20:30/23:00), per avere più occasioni di catturare un dato corretto prima di un'eventuale rielaborazione notturna lato Football-Data. Totale stimato ~35 chiamate/giorno all'API, ampiamente sotto i limiti free tier.
- ✅ **Deduplica avvisi anomalie**: `task_controlla_anomalie_partite` avvisava ad ogni controllo (ogni 2 ore) anche per la stessa anomalia persistente — rumoroso quando un problema dura giorni come quello del 30/08. Ora confronta contro l'ultimo set di anomalie segnalate (identità stabile, non il testo con le ore trascorse) e avvisa solo su cambiamento (nuova anomalia, o risoluzione di una precedente).

### 30/08/2026 — Sessione 6 (Incidente dati Football-Data, manutenzione, fix normalizzazione)
**Incidente — dati Football-Data.org regrediti su Giornata 2:**
- ⚠️ Scoperto che football-data.org restituiva `TIMED`/punteggio `null` per partite di Giornata 2 già `FINISHED` in run precedenti (Sassuolo-Torino, Monza-Udinese, Fiorentina-Frosinone, Juventus-Parma). Confermato **non** essere un problema del nostro account: stessa risposta sbagliata sia con la chiave nuova che con quella vecchia. Colpiva solo il turno "corrente"/appena concluso — Giornata 1 (archiviata) e dati storici di altre competizioni restavano perfetti sulle stesse chiavi. Ipotesi più probabile: problema temporaneo di elaborazione lato loro sul turno live, non un difetto strutturale del provider — **non è stato deciso di cambiare provider**, da rivalutare solo se il pattern si ripete nei prossimi turni.
- ✅ **Sito messo in manutenzione temporanea** (`app.py`, flag `MANUTENZIONE`) finché i dati non sono stati verificati — poi rimesso online lo stesso giorno.
- ✅ **Blindato `esegui_calcolo_risultati`** (`bot_telegram.py`): se una riga ha già un esito finale (VINTA/PERSA/ANNULLATA) e l'API dice che la partita non è FINISHED, non si retrocede più il dato — si mantiene quello già salvato. Non risolve il problema a monte (partite mai processate restano IN CORSO finché l'API non guarisce).
- ✅ **Ripristinati manualmente i risultati reali delle 4 partite** (Sassuolo-Torino 2-1, Monza-Udinese 2-3, Fiorentina-Frosinone 0-3, Juventus-Parma 2-0, verificati incrociando pronostici/punti già salvati per altri giocatori) rieseguendo `esegui_calcolo_risultati` con l'API mockata sui risultati reali invece che chiamare l'endpoint rotto — stessa logica del bot, nessuna scorciatoia manuale sui punteggi.
- ✅ **Fix UI**: in Schedine Live, se l'Esito è già finale ma il live-fetch dice ancora "Da giocare" (disallineamento con l'incidente sopra), il badge "Risultato" contraddittorio ora viene nascosto invece di mostrare un'informazione fuorviante.

**Bug di normalizzazione confermati e corretti:**
- ✅ Pronostici doppia chance scritti in ordine invertito (`2X`, `X1`, `21`) non venivano riconosciuti da `controlla_esito` → sarebbero sempre risultati vinti a prescindere dal risultato reale. Aggiunti gli alias (`normalizza_pronostico`), sia per pronostici singoli che dentro le combo. Corretta anche la riga già salvata di Michele (Sassuolo-Torino, era ancora IN CORSO, nessun ricalcolo necessario).

**Altri fix minori:**
- ✅ Confronto giocate: la riga "Vincita potenziale" mostrava 0€ per vincite oltre i 1.000€ — il parsing non gestiva il punto delle migliaia del formato italiano (`1.674,56` → `1.674.56`, non convertibile). Aggiunto anche il separatore delle migliaia in visualizzazione.
- ✅ Semper Fidelis: ora anche le doppie chance (1X/X2) contano come voto per la squadra corrispondente, non solo le fisse pure (1/2) — "12" resta escluso (non favorisce una squadra specifica). Rimossa la spiegazione ridondante sotto la card.
- ✅ Cassa Giornata 1: corretto manualmente a 430,00€ (Paolo ha versato in contanti una cifra arrotondata, non i 427,85€ calcolati) — **solo** su `Entrate`/`Saldo Totale` in Cassa, la Vincita Potenziale in Giocate resta quella reale (855,70€).

**Idea proposta, in attesa di decisione:** comando admin per inserire/correggere dati a mano dal bot (vedi TODO) — utile visto l'incidente di oggi.

### 29-30/08/2026 — Sessione 5 (Sicurezza, rotazione chiavi, UI/statistiche, fix bot)
**Sicurezza:**
- ✅ Rigenerati `TELEGRAM_TOKEN` (via @BotFather) e `FOOTBALL_DATA_KEY` (nuovo account football-data.org, il piano free non ha un vero "rigenera token"), aggiornati su Render, Streamlit Cloud e file locali (`.env`, `.streamlit/secrets.toml`)
- ✅ Eliminato `test_api.py` (conteneva una API key api-sports.io in chiaro, pubblica su GitHub)
- ✅ Corretta manualmente su Google Sheets la riga Michele/Giornata 2/Lazio-Genoa: pronostico `SI` → `GOAL`

**UI (`app.py`):**
- ✅ Rimossa la classifica live provvisoria (quella definitiva si aggiorna già ad ogni evento concluso)
- ✅ Confronto giocate: asterisco sulle quote ≥3.50 (punti doppi), riga totale vincita potenziale per giocatore, prima colonna (partita) fissa durante lo scroll orizzontale — testato su mobile
- ✅ Regolamento: sezioni riordinate per leggersi 1-2-3-4 anche su mobile, tipologie di giocata in ordine crescente (Combo, Doppie Chance, Variabili, Fisse)
- ✅ Menu "Giocatore" in Schedine Live: da dropdown a `st.pills` (chip toccabili, niente tastiera su mobile) — testato dal vivo
- ✅ Statistiche: aggiunte "Quello che ha bisogno di una benedizione" (contrario del Cecchino, win rate più basso), "Giornata da incorniciare" (record punti in una singola giornata, con nome giocatore e giornata), "Semper Fidelis" (giocatore che ripete più spesso lo stesso segno sulla stessa squadra, con spiegazione visibile in pagina); "La squadra maledetta" ora con `delta_color="inverse"` come "benedizione"
- ✅ Fondo Cassa: mini grafico a barre dei versamenti per giornata (incluse le giornate a zero), dentro l'expander "Movimenti di cassa" — attenzione, `st.bar_chart` ordina alfabeticamente un indice stringa ("Giornata 10" prima di "Giornata 2"): risolto usando il numero di giornata come indice
- ✅ Nuovo tab "Coppa": placeholder "In arrivo prossimamente..." in attesa del formato eliminazione diretta (vedi TODO)
- ✅ Deciso di **non** aggiungere badge emoji 🔥/❄️ per striscia vincente/perdente in classifica: essendo pronostici calcio, la maggior parte del tempo il segnale sarebbe negativo per la maggioranza dei giocatori — scartata

**Bot (`bot_telegram.py`):**
- ✅ **Fix bug promemoria schedine mancanti**: `task_schedula_promemoria` cercava le partite per "giornata corrente" (`ottieni_giornata_corrente()`), che può restare ferma sulla giornata precedente per ore dopo l'inizio del turno — causa nota di un alert arrivato di sabato invece che venerdì. Ora cerca le partite di oggi per **data** (`dateFrom`/`dateTo`) e legge la giornata dal campo `matchday` della partita stessa, passandola esplicitamente al job successivo
- ✅ Rafforzato il prompt IA e aggiunto fallback in `normalizza_pronostico` contro pronostici bare "SI"/"NO"/"SÌ" (bug di normalizzazione sui mercati Sì/No tipo "Entrambe le squadre segnano")
- ✅ **Fix bug "il bot si blocca"**: le chiamate sincrone e lente (lettura IA Gemini, `esegui_calcolo_risultati`, scritture Sheets) bloccavano l'intero event loop del bot, rendendolo non responsivo finché non finivano — spostate su thread separati con `asyncio.to_thread`
- ✅ Nuovo comando `/status`: giornata corrente e schedine mancanti a colpo d'occhio, senza aprire la dashboard

**Note tecniche:**
- Aggiunto `.claude/launch.json` per avviare l'anteprima Streamlit locale da Claude Code (nessun segreto, committato)

### 28/08/2026 — Sessione 4 (UX avanzata, Classifica Live, Notifica Schedine)
**Operazioni eseguite:**
- ✅ Notifica Schedine Mancanti (`bot_telegram.py`): ogni giorno alle 10:00 il bot controlla se ci sono partite in giornata e schedula un promemoria 30 minuti prima della prima partita, avvisando l'admin con la lista di chi non ha ancora caricato la schedina.
- ✅ Indicatore Ultimo Aggiornamento (`app.py`): timestamp "Agg. HH:MM" accanto al pulsante Aggiorna per sapere quanto sono freschi i dati.
- ✅ KPI Cassa migliorato (`app.py`): aggiunto label esplicito `€ X / € Y` sopra la progress bar del montepremi.
- ✅ Colori Esiti nel Confronto (`app.py`): nella tabella pivot del tab Confronto, le celle sono ora colorate verde (semi-trasparente) per pronostici vinti e rosso per persi. Funziona sia in dark che in light mode. Aggiunta anche icona ✅/❌.
- ✅ Gestione Errori API Football-Data (`app.py`): messaggio di warning esplicito "Dati live non disponibili momentaneamente" se l'API non risponde o restituisce errore.
- ✅ Tiebreaker Classifica (`app.py`): in caso di parità di punti, il giocatore con più pronostici vinti si posiziona sopra.
- ✅ Classifica Live Provvisoria (`app.py`): nuovo expander "Classifica provvisoria di giornata" sotto il podio che mostra i punti provvisori delle partite in corso sommati ai definitivi. Appare solo durante le partite.
- ✅ Avvisi Intelligenti nel Bot (`bot_telegram.py`): nel riepilogo post-lettura IA, il bot ora segnala automaticamente anomalie: vincita non rilevata, eventi mancanti, eccessi per categoria, totale eventi < 10.
- ✅ Numerazione ordinale classifica (`app.py`): aggiunto 🥇 1°, 🥈 2°, 🥉 3°, 4°... nella tabella classifica.
- ✅ Fix Confronto (`app.py`): rimosse le emoji (✅/❌) dalle celle della tabella pivot per risparmiare spazio, mantenendo solo i colori verde/rosso. Aggiunti bordi alle celle per migliorare la leggibilità.
- ✅ Fix Schedine Live (`app.py`): le partite ora sono mostrate in ordine di orario di inizio.
- ✅ Fix Podio (`app.py`): rimosso il grafico a barre sparkline per migliorare la resa estetica con poche giornate giocate.
- ✅ Normalizzazione Pronostici Avanzata (`bot_telegram.py`): aggiornato il `PROMPT_IA` per forzare Gemini a restituire solo formati puliti ed esatti (es. `1`, `OVER_2.5`, `X2+GOAL`), vietando l'uso di prefissi (es. "ESITO FINALE:") o nomi di squadre.
- ✅ Pulizia Storico DB Avanzata: eseguito un secondo script (`fix_sheets_v2.py`) che ha intersecato i nomi delle squadre con i dati dell'API Football-Data per mappare correttamente "MILAN", "ROMA", ecc. nei rispettivi segni `1` o `2` e ripulire tutte le vecchie bollette sporche della Giornata 2.

- ✅ Fix Confronto (`app.py`): rimosso il testo `Partita_Pulita` dall'intestazione della tabella pivot per pulire l'interfaccia.

**Reminders:**
- ⚠️ Ricordare al creatore del torneo di aggiungere nel regolamento ufficiale la gestione dei pareggi (il tiebreaker basato sul maggior numero di pronostici vinti).
- ⚠️ Se il creatore approva la regola sui pareggi, aggiungerla anche nella pagina Regolamento (`app.py`) dell'app.

### 27/08/2026 — Sessione 3 (Sicurezza e Human-in-the-loop)
**Operazioni eseguite:**
- ✅ Implementata Conferma Umana IA (`bot_telegram.py`): ora Gemini restituisce un riepilogo testuale formattato (invece di scrivere direttamente su Sheets). L'admin deve premere "✅ Conferma e Salva" (o "❌ Annulla") prima di confermare.
- ✅ Implementato Health-Check (`bot_telegram.py`): aggiunto un controllo nel server Flask. Se il bot non riceve un ping (es. da cron-job.org) per più di 30 minuti, alla prima accensione utile manda un allarme su Telegram all'admin avvisando del downtime.
- ✅ Aggiunte Data e Orari in Schedine Live (`app.py`): il frontend estrae ora `utcDate` dalle API di Football-Data, le converte al fuso `Europe/Rome` e le mostra accanto alle partite in diretta (es. 🗓️ 27/08 20:45).
- ✅ Ottimizzazione UI e UX (`app.py`): convertiti tutti gli `st.dataframe` in `st.table` (tabelle native HTML) per disabilitare la fastidiosa selezione azzurra delle celle su mobile durante lo scrolling.
- ✅ Ottimizzazione Caching (`app.py`): regolato il TTL della cache a 180 secondi (3 minuti). Bilanciamento perfetto tra reattività immediata per l'utente e bassissimo impatto sui limiti della API gratuita di Football-Data (massimo 1 richiesta API ogni 3 minuti per view). L'utente può comunque usare il tasto "Aggiorna" per forzare un refresh.

### 27/08/2026 — Sessione 2 (Redesign Web App)
**Operazioni eseguite:**
- ✅ Redesign completo `app.py`: tema scuro, card con bordi, podio con sparkline, badge nativi, icone Material Symbols
- ✅ Creato `.streamlit/config.toml` con tema scuro + chiaro automatico (segue sistema operativo utente)
- ✅ Fix `.gitignore`: ora esclude solo `secrets.toml`, non tutta la cartella `.streamlit/` → `config.toml` viene committato e visto da Streamlit Cloud
- ✅ Performance: `@st.cache_resource` per il service Sheets + singola chiamata `batchGet` (1 richiesta invece di 3)
- ✅ Fix bug win rate: esclude esiti IN CORSO e vuoti dal calcolo percentuale
- ✅ Fix squadra maledetta: delta allineato visivamente alle altre statistiche
- ✅ Fix ArrowInvalid: colonne numeriche miste nella tabella punteggi ora tutte stringhe
- ✅ Credenziali: doppio livello locale (`credenziali.json`) / cloud (`st.secrets`) per sviluppo senza problemi di parsing TOML

**Note architettura:**
- Il tema light/dark segue automaticamente il sistema dell'utente (iPhone dark → app dark, iPhone light → app light)
- Il toggle manuale è accessibile da ⋮ → Settings → Theme (nascosto dall'header CSS, ma il sistema auto funziona)

**Operazioni eseguite:**
- ✅ Analisi completa del codebase e dell'architettura
- ✅ Confermata obsolescenza di `bot_lettore.py` e `calcola_risultati.py` (funzioni migrate in `bot_telegram.py`)
- ✅ Archiviati `bot_lettore.py` e `calcola_risultati.py` in `_archivio/` (rimosso SPREADSHEET_ID hardcoded da `bot_lettore.py`, aggiunto header di archivio a entrambi)
- ✅ Eliminato `info project.txt` (note personali non aggiornate)
- ✅ Creato `PROJECT_LOG.md` (questo file) come memoria persistente del progetto

**Scoperte sicurezza (risolte il 29-30/08/2026, vedi Sessione 5):**
- ⚠️ Trovati nella history git (commit storici pubblici su GitHub): `TELEGRAM_TOKEN` e `FOOTBALL_DATA_KEY` in chiaro in vari commit — **entrambe le chiavi sono state rigenerate e sostituite** su Render/Streamlit Cloud/locale. Le vecchie chiavi restano nella history git ma sono ormai revocate e innocue.
- ⚠️ `test_api.py` (tracciato in git, pubblico) conteneva una API key di api-sports.io in chiaro — file eliminato.
- **File attuali**: nessuna credenziale in chiaro nel codice corrente.

---

## 📋 TODO / Azioni Pendenti

### 🔴 Priorità Alta — Da fare ASAP
- [ ] **Rimuovere `RISULTATI_MANUALI` da `app.py`** (aggiunta in Sessione 6) non appena Football-Data.org torna a riportare correttamente le 4 partite di Giornata 2 (Sassuolo-Torino, Monza-Udinese, Fiorentina-Frosinone, Juventus-Parma) — è una toppa temporanea con punteggi scritti a mano, non deve restare nel codice più del necessario.
- [x] ~~**STRESS TEST REVISIONE CLAUDE**~~ — svolto in Sessione 8: revisione completa che ha portato alla luce due bug latenti gravi (esiti "vinti per default", vincite a quattro cifre in Cassa) e alla prima suite di test automatici.
- [ ] **Impostare `GEMINI_API_KEY` come variabile d'ambiente su Render** (Sessione 8): senza, una chiave cambiata con `/setkey` torna silenziosamente a quella vecchia al primo riavvio.
- [ ] **Coppa a eliminazione diretta** (nuova, priorità alta in vista del finale di campionato): ottavi, quarti, semifinale, finale tra i migliori giocatori. Il tab "Coppa" in `app.py` mostra per ora solo un placeholder "In arrivo prossimamente...". **Da decidere prima di poter implementare:** criterio di qualificazione/seeding (es. classifica generale?), come si estraggono gli accoppiamenti, formato delle singole sfide (una schedina di sfida diretta? somma punti su più giornate?), quando parte rispetto alla fine del campionato.

### 🟡 Priorità Media — Prossime sessioni
- [ ] **Crescita memoria con l'accumularsi delle giornate** (Sessione 15): il 01/09/2026 Render ha ucciso il processo per superamento del limite di memoria (mail "exceeded memory limit"), riavviato da Render stessa in autonomia. Il crash coincide esattamente con l'orario di `task_aggiornamento_automatico` (20:30/23:00 CEST) — correlazione precisa ma su un solo evento, non ancora una prova. Cosa si sa per certo: `esegui_calcolo_risultati` (chiamata da quel task, 2 volte al giorno + su richiesta admin) rilegge per intero `Giocate!A:I` a ogni chiamata anche se elabora solo una giornata; `task_controlla_anomalie_partite` (ogni 2h, quindi il più frequente) rilegge per intero `Giocate!A:G`; `task_backup_periodico` (settimanale) fa un `batchGet` su tutto `Giocate!A:I`. Tutte e tre crescono linearmente con le giornate giocate in stagione (16 giocatori × 10 partite/giornata). Non sono la prova certa del crash, ma sono l'unico meccanismo concreto nel codice che peggiora con l'andare avanti del campionato. **Prima mossa se ricapita**: aggiungere un log di `resource.getrusage(...).ru_maxrss` (o `psutil`) a inizio/fine di `esegui_calcolo_risultati` e `task_controlla_anomalie_partite`, per avere numeri reali invece di una correlazione temporale. Altre leve, da valutare solo se il problema si ripresenta: abbassare la frequenza di `task_controlla_anomalie_partite` (2h → 4-6h, è il meno critico dei tre); far leggere a queste funzioni solo le righe della giornata invece di tutto il foglio (richiede una ricerca preliminare più leggera del range di riga — cambio non banale, da fare con test di non-regressione). La crescita comunque NON è illimitata anno su anno: `archivia_stagione()` (Sessione 13) svuota i fogli a fine stagione, quindi il tetto massimo resta legato a una sola stagione (~38 giornate), non accumula per sempre.
- [ ] **Secondo controllore esterno (UptimeRobot o simile)** — deciso in Sessione 14 di **non** farlo per ora, ma tenerlo pronto. Oggi le fonti di keep-alive sono due (auto-ping interno + cron-job.org); un terzo controllore gratuito indipendente (ping ogni 5 min) coprirebbe anche il caso in cui il processo muore davvero, che l'auto-ping per definizione non può gestire. Da valutare se il problema si ripresenta.
- [x] ~~**Girone di ritorno**~~ — svolto in Sessione 10 (`tests/test_girone_di_ritorno.py`, 4 test): andata/ritorno indipendenti senza contaminazione, ordine invertito nel ritorno gestito correttamente (verificato iniettando il bug e controllando che il test lo scopra), nessuna collisione di prefisso Milan/Inter. Resta genericamente da tenere d'occhio la robustezza con moli di dati molto più grandi (fine campionato).
- [ ] **Multi-admin**: possibilità in futuro di aprire l'accesso al bot ad altri utenti admin (oltre a `ADMIN_ID`), che potrebbero così caricare schedine e correggere dati anche loro. Oggi il bot riconosce un solo `ADMIN_ID` hardcoded dall'env var — servirebbe passare a una lista di ID autorizzati (`ADMIN_IDS`) con lo stesso controllo ovunque viene fatto `update.effective_user.id != ADMIN_ID`.
- [ ] **Modifica dati anche dalla web app** — valutato in Sessione 7, **sconsigliato per ora**: la Web App oggi è pubblica, senza alcun sistema di login, e legge Sheets in sola lettura (`spreadsheets.readonly`); aggiungere una modalità di scrittura richiederebbe (a) costruire un sistema di autenticazione admin dentro Streamlit da zero, (b) dare a un'app pubblica credenziali di scrittura su Sheets, aumentando la superficie d'attacco rispetto al bot Telegram (che ha già l'identità admin gratis tramite `ADMIN_ID`), (c) duplicare la logica di correzione in due posti invece di uno, con rischio di comportamenti divergenti. Il comando admin nel bot copre già il bisogno pratico. Da rivalutare solo se emerge un'esigenza che il bot non riesce a coprire.

### 🟢 Idee Future
- [ ] Pagina pubblica per ogni giocatore con le sue statistiche personali
- [ ] ~~Integrazione con calendario Serie A (avvisi pre-partita)~~ — scartata, valore aggiunto marginale rispetto a Schedine Live + promemoria schedine mancanti già esistenti

---

## 🤖 Note per Agenti IA Futuri

- Il **bot Telegram** è il cuore operativo del sistema. Contiene tutta la logica di: lettura IA schedine, validazione regole, scrittura su Sheets, calcolo risultati, aggiornamento classifica e cassa.
- La **Web App** è read-only: legge da Sheets e mostra dati. Non scrive mai nulla.
- I **file archiviati** in `_archivio/` sono intenzionalmente obsoleti ma mantenuti come backup manuale.
- Le **credenziali GCP** (`credenziali.json`) vengono iniettate come Secret File su Render e come `gcp_service_account` (JSON inline) su Streamlit Secrets.
- La **chiave Gemini** viene letta dal file `chiave_api.txt` (su Render è un Secret File), aggiornabile al volo via comando Telegram `/setkey`.
