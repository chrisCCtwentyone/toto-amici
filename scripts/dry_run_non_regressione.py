#!/usr/bin/env python3
"""
Dry-run di NON-REGRESSIONE sui dati veri di produzione. Non scrive nulla.

PERCHE' ESISTE
--------------
I test in tests/ girano su dati finti: verificano che la logica sia corretta
in astratto. Questo script fa una cosa diversa e complementare: prende i dati
REALI dello spreadsheet, ricalcola le giornate gia' concluse con il codice
appena modificato, e confronta cella per cella con quello che c'e' scritto
adesso. Se il risultato e' identico, la modifica non ha cambiato nulla di
cio' che era gia' stato calcolato.

E' il controllo che ha protetto il progetto dalle regressioni piu' pericolose:
quelle che i test non vedono perche' riguardano combinazioni di dati veri che
nessuno aveva pensato di simulare (vedi Sessione 13, il bug della sottostringa
che riscrisse gli esiti di 13 giornate).

Fino alla Sessione 18 questo script veniva riscritto a mano ogni volta in una
cartella temporanea, e ogni volta andava perso. Ora vive nel repo.

COME SI USA
-----------
    python3 scripts/dry_run_non_regressione.py            # giornate 1 e 2
    python3 scripts/dry_run_non_regressione.py 1 2 3      # giornate scelte

Serve un .env con SPREADSHEET_ID e FOOTBALL_DATA_KEY, e credenziali.json —
gli stessi file che servono per far girare il bot in locale.

Esce con codice 0 se non ci sono differenze, 1 se ne trova: cosi' puo' essere
usato anche dentro un controllo automatico.

SICUREZZA
---------
connetti_sheets() viene sostituito da un finto che intercetta OGNI scrittura
(update, append, batchUpdate) e la registra invece di eseguirla. Le letture
passano al servizio vero. Non e' possibile che questo script modifichi lo
spreadsheet: se un giorno il codice del bot introducesse un nuovo tipo di
scrittura non previsto qui, il finto solleverebbe AttributeError invece di
scrivere per sbaglio.
"""
import os
import sys

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RADICE)


def carica_env():
    """Legge il .env come farebbe Render con le variabili d'ambiente."""
    percorso = os.path.join(RADICE, ".env")
    if not os.path.exists(percorso):
        sys.exit("ERRORE: manca il file .env (servono SPREADSHEET_ID e FOOTBALL_DATA_KEY).")
    for riga in open(percorso):
        riga = riga.strip()
        if riga and "=" in riga and not riga.startswith("#"):
            chiave, valore = riga.split("=", 1)
            os.environ.setdefault(chiave, valore.strip().strip('"').strip("'"))


carica_env()
import bot_telegram as bt  # noqa: E402  (dopo carica_env: il modulo legge l'ambiente all'import)


class _RispostaVuota:
    def execute(self, **kwargs):
        return {}


class _ValoriIntercettati:
    """Le letture passano al servizio vero, le scritture vengono solo registrate."""

    def __init__(self, reali, scritture):
        self._reali = reali
        self._scritture = scritture

    def get(self, **kwargs):
        return self._reali.get(**kwargs)

    def update(self, **kwargs):
        self._scritture.append(("update", kwargs.get("range"), kwargs.get("body")))
        return _RispostaVuota()

    def append(self, **kwargs):
        self._scritture.append(("append", kwargs.get("range"), kwargs.get("body")))
        return _RispostaVuota()

    def batchUpdate(self, **kwargs):
        for dato in kwargs.get("body", {}).get("data", []):
            self._scritture.append(("cella", dato["range"], dato["values"]))
        return _RispostaVuota()

    def clear(self, **kwargs):
        self._scritture.append(("clear", kwargs.get("range"), None))
        return _RispostaVuota()


class _FogliIntercettati:
    def __init__(self, reali, scritture):
        self._reali = reali
        self._scritture = scritture

    def values(self):
        return _ValoriIntercettati(self._reali.values(), self._scritture)

    def get(self, **kwargs):
        return self._reali.get(**kwargs)

    def batchUpdate(self, **kwargs):
        # Qui passano solo le richieste di formattazione (colori di sfondo):
        # non toccano i dati, quindi non entrano nel confronto.
        return _RispostaVuota()


class _ServizioIntercettato:
    def __init__(self, reale, scritture):
        self._reale = reale
        self._scritture = scritture

    def spreadsheets(self):
        return _FogliIntercettati(self._reale.spreadsheets(), self._scritture)


def valore_attuale(griglia, riferimento):
    """Da 'Giocate!G42' al valore che c'e' ORA in quella cella."""
    cella = riferimento.split("!")[1]
    colonna, riga = cella[0], int(cella[1:])
    indice_colonna = ord(colonna) - ord("A")
    righe = griglia[riga - 1] if riga - 1 < len(griglia) else []
    return righe[indice_colonna] if indice_colonna < len(righe) else ""


def main(giornate):
    servizio_vero = bt.connetti_sheets()
    scritture = []
    bt.connetti_sheets = lambda: _ServizioIntercettato(servizio_vero, scritture)

    attuale = servizio_vero.spreadsheets().values().get(
        spreadsheetId=bt.SPREADSHEET_ID, range="Giocate!A:I"
    ).execute(num_retries=3).get("values", [])

    totale, differenze = 0, []
    for giornata in giornate:
        scritture.clear()
        bt.esegui_calcolo_risultati(str(giornata))
        for tipo, riferimento, valori in scritture:
            if tipo != "cella":
                continue
            nuovo = str(valori[0][0])
            vecchio = str(valore_attuale(attuale, riferimento))
            totale += 1
            if nuovo != vecchio:
                differenze.append(f"  G.{giornata} {riferimento}: '{vecchio}' -> '{nuovo}'")

    print(f"\n  giornate controllate: {', '.join(str(g) for g in giornate)}")
    print(f"  celle confrontate:    {totale}")
    print(f"  differenze:           {len(differenze)}")
    for differenza in differenze[:20]:
        print(differenza)
    if len(differenze) > 20:
        print(f"  ... e altre {len(differenze) - 20}")

    if differenze:
        print("\n  ATTENZIONE: il ricalcolo cambierebbe dati gia' scritti.")
        print("  Verifica che sia voluto PRIMA di pubblicare.\n")
        return 1
    print("\n  OK: nessuna regressione.\n")
    return 0


if __name__ == "__main__":
    scelte = sys.argv[1:] or ["1", "2"]
    sys.exit(main(scelte))
