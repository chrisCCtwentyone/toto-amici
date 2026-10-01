"""
Test della PAUSA NOTTURNA (02:00-07:30 ora italiana).

Il piano gratuito di Render da' 750 ore al mese: un bot sveglio 24/7 ne usa 744.
Il bot dorme di notte (cron-job.org smette di pingare, task_autoping pure), e
questo ha tre conseguenze bloccate qui:

1. `in_pausa_notturna` ragiona SEMPRE in ora italiana, con ora legale e solare.
2. Il buco fra due ping che attraversa la notte non e' un guasto: niente
   allarme keep-alive al risveglio.
3. L'AUTO UPDATE non si ripete dopo ogni risveglio: l'impronta sta nel foglio
   Stato, non in RAM (che si azzera a ogni riavvio). E lo stato non e' mai piu'
   importante del lavoro: se non si legge, il messaggio parte comunque.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytz

import bot_telegram as bt

ROMA = pytz.timezone("Europe/Rome")


def roma(anno, mese, giorno, ora, minuto=0):
    return ROMA.localize(datetime(anno, mese, giorno, ora, minuto))


def utc(anno, mese, giorno, ora, minuto=0):
    return pytz.UTC.localize(datetime(anno, mese, giorno, ora, minuto))


class TestInPausaNotturna:

    @pytest.mark.parametrize("ora, minuto, atteso", [
        (1, 59, False), (2, 0, True), (7, 29, True), (7, 30, False), (12, 0, False), (23, 59, False),
    ])
    def test_confini(self, ora, minuto, atteso):
        assert bt.in_pausa_notturna(roma(2026, 10, 1, ora, minuto)) is atteso
        assert bt.in_pausa_notturna(roma(2026, 12, 1, ora, minuto)) is atteso

    def test_utc_con_ora_legale(self):
        # 01/10: CEST (UTC+2). 01:00 UTC = 03:00 italiane -> pausa.
        assert bt.in_pausa_notturna(utc(2026, 10, 1, 1, 0)) is True
        # 00:00 UTC = 02:00 italiane -> pausa; 23:59 UTC = 01:59 -> no.
        assert bt.in_pausa_notturna(utc(2026, 10, 1, 0, 0)) is True
        assert bt.in_pausa_notturna(utc(2026, 9, 30, 23, 59)) is False

    def test_utc_con_ora_solare(self):
        # 01/12: CET (UTC+1). 02:00 UTC = 03:00 italiane -> pausa;
        # 00:30 UTC = 01:30 italiane -> no; 06:30 UTC = 07:30 -> no.
        assert bt.in_pausa_notturna(utc(2026, 12, 1, 2, 0)) is True
        assert bt.in_pausa_notturna(utc(2026, 12, 1, 0, 30)) is False
        assert bt.in_pausa_notturna(utc(2026, 12, 1, 6, 30)) is False
        assert bt.in_pausa_notturna(utc(2026, 12, 1, 6, 29)) is True


class TestBucoSpiegatoDaPausa:

    def test_buco_che_inizia_prima_e_finisce_dentro(self):
        assert bt.buco_spiegato_da_pausa(roma(2026, 10, 1, 1, 50), roma(2026, 10, 1, 2, 10))

    def test_buco_diurno_non_e_spiegato(self):
        assert not bt.buco_spiegato_da_pausa(roma(2026, 10, 1, 9, 0), roma(2026, 10, 1, 9, 20))

    def test_buco_che_attraversa_la_notte(self):
        assert bt.buco_spiegato_da_pausa(roma(2026, 10, 1, 23, 0), roma(2026, 10, 2, 8, 0))

    def test_buco_che_scavalca_tutta_la_pausa(self):
        # Ne' da ne' a sono in pausa, ma in mezzo c'e' tutta la notte.
        assert bt.buco_spiegato_da_pausa(roma(2026, 10, 1, 1, 0), roma(2026, 10, 1, 8, 0))

    def test_buco_oltre_24_ore(self):
        assert bt.buco_spiegato_da_pausa(roma(2026, 10, 1, 9, 0), roma(2026, 10, 2, 9, 0))

    def test_buco_pomeridiano_lungo_non_e_spiegato(self):
        assert not bt.buco_spiegato_da_pausa(roma(2026, 10, 1, 8, 0), roma(2026, 10, 1, 23, 0))

    def test_buco_dopo_mezzanotte_prima_della_pausa(self):
        assert not bt.buco_spiegato_da_pausa(roma(2026, 10, 2, 0, 10), roma(2026, 10, 2, 1, 50))

    def test_funziona_con_datetime_utc(self):
        # 23:00 UTC del 30/9 = 01:00 italiane; 07:00 UTC = 09:00 italiane.
        assert bt.buco_spiegato_da_pausa(utc(2026, 9, 30, 23, 0), utc(2026, 10, 1, 7, 0))


class TestAutopingInPausa:

    def _contesto(self, monkeypatch, adesso):
        chiamate = []
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://esempio.invalid")
        monkeypatch.setattr(bt, "richiedi_con_retry", lambda *a, **k: chiamate.append(a))

        class FakeDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return adesso.astimezone(tz) if tz else adesso.replace(tzinfo=None)

        monkeypatch.setattr(bt, "datetime", FakeDatetime)
        return chiamate

    def test_di_notte_non_pinga(self, monkeypatch):
        chiamate = self._contesto(monkeypatch, roma(2026, 10, 1, 3, 0))
        asyncio.run(bt.task_autoping(None))
        assert chiamate == []

    def test_di_giorno_pinga(self, monkeypatch):
        chiamate = self._contesto(monkeypatch, roma(2026, 10, 1, 12, 0))
        asyncio.run(bt.task_autoping(None))
        assert len(chiamate) == 1


class TestAllarmeKeepAlive:

    def _ping(self, monkeypatch, precedente, adesso):
        """Simula un ping alla route `home()` e ritorna le POST di allarme."""
        inviati = []
        monkeypatch.setattr(bt.requests, "post", lambda *a, **k: inviati.append(k))
        monkeypatch.setattr(bt, "ADMIN_IDS", [1])

        class FakeDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return adesso

        monkeypatch.setattr(bt, "last_ping_time", precedente)
        # home() fa `from datetime import datetime` al suo interno: lo si
        # intercetta sul modulo datetime.
        import datetime as modulo
        monkeypatch.setattr(modulo, "datetime", FakeDatetime)
        bt.home()
        return inviati

    def test_buco_notturno_non_fa_allarme(self, monkeypatch):
        inviati = self._ping(monkeypatch, roma(2026, 10, 1, 1, 55), roma(2026, 10, 1, 7, 31))
        assert inviati == []

    def test_buco_diurno_fa_allarme(self, monkeypatch):
        inviati = self._ping(monkeypatch, roma(2026, 10, 1, 10, 0), roma(2026, 10, 1, 10, 40))
        assert len(inviati) == 1


class TestDeduplicaAutoUpdate:

    def _prepara(self, monkeypatch, report="REPORT G3", stato=None, leggi=None):
        stato = {} if stato is None else stato
        inviati = []

        async def finto_avvisa(context, testo, **k):
            inviati.append(testo)
            return 1

        monkeypatch.setattr(bt, "ottieni_giornata_corrente", lambda: 3)
        monkeypatch.setattr(bt, "esegui_calcolo_risultati", lambda g: report)
        monkeypatch.setattr(bt, "avvisa_admin", finto_avvisa)
        monkeypatch.setattr(bt, "leggi_stato", leggi or (lambda chiave, default=None: stato.get(chiave, default)))
        monkeypatch.setattr(bt, "scrivi_stato", lambda chiave, valore: stato.__setitem__(chiave, str(valore)))
        return stato, inviati

    def test_stesso_report_non_si_reinvia(self, monkeypatch):
        stato, inviati = self._prepara(monkeypatch)
        asyncio.run(bt.task_aggiornamento_automatico(None))
        asyncio.run(bt.task_aggiornamento_automatico(None))
        assert len(inviati) == 1
        assert stato[bt.CHIAVE_ULTIMO_AUTO_UPDATE].startswith("3|")
        assert len(stato[bt.CHIAVE_ULTIMO_AUTO_UPDATE]) < 40  # un hash, non il report

    def test_report_cambiato_si_reinvia(self, monkeypatch):
        stato, inviati = self._prepara(monkeypatch)
        asyncio.run(bt.task_aggiornamento_automatico(None))
        monkeypatch.setattr(bt, "esegui_calcolo_risultati", lambda g: "REPORT G3 AGGIORNATO")
        asyncio.run(bt.task_aggiornamento_automatico(None))
        assert len(inviati) == 2

    def test_sopravvive_al_riavvio(self, monkeypatch):
        """Il foglio Stato c'e' ancora, la RAM no: non deve ripartire."""
        stato, inviati = self._prepara(monkeypatch)
        asyncio.run(bt.task_aggiornamento_automatico(None))
        assert not hasattr(bt, "ultimo_report_inviato")
        asyncio.run(bt.task_aggiornamento_automatico(None))
        assert len(inviati) == 1

    def test_lettura_stato_che_solleva_non_blocca_l_invio(self, monkeypatch):
        def rotta(chiave, default=None):
            raise RuntimeError("Sheets giu'")
        _, inviati = self._prepara(monkeypatch, leggi=rotta)
        asyncio.run(bt.task_aggiornamento_automatico(None))
        assert len(inviati) == 1

    def test_scrittura_stato_che_solleva_non_blocca_l_invio(self, monkeypatch):
        _, inviati = self._prepara(monkeypatch)
        def rotta(chiave, valore):
            raise RuntimeError("Sheets giu'")
        monkeypatch.setattr(bt, "scrivi_stato", rotta)
        asyncio.run(bt.task_aggiornamento_automatico(None))
        assert len(inviati) == 1

    def test_l_archiviazione_azzera_la_chiave(self):
        import inspect
        assert "CHIAVE_ULTIMO_AUTO_UPDATE" in inspect.getsource(bt.archivia_stagione)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
