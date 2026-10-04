#!/usr/bin/env python3
"""
Genera lo snapshot JSON del restyling sui dati VERI, in locale. Non pubblica
niente e non scrive niente su Google Sheets.

Cosa fa: legge Classifica, Cassa e Giocate con UNA batchGet (scope di sola
lettura, quindi non potrebbe scrivere nemmeno per errore), scarica le 380
partite della stagione da Football-Data con UNA sola chiamata
(richiedi_con_retry), costruisce lo snapshot con statistiche.costruisci_snapshot
e lo salva in un file JSON. Stampa la dimensione grezza e compressa (gzip).

Uso:
    python3 scripts/genera_snapshot_locale.py                      # restyling/snapshot-locale.json
    python3 scripts/genera_snapshot_locale.py /percorso/file.json

Serve un .env con SPREADSHEET_ID e FOOTBALL_DATA_KEY e credenziali.json,
gli stessi file del bot in locale. Il file prodotto contiene dati dei
giocatori: e' in .gitignore, non va committato.

Se i dati sono illeggibili esce con errore e NON scrive il file: e' lo stesso
comportamento previsto per il bot (non pubblica, tiene lo snapshot precedente).
"""
import gzip
import json
import os
import sys
from datetime import datetime

import pytz

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RADICE)

from api_utils import richiedi_con_retry  # noqa: E402
from statistiche import costruisci_snapshot_con_avvisi  # noqa: E402

PERCORSO_DEFAULT = os.path.join(RADICE, "restyling", "snapshot-locale.json")


def carica_env():
    """Legge il .env come farebbe Render con le variabili d'ambiente."""
    percorso = os.path.join(RADICE, ".env")
    if not os.path.exists(percorso):
        return
    for riga in open(percorso):
        riga = riga.strip()
        if riga and "=" in riga and not riga.startswith("#"):
            chiave, valore = riga.split("=", 1)
            os.environ.setdefault(chiave, valore.strip().strip('"').strip("'"))


def leggi_dati_veri():
    """(valori Classifica, valori Cassa, valori Giocate, risposta Football-Data).
    Solo letture: scope readonly e una chiamata a Football-Data."""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    carica_env()
    for nome in ("SPREADSHEET_ID", "FOOTBALL_DATA_KEY"):
        if not os.environ.get(nome):
            sys.exit(f"ERRORE: manca {nome} (.env o ambiente).")
    credenziali = Credentials.from_service_account_file(
        os.path.join(RADICE, "credenziali.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    servizio = build("sheets", "v4", credentials=credenziali)
    risposta = servizio.spreadsheets().values().batchGet(
        spreadsheetId=os.environ["SPREADSHEET_ID"], ranges=["Classifica", "Cassa!A:D", "Giocate!A:I"]
    ).execute(num_retries=3)
    classifica, cassa, giocate = ([v.get("values", []) for v in risposta.get("valueRanges", [])] + [[], [], []])[:3]
    partite = richiedi_con_retry(
        "https://api.football-data.org/v4/competitions/SA/matches",
        headers={"X-Auth-Token": os.environ["FOOTBALL_DATA_KEY"]},
    ).json()
    return classifica, cassa, giocate, partite


def main(percorso):
    classifica, cassa, giocate, partite = leggi_dati_veri()
    try:
        snapshot, avvisi = costruisci_snapshot_con_avvisi(classifica, cassa, giocate, partite, datetime.now(pytz.UTC))
    except ValueError as errore:
        sys.exit(f"ERRORE: dati illeggibili, snapshot NON generato: {errore}")

    testo = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    os.makedirs(os.path.dirname(os.path.abspath(percorso)), exist_ok=True)
    with open(percorso, "w", encoding="utf-8") as f:
        f.write(testo)

    grezzo = len(testo.encode("utf-8"))
    compresso = len(gzip.compress(testo.encode("utf-8"), 9))
    print(f"\n  snapshot salvato in {percorso}")
    print(f"  stagione {snapshot['stagione']} · giornata corrente {snapshot['giornata_corrente']}"
          f" · {len(snapshot['partite'])} partite · {len(snapshot['schedine'])} schedine")
    print(f"  dimensione grezza: {grezzo / 1024:.1f} KB ({grezzo} byte)")
    print(f"  dimensione gzip -9: {compresso / 1024:.1f} KB ({compresso} byte)")
    print(f"  avvisi: {len(avvisi)}")
    for avviso in avvisi:
        print(f"   - {avviso}")
    print()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else PERCORSO_DEFAULT)
