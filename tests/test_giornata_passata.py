"""Blocco di sicurezza sul caricamento: una schedina assegnata a una giornata gia'
finita (clic su 7 invece di 8, 23/10/2026) chiede una doppia conferma."""
import asyncio
import os
import sys
from datetime import datetime, timedelta

import pytz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot_telegram as bt


ADESSO = datetime(2026, 10, 23, 14, 0, tzinfo=pytz.UTC)


def _partita(ore_dal_via):
    via = ADESSO - timedelta(hours=ore_dal_via)
    return {"utcDate": via.strftime("%Y-%m-%dT%H:%M:%SZ")}


class _Query:
    def __init__(self, dati):
        self.data = dati
        self.testi = []
        self.tastiere = []

    async def answer(self):
        pass

    async def edit_message_text(self, text=None, reply_markup=None, **kwargs):
        self.testi.append(text)
        self.tastiere.append(reply_markup)


class _Update:
    def __init__(self, dati):
        self.callback_query = _Query(dati)


class _Context:
    def __init__(self):
        self.user_data = {}


def _pulsanti(tastiera):
    return [b.callback_data for riga in tastiera.inline_keyboard for b in riga]


class TestUltimoCalcioInizioPassato:

    def test_giornata_finita(self):
        assert bt.ultimo_calcio_inizio_passato([_partita(80), _partita(70)], ADESSO) is not None

    def test_giornata_in_corso_o_futura_nessun_avviso(self):
        assert bt.ultimo_calcio_inizio_passato([_partita(5), _partita(-3)], ADESSO) is None
        assert bt.ultimo_calcio_inizio_passato([_partita(-24)], ADESSO) is None

    def test_dati_mancanti_nessun_avviso(self):
        assert bt.ultimo_calcio_inizio_passato([], ADESSO) is None
        assert bt.ultimo_calcio_inizio_passato([_partita(80), {"utcDate": None}], ADESSO) is None


class TestSceltaGiornata:

    def _scegli(self, monkeypatch, partite=None, errore=None):
        def finte(giornata):
            if errore:
                raise errore
            return partite
        monkeypatch.setattr(bt, "partite_della_giornata", finte)
        upd, ctx = _Update("giornata_7"), _Context()
        stato = asyncio.run(bt.scegli_giornata(upd, ctx))
        return stato, upd.callback_query, ctx

    def test_giornata_finita_chiede_conferma(self, monkeypatch):
        stato, query, ctx = self._scegli(monkeypatch, [_partita(24 * 4), _partita(24 * 3)])
        assert stato == bt.SCELTA_GIORNATA
        assert "già finita" in query.testi[-1]
        assert {"giornataok_7", "cambia_giornata", "annulla_azione"} <= set(_pulsanti(query.tastiere[-1]))

    def test_giornata_futura_va_avanti(self, monkeypatch):
        partite = [{"utcDate": (datetime.now(pytz.UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}]
        stato, query, _ = self._scegli(monkeypatch, partite)
        assert stato == bt.SCELTA_GIOCATORE

    def test_football_data_giu_non_blocca(self, monkeypatch):
        stato, _, _ = self._scegli(monkeypatch, errore=RuntimeError("API giu'"))
        assert stato == bt.SCELTA_GIOCATORE

    def test_confermata_si_prosegue_con_quella_giornata(self):
        upd, ctx = _Update("giornataok_7"), _Context()
        assert asyncio.run(bt.conferma_giornata_passata(upd, ctx)) == bt.SCELTA_GIOCATORE
        assert ctx.user_data["giornata"] == "7"

    def test_cambia_giornata_torna_alla_scelta(self):
        upd, ctx = _Update("cambia_giornata"), _Context()
        assert asyncio.run(bt.conferma_giornata_passata(upd, ctx)) == bt.SCELTA_GIORNATA
        assert "giornata_8" in _pulsanti(upd.callback_query.tastiere[-1])

    def test_i_pulsanti_nuovi_sono_registrati_nel_menu(self):
        import inspect
        sorgente = inspect.getsource(bt)
        assert 'conferma_giornata_passata, pattern="^(giornataok_|cambia_giornata$)"' in sorgente


class TestRisultatoManuale:
    """24/10/2026: ogni risultato scritto a mano tornava 'formato non valido'
    perche' le tastiere dei telefoni mettono lineette, spazi e caratteri invisibili."""

    def test_accetta_le_varianti_delle_tastiere(self):
        for testo in ("2-1", "2 - 1", "2–1", "2 — 1", "2−1", "2:1", " 2-1 ", "‎2-1", "2 - 1"):
            assert bt.leggi_risultato_manuale(testo) == (2, 1), testo

    def test_rifiuta_tutto_il_resto(self):
        for testo in ("2-1 fine", "=2-1", "2", "2--1", "123-1", "a-b", ""):
            assert bt.leggi_risultato_manuale(testo) is None, testo
