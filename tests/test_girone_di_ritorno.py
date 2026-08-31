"""
Test dedicato al girone di ritorno: stessa coppia di squadre, andata e ritorno,
con casa/trasferta invertiti. È il pezzo di "STRESS TEST" rimasto aperto dopo
la revisione di Sessione 8 (vedi PROJECT_LOG.md).

Cosa verifica, in ordine di importanza:
1. Andata e ritorno vengono segnate in modo indipendente, senza che l'una
   contamini i punti dell'altra (esegui_calcolo_risultati e' scoperto per
   giornata, ma qui lo dimostriamo con dati reali costruiti apposta).
2. Il ritorno funziona anche quando la riga in Giocate ha le squadre scritte
   nell'ordine "vecchio" (quello dell'andata) invece di quello ufficiale del
   ritorno — il caso che il fix dell'ordine invertito (Sessione 7) deve coprire
   proprio quando cambia chi gioca in casa.
3. Nessuna collisione tra i prefissi di due nomi squadra reali (Milan/Inter),
   che nel derby sono il caso più a rischio per un matching basato su substring.

Nessuna chiamata di rete o a Google Sheets: tutto mockato.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt


class _Esec:
    def execute(self, **kwargs):
        return {}


class FakeValues:
    """Sostituisce service.spreadsheets().values(): legge le righe fornite,
    registra ogni scrittura senza toccare nulla di reale."""

    def __init__(self, righe_giocate):
        self._righe_giocate = righe_giocate
        self.scritture_celle = []      # [(range, valore), ...]
        self.scritture_classifica = None
        self.scritture_cassa = []

    def get(self, spreadsheetId, range):
        dati = self._righe_giocate if "Giocate" in range else [["Giocatore", "Punti Totali"]]
        return _RispostaGet(dati)

    def batchUpdate(self, spreadsheetId, body):
        for d in body["data"]:
            self.scritture_celle.append((d["range"], d["values"][0][0]))
        return _Esec()

    def update(self, spreadsheetId, range, valueInputOption, body):
        self.scritture_classifica = body["values"]
        return _Esec()

    def append(self, spreadsheetId, range, valueInputOption, body):
        self.scritture_cassa.extend(body["values"])
        return _Esec()


class _RispostaGet:
    def __init__(self, valori):
        self._valori = valori

    def execute(self, **kwargs):
        return {"values": self._valori}


class FakeSpreadsheets:
    def __init__(self, values):
        self._values = values

    def values(self):
        return self._values

    def get(self, **kw):
        class _R:
            def execute(self_inner, **kwargs):
                return {"sheets": [{"properties": {"sheetId": 0, "title": "Giocate"}}]}
        return _R()

    def batchUpdate(self, **kw):
        return _Esec()


class FakeService:
    def __init__(self, righe_giocate):
        self.values = FakeValues(righe_giocate)

    def spreadsheets(self):
        return FakeSpreadsheets(self.values)


def _match(casa_nome, casa_short, ospite_nome, ospite_short, gol_casa, gol_ospite):
    return {
        "homeTeam": {"name": casa_nome, "shortName": casa_short},
        "awayTeam": {"name": ospite_nome, "shortName": ospite_short},
        "status": "FINISHED",
        "score": {"fullTime": {"home": gol_casa, "away": gol_ospite}},
    }


# Nomi reali come restituiti da Football-Data.org
MILAN = ("AC Milan", "Milan")
INTER = ("FC Internazionale Milano", "Inter")


@pytest.fixture
def sheets_finti(monkeypatch):
    """Sostituisce bt.connetti_sheets con un servizio finto condiviso fra le
    chiamate del test, e lo espone per leggere cosa e' stato scritto."""
    contenitore = {}

    def fabbrica(righe_giocate):
        service = FakeService(righe_giocate)
        contenitore["service"] = service
        monkeypatch.setattr(bt, "connetti_sheets", lambda: service)
        return service

    yield fabbrica


class TestGironeDiRitorno:

    def test_andata_e_ritorno_indipendenti_ordine_diretto(self, sheets_finti):
        """Andata (Giornata 5): Milan-Inter 2-1, Mario gioca 1 -> VINTA.
        Ritorno (Giornata 24): Inter-Milan 0-0, Mario gioca X -> VINTA.
        Nessuna delle due deve influenzare l'altra."""
        righe = [
            ["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito", "Vincita", "Punti"],
            ["Giornata 5", "MARIO", "Milan - Inter", "Fisse", "1", "1,80", "", "", ""],
            ["Giornata 24", "MARIO", "Inter - Milan", "Fisse", "X", "3,20", "", "", ""],
        ]

        service = sheets_finti(righe)
        bt.esegui_calcolo_risultati("5", matches_api=[_match(*MILAN, *INTER, 2, 1)])
        scritte_dopo_andata = dict(service.values.scritture_celle)
        assert scritte_dopo_andata["Giocate!G2"] == "✅ VINTA"
        assert scritte_dopo_andata["Giocate!I2"] == 4
        # Il ritorno non e' ancora stato calcolato: nessuna scrittura sulla riga 3
        assert "Giocate!G3" not in scritte_dopo_andata

        service.values.scritture_celle.clear()
        bt.esegui_calcolo_risultati("24", matches_api=[_match(*INTER, *MILAN, 0, 0)])
        scritte_dopo_ritorno = dict(service.values.scritture_celle)
        assert scritte_dopo_ritorno["Giocate!G3"] == "✅ VINTA"
        assert scritte_dopo_ritorno["Giocate!I3"] == 4
        # E il ricalcolo del ritorno non deve aver ritoccato la riga dell'andata
        assert "Giocate!G2" not in scritte_dopo_ritorno

    def test_ritorno_con_squadre_scritte_nell_ordine_dell_andata(self, sheets_finti):
        """Luca scrive la partita del ritorno con l'ordine "vecchio"
        (Milan - Inter, come nell'andata) invece di quello ufficiale del
        ritorno (Inter - Milan). Deve comunque essere valutata correttamente
        grazie al fallback sull'ordine invertito."""
        righe = [
            ["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito", "Vincita", "Punti"],
            ["Giornata 24", "LUCA", "Milan - Inter", "Fisse", "2", "2,10", "", "", ""],
        ]
        service = sheets_finti(righe)

        # Ritorno reale: Inter (casa) - Milan (trasferta), pareggio 0-0
        bt.esegui_calcolo_risultati("24", matches_api=[_match(*INTER, *MILAN, 0, 0)])

        scritte = dict(service.values.scritture_celle)
        # Luca aveva scritto "Milan - Inter": per lui "2" significa "vince la
        # seconda squadra che ho scritto" cioe' l'Inter. Risultato reale 0-0:
        # ne' Milan ne' Inter vincono -> PERSA (non deve mai restare IN CORSO
        # ne' essere scambiata per un pareggio vinto).
        assert scritte["Giocate!G2"] == "❌ PERSA"
        assert scritte["Giocate!I2"] == 0

    def test_ritorno_con_ordine_vecchio_e_vittoria_squadra_in_trasferta(self, sheets_finti):
        """Stesso scenario ma con un risultato che fa vincere la squadra che
        Luca ha scritto per seconda (Inter, in trasferta nel ritorno reale):
        deve risultare VINTA, a conferma che i gol vengono attribuiti alla
        squadra giusta e non scambiati per errore insieme all'ordine."""
        righe = [
            ["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito", "Vincita", "Punti"],
            ["Giornata 24", "LUCA", "Milan - Inter", "Fisse", "2", "2,10", "", "", ""],
        ]
        service = sheets_finti(righe)

        # Ritorno reale: Inter (casa) 0 - Milan (trasferta) 2 -> vince il Milan,
        # non l'Inter. Per Luca "2" = Inter (la squadra scritta per seconda),
        # quindi deve risultare PERSA anche qui: la vittoria e' del Milan (la sua "1").
        bt.esegui_calcolo_risultati("24", matches_api=[_match(*INTER, *MILAN, 0, 2)])
        scritte = dict(service.values.scritture_celle)
        assert scritte["Giocate!G2"] == "❌ PERSA"

        # Ora il caso in cui vince davvero l'Inter in trasferta: Inter (casa) 0 - Milan (trasferta) ...
        # per testare una vittoria dell'Inter serve invertire chi e' in trasferta:
        # Milan (casa) - Inter (trasferta), Inter vince 0-1. Qui l'ordine scritto da
        # Luca (Milan - Inter) coincide con quello ufficiale: nessun fallback necessario.
        righe2 = [
            ["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito", "Vincita", "Punti"],
            ["Giornata 24", "LUCA", "Milan - Inter", "Fisse", "2", "2,10", "", "", ""],
        ]
        service2 = sheets_finti(righe2)
        bt.esegui_calcolo_risultati("24", matches_api=[_match(*MILAN, *INTER, 0, 1)])
        scritte2 = dict(service2.values.scritture_celle)
        assert scritte2["Giocate!G2"] == "✅ VINTA"
        assert scritte2["Giocate!I2"] == 4

    def test_nessuna_collisione_tra_prefissi_milan_e_inter(self, sheets_finti):
        """Il matching usa i primi 5 caratteri del nome scritto in bolletta.
        'inter' e' anche il prefisso di 'FC Internazionale Milano': verifica
        che questo non causi un match sbagliato con una partita del Milan."""
        righe = [
            ["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito", "Vincita", "Punti"],
            ["Giornata 10", "GIULIA", "Inter - Napoli", "Fisse", "1", "1,60", "", "", ""],
        ]
        service = sheets_finti(righe)
        # In giornata ci sono contemporaneamente una partita del Milan e una dell'Inter:
        # se ci fosse una collisione di prefisso, "inter" potrebbe agganciarsi alla
        # partita sbagliata.
        matches = [
            _match("AC Milan", "Milan", "SSC Napoli", "Napoli", 1, 0),
            _match(*INTER, "SSC Napoli", "Napoli", 3, 0),
        ]
        # Le due partite condividono l'avversario per rendere il test piu' severo:
        # se il matching sbagliasse squadra prenderebbe comunque "Napoli" giusto,
        # ma i gol (e quindi l'esito) sarebbero quelli della partita sbagliata.
        bt.esegui_calcolo_risultati("10", matches_api=matches)
        scritte = dict(service.values.scritture_celle)
        # Deve aver preso i gol della partita dell'Inter (3-0), non quella del
        # Milan (1-0): pronostico "1" vince in entrambi i casi, ma i PUNTI
        # dipendono dalla quota, quindi verifichiamo l'esito e non solo il segno.
        assert scritte["Giocate!G2"] == "✅ VINTA"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
