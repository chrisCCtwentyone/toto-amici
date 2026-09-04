"""
Test dell'archiviazione di fine stagione (Sessione 13).

È l'unica operazione del progetto che CANCELLA dati, quindi i test si
concentrano soprattutto sulla sicurezza: nessuna cancellazione deve mai
avvenire se le copie non sono state create davvero.
"""
import asyncio
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


class _MessaggioFinto:
    def __init__(self, testo):
        self.text = testo
        self.risposte = []
    async def reply_text(self, testo, **kw):
        self.risposte.append(testo)

class _UpdateFinto:
    def __init__(self, testo):
        self.message = _MessaggioFinto(testo)

class _BotFinto:
    def __init__(self):
        self.inviati = []
    async def send_message(self, chat_id, text, **kw):
        self.inviati.append(text)

class _ContextFinto:
    def __init__(self, dati=None):
        self.user_data = dati if dati is not None else {}
        self.bot = _BotFinto()

class _QueryFinto:
    def __init__(self):
        self.testo = None
    async def answer(self): pass
    async def edit_message_text(self, testo, **kw): self.testo = testo

class _UpdateCallbackFinto:
    def __init__(self):
        self.callback_query = _QueryFinto()


class TestConfermaArchiviazioneConCodice:
    """Sessione 17: un bottone "Sì" era un solo tap dallo svuotare i fogli di
    lavoro. La conferma ora richiede di DIGITARE un codice a 6 cifre mostrato
    nel messaggio — non sicurezza contro un attaccante (bisogna già essere
    admin per arrivarci), ma un freno contro il tap distratto."""

    def _contesto_in_attesa(self, codice="123456", stagione="2026-27"):
        return _ContextFinto({
            "codice_conferma_archiviazione": codice,
            "stagione_da_archiviare": stagione,
        })

    def test_codice_sbagliato_non_archivia_e_resta_in_attesa(self, monkeypatch):
        chiamato = []
        monkeypatch.setattr(bt, "archivia_stagione", lambda etichetta: chiamato.append(etichetta) or "fatto")

        ctx = self._contesto_in_attesa(codice="123456")
        upd = _UpdateFinto("000000")
        stato = asyncio.run(bt.verifica_codice_archiviazione(upd, ctx))

        assert chiamato == [], "un codice sbagliato non deve MAI archiviare"
        assert stato == bt.CONFERMA_ARCHIVIA_STAGIONE, "deve restare nella stessa conversazione, non uscirne"
        assert "codice_conferma_archiviazione" in ctx.user_data, "il codice atteso resta valido per ritentare"

    def test_codice_giusto_archivia_e_chiude_la_conversazione(self, monkeypatch):
        chiamato = []
        monkeypatch.setattr(bt, "archivia_stagione", lambda etichetta: chiamato.append(etichetta) or "fatto")

        ctx = self._contesto_in_attesa(codice="654321", stagione="2027-28")
        upd = _UpdateFinto("654321")
        stato = asyncio.run(bt.verifica_codice_archiviazione(upd, ctx))

        assert chiamato == ["2027-28"]
        assert stato == bt.ConversationHandler.END
        assert "codice_conferma_archiviazione" not in ctx.user_data
        assert "stagione_da_archiviare" not in ctx.user_data

    def test_spazi_attorno_al_codice_non_lo_invalidano(self, monkeypatch):
        """Chi digita da telefono puo' lasciare uno spazio prima/dopo per sbaglio."""
        chiamato = []
        monkeypatch.setattr(bt, "archivia_stagione", lambda etichetta: chiamato.append(etichetta) or "fatto")

        ctx = self._contesto_in_attesa(codice="111222")
        upd = _UpdateFinto("  111222  ")
        asyncio.run(bt.verifica_codice_archiviazione(upd, ctx))

        assert chiamato == ["2026-27"]

    def test_annulla_pulisce_lo_stato_in_sospeso(self):
        """Il bottone Annulla non deve lasciare il codice valido appeso in
        user_data: altrimenti resterebbe confermabile in un secondo momento."""
        ctx = self._contesto_in_attesa()
        upd = _UpdateCallbackFinto()

        stato = asyncio.run(bt.annulla_archiviazione(upd, ctx))

        assert stato == bt.ConversationHandler.END
        assert "codice_conferma_archiviazione" not in ctx.user_data
        assert "stagione_da_archiviare" not in ctx.user_data
        assert "annullata" in upd.callback_query.testo.lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
