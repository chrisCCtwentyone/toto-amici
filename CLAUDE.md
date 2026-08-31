# CLAUDE.md — Toto-Amici

Punto d'ingresso rapido per Claude Code su questo repo. Per l'architettura completa, il changelog per sessione e i TODO aggiornati, leggi sempre **[PROJECT_LOG.md](PROJECT_LOG.md)** — è la memoria persistente del progetto e va aggiornata dopo ogni sessione di sviluppo.

## Cos'è il progetto
Torneo di pronostici Serie A tra amici. Due componenti in produzione:
- `app.py` — Web Dashboard Streamlit (read-only, legge da Google Sheets)
- `bot_telegram.py` — Bot Telegram (cuore operativo: lettura IA schedine via Gemini, scrittura su Sheets, calcolo risultati/classifica/cassa)

Database: Google Sheets (nessun DB tradizionale).

## Regole operative
- La Web App non scrive **mai** su Sheets — solo il bot Telegram scrive.
- `_archivio/` contiene script obsoleti tenuti come backup manuale — non sono più in uso, non reintrodurli.
- Non committare mai `credenziali.json`, `chiave_api.txt`, `.env`, `.streamlit/secrets.toml` (già in `.gitignore`).
- Prima di aggiungere una chiave/API key hardcoded in qualsiasi script di test, ricorda: il repo è pubblico su GitHub — vedi la sezione "Scoperte sicurezza" in `PROJECT_LOG.md` per i precedenti (chiavi trapelate in commit storici, mai completamente rimovibili dalla history senza rewrite).
- **Prima di ogni push che tocca la logica del bot, esegui i test**: `python3 -m pytest tests/ -v` (dipendenze: `pip3 install -r requirements-dev.txt`). Coprono normalizzazione pronostici, calcolo esiti, punteggi e parsing importi — cioè i punti dove il progetto ha già subito regressioni sui dati reali.
- **Mai far "vincere per default"**: se il codice non riconosce un pronostico, non deve indovinare. `controlla_esito` restituisce `ESITO_DA_VERIFICARE` e il bot avvisa l'admin; una schedina con righe da verificare non può essere dichiarata chiusa né generare pagamenti in Cassa.
- **Attenzione al formato numerico italiano** (`1.674,56`): usa sempre `estrai_numero()` lato bot, mai `float(x.replace(',', '.'))` — il punto delle migliaia ha già causato due bug, uno dei quali sugli importi in Cassa.
- **Rate limit Football-Data: 10 richieste/minuto.** Non chiamare l'API dentro un ciclo sulle giornate: per i nomi squadra usa `scarica_squadre_serie_a()` (una sola chiamata per stagione).
- **Chiamate a servizi esterni**: usa sempre `richiedi_con_retry()` da `api_utils.py` invece di `requests.get()` diretto — copre i blip di rete transitori con retry/backoff, sia in `app.py` che in `bot_telegram.py`.
- Dopo ogni sessione di modifiche rilevanti, aggiorna il changelog in `PROJECT_LOG.md`.
- Ad ogni release pubblicata su `app.py`, aggiorna anche `VERSIONE_APP` e la lista `NOVITA` in cima al file (schema MAJOR.MINOR.PATCH: MAJOR = redesign importante, MINOR = nuove funzionalità, PATCH = fix minori). `NOVITA` è per i giocatori: linguaggio semplice, niente dettagli tecnici — quelli restano nel changelog di `PROJECT_LOG.md`.
