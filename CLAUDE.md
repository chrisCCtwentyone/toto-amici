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
- Dopo ogni sessione di modifiche rilevanti, aggiorna il changelog in `PROJECT_LOG.md`.
