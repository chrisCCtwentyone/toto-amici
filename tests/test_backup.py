"""
Test di task_backup_periodico (Sessione 10): il backup settimanale che esporta
Giocate/Classifica/Cassa e le manda come documento Telegram all'admin.

Nessuna chiamata di rete o a Google Sheets reale, nessun invio Telegram reale:
tutto mockato. Verifica principalmente la robustezza (il file locale non deve
mai restare sul disco, ne' in caso di successo ne' di fallimento) e la
struttura del backup prodotto.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt


class _Esec:
    def __init__(self, dati):
        self._dati = dati

    def execute(self):
        return self._dati


class FakeServiceBatchGet:
    """Sostituisce connetti_sheets() solo per la chiamata batchGet usata dal backup."""

    def __init__(self, giocate, classifica, cassa):
        self._value_ranges = [
            {"values": giocate},
            {"values": classifica},
            {"values": cassa},
        ]

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def batchGet(self, spreadsheetId, ranges):
        return _Esec({"valueRanges": self._value_ranges})


class FakeBot:
    def __init__(self, fallisce=False):
        self.fallisce = fallisce
        self.documento_inviato = None
        self.messaggi_errore = []

    async def send_document(self, chat_id, document, filename, caption):
        if self.fallisce:
            raise Exception("Telegram non risponde (simulato)")
        self.documento_inviato = {
            "filename": filename,
            "caption": caption,
            "contenuto": json.loads(document.read()),
        }

    async def send_message(self, chat_id, text):
        self.messaggi_errore.append(text)


class FakeContext:
    def __init__(self, bot):
        self.bot = bot


GIOCATE = [
    ["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito", "Vincita", "Punti"],
    ["Giornata 1", "MARIO", "Milan - Inter", "Fisse", "1", "1,80", "✅ VINTA", "", "4"],
]
CLASSIFICA = [["Giocatore", "Punti Totali", "Giornata 1"], ["MARIO", "4", "4"]]
CASSA = [["Giornata", "Descrizione", "Entrate", "Saldo Totale"]]


@pytest.fixture
def sheets_finti(monkeypatch):
    monkeypatch.setattr(bt, "connetti_sheets", lambda: FakeServiceBatchGet(GIOCATE, CLASSIFICA, CASSA))


class TestBackupPeriodico:

    def test_backup_contiene_i_tre_fogli(self, sheets_finti):
        bot = FakeBot()
        asyncio.run(bt.task_backup_periodico(FakeContext(bot)))

        assert bot.documento_inviato is not None
        contenuto = bot.documento_inviato["contenuto"]
        assert contenuto["giocate"] == GIOCATE
        assert contenuto["classifica"] == CLASSIFICA
        assert contenuto["cassa"] == CASSA
        assert "esportato_il" in contenuto

    def test_nome_file_ha_la_data_di_oggi(self, sheets_finti):
        bot = FakeBot()
        asyncio.run(bt.task_backup_periodico(FakeContext(bot)))
        assert bot.documento_inviato["filename"].startswith("backup_toto_amici_")
        assert bot.documento_inviato["filename"].endswith(".json")

    def test_file_locale_non_resta_sul_disco_dopo_il_successo(self, sheets_finti):
        bot = FakeBot()
        asyncio.run(bt.task_backup_periodico(FakeContext(bot)))
        rimasti = [f for f in os.listdir(".") if f.startswith("backup_toto_amici_")]
        assert rimasti == []

    def test_file_locale_non_resta_sul_disco_dopo_un_fallimento(self, sheets_finti):
        """Il punto critico: se l'invio a Telegram fallisce, il file scritto
        nel frattempo non deve restare orfano sul disco."""
        bot = FakeBot(fallisce=True)
        asyncio.run(bt.task_backup_periodico(FakeContext(bot)))
        rimasti = [f for f in os.listdir(".") if f.startswith("backup_toto_amici_")]
        assert rimasti == []

    def test_fallimento_avvisa_l_admin(self, sheets_finti):
        bot = FakeBot(fallisce=True)
        asyncio.run(bt.task_backup_periodico(FakeContext(bot)))
        assert len(bot.messaggi_errore) == 1
        assert "fallito" in bot.messaggi_errore[0].lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
