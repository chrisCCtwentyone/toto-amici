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
├── _archivio/              # 📦 Script obsoleti ma recuperabili
│   ├── bot_lettore.py      # Vecchio lettore locale schedine (sostituito dal bot)
│   └── calcola_risultati.py # Vecchio calcolo manuale da CLI (sostituito dal bot)
├── .streamlit/             # 🔒 Non in git — secrets per Streamlit locale
│   └── secrets.toml
├── schedine_whatsapp/      # 🔒 Non in git — cartella foto locali
├── temp_telegram/          # Cartella temporanea per foto ricevute via Telegram
└── test_api.py             # Script di test connessione API (non in produzione)
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

**Scoperte sicurezza:**
- ⚠️ Trovati nella history git (commit storici ora pubblici su GitHub):
  - `TELEGRAM_TOKEN`: `8996951565:AAGbxyDm4ZuA_Wntv1Vv_IoxQPS-Hvf7euw` (commit `8db6be6`, `455caff`, `14a58f7`)
  - `FOOTBALL_DATA_KEY`: `ef8a4016b5ab4f90a486ea0fea46fd1f` (multipli commit)
- **File attuali**: tutti sicuri — nessuna credenziale in chiaro nel codice corrente
- **Azione pendente**: rigenerare entrambe le chiavi (vedi TODO sotto)

---

## 📋 TODO / Azioni Pendenti

### 🔴 Priorità Alta — Da fare ASAP
- [ ] **STRESS TEST REVISIONE CLAUDE (URGENTISSIMO)**: far controllare a Claude Thinking tutte le modifiche fatte in questa sessione da Gemini (soprattutto la funzione `normalizza_nomi_partite` e il supporto al girone di ritorno). Eseguire uno stress test assoluto per scovare eventuali bug latenti introdotti.
- [ ] **Rigenerare TELEGRAM_TOKEN**: @BotFather → `/mybots` → `Revoke current token` → aggiornare su Render
- [ ] **Rigenerare FOOTBALL_DATA_KEY**: [football-data.org dashboard](https://www.football-data.org/client/profile) → rigenera → aggiornare su Render (env var) e Streamlit Cloud (Secrets)

### 🟡 Priorità Media — Prossime sessioni
- [ ] **Redesign UI `app.py`**: tema scuro premium, card animate, grafico interattivo andamento punti
- [ ] **Statistiche avanzate**: confronto testa a testa tra giocatori, giocatore più consistente, grafico a linee per giornata
- [ ] **Stress Test Periodici**: verificare la robustezza del bot al giro di boa (girone di ritorno, inversioni casa/trasferta) e con elevate moli di dati.

### 🟢 Idee Future
- [ ] Pagina pubblica per ogni giocatore con le sue statistiche personali
- [ ] Integrazione con calendario Serie A (avvisi pre-partita)

---

## 🤖 Note per Agenti IA Futuri

- Il **bot Telegram** è il cuore operativo del sistema. Contiene tutta la logica di: lettura IA schedine, validazione regole, scrittura su Sheets, calcolo risultati, aggiornamento classifica e cassa.
- La **Web App** è read-only: legge da Sheets e mostra dati. Non scrive mai nulla.
- I **file archiviati** in `_archivio/` sono intenzionalmente obsoleti ma mantenuti come backup manuale.
- Le **credenziali GCP** (`credenziali.json`) vengono iniettate come Secret File su Render e come `gcp_service_account` (JSON inline) su Streamlit Secrets.
- La **chiave Gemini** viene letta dal file `chiave_api.txt` (su Render è un Secret File), aggiornabile al volo via comando Telegram `/setkey`.
