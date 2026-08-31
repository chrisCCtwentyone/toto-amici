"""
Test dell'archiviazione di fine stagione (Sessione 13).

È l'unica operazione del progetto che CANCELLA dati, quindi i test si
concentrano soprattutto sulla sicurezza: nessuna cancellazione deve mai
avvenire se le copie non sono state create davvero.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt


class TestEtichettaStagione:

    @pytest.mark.parametrize("inizio, atteso", [
        ("2026-08-23", "2026-27"),
        ("2027-08-20", "2027-28"),
        ("1999-09-01", "1999-00"),
    ])
    def test_stagione_a_cavallo_di_due_anni(self, inizio, atteso):
        assert bt.etichetta_stagione(inizio) == atteso

    @pytest.mark.parametrize("cattivo", [None, "", "boh", 12345])
    def test_input_non_validi(self, cattivo):
        assert bt.etichetta_stagione(cattivo) is None


class _Esec:
    def __init__(self, dati=None):
        self._dati = dati if dati is not None else {}

    def execute(self, **kwargs):
        return self._dati


class FakeSheets:
    """Spreadsheet finto che registra duplicazioni e cancellazioni."""

    def __init__(self, fogli_esistenti, duplicazione_funziona=True):
        self.titoli = list(fogli_esistenti)
        self.duplicazione_funziona = duplicazione_funziona
        self.duplicati = []
        self.cancellazioni = []

    # --- service.spreadsheets() ---
    def spreadsheets(self):
        return self

    def get(self, spreadsheetId):
        return _Esec({
            "sheets": [{"properties": {"title": t, "sheetId": i}} for i, t in enumerate(self.titoli)]
        })

    def batchUpdate(self, spreadsheetId, body):
        for r in body.get("requests", []):
            nuovo = r["duplicateSheet"]["newSheetName"]
            self.duplicati.append(nuovo)
            if self.duplicazione_funziona:
                self.titoli.append(nuovo)
        return _Esec()

    # --- service.spreadsheets().values() ---
    def values(self):
        return self

    def clear(self, spreadsheetId, range, body):
        self.cancellazioni.append(range)
        return _Esec()

    # get() serve sia per i metadati che per i valori: distinguo dagli argomenti
    def __getattr__(self, nome):
        raise AttributeError(nome)


class FakeSheetsConValori(FakeSheets):
    def get(self, spreadsheetId, range=None):
        if range is None:
            return super().get(spreadsheetId)
        return _Esec({"values": [["intestazione"], ["riga1"], ["riga2"]]})


FOGLI_BASE = ["Giocate", "Classifica", "Cassa"]


class TestArchiviaStagione:

    def test_duplica_tutti_i_fogli_e_poi_svuota(self, monkeypatch):
        finto = FakeSheetsConValori(FOGLI_BASE)
        monkeypatch.setattr(bt, "connetti_sheets", lambda: finto)

        esito = bt.archivia_stagione("2026-27")

        assert set(finto.duplicati) == {"Giocate 2026-27", "Classifica 2026-27", "Cassa 2026-27"}
        assert len(finto.cancellazioni) == 3
        assert all("A2:Z" in c for c in finto.cancellazioni), "deve preservare la riga di intestazione"
        assert "2026-27" in esito

    def test_se_la_duplicazione_fallisce_non_cancella_nulla(self, monkeypatch):
        """Il controllo più importante: meglio interrompere che restare senza dati."""
        finto = FakeSheetsConValori(FOGLI_BASE, duplicazione_funziona=False)
        monkeypatch.setattr(bt, "connetti_sheets", lambda: finto)

        with pytest.raises(Exception, match="NON ho cancellato nulla"):
            bt.archivia_stagione("2026-27")

        assert finto.cancellazioni == [], "ha cancellato dati pur non avendo le copie!"

    def test_rifiuta_se_l_archivio_esiste_gia(self, monkeypatch):
        finto = FakeSheetsConValori(FOGLI_BASE + ["Giocate 2026-27"])
        monkeypatch.setattr(bt, "connetti_sheets", lambda: finto)

        with pytest.raises(Exception, match="gia'"):
            bt.archivia_stagione("2026-27")

        assert finto.cancellazioni == []
        assert finto.duplicati == []

    def test_rifiuta_se_manca_un_foglio_di_lavoro(self, monkeypatch):
        finto = FakeSheetsConValori(["Giocate", "Classifica"])  # manca Cassa
        monkeypatch.setattr(bt, "connetti_sheets", lambda: finto)

        with pytest.raises(Exception, match="non trovato"):
            bt.archivia_stagione("2026-27")

        assert finto.cancellazioni == []
        assert finto.duplicati == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
