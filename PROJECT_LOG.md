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
| `ADMIN_ID` | Render (Environment Variables) | ID Telegram dell'**owner**: l'unico che può usare `/setkey` e `/archiviastagione` |
| `ADMIN_IDS` | Render (Environment Variables, opzionale) | Altri admin autorizzati, separati da virgola (es. `123456,789012`). Fanno tutta la gestione quotidiana; l'owner è sempre incluso anche se non elencato |
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

### 19/09/2026 — Sessione 24 (Multi-admin: owner + admin, notifiche a tutti, tracciabilità in chat)

> *Nota di numerazione: i test di consistenza sugli inserimenti (`tests/test_consistenza_inserimenti.py`, commit `74af8ee`) si dichiarano "Sessione 23" ma non hanno un proprio blocco qui.*

**Il bot riconosceva un solo `ADMIN_ID`. Ora riconosce una lista, con due livelli.** Implementato il TODO analizzato in Sessione 17 senza scriverlo. Le due decisioni che erano rimaste aperte, prese dall'utente all'inizio della sessione:

- **Due livelli, non uno.** `ADMIN_ID` resta l'**owner**: è l'unico che può usare `/setkey` (tocca una credenziale) e `/archiviastagione` (l'unica operazione che cancella dati). Gli altri admin, elencati nella nuova variabile `ADMIN_IDS`, fanno **tutta la gestione quotidiana**: caricamento schedine, aggiornamento risultati, correzioni manuali, `/status`, `/diagnostica`, `/backup`, `/riepilogo`.
- **Tracciabilità in chat, non su Sheets.** Chi compie un'azione che tocca punteggi o Cassa riceve l'esito completo; gli **altri** admin ricevono una riga breve — «👤 *Dario* ha inserito a mano Inter 2-1 Roma (Giornata 5)». Niente colonne nuove sul foglio: avrebbe voluto dire toccare la scrittura per indice di riga, la stessa area del bug che riscrisse 13 giornate (Sessione 13). Tracciate: correzione manuale di un risultato, ricalcolo di una giornata, archiviazione stagione. Ogni azione finisce anche nei log di Render (`AZIONE ADMIN — ...`).

**La parte che non si vede: le 18 notifiche automatiche.** Il lavoro vero non erano i 10 controlli d'accesso (sostituzione meccanica con `e_admin`/`e_owner`), ma il capire, riga per riga, a chi debba arrivare ogni messaggio. Sono emerse tre categorie, che prima coincidevano perché il destinatario era sempre lo stesso:
- **Notifiche schedulate** (AUTO UPDATE, anomalie partite, schedine mancanti, keep-alive) → a **tutti** gli admin.
- **Risposte a un'azione** (esito di un ricalcolo, elenco partite per la correzione manuale, errori) → **solo a chi ha agito**. Prima andavano a `chat_id=ADMIN_ID` anche quando erano la risposta a un bottone premuto: con un secondo admin, la sua correzione gli sarebbe sparita davanti agli occhi per comparire nella chat di un altro.
- **Funzioni a doppio uso**: `task_backup_periodico` e `task_riepilogo_whatsapp` sono chiamate **sia** da un job schedulato **sia** da un comando. Hanno ora un parametro `destinatari`: `None` per il job (tutti), l'id di chi ha scritto per il comando. Il riepilogo WhatsApp fa eccezione e va comunque a tutti anche se lo forza uno solo — è il testo da incollare, e può averlo in mano chiunque dei due.

**Due garanzie dentro `avvisa_admin()`**, entrambe da incidenti già visti:
1. **Un invio fallito non ferma gli altri.** Basta che un admin abbia bloccato il bot (Telegram risponde 403) perché un `send_message` in cima al giro faccia sparire l'avviso anche a chi l'avrebbe ricevuto. Il `try` sta **dentro** il ciclo, non attorno.
2. **Se Telegram rifiuta la formattazione, il testo parte lo stesso senza `parse_mode`.** Un underscore dispari (`OVER_2.5`) rompe il Markdown legacy e fa rifiutare l'intero messaggio (Sessione 15): un errore di formattazione non deve far buttare via il contenuto.
Stessa logica per il backup: il file viene **riaperto per ogni destinatario** (Telegram consuma lo stream, riusare l'handle manderebbe un allegato vuoto dal secondo admin in poi), e se non arriva a **nessuno** parte comunque un messaggio di avviso — un allegato può fallire dove un testo passa.

**Nascondere un bottone non è un controllo d'accesso.** Il menu `/start` non mostra più «Cambia Chiave API» a chi non è owner, e Telegram mostra due liste di comandi diverse (`BotCommandScopeChat`): proporre nel menu un comando che poi risponde «riservato» è un invito a premerlo. Ma il controllo vero resta nell'handler, perché un `callback_data` si può rimandare da un messaggio di ieri — c'è un test che lo fa.

**Un admin che sbaglia comando riceve una spiegazione; un estraneo resta senza risposta.** «🔒 Questo comando è riservato all'amministratore principale» a chi è admin ma non owner; silenzio totale per tutti gli altri, come prima — spiegare a uno sconosciuto che esiste un «amministratore principale» non serve a niente.

**Robustezza della configurazione.** `ADMIN_IDS` accetta virgole, punti e virgola, spazi e a capo; l'owner è sempre il primo della lista (è l'ordine di invio) e non ci sono duplicati. Un valore non numerico viene **ignorato con un warning invece di far fallire l'avvio**: una virgola di troppo incollata nel pannello Render terrebbe il bot giù fino al prossimo intervento manuale, che è molto peggio di un admin in meno per un giro. Lo `0` non entra mai: è il valore che `ADMIN_ID` assume quando la variabile manca, e **con la lista vuota `e_admin` dice no a chiunque** — meglio un bot muto che un bot aperto a tutti. `/diagnostica` mostra ora quanti admin sono attivi: un `ADMIN_IDS` scritto male non dà nessun errore, e senza quella riga lo si scoprirebbe solo quando il secondo admin prova a usare il bot.

**Carico su Render: irrilevante, verificato sui numeri** (domanda esplicita dell'utente). Con 2 admin le chiamate uscenti verso Telegram aumentano di **5-15 al giorno nel caso peggiore** (AUTO UPDATE manda solo se il report è cambiato, le anomalie solo se la situazione cambia), su un traffico di ~2.880 richieste di polling al giorno. Soprattutto: **le chiamate in uscita non contano per lo spegnimento dopo 15 minuti**, che dipende solo dal traffico **in entrata** — il keep-alive non è toccato. In memoria si aggiunge una lista di due interi, e il backup tiene aperto un file alla volta, non uno per admin.

**Test: 452 totali** (erano 419). Il file nuovo `tests/test_multi_admin.py` ne contiene 33, scritti attorno alle proprietà più che ai casi: un bot non configurato non autorizza nessuno; un invio fallito non ferma gli altri; le operazioni riservate restano riservate anche arrivando da un bottone vecchio; il rifiuto di `/setkey` **non scrive** la chiave, non si limita a rispondere male. Due test guardano il **sorgente** invece del comportamento — nessun `chat_id=ADMIN_ID` e nessun `effective_user.id != ADMIN_ID` devono sopravvivere: è la regressione più facile da introdurre (si aggiunge un handler copiando una riga esistente, e il secondo admin smette di ricevere quella notifica senza nessun errore e senza niente nei log), ed è invisibile ai test sul comportamento perché l'handler nuovo non ce l'ha ancora nessuno.
- Nuovo `tests/conftest.py`: i test girano senza variabili d'ambiente, quindi senza configurazione `ADMIN_IDS` resterebbe vuota e tutti i test che simulano un admin fallirebbero per il motivo sbagliato. Configura un bot a un solo admin, la situazione storica che i test esistenti danno per scontata.
- **Dry-run di non regressione superato** sui dati veri: giornate 1-2-3, 960 celle confrontate, **0 differenze**.

**Da fare lato utente (pannello Render):** aggiungere la variabile `ADMIN_IDS` con l'ID Telegram del secondo admin. Senza quella variabile il comportamento è identico a prima, con un solo admin. Il secondo admin deve scrivere almeno una volta al bot perché Telegram gli associ la lista comandi ridotta (il bot lo gestisce da solo: se non ci riesce scrive un warning e parte lo stesso).

### 19/09/2026 — Sessione 23 (Consistenza degli inserimenti: doppia schedina bloccata)

**Domanda dell'utente**: «se carico una schedina per un giocatore che ce l'ha gia', cosa succede? si sovrascrive? si blocca tutto?». Risposta misurata, non dedotta: **si accodava in silenzio**.
- **Il buco**: `scrivi_su_sheets_con_regole` faceva un `append` puro, senza nessun controllo. Il secondo caricamento aggiungeva un secondo blocco di righe, senza errori ne' avvisi. Effetto misurato eseguendo il vero `esegui_calcolo_risultati` su un foglio finto: una schedina da **50 punti ne faceva 90** (20 eventi contati invece di 10, piu' il bonus chiusura). Nel Confronto Giocate il giocatore comparirebbe con i pronostici doppi nella stessa cella.
- **Cosa regge invece**: la Cassa non paga due volte (la guardia sulla descrizione gia' presente funziona), gli eventi oltre il limite restano marcati `(ANNULLATA ECCESSO)` e valgono 0, una lettura IA vuota non scrive nulla, un JSON malformato solleva prima di scrivere, il risultato manuale accetta solo `cifre-trattino-cifre` (nessuna formula puo' finire in una cella), e chi non e' admin non ottiene niente.
- **Correzione**: nuove `righe_schedina_esistente()` (confronto per numero di giornata, mai per sottostringa) e `SchedinaGiaPresente`, controllate **prima di qualunque scrittura** leggendo solo `Giocate!A:B`. Il gestore mostra un messaggio che dice quante righe esistono, dove stanno nel foglio, che **non e' stato salvato niente** e cosa fare.
- **Perche' NON la sostituzione automatica**, valutata e scartata con l'utente: cancellare righe significa `deleteDimension` per indice di riga, in ordine decrescente, sulla stessa area del bug che riscrisse 13 giornate (Sessione 13). L'asimmetria decide: il doppio caricamento e' **frequente e invisibile**, la cancellazione e' **rara e irreversibile**. Il blocco toglie il 100% del danno con rischio zero; la cancellazione a mano sul foglio resta all'admin, che vede cosa sta togliendo e ha la cronologia di Google alle spalle.
- Corretto anche un dettaglio: il nome del giocatore ora passa da `strip().upper()`. Prima gli spazi restavano (`' mario '` -> `' MARIO '`) e quel nome non avrebbe coinciso con la Classifica.
- **33 test** in `tests/test_consistenza_inserimenti.py` (totale progetto **461**), dry-run sui dati veri: 960 celle, 0 differenze.
- Nota di coordinamento: i test sono stati scritti mentre un'altra sessione implementava il multi-admin. La fixture `admin` patcha sia `ADMIN_ID` sia `ADMIN_IDS`, quindi regge entrambe le forme del controllo d'accesso.

### 18/09/2026 — Sessione 22 (Confronto cronologico, sito a prova di errore, bot alleggerito)

**Le partite erano in ordine alfabetico.** `pivot_table` ordina l'indice per nome, quindi la prima partita della giornata poteva finire in fondo alla tabella. Ora le righe seguono il calcio d'inizio, preso dagli orari della stessa chiamata API gia' fatta in quella scheda (nessuna richiesta in piu'). `ordina_partite_per_orario()` in `statistiche.py`, 4 test.
- **Le partite senza orario non si perdono**: un nome che l'API non riconosce, o l'API non raggiungibile, mandano la riga in fondo in ordine alfabetico invece di farla sparire.
- Verificato sui dati veri della Giornata 5: l'ordine della dashboard coincide con quello dell'API (Monza-Sassuolo venerdi' 20:45 → Milan-Lecce domenica 20:45).
- **Trovato un errore nei dati**: in Giocate, Giornata 5, c'e' una riga `Prosinone - Como 1907` (refuso per Frosinone). Il matching del bot usa i primi 5 caratteri del nome, quindi quella riga non verra' mai agganciata e resta IN CORSO per sempre, bloccando la chiusura della schedina. Nel Confronto compare in fondo tra le non riconosciute. Da correggere sul foglio.

**Sito down per la seconda volta con lo stesso ImportError** (18/09, dashboard 2.11.2). Dopo il push della 2.11.1 Streamlit Cloud ha rieseguito il nuovo `app.py` con la vecchia copia di `statistiche.py` in memoria: `ordina_partite_per_orario` non esisteva e i giocatori hanno visto la schermata rossa con il traceback. Si risolve con "Reboot app", ma andava reso innocuo:
- `.streamlit/config.toml`: `client.showErrorDetails = "none"`, così un errore qualsiasi non mostra più dettagli tecnici a chi visita il sito (in locale si riattiva con `--client.showErrorDetails=full`).
- `app.py`: l'import di `statistiche.py` è dentro un `try/except ImportError` che mostra una pagina "Aggiornamento in corso" e scrive il dettaglio nei log. **La modalità manutenzione non poteva intercettarlo**: l'errore avviene sugli import, prima che il codice la legga.
- Verificato simulando il guasto vero: `AppTest` con un modulo `statistiche` vuoto al posto di quello buono → nessuna eccezione mostrata, compare il messaggio, nessun dettaglio tecnico in pagina.

**Analisi del progetto su richiesta dell'utente: cosa pesa e cosa no.**
- **Non pesa niente di quello che conserviamo**: 741 righe in Giocate, 17 in Classifica, 1 in Cassa; le stagioni passate vanno in fogli separati; i backup temporanei vengono cancellati dopo l'invio; nessun import o costante morta (tranne una funzione, vedi sotto). Memoria del bot fra 166 e 278 MB su 512, in calo spontaneo.
- **Pesa davvero il `requirements.txt` unico**: il bot installa streamlit (35 MB), pandas (72), pyarrow (127), numpy (60), altair (10) e non li importa mai. Attenzione: sono *installati*, non caricati, quindi separarli **non rende il bot più veloce né più leggero in RAM** — accorcia il deploy (oggi ~80s) e lo spazio occupato. Richiede un `requirements-bot.txt` e il cambio del comando di build su Render (lato utente). **Non fatto**, in attesa di decisione.
- **Rumore nei log**: `httpx` scriveva una riga per ogni chiamata a Telegram, circa **8.600 al giorno**, dentro cui andava cercato l'errore vero. Portato a WARNING.
- **Pulizia fatta**: rimossa la funzione mai usata `chiave_api_da_env`; la cartella delle foto passa dalla costante `CARTELLA_FOTO`; nuova `pulisci_foto_residue()` chiamata all'avvio per le foto di un caricamento interrotto (3 test). Il disco di Render è effimero e le avrebbe tolte comunque al riavvio: qui è esplicito e vale anche in locale.
- **Non fatto di proposito**: la chiamata a Sheets per l'anagrafica del foglio, ripetuta a ogni calcolo risultati (5-6 al giorno), si potrebbe tenere in memoria; da sola non vale il rischio di toccare `esegui_calcolo_risultati`.
- **Errore nei dati corretto sul foglio**: `Giocate!C655` da `PROSINONE - COMO` a `Frosinone - Como 1907` (Giornata 5, MARIO). Con il refuso quella riga non sarebbe mai stata agganciata e la schedina non avrebbe potuto chiudersi.

**Ottimizzazioni misurate, non ipotizzate** (dashboard 2.11.3). Misure di partenza: dashboard 3,5s a freddo e 0,26s a caldo in locale; nel profilo a caldo il tempo e' quasi tutto dentro Streamlit (scansione dei pacchetti installati), non nel nostro codice. Un caricamento a freddo fa **4 chiamate di rete**: 1 batchGet a Sheets e 3 a Football-Data (giornata corrente, giornata 1 **solo per il timer**, elenco squadre).
- **`orari_partite_giornata()` con cache 24h** (`app.py`): il timer guarda una giornata gia' conclusa, i cui orari non cambiano piu', mentre `scarica_risultati_api` ha cache 3 minuti perche' segue i risultati in diretta. Il primissimo caricamento fa comunque quella chiamata; il risparmio e' sulle ripetizioni, che erano una ogni 3 minuti **per ogni visitatore** — con 16 giocatori e un limite di 10 richieste/minuto, era la pressione piu' inutile che avessimo.
- **Polling Telegram da 10 a 30 secondi** (`app.run_polling(timeout=30)`): e' polling lungo, quindi le risposte restano immediate, ma le richieste passano da ~8.640 a ~2.880 al giorno.
- **`id_foglio_giocate()`**: l'anagrafica del file veniva richiesta a Google a ogni calcolo risultati solo per leggere un identificativo che non cambia mai. Ora una volta per processo (1 test).
- **`requirements-bot.txt` creato ma non ancora attivo**: contiene solo le dipendenze che il bot importa davvero (verificato scansionando gli import di `bot_telegram.py`, `api_utils.py`, `statistiche.py`). Per usarlo serve cambiare il comando di build su Render in `pip install -r requirements-bot.txt` — operazione del pannello, lato utente. Ripetuto perche' e' la parte che si fraintende: **non rende il bot piu' veloce ne' piu' leggero in RAM**, accorcia il deploy e lo spazio occupato. **Attivato dall'utente lo stesso giorno**, e qui i numeri veri: deploy da 79s, 91s e 76s con il file unico, **68s** con `requirements-bot.txt`. Guadagno reale ma modesto (~10-15%): il tempo di deploy non e' solo `pip install`, e Render ha il profilo di cache disattivato. Al riavvio compare un `telegram.error.Conflict: terminated by other getUpdates request`: e' la vecchia istanza che sta ancora interrogando Telegram mentre parte la nuova (visto nelle metriche: sovrapposizione di pochi secondi), si esaurisce da solo.

**Analisi richiesta dall'utente: si possono avere i risultati LIVE come SofaScore?** Misurato, non ipotizzato.
- **Football-Data piano gratuito: niente minuto, niente eventi.** I campi di una partita sono solo `status`, `score.fullTime`, `score.halfTime`, `lastUpdated`: nessun minuto di gioco, nessun marcatore, nessun cartellino. La pagina prezzi conferma: il gratuito ha "Scores delayed", il live vero costa 12 €/mese, marcatori e cartellini 29 €/mese.
- **Ritardo misurato in diretta** su Groningen-Zwolle (Eredivisie, 18/09): gol al 20' (visto su ESPN alle 18:20 UTC), Football-Data lo mostrava ancora 0-0 alle 18:26:10 e 1-0 alle 18:26:55. **Ritardo di circa 5-6 minuti.**
- **Fonte alternativa**: l'endpoint pubblico di ESPN (`site.api.espn.com/.../soccer/ita.1/scoreboard`) dà minuto, punteggio live ed eventi (gol con marcatore) gratis, ma e' **non documentato e non ufficiale**: puo' cambiare o essere bloccato senza preavviso. Utilizzabile al massimo come fonte "best effort" con fallback, mai per dati che contano.
- **Il sito regge il carico?** Sì, con due vincoli. `st.cache_data` e' **condiviso fra tutti i visitatori** (documentazione Streamlit), quindi le chiamate all'API dipendono dalla frequenza di aggiornamento, **non** da quante persone sono collegate: con cache di 60s si resta a 1 chiamata/minuto contro un limite di 10 (condiviso col bot). Memoria della dashboard misurata: **311 MB** dopo un caricamento completo, dentro i limiti di Community Cloud (690 MB - 2,7 GB). Il vincolo vero e' la CPU: l'allocazione parte da **0,078 core**, cioe' ~4,7s di CPU al minuto, mentre un rerun a caldo costa 0,15s in locale. Con 16 visitatori e aggiornamento ogni 30s si arriverebbe a sfiorare il tetto; con `st.fragment(run_every=60)` sul solo pannello live si resta molto sotto.
- **Conclusione proposta**: non replicare SofaScore (con il piano gratuito non e' possibile, e con 29 €/mese si otterrebbe comunque una copia peggiore). Il valore nostro e' **tradurre i risultati in punti e schedine in tempo reale** — chi sta vincendo la giornata, quali schedine sono ancora vive — cosa che nessun sito di risultati puo' fare. Resta valida la regola del progetto: **i punti ufficiali li scrive solo il bot**, il sito mostrerebbe una stima provvisoria dichiarata come tale, con l'ora dell'ultimo aggiornamento.

### 16/09/2026 — Sessione 21 (Coppa: tabellone con i nomi, dalla classifica attuale)

**Il tabellone della Coppa non nascondeva nomi veri.** I "nomi sfocati" erano barre di caratteri pieni scritte a mano nel codice, e gli accoppiamenti non esistevano da nessuna parte (criterio ancora "da decidere" nel TODO). Togliere la sfocatura non bastava: serviva una regola. Scelta dell'utente, fra tre proposte: **tabellone provvisorio dalla classifica attuale**, 1° contro 16°, 2° contro 15° e così via, aggiornato a ogni giornata finché la Coppa non parte. Scartati "solo i 16 partecipanti, accoppiamenti da sorteggiare" e "coppie vicine (1°-2°, 3°-4°)".
- **Schema classico dei tornei a 16** (`ORDINE_TABELLONE_16` in `statistiche.py`): 1-16, 8-9, 5-12, 4-13 nella prima metà, 6-11, 3-14, 7-10, 2-15 nella seconda. I primi due si incontrano solo in finale, 1° e 4° al massimo in semifinale.
- **Stesso elenco della scheda Classifica** (`df_classifica`, già ordinata con lo spareggio sui pronostici vinti e senza ritirati): la posizione accanto al nome nel tabellone coincide con quella che i giocatori vedono in classifica. PULIZZER (ritirato) è fuori, SIRACUSA dentro.
- `tabellone_ottavi()` restituisce None se i partecipanti non sono esattamente 16: il tabellone è fatto per 16 e non si indovina chi escludere o ripescare. In quel caso la scheda mostra "Da definire" e un avviso.
- Quarti, semifinali e finale mostrano "Vincente ottavo 1", "Vincente quarto 1"... Nomi passati da `html.escape`. Il riquadro "Il sorteggio" è diventato "Gli accoppiamenti", con la regola spiegata ai giocatori.
- 5 test nuovi in `tests/test_statistiche.py`, fra cui la classifica vera del 16/09 (PAOLO–NICO, VILLARI–MICHELE).
- Tocca `statistiche.py`: dopo il push serve **"Reboot app"** su Streamlit Cloud (vedi Sessione 20).

**Seconda richiesta, nella stessa sessione: calendario della Coppa e passaggi di turno** (dashboard 2.11.0). L'utente ha confermato che la Coppa si gioca sulle **ultime 4 giornate** di Serie A (38): ottavi alla 35ª, quarti alla 36ª, semifinali alla 37ª, finale alla 38ª (costanti `TURNI_COPPA`, `PRIMA_GIORNATA_COPPA`, `ULTIMA_GIORNATA_TABELLONE` in `statistiche.py`).
- **Tabellone fisso dalla 34ª**: `classifica_per_coppa()` somma solo i punti delle giornate 1–34, e lo spareggio sui pronostici vinti conta solo le stesse giornate. Fino alla 34ª coincide con la scheda Classifica (test sui dati veri del 16/09); dalla 35ª i punti nuovi non spostano più nessuno. La scheda passa da "provvisorio" a "definitivo" appena in Giocate compare una giornata dalla 35ª in poi.
- **Passaggi di turno automatici** (`turni_coppa()`), con la regola già scritta nella scheda: passa chi fa più punti nella giornata del turno. A parità passa chi era più in alto nella classifica del tabellone: nella pratica coincide con "più in alto in classifica generale", perché due giocatori pari nella giornata non cambiano ordine fra loro. Durante il turno la sfida mostra i punti che maturano (colonna "Giornata N" della Classifica; cella vuota = nessun punto ancora, diverso da 0).
- **Nessun vincente a giornata aperta**: `giornate_concluse()` considera conclusa una giornata solo se tutte le sue righe in Giocate sono VINTA, PERSA o ANNULLATA. Basta una riga in corso, rinviata, da verificare o senza esito per non dichiarare niente: i punti potrebbero ancora cambiare. Stessa prudenza di "mai vincere per default". A giornata conclusa, chi non ha punti ne ha fatti 0.
- Vincitori evidenziati in verde, eliminati in trasparenza, campione sotto il trofeo. Ogni colonna mostra la giornata del turno.
- 15 test nuovi in `tests/test_statistiche.py`. Verificato sulla dashboard vera con i dati di oggi (tabellone provvisorio, nessun turno giocato); la parte con i risultati è coperta dai test e da una **simulazione**: `app.py` eseguito per intero con `streamlit.testing.v1.AppTest`, sostituendo solo `punti_per_giornata` e `giornate_concluse` con dati finti (ottavi conclusi, quarti in corso), poi l'HTML del tabellone iniettato nella dashboard vera per vederlo con i suoi stili. Risultato atteso e ottenuto: NICO (16°) elimina PAOLO 14-10, DARIO e MARIO pari a 10 → passa DARIO (8°), quarti con i punti ma senza vincitore. Nota: il pannello del browser mostra copie non aggiornate dei file HTML locali, per questo la verifica è stata fatta iniettando l'HTML nella pagina vera. Corretto anche il trofeo, che la colonna della finale spingeva in fondo: ora sta in un blocco unico con la sfida.

### 16/09/2026 — Sessione 20 (Cambio giocatore: Pulizzer sostituito da Siracusa)

**Siracusa prende il posto di Pulizzer, storico compreso.** Il bot e la dashboard identificano un giocatore solo dal nome (in maiuscolo nella colonna `Giocatore` di Giocate e nella colonna A di Classifica), quindi è bastato rinominare le celle perché punti e schedine passassero a Siracusa, senza toccare altro.
- `bot_telegram.py`: `GIOCATORI` ora contiene `siracusa` al posto di `pulizzer` (ordine alfabetico: cambia di un posto la tastiera di scelta giocatore).
- Google Sheets: `findReplace` con `matchEntireCell` su tutti i fogli → 41 celle (40 in Giocate, 1 in Classifica), nessuna in Cassa. Verificato con un confronto cella per cella contro un backup preso subito prima: cambiate solo quelle 41 celle. Classifica di Siracusa: 90 punti, invariati.
- Dry-run su G.1–3: 960 celle, 0 differenze.
- Il file locale `giocate_completate.txt` (fuori da git, non usato da nessuno script) cita ancora il vecchio nome: è un residuo del vecchio flusso WhatsApp.

**Seconda richiesta, nella stessa sessione: Pulizzer resta in classifica come ritirato** (dashboard 2.9.0). In Classifica c'è una riga in più, `PULIZZER (RITIRATO)`: una copia congelata della riga di Siracusa al momento del cambio (90 punti). Giocate resta tutto a nome SIRACUSA, perché le schedine passate sono ormai sue: le statistiche della dashboard calcolate da Giocate valgono per lui.
- **Il ritiro sta nel nome, non in una riga vuota nel foglio.** `esegui_calcolo_risultati` riscrive l'intera Classifica e costruisce la mappa dei nomi con `r[0]`: una riga vuota (che l'API restituisce come `[]`) lo farebbe andare in errore. Con il suffisso, il nome non coincide con nessun giocatore di Giocate, quindi il bot non tocca mai quella riga. Invariante bloccato in `TestInvariantiRitirati` (`tests/test_invarianti.py`), anche nel caso in cui il nome senza suffisso coincida con un giocatore attivo.
- `statistiche.py`: `SUFFISSO_RITIRATO`, `e_ritirato()`, `nome_senza_ritiro()`, usate da entrambe le parti.
- `app.py`: i ritirati escono da podio, posizioni, frecce di tendenza e "Giornata da incorniciare". In Classifica completa compaiono in fondo, dopo una riga "—", con posizione "Ritirato"; nello storico per giornata come "PULIZZER (ritirato)". Verificato sulla dashboard vera.
- Riepilogo WhatsApp: i ritirati vanno in fondo dopo una riga `———`, con 🚪 e senza medaglia.
- Per ritirare un giocatore in futuro: rinominare le sue celle in Giocate e Classifica con il nome del sostituto, aggiornare `GIOCATORI`, aggiungere in fondo a Classifica la copia della riga con il suffisso ` (RITIRATO)` e registrare la coppia in `SOSTITUTI_DEI_RITIRATI` (`statistiche.py`).

**ImportError sul sito dopo il deploy della 2.9.0.** Il codice su GitHub era corretto: Streamlit Cloud aveva rieseguito il nuovo `app.py` tenendo in memoria il vecchio `statistiche.py`, che non aveva ancora le funzioni importate. Risolto con "Reboot app". Regola aggiunta a `CLAUDE.md`.

**Pulizzer anche nella tabella completa delle Statistiche** (dashboard 2.9.1). Le sue schedine in Giocate sono ormai a nome Siracusa, quindi la riga "PULIZZER (ritirato)" si calcola sulle schedine di Siracusa fino all'ultima giornata con punti nella riga congelata della Classifica (oggi la 4). Da quella dopo in poi le statistiche sono solo di Siracusa. Nuove funzioni pure `ultima_giornata_con_punti()` e `righe_del_ritirato()` (confronto per numero di giornata, mai per sottostringa), con test. Il ritirato resta fuori dai premi "I protagonisti". Verificato sulla dashboard vera.

### 14/09/2026 — Sessione 19 (Timer dall'ultima schedina vinta, righe del Confronto Giocate)

**Confronto Giocate: righe invisibili nella colonna partite.** Il bordo delle celle lo disegna lo Styler di Pandas, che però tocca solo le celle dati (`td`). La colonna con i nomi delle partite è l'**indice** della pivot, e Pandas la rende come celle `th`: nessuno stile la raggiungeva. Aggiunta una regola CSS `.confronto-scroll th` con lo stesso bordo delle celle (vale anche per l'intestazione con i nomi dei giocatori).

**Trappola trovata verificando sulla dashboard vera, non su una copia: DOMPurify scarta un intero blocco `style` se il suo testo contiene qualcosa che somiglia a un tag.** La prima versione della correzione era stata verificata su un HTML ricostruito a parte, dove funzionava. Sulla dashboard vera il bordo risultava ancora `0px none`: nella pagina non c'era **nessuna** delle regole di `.confronto-scroll`. `st.html` passa l'HTML da DOMPurify (configurazione letta nel frontend installato: `USE_PROFILES: html`, `FORCE_BODY: true`), che elimina un elemento il cui testo contiene una parentesi angolare seguita da lettera o barra. Il commento CSS aggiunto con la correzione citava letteralmente i tag delle celle, e così è sparito l'intero blocco: non solo il nuovo bordo, ma anche la **colonna partite fissa** durante lo scorrimento orizzontale, che prima funzionava. Riscritto il commento senza parentesi angolari; controllati tutti gli altri blocchi `style` passati a `st.html` (nessuno a rischio). Una prima ipotesi ("uno `style` in apertura viene scartato") era sbagliata ed è stata esclusa misurando: lo `style` dello Styler, nella stessa posizione, sopravviveva. Regola aggiunta a `CLAUDE.md`. Lezione: la verifica su una copia isolata non vale come verifica sulla pagina vera, perché la copia saltava proprio il passaggio (la sanificazione) che rompeva tutto.

**Nuova statistica: "Tempo passato dall'ultima schedina vinta"** (`app.py` 2.8.0) — un conteggio in settimane, giorni, ore, minuti e secondi che scorre nel browser e si azzera alla schedina vinta successiva.
- **Il problema vero non era il timer, ma il momento di partenza: i fogli non hanno una colonna data.** Chi ha vinto e in quale giornata lo dice `Cassa` (la riga "X chiude la schedina!", scritta dal bot solo dopo tutti i controlli: niente righe perse, in corso, rinviate o da verificare). La dashboard non ricalcola da sola la chiusura, per non dichiarare vinta una schedina che il bot non ha chiuso. Il **momento** si stima come inizio dell'ultima partita di quella schedina (orario da Football-Data) **+ 2 ore**. Se anche una sola partita della schedina non ha un orario noto, il timer non viene mostrato: proprio quella potrebbe essere l'ultima, e un tempo sbagliato è il tipo di errore che nessuno nota.
- **Logica pura in un modulo nuovo, `statistiche.py`**, con 14 test in `tests/test_statistiche.py`: `app.py` esegue Streamlit al momento dell'import e non si può testare. La giornata si confronta per **numero** (`numero_giornata`), mai per sottostringa (vedi Sessione 13), e "Giornata 10" viene correttamente dopo "Giornata 9".
- **Verificato sui dati veri**: l'unica schedina chiusa finora è PAOLO in Giornata 1; tutte e 10 le sue partite riconosciute, ultima Roma-Fiorentina lunedì 24/08 alle 20:45, quindi timer dalle 22:45 del 24/08.
- **Trappole di `st.iframe` trovate misurando nel browser** (serve l'iframe: `st.html` non esegue JavaScript): `height="content"` non ha effetto e l'iframe resta ai 150px di default del browser; ridimensionare l'iframe via JavaScript non basta, perché il contenitore di Streamlit resta all'altezza passata in Python (spazio vuoto sotto i riquadri da telefono). Soluzione deterministica: riquadri ad **altezza fissa, identica da desktop e da telefono** (`ALTEZZA_TIMER_PX`), passata anche a `st.iframe`. L'iframe non eredita il tema: il colore del testo viene letto dalla dashboard **a ogni secondo**, perché letto una volta sola restava chiaro su fondo chiaro dopo un cambio di tema a pagina aperta (visto nel browser).
**Nuova statistica: "Per un soffio"** — tabella delle schedine perse per un solo evento: giocatore, giornata, partita, pronostico e quota dell'evento sbagliato. Conta solo una schedina **già decisa del tutto**: esattamente una riga PERSA, tutte le altre VINTA o ANNULLATA (le annullate non contano né a favore né contro), almeno una vinta. Basta una riga in corso, rinviata o da verificare per escluderla, altrimenti una schedina ancora aperta comparirebbe come "persa per un soffio" e potrebbe bruciarsi alla partita dopo. Logica in `statistiche.py` (`schedine_perse_per_un_soffio`), 7 test. Sui dati veri al 14/09 c'è un solo caso: VINCENZO, Giornata 3, Fiorentina - Torino, X a quota 3,2. Il timer resta di proposito solo nelle Statistiche, non in prima pagina: vederlo appena si apre il sito potrebbe infastidire.

**Confronto Giocate: colonna "Scelta del gruppo"**, l'ultima, dopo tutti i giocatori: per ogni partita il pronostico più giocato e da quanti ("1 · 5 su 7"), con le parità mostrate entrambe ("1 / X · 3 su 7") e "Tutti diversi" se nessuno coincide. Ogni giocatore conta una volta per pronostico; conta solo il pronostico identico (`1+OVER_2.5` non vale come `1`). Scartata, su scelta dell'utente, la variante con un contorno sulle celle di chi ha seguito il gruppo: le celle sono già colorate per esito, e da telefono avrebbe fatto confusione. La colonna va aggiunta **dopo** la riga delle vincite potenziali, che è costruita sulle colonne dei giocatori: prima, in fondo alla colonna sarebbe comparso "0,00 €". Logica in `statistiche.py` (`scelta_del_gruppo`), 5 test. Verificato sulla dashboard vera da desktop e da telefono (375x812, tema scuro): colonna in fondo, riga delle vincite vuota, nessuno scorrimento laterale della pagina.

**Test**: 26 nuovi test in `tests/test_statistiche.py`, totale progetto **353**, tutti verdi. Il calcolo dei risultati del bot non è stato toccato, quindi il dry-run di non-regressione non era necessario.

- `scarica_risultati_api` restituisce ora anche l'orario UTC grezzo (`"utc"`): il campo `"data"` è solo testo da mostrare e non contiene l'anno.

### 09/09/2026 — Sessione 18 (La correzione sulla memoria ha funzionato: i numeri di Render)

**La verifica in sospeso dalla Sessione 17.** La correzione (`libera_memoria_al_sistema_operativo()`, pubblicata il 04/09) era stata dichiarata "non verificabile in locale": `malloc_trim` esiste solo su glibc/Linux, e la prova poteva arrivare solo dalla produzione. È arrivata, grazie al server MCP di Render appena disponibile — metriche e log letti direttamente, senza doverli far copiare all'utente.

**Prima della correzione** (27/08 → 03/09): **8 mail** "exceeded its memory limit" in 8 giorni. Le metriche mostrano il profilo tipico del problema: la memoria **saliva in modo monotono** fino a 490–533 MB, il processo veniva ucciso, ripartiva, e ricominciava a salire. Non scendeva **mai** se non per un riavvio.

**Dopo la correzione** (04/09 17:00 → 09/09 12:00):
- **Zero mail di allarme in 5 giorni** (prima ne arrivava circa una al giorno).
- **Zero riavvii**: la stessa istanza (`9jtnq`) è viva ininterrottamente da 5 giorni. Prima nessuna istanza superava le ~24 ore.
- La memoria ora **oscilla e scende da sola**: 320 MB alle 15:30 dell'08/09, 222 MB alle 18:30 — un centinaio di MB restituiti al sistema operativo senza alcun riavvio. È esattamente ciò che `malloc_trim` doveva fare.
- Il picco si è **stabilizzato a 409–414 MB** invece di continuare a salire verso il limite.

**Sfumatura sulla causa, ora che ci sono i dati.** Cinque delle otto mail sono arrivate a orari che coincidono al secondo con i job schedulati (21:00 UTC = 23:00 CEST, 18:30 UTC = 20:30 CEST). In Sessione 15 questa coincidenza era stata ipotizzata e poi archiviata come "mai supportata da un numero"; i numeri ora ci sono, ma il quadro completo è più preciso di entrambe le ipotesi precedenti: **la causa di fondo era la crescita continua** (memoria non restituita all'OS dalle arene dei thread), **il job schedulato era solo la goccia** che di volta in volta faceva traboccare un vaso già pieno. Ecco perché intervenire sulla crescita ha risolto, mentre nè ottimizzare le foto nè spostare l'orario del job avrebbero funzionato.

**Buco nella strumentazione, trovato cercando la prova.** La riga di log `... -> ... MB dopo il rilascio` non compariva **mai** nei log di produzione: era stata messa solo in `analizza_schedine_multiple` (una schedina si carica una volta a giornata), non in `esegui_calcolo_risultati` (che gira più volte al giorno). Corretto: ora il punto più frequente è quello strumentato, e la prossima verifica non richiederà l'accesso alle metriche.

**Nuovo strumento nel repo: `scripts/dry_run_non_regressione.py`.** Il dry-run contro i dati di produzione veniva riscritto a mano in una cartella temporanea a ogni sessione, e ogni volta andava perso (in questa sessione lo scratchpad era di nuovo vuoto). Ora è uno script del progetto: legge i dati veri, ricalcola le giornate scelte, intercetta **ogni** scrittura senza eseguirla e confronta cella per cella. Esce con codice 1 se trova differenze, quindi è usabile anche in un controllo automatico. Verificato: 960 celle su 3 giornate, 0 differenze.

### 04/09/2026 — Sessione 17 (489 MB su 512: non erano le foto)

**Sintomo**: `/diagnostica` (appena introdotto in Sessione 16) ha misurato **489 MB su 512** subito dopo il caricamento di una schedina — 95% del limite, un solo picco dal disastro.

**La spiegazione della Sessione 16 non regge fino in fondo**: il calcolo dei "46,7 MB per foto" era su un file 4032x3024 **non compresso**. Verificato il codice: l'unico handler registrato per ricevere le foto è `filters.PHOTO`, non `filters.Document` — significa che **Telegram comprime sempre le foto a ~1280px prima di consegnarle al bot**, il caso "file grezzo" della Sessione 16 semplicemente non si presenta mai nell'uso reale. Tre foto reali costano una frazione di quei 140 MB stimati, non abbastanza per spiegare 489.

**Il sospetto vero**: comportamento noto di Python su Linux (glibc). Quando un thread libera memoria, l'interprete non la restituisce sempre al sistema operativo — la tiene riservata nell'arena di quel thread per riusarla. Il bot passa **ogni** operazione pesante da `asyncio.to_thread` (lettura foto, calcolo risultati, chiamate API): ogni thread che ha fatto un lavoro grosso può restare con memoria "intrappolata" nella propria arena anche a oggetto Python già liberato — senza che sia un leak vero, e senza che `gc.collect()` da solo la riporti indietro (ripulisce i cicli di riferimento, non tocca l'allocatore sottostante).

**Correzione — `libera_memoria_al_sistema_operativo()`**: `gc.collect()` seguito da `malloc_trim(0)`, la chiamata di glibc che chiede esplicitamente all'OS di riprendersi la memoria libera in cima alle arene. Richiamata in due punti, subito dopo `del` sugli oggetti grandi appena diventati inutili:
- `analizza_schedine_multiple`, dopo aver ottenuto la risposta da Gemini (le immagini decodificate non servono più).
- `esegui_calcolo_risultati`, dopo aver finito di scrivere su Sheets (le righe di Giocate/Classifica lette non servono più).

Entrambi i punti loggano memoria **prima e dopo** il rilascio: la correzione si autoverifica nei log di produzione, invece di restare una teoria. Non testabile fino in fondo in locale — `malloc_trim` è una funzione di glibc, assente su macOS (dove girano lo sviluppo e i test): lì fallisce silenziosamente per costruzione, ed è il comportamento corretto.

**Onestà sui limiti**: non c'è la controprova su Render che il numero scenda davvero. La prossima volta che il bot elabora una schedina in produzione, la riga di log `Analisi schedina completata: memoria X MB -> Y MB dopo il rilascio` dice se l'ipotesi era giusta. Se Y resta vicino a X, il sospetto era sbagliato e si torna a guardare altrove — con un dato in mano, non un'altra ipotesi.

**Verifiche**: 323 test verdi; dry-run di non-regressione su dati di produzione (352 celle, 0 differenze); percorso reale (`analizza_schedine_multiple` con foto e chiamata Gemini vera) eseguito end-to-end con il log visibile.

**`/archiviastagione` — da un tap a un codice digitato.** Analizzando cosa servirebbe per un secondo admin (vedi TODO "Multi-admin"), l'utente ha fatto notare che l'unica operazione del progetto che cancella dati era protetta da un solo bottone "Sì" — già con backup automatico e testo esplicito, ma comunque un tap distratto di distanza dallo svuotare i fogli di lavoro. La conferma ora richiede di **digitare un codice a 6 cifre generato al momento** e mostrato solo in quel messaggio: non è sicurezza contro un attaccante (bisogna già essere admin per arrivarci), è un freno contro il tap a vuoto — costringe a fermarsi e leggere. Un codice sbagliato non fa uscire dalla conversazione (si può ritentare o `/cancel`), e `/cancel` ora ripulisce anche lo stato dell'archiviazione in sospeso, che prima restava appeso in `user_data`. 5 nuovi test in `tests/test_archivio_stagione.py` (totale progetto: **327**).

### 04/09/2026 — Sessione 16 (Memoria: l'ipotesi era sbagliata, la misura l'ha smentita)

**L'ipotesi da verificare** (da Sessione 15): "la memoria cresce con l'accumularsi delle giornate, prima o poi Render ucciderà il bot". Sembrava solidissima: tre funzioni rileggono tutto `Giocate` a ogni chiamata, e le righe crescono di 160 a giornata.

**La misura l'ha demolita in due minuti**:

| cosa | costo reale in memoria |
|---|---|
| una **stagione intera** di Giocate (6080 righe) | **1,6 MB** |
| **una sola foto** 4032x3024 al momento della decodifica | **46,7 MB** |
| la stessa foto con `draft()` | **~0 MB** |

Una singola foto di schedina costa **quasi 30 volte** tutti i dati di un campionato. Tre foto caricate insieme fanno ~140 MB di picco su un piano da 512 — mentre l'intero storico delle giocate, quello che temevamo, ne occupa meno di due. La direzione in cui stavamo per lavorare era quella sbagliata.

**Cosa è stato fatto, di conseguenza**:
- **`draft()` nella lettura delle foto**: dice al decoder JPEG di produrre già l'immagine ridotta invece di decodificarla a piena risoluzione per poi rimpicciolirla. È il cambio con il rapporto beneficio/rischio più alto dell'intera sessione: due righe, ~47 MB di picco risparmiati per foto.
- **NON è stato fatto** il refactor "leggi solo le righe della giornata": avrebbe richiesto di toccare la scrittura per indice di riga in `esegui_calcolo_risultati` — la stessa area del bug che in Sessione 13 riscrisse 13 giornate — per guadagnare 1,6 MB. Rischio alto, beneficio misurato irrilevante.
- **Strumentazione**: `memoria_mb()` (attuale, da `/proc/self/status`) e `memoria_picco_mb()` (massimo storico, da `getrusage`) loggate all'analisi schedina e al calcolo risultati. Distinguerle è essenziale: `ru_maxrss` non scende **mai**, quindi da sola farebbe sembrare critico un bot in salute.
- **Controllo anomalie da 2h a 4h**: era il più frequente dei lavori che rileggono tutto Giocate (12 volte al giorno), ed è un avviso preventivo che non serve al minuto.

**Comando `/diagnostica`** — nato dal dolore delle Sessioni 14-15, dove per scoprire che un modello metteva 96s a rispondere è servito scrivere script in locale con la chiave API. Controlla in un colpo solo: memoria (attuale e picco), ultimo ping keep-alive, Google Sheets (righe e latenza), Football-Data (giornata e latenza), e ogni modello della catena IA con i tempi reali.
> **Ha mentito al primo test, ed è stato corretto prima di pubblicarlo.** Con la soglia a 10s (il minimo consentito dall'API) bocciava tutti e quattro i modelli — mentre in realtà tre rispondevano in 2,6s, 8,7s e 15,6s. Soglia portata a 30s, oltre la peggiore latenza valida osservata, e prove eseguite **in parallelo** (caso peggiore 30s invece di due minuti). Una diagnostica che grida al lupo è peggio di nessuna diagnostica.

**Altre due migliorie richieste**:
- **"L'IA ha faticato" nel riepilogo**: se ha risposto un modello di riserva, o se la lettura ha superato i 30s, ora te lo dice nel messaggio invece di lasciarlo solo nei log di Render. È il primo segnale che i modelli stanno peggiorando.
- **Auto update che non si ripete**: il ricalcolo avviene sempre (è quello che aggiorna Sheets), ma il messaggio parte solo se è cambiato qualcosa rispetto all'ultimo inviato. Un messaggio identico ogni sera smette di essere letto, e quando poi cambia davvero non lo noti più.

**Dashboard più usabile da telefono** (`app.py` 2.7.1) — verificata nel browser a 375x812, non a occhio. Streamlit impila le colonne sotto i ~640px ma **non riduce i caratteri**: le tre metriche del Fondo Cassa diventavano una colonna di riquadri altissimi. Una media query `max-width: 640px` riduce metriche, titoli, margini laterali, schede e tabelle. Misurato disattivando e riattivando la regola sullo stesso viewport: la scheda Classifica passa da **2105px a 1925px** (-180px, -9%), e soprattutto podio completo e inizio classifica ora entrano in una sola schermata. Desktop verificato invariato (metriche di nuovo a 31,5px, margini a 70px).

**Rimosso `RISULTATI_MANUALI`** da `app.py`: verificato in diretta sull'API che tutte e quattro le partite ora risultano `FINISHED` con risultati **identici** a quelli scritti a mano. Toppa nata in Sessione 6, rimossa a rischio zero.

**Verifiche**: 318 test verdi; dry-run di non-regressione su dati di produzione (640 celle confrontate, **0 differenze**); `/diagnostica` eseguito per davvero contro Sheets, Football-Data e Gemini reali.

**Lezione**: l'ipotesi sulla memoria era mia, era plausibile e l'utente l'aveva fatta propria come priorità numero uno. Bastavano due minuti di misura per scoprire che il bersaglio era un altro. Prima di ottimizzare, misurare — anche quando la spiegazione "ha senso".

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
- [x] ~~**Rimuovere `RISULTATI_MANUALI` da `app.py`**~~ — fatto in Sessione 16: verificato in diretta che l'API riporta ora tutte e quattro le partite come `FINISHED` con risultati identici alla toppa, quindi rimossa senza alcun cambiamento visibile ai giocatori. Testo originale: (aggiunta in Sessione 6) non appena Football-Data.org torna a riportare correttamente le 4 partite di Giornata 2 (Sassuolo-Torino, Monza-Udinese, Fiorentina-Frosinone, Juventus-Parma) — è una toppa temporanea con punteggi scritti a mano, non deve restare nel codice più del necessario.
- [x] ~~**STRESS TEST REVISIONE CLAUDE**~~ — svolto in Sessione 8: revisione completa che ha portato alla luce due bug latenti gravi (esiti "vinti per default", vincite a quattro cifre in Cassa) e alla prima suite di test automatici.
- [x] ~~**Impostare `GEMINI_API_KEY` come variabile d'ambiente su Render**~~ — fatto dall'utente (confermato in Sessione 16).
- [ ] **Coppa a eliminazione diretta** (nuova, priorità alta in vista del finale di campionato): ottavi, quarti, semifinale, finale tra i migliori giocatori. Il tab "Coppa" in `app.py` mostra per ora solo un placeholder "In arrivo prossimamente...". **Da decidere prima di poter implementare:** criterio di qualificazione/seeding (es. classifica generale?), come si estraggono gli accoppiamenti, formato delle singole sfide (una schedina di sfida diretta? somma punti su più giornate?), quando parte rispetto alla fine del campionato.
  - *Aggiornamento Sessione 21*: il criterio degli accoppiamenti è deciso (tabellone dalla classifica, 1° contro 16°, provvisorio fino all'inizio della Coppa). Poi deciso anche il calendario: ultime 4 giornate (35ª–38ª), tabellone definitivo dopo la 34ª, passaggi di turno automatici. Resta solo la conferma del regolamento da parte del creatore del torneo.

### 🟡 Priorità Media — Prossime sessioni
- [x] ~~**Crescita memoria con l'accumularsi delle giornate**~~ — **ipotesi smentita dalla misura** in Sessione 16: una stagione intera di Giocate occupa 1,6 MB, mentre una singola foto di schedina ne costava 46,7 in fase di decodifica. Risolto alla radice con `draft()` (~0 MB) invece che con il rischioso refactor delle letture. Restano strumentazione nei log e `/diagnostica` per vedere i numeri veri al prossimo episodio.
- [ ] **Secondo controllore esterno (UptimeRobot o simile)** — deciso in Sessione 14 di **non** farlo per ora, ma tenerlo pronto. Oggi le fonti di keep-alive sono due (auto-ping interno + cron-job.org); un terzo controllore gratuito indipendente (ping ogni 5 min) coprirebbe anche il caso in cui il processo muore davvero, che l'auto-ping per definizione non può gestire. Da valutare se il problema si ripresenta.
- [x] ~~**Girone di ritorno**~~ — svolto in Sessione 10 (`tests/test_girone_di_ritorno.py`, 4 test): andata/ritorno indipendenti senza contaminazione, ordine invertito nel ritorno gestito correttamente (verificato iniettando il bug e controllando che il test lo scopra), nessuna collisione di prefisso Milan/Inter. Resta genericamente da tenere d'occhio la robustezza con moli di dati molto più grandi (fine campionato).
- [x] ~~**Multi-admin**~~ — **fatto in Sessione 24**. `ADMIN_ID` resta l'owner (`/setkey` e `/archiviastagione`), gli altri admin si aggiungono con `ADMIN_IDS` e fanno tutta la gestione quotidiana. Le due domande lasciate aperte in Sessione 17 sono state decise dall'utente: **due livelli** (non pari funzionalità) e **tracciabilità in chat** (riga «X ha fatto Y» agli altri admin + log su Render), non su Sheets. Le ~18 notifiche automatiche sono state divise fra schedulate (a tutti) e risposte a un'azione (a chi ha agito); `task_backup_periodico` e `task_riepilogo_whatsapp`, chiamate sia da job sia da comando, hanno un parametro `destinatari`. 33 test nuovi, dry-run di non regressione superato. **Resta da fare lato utente**: aggiungere `ADMIN_IDS` su Render con l'ID del secondo admin — senza quella variabile il comportamento è identico a prima. La convenzione per non agire in contemporanea sulle operazioni delicate resta un accordo fra persone, non un lock nel codice: sproporzionato per due.
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
