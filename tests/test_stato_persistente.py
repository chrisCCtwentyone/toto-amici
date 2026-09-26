"""
Test dello STATO PERSISTENTE fra un riavvio e l'altro (Sessione 25).

`ultima_giornata_riepilogo_inviata` viveva solo in RAM: a ogni riavvio di
Render si azzerava, e il riepilogo WhatsApp di una giornata già conclusa
ripartiva da capo — lo stesso testo, una seconda volta, senza che fosse
cambiato niente. Il disco di Render è effimero, quindi l'unico posto stabile
è lo spreadsheet: un foglio "Stato" a due colonne scritto solo dal bot.

Le proprietà bloccate qui:

1. **Dopo un riavvio il riepilogo NON riparte.** È il motivo per cui esiste
   tutto il resto.
2. **Lo stato non è mai più importante del lavoro.** Se il foglio Stato non è
   leggibile o non è scrivibile, il riepilogo parte lo stesso: si perde la
   protezione contro il doppio invio, non il messaggio.
3. **Il foglio si riscrive per intero, mai per indice di riga** — è la
   meccanica che causò la riscrittura di 13 giornate.
4. **Una nuova stagione azzera lo stato**, altrimenti la Giornata 5 dell'anno
   dopo verrebbe scambiata per già mandata: è lo stesso numero.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt


class FakeStato:
    """Spreadsheet finto con il solo foglio Stato, che registra le scritture."""

    def __init__(self, righe=None, foglio_esiste=True, rompi_lettura=False):
        self.righe = righe if righe is not None else [["Chiave", "Valore"]]
        self.foglio_esiste = foglio_esiste
        self.rompi_lettura = rompi_lettura
        self.fogli_creati = []
        self.range_scritti = []

    # --- catena di chiamate googleapiclient ---
    def spreadsheets(self): return self
    def values(self): return self

    def get(self, spreadsheetId, range=None):
        esito = self
        if range is None:  # metadati dello spreadsheet
            titoli = [bt.NOME_FOGLIO_STATO] if self.foglio_esiste else []
            return _Esec({"sheets": [{"properties": {"title": t}} for t in titoli]})
        if self.rompi_lettura:
            return _EsecRotta()
        return _Esec({"values": self.righe})

    def update(self, spreadsheetId, range, valueInputOption, body):
        self.range_scritti.append(range)
        self.righe = body["values"]
        return _Esec({})

    def batchUpdate(self, spreadsheetId, body):
        for richiesta in body["requests"]:
            self.fogli_creati.append(richiesta["addSheet"]["properties"]["title"])
        self.foglio_esiste = True
        return _Esec({})


class _Esec:
    def __init__(self, dati): self._dati = dati
    def execute(self, **kw): return self._dati


class _EsecRotta:
    def execute(self, **kw): raise RuntimeError("Sheets non risponde")


# ---------------------------------------------------------------------------
# 1. leggi_stato / scrivi_stato
# ---------------------------------------------------------------------------
class TestLeggiScriviStato:
    def test_scrivi_e_rileggi(self, monkeypatch):
        finto = FakeStato()
        monkeypatch.setattr(bt, "connetti_sheets", lambda: finto)
        bt.scrivi_stato("chiave", "42")
        assert bt.leggi_stato("chiave") == "42"

    def test_chiave_assente_torna_il_default(self, monkeypatch):
        monkeypatch.setattr(bt, "connetti_sheets", lambda: FakeStato())
        assert bt.leggi_stato("mai_scritta") is None
        assert bt.leggi_stato("mai_scritta", default="x") == "x"

    def test_valore_vuoto_vale_come_non_impostato(self, monkeypatch):
        """È così che si azzera una chiave senza accorciare il foglio."""
        finto = FakeStato([["Chiave", "Valore"], ["chiave", ""]])
        monkeypatch.setattr(bt, "connetti_sheets", lambda: finto)
        assert bt.leggi_stato("chiave") is None

    def test_foglio_illeggibile_non_solleva(self, monkeypatch):
        """PROPRIETÀ: una deduplica che non funziona fa mandare un messaggio in
        più; un'eccezione qui bloccherebbe il lavoro vero."""
        monkeypatch.setattr(bt, "connetti_sheets", lambda: FakeStato(rompi_lettura=True))
        assert bt.leggi_stato("chiave", default="fallback") == "fallback"

    def test_il_foglio_viene_creato_se_non_esiste(self, monkeypatch):
        finto = FakeStato(foglio_esiste=False)
        monkeypatch.setattr(bt, "connetti_sheets", lambda: finto)
        bt.scrivi_stato("chiave", "1")
        assert finto.fogli_creati == [bt.NOME_FOGLIO_STATO]

    def test_le_altre_chiavi_non_si_perdono(self, monkeypatch):
        finto = FakeStato([["Chiave", "Valore"], ["altra", "importante"]])
        monkeypatch.setattr(bt, "connetti_sheets", lambda: finto)
        bt.scrivi_stato("nuova", "1")
        assert bt.leggi_stato("altra") == "importante"
        assert bt.leggi_stato("nuova") == "1"

    def test_si_riscrive_sempre_da_A1_mai_per_indice_di_riga(self, monkeypatch):
        """PROPRIETÀ: scrivere per indice di riga è la meccanica che riscrisse
        gli esiti di 13 giornate. Qui il foglio è minuscolo e si riscrive
        intero, quindi quell'aritmetica non esiste proprio."""
        finto = FakeStato([["Chiave", "Valore"], ["a", "1"], ["b", "2"]])
        monkeypatch.setattr(bt, "connetti_sheets", lambda: finto)
        bt.scrivi_stato("b", "3")
        assert finto.range_scritti == [f"{bt.NOME_FOGLIO_STATO}!A1"]
        assert finto.righe[0] == ["Chiave", "Valore"], "l'intestazione resta"

    def test_l_intestazione_non_viene_scambiata_per_una_chiave(self, monkeypatch):
        finto = FakeStato([["Chiave", "Valore"], ["a", "1"]])
        monkeypatch.setattr(bt, "connetti_sheets", lambda: finto)
        bt.scrivi_stato("a", "2")
        assert [r[0] for r in finto.righe] == ["Chiave", "a"]


# ---------------------------------------------------------------------------
# 2. Il riepilogo dopo un riavvio
# ---------------------------------------------------------------------------
GIOCATE_COMPLETA = [
    ["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito"],
    ["Giornata 3", "MARIO", "Milan - Inter", "Fisse", "1", "1,80", "✅ VINTA"],
]
CLASSIFICA = [["Giocatore", "Punti Totali", "Giornata 3"], ["MARIO", "4", "4"]]
CASSA = [["Giornata", "Descrizione", "Entrate", "Saldo Totale"]]


class FakeSheets:
    """Giocate/Classifica/Cassa piene e una giornata conclusa."""
    def __init__(self):
        self.dati = {"Giocate": GIOCATE_COMPLETA, "Classifica": CLASSIFICA, "Cassa": CASSA}

    def spreadsheets(self): return self
    def values(self): return self

    def get(self, spreadsheetId, range):
        for nome, valori in self.dati.items():
            if nome in range:
                return _Esec({"values": valori})
        return _Esec({"values": []})


class FakeBot:
    def __init__(self): self.messaggi = []
    async def send_message(self, chat_id, text, **kw): self.messaggi.append(text)


class FakeContext:
    def __init__(self): self.bot = FakeBot()


@pytest.fixture
def giornata_conclusa(monkeypatch):
    monkeypatch.setattr(bt, "ottieni_giornata_corrente", lambda: "3")
    monkeypatch.setattr(bt, "connetti_sheets", lambda: FakeSheets())
    bt.ultima_giornata_riepilogo_inviata = None
    yield
    bt.ultima_giornata_riepilogo_inviata = None


class TestRiepilogoDopoIlRiavvio:
    def test_dopo_un_riavvio_non_lo_rimanda(self, monkeypatch, giornata_conclusa):
        """LA PROPRIETÀ CENTRALE. Il riavvio è simulato come succede davvero:
        la variabile in RAM è azzerata, ma il foglio Stato ricorda."""
        monkeypatch.setattr(bt, "leggi_stato", lambda chiave, default=None: "3")
        bt.ultima_giornata_riepilogo_inviata = None  # il riavvio

        ctx = FakeContext()
        asyncio.run(bt.task_riepilogo_whatsapp(ctx))
        assert ctx.bot.messaggi == [], "il riepilogo era già stato mandato prima del riavvio"

    def test_una_giornata_nuova_viene_mandata_lo_stesso(self, monkeypatch, giornata_conclusa):
        """Lo stato ricorda la giornata 2: la 3 deve partire."""
        monkeypatch.setattr(bt, "leggi_stato", lambda chiave, default=None: "2")
        monkeypatch.setattr(bt, "scrivi_stato", lambda chiave, valore: None)

        ctx = FakeContext()
        asyncio.run(bt.task_riepilogo_whatsapp(ctx))
        assert any("Giornata 3" in m for m in ctx.bot.messaggi)

    def test_l_invio_salva_lo_stato(self, monkeypatch, giornata_conclusa):
        salvati = []
        monkeypatch.setattr(bt, "leggi_stato", lambda chiave, default=None: None)
        monkeypatch.setattr(bt, "scrivi_stato", lambda chiave, valore: salvati.append((chiave, valore)))

        asyncio.run(bt.task_riepilogo_whatsapp(FakeContext()))
        assert salvati == [(bt.CHIAVE_ULTIMO_RIEPILOGO, "3")]

    def test_se_lo_stato_non_si_salva_il_riepilogo_parte_lo_stesso(self, monkeypatch, giornata_conclusa):
        """PROPRIETÀ: a quel punto il messaggio è già partito. Si perde la
        protezione contro il doppio invio, non il riepilogo."""
        def rotta(chiave, valore):
            raise RuntimeError("Sheets non risponde")
        monkeypatch.setattr(bt, "leggi_stato", lambda chiave, default=None: None)
        monkeypatch.setattr(bt, "scrivi_stato", rotta)

        ctx = FakeContext()
        asyncio.run(bt.task_riepilogo_whatsapp(ctx))
        assert any("Giornata 3" in m for m in ctx.bot.messaggi)

    def test_se_lo_stato_non_si_legge_il_riepilogo_parte(self, monkeypatch, giornata_conclusa):
        monkeypatch.setattr(bt, "leggi_stato", lambda chiave, default=None: default)
        monkeypatch.setattr(bt, "scrivi_stato", lambda chiave, valore: None)

        ctx = FakeContext()
        asyncio.run(bt.task_riepilogo_whatsapp(ctx))
        assert any("Giornata 3" in m for m in ctx.bot.messaggi)

    def test_forza_ignora_lo_stato_salvato(self, monkeypatch, giornata_conclusa):
        """/riepilogo deve poterlo rimandare anche se risulta già mandato."""
        monkeypatch.setattr(bt, "leggi_stato", lambda chiave, default=None: "3")
        monkeypatch.setattr(bt, "scrivi_stato", lambda chiave, valore: None)
        bt.ultima_giornata_riepilogo_inviata = "3"

        ctx = FakeContext()
        asyncio.run(bt.task_riepilogo_whatsapp(ctx, forza=True))
        assert any("Giornata 3" in m for m in ctx.bot.messaggi)

    def test_senza_riavvio_la_memoria_in_ram_basta_e_non_legge_il_foglio(self, monkeypatch, giornata_conclusa):
        """Nel caso normale non serve una lettura in più a Sheets."""
        letture = []
        monkeypatch.setattr(bt, "leggi_stato",
                            lambda chiave, default=None: letture.append(chiave) or None)
        bt.ultima_giornata_riepilogo_inviata = "3"

        ctx = FakeContext()
        asyncio.run(bt.task_riepilogo_whatsapp(ctx))
        assert ctx.bot.messaggi == []
        assert letture == [], "la globale bastava, il foglio non andava letto"


# ---------------------------------------------------------------------------
# 3. Nuova stagione
# ---------------------------------------------------------------------------
class TestArchiviazioneAzzeraLoStato:
    def test_la_chiave_del_riepilogo_viene_azzerata(self, monkeypatch):
        """PROPRIETÀ: senza l'azzeramento, il riepilogo della Giornata 5 della
        stagione NUOVA verrebbe scambiato per già mandato — stesso numero."""
        azzerate = []
        monkeypatch.setattr(bt, "scrivi_stato", lambda chiave, valore: azzerate.append((chiave, valore)))

        class FakeArchivio:
            def spreadsheets(self): return self
            def values(self): return self
            def get(self, spreadsheetId, range=None):
                if range is None:
                    return _Esec({"sheets": [{"properties": {"title": n, "sheetId": i}}
                                             for i, n in enumerate(bt.FOGLI_STAGIONE)]})
                return _Esec({"values": [["intestazione"], ["riga"]]})
            def batchUpdate(self, spreadsheetId, body):
                for n in bt.FOGLI_STAGIONE:
                    self._titoli_nuovi = True
                return _Esec({})
            def clear(self, spreadsheetId, range, body): return _Esec({})

        finto = FakeArchivio()
        chiamate = {"n": 0}
        def get_meta(spreadsheetId):
            chiamate["n"] += 1
            titoli = list(bt.FOGLI_STAGIONE)
            if chiamate["n"] > 1:  # dopo la duplicazione ci sono anche le copie
                titoli += [f"{n} 2026-27" for n in bt.FOGLI_STAGIONE]
            return _Esec({"sheets": [{"properties": {"title": t, "sheetId": i}}
                                     for i, t in enumerate(titoli)]})
        finto.get = lambda spreadsheetId, range=None: (
            get_meta(spreadsheetId) if range is None else _Esec({"values": [["h"], ["r"]]}))

        monkeypatch.setattr(bt, "connetti_sheets", lambda: finto)
        bt.archivia_stagione("2026-27")

        assert (bt.CHIAVE_ULTIMO_RIEPILOGO, "") in azzerate


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
