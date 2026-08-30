# PROJECT_LOG.md — Toto-Amici 2026
> Documento di tracciamento architettura, modifiche e decisioni tecniche del progetto.
> **Aggiornare dopo ogni sessione di sviluppo.**

---

## 🗂️ Architettura del Sistema (Stato Attuale)

### Deploy
| Componente | Piattaforma | Sorgente | Note |
|---|---|---|---|
| Web Dashboard (`app.py`) | Streamlit Community Cloud | GitHub `main` | Pubblica, sempre online |
| Bot Telegram (`bot_telegram.py`) | Render (Web Service) | GitHub `main` | Mantenuto sveglio da Flask + ping cron-job.org ogni 14 min |
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
└── temp_telegram/          # Cartella temporanea per foto ricevute via Telegram
```

---

## 🏗️ Struttura Google Sheets

| Foglio | Colonne | Descrizione |
|---|---|---|
| `Giocate` | A: Giornata, B: Giocatore, C: Partita, D: Tipologia, E: Pronostico, F: Quota, G: Esito, H: Vincita Potenziale, I: Punti Partita | Archivio analitico di ogni singola selezione giocata |
| `Classifica` | A: Giocatore, B: Punti Totali, C+: Punteggio per Giornata | Leaderboard generale con storico per giornata |
| `Cassa` | A: Giornata, B: Descrizione, C: Entrate, D: Saldo Totale | Registro movimenti del fondo montepremi |

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
- [ ] **STRESS TEST REVISIONE CLAUDE**: far controllare a Claude tutte le modifiche fatte da Gemini su `normalizza_nomi_partite` e il supporto al girone di ritorno. Ancora da fare in modo dedicato (in questa sessione è stato risolto solo il bug puntuale SI/NO).
- [ ] **Coppa a eliminazione diretta** (nuova, priorità alta in vista del finale di campionato): ottavi, quarti, semifinale, finale tra i migliori giocatori. Il tab "Coppa" in `app.py` mostra per ora solo un placeholder "In arrivo prossimamente...". **Da decidere prima di poter implementare:** criterio di qualificazione/seeding (es. classifica generale?), come si estraggono gli accoppiamenti, formato delle singole sfide (una schedina di sfida diretta? somma punti su più giornate?), quando parte rispetto alla fine del campionato.

### 🟡 Priorità Media — Prossime sessioni
- [ ] **Comando admin per correzioni manuali** — approvato in linea di principio (Sessione 6/7), progettato in dettaglio nel changelog di Sessione 7. Da implementare.
- [ ] **Stress Test Periodici**: verificare la robustezza del bot al giro di boa (girone di ritorno, inversioni casa/trasferta) e con elevate moli di dati.

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
