"""
Test del riepilogo di fine giornata "pronto per WhatsApp" (Sessione 11):
costruisci_riepilogo_whatsapp() (pura, testabile senza rete) e
task_riepilogo_whatsapp() (il job schedulato, con Sheets e Telegram mockati).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt


# ---------------------------------------------------------------------------
# costruisci_riepilogo_whatsapp — funzione pura
# ---------------------------------------------------------------------------
class TestCostruisciRiepilogo:

    def test_ordina_per_punti_totali_decrescenti(self):
        classifica = [
            ["Giocatore", "Punti Totali", "Giornata 1"],
            ["MARIO", "10", "10"],
            ["LUCA", "20", "20"],
        ]
        testo = bt.costruisci_riepilogo_whatsapp("1", classifica, [])
        assert testo.index("Luca") < testo.index("Mario"), "Luca (20pt) deve comparire prima di Mario (10pt)"
        assert "🥇 Luca" in testo
        assert "🥈 Mario" in testo

    def test_mostra_solo_il_delta_della_giornata_richiesta(self):
        classifica = [
            ["Giocatore", "Punti Totali", "Giornata 1", "Giornata 2"],
            ["MARIO", "14", "10", "4"],
        ]
        assert "(+10)" in bt.costruisci_riepilogo_whatsapp("1", classifica, [])
        assert "(+4)" in bt.costruisci_riepilogo_whatsapp("2", classifica, [])

    def test_nessun_delta_mostrato_se_zero_punti_in_giornata(self):
        classifica = [["Giocatore", "Punti Totali", "Giornata 1"], ["MARIO", "0", "0"]]
        testo = bt.costruisci_riepilogo_whatsapp("1", classifica, [])
        assert "(+0)" not in testo

    def test_giornata_inesistente_ritorna_none(self):
        classifica = [["Giocatore", "Punti Totali", "Giornata 1"], ["MARIO", "10", "10"]]
        assert bt.costruisci_riepilogo_whatsapp("99", classifica, []) is None

    def test_classifica_vuota_ritorna_none(self):
        assert bt.costruisci_riepilogo_whatsapp("1", [], []) is None
        assert bt.costruisci_riepilogo_whatsapp("1", [["Giocatore", "Punti Totali"]], []) is None

    def test_segnala_chi_ha_chiuso_la_schedina_nella_giornata_giusta(self):
        classifica = [["Giocatore", "Punti Totali", "Giornata 1"], ["MARIO", "50", "50"]]
        cassa = [
            ["Giornata", "Descrizione", "Entrate", "Saldo Totale"],
            ["Giornata 1", "MARIO chiude la schedina!", "100,00€", "100,00€"],
        ]
        testo = bt.costruisci_riepilogo_whatsapp("1", classifica, cassa)
        assert "Schedina chiusa" in testo
        assert "Mario" in testo.split("Schedina chiusa")[1]

    def test_non_segnala_chiusure_di_altre_giornate(self):
        classifica = [["Giocatore", "Punti Totali", "Giornata 1", "Giornata 2"], ["MARIO", "50", "50", "0"]]
        cassa = [
            ["Giornata", "Descrizione", "Entrate", "Saldo Totale"],
            ["Giornata 1", "MARIO chiude la schedina!", "100,00€", "100,00€"],
        ]
        testo = bt.costruisci_riepilogo_whatsapp("2", classifica, cassa)
        assert "Schedina chiusa" not in testo

    def test_mostra_il_saldo_cassa_quando_presente(self):
        classifica = [["Giocatore", "Punti Totali", "Giornata 1"], ["MARIO", "10", "10"]]
        cassa = [
            ["Giornata", "Descrizione", "Entrate", "Saldo Totale"],
            ["Giornata 1", "x", "50,00€", "430,00€"],
        ]
        testo = bt.costruisci_riepilogo_whatsapp("1", classifica, cassa)
        assert "430,00€" in testo

    def test_cassa_con_solo_intestazione_non_mostra_saldo_fasullo(self):
        """Regressione: con Cassa vuota (solo header), il codice leggeva la riga
        di intestazione come se fosse un movimento, mostrando "Saldo Totale"
        (il nome della colonna) al posto di un importo."""
        classifica = [["Giocatore", "Punti Totali", "Giornata 1"], ["MARIO", "10", "10"]]
        cassa_solo_header = [["Giornata", "Descrizione", "Entrate", "Saldo Totale"]]
        testo = bt.costruisci_riepilogo_whatsapp("1", classifica, cassa_solo_header)
        assert "Saldo Totale" not in testo
        assert "Fondo Cassa" not in testo

    def test_usa_asterisco_singolo_per_il_grassetto_stile_whatsapp(self):
        classifica = [["Giocatore", "Punti Totali", "Giornata 1"], ["MARIO", "10", "10"]]
        testo = bt.costruisci_riepilogo_whatsapp("1", classifica, [])
        assert "*Giornata 1" in testo
        assert "**" not in testo  # non deve essere markdown "standard" a doppio asterisco


# ---------------------------------------------------------------------------
# task_riepilogo_whatsapp — il job schedulato
# ---------------------------------------------------------------------------
class FakeSheetsBase:
    def __init__(self, giocate, classifica=None, cassa=None):
        self.giocate = giocate
        self.classifica = classifica or [["Giocatore", "Punti Totali"]]
        self.cassa = cassa or [["Giornata", "Descrizione", "Entrate", "Saldo Totale"]]

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, spreadsheetId, range):
        if "Giocate" in range:
            dati = self.giocate
        elif "Classifica" in range:
            dati = self.classifica
        else:
            dati = self.cassa

        class _R:
            def execute(self_inner, **kwargs):
                return {"values": dati}
        return _R()


class FakeBot:
    def __init__(self):
        self.messaggi = []

    async def send_message(self, chat_id, text):
        self.messaggi.append(text)


class FakeContext:
    def __init__(self):
        self.bot = FakeBot()


GIOCATE_INCOMPLETA = [
    ["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito"],
    ["Giornata 3", "MARIO", "Milan - Inter", "Fisse", "1", "1,80", "⏳ IN CORSO"],
]
GIOCATE_COMPLETA = [
    ["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito"],
    ["Giornata 3", "MARIO", "Milan - Inter", "Fisse", "1", "1,80", "✅ VINTA"],
]
CLASSIFICA_G3 = [["Giocatore", "Punti Totali", "Giornata 3"], ["MARIO", "4", "4"]]


@pytest.fixture(autouse=True)
def reset_dedup():
    """Il tracker e' globale nel modulo: azzeralo prima e dopo ogni test così
    i test non si influenzano a vicenda."""
    bt.ultima_giornata_riepilogo_inviata = None
    yield
    bt.ultima_giornata_riepilogo_inviata = None


@pytest.fixture
def giornata_corrente(monkeypatch):
    monkeypatch.setattr(bt, "ottieni_giornata_corrente", lambda: "3")


class TestTaskRiepilogoWhatsapp:

    def test_non_manda_nulla_se_ci_sono_eventi_in_corso(self, monkeypatch, giornata_corrente):
        monkeypatch.setattr(bt, "connetti_sheets", lambda: FakeSheetsBase(GIOCATE_INCOMPLETA))
        ctx = FakeContext()
        asyncio.run(bt.task_riepilogo_whatsapp(ctx))
        assert ctx.bot.messaggi == []

    def test_manda_il_riepilogo_quando_la_giornata_e_completa(self, monkeypatch, giornata_corrente):
        monkeypatch.setattr(bt, "connetti_sheets", lambda: FakeSheetsBase(GIOCATE_COMPLETA, CLASSIFICA_G3))
        ctx = FakeContext()
        asyncio.run(bt.task_riepilogo_whatsapp(ctx))
        assert len(ctx.bot.messaggi) == 1
        assert "Giornata 3" in ctx.bot.messaggi[0]

    def test_non_rimanda_due_volte_la_stessa_giornata(self, monkeypatch, giornata_corrente):
        monkeypatch.setattr(bt, "connetti_sheets", lambda: FakeSheetsBase(GIOCATE_COMPLETA, CLASSIFICA_G3))
        ctx = FakeContext()
        asyncio.run(bt.task_riepilogo_whatsapp(ctx))
        asyncio.run(bt.task_riepilogo_whatsapp(ctx))
        assert len(ctx.bot.messaggi) == 1

    def test_notifica_se_non_pronto_spiega_le_partite_in_corso(self, monkeypatch, giornata_corrente):
        monkeypatch.setattr(bt, "connetti_sheets", lambda: FakeSheetsBase(GIOCATE_INCOMPLETA))
        ctx = FakeContext()
        asyncio.run(bt.task_riepilogo_whatsapp(ctx, notifica_se_non_pronto=True))
        assert len(ctx.bot.messaggi) == 1
        assert "IN CORSO" in ctx.bot.messaggi[0]

    def test_notifica_se_non_pronto_e_gia_stato_mandato(self, monkeypatch, giornata_corrente):
        monkeypatch.setattr(bt, "connetti_sheets", lambda: FakeSheetsBase(GIOCATE_COMPLETA, CLASSIFICA_G3))
        ctx = FakeContext()
        asyncio.run(bt.task_riepilogo_whatsapp(ctx))  # invio normale
        asyncio.run(bt.task_riepilogo_whatsapp(ctx, notifica_se_non_pronto=True))
        assert len(ctx.bot.messaggi) == 2
        assert "già stato mandato" in ctx.bot.messaggi[1]

    def test_nessun_dato_per_la_giornata_non_manda_nulla_silenziosamente(self, monkeypatch, giornata_corrente):
        monkeypatch.setattr(bt, "connetti_sheets", lambda: FakeSheetsBase([["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito"]]))
        ctx = FakeContext()
        asyncio.run(bt.task_riepilogo_whatsapp(ctx))
        assert ctx.bot.messaggi == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
