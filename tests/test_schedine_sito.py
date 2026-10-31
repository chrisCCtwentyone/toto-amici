"""
Schedine dal sito (prova dal 31/10/2026, docs/ANALISI-SCHEDINE-SEGRETE.md).

Il bot pubblica la giornata aperta e crea le password; il Worker controlla la
scadenza e la password con le STESSE regole. Le proprietà bloccate qui:

1. La giornata aperta è la prima con la scadenza (prima partita meno 5 minuti)
   ancora futura, e un recupero nel futuro non riapre una giornata vecchia.
2. L'impronta della password coincide con quella del Worker (stesso vettore di
   frontend/worker/schedina.test.ts): se divergono, nessuno riesce a consegnare.
3. La password arriva solo a chi l'ha chiesta; gli altri admin sanno solo che è
   stata cambiata.
"""
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytz

import bot_telegram as bt
from conftest import ADMIN_DI_TEST


def partita(id_, giornata, utc, casa="Inter", ospite="Lecce"):
    return {"id": id_, "matchday": giornata, "utcDate": utc,
            "homeTeam": {"shortName": casa, "name": casa + " FC"}, "awayTeam": {"shortName": ospite}}


ORA = datetime(2026, 11, 7, 12, 0, tzinfo=pytz.UTC)


class TestGiornataAperta:
    def test_prima_giornata_con_scadenza_futura_e_partite_in_ordine(self):
        partite = [
            partita(1, 10, "2026-11-01T14:00:00Z"),                   # giornata 10: gia' iniziata
            partita(2, 10, "2026-11-08T19:45:00Z"),                   # ...anche se una partita e' futura
            partita(4, 11, "2026-11-08T17:00:00Z", "Roma", "Genoa"),
            partita(3, 11, "2026-11-07T14:00:00Z", "Milan", "Como"),
            partita(5, 12, "2026-11-22T14:00:00Z"),
        ]
        aperta = bt.giornata_aperta(partite, ORA, giocatori=["davide", "silvio"])
        assert aperta["giornata"] == 11
        assert aperta["scadenza_il"] == "2026-11-07T13:55:00Z"
        assert [p["id"] for p in aperta["partite"]] == [3, 4]
        assert aperta["partite"][0] == {"id": 3, "casa": "Milan", "ospite": "Como", "inizio_il": "2026-11-07T14:00:00Z"}
        assert aperta["giocatori"] == ["DAVIDE", "SILVIO"]

    def test_negli_ultimi_cinque_minuti_la_giornata_e_chiusa(self):
        partite = [partita(3, 11, "2026-11-07T12:04:00Z"), partita(5, 12, "2026-11-22T14:00:00Z")]
        assert bt.giornata_aperta(partite, ORA)["giornata"] == 12

    def test_un_recupero_futuro_non_riapre_una_giornata_vecchia(self):
        partite = [partita(1, 4, "2026-09-20T14:00:00Z"), partita(2, 4, "2026-11-20T18:00:00Z"),
                   partita(5, 12, "2026-11-22T14:00:00Z")]
        assert bt.giornata_aperta(partite, ORA)["giornata"] == 12

    def test_stagione_finita_o_senza_orari(self):
        assert bt.giornata_aperta([partita(1, 38, "2026-05-30T18:00:00Z")], ORA) is None
        assert bt.giornata_aperta([partita(1, 11, None)], ORA) is None

    def test_tutti_i_giocatori_del_torneo(self):
        aperta = bt.giornata_aperta([partita(3, 11, "2026-11-07T14:00:00Z")], ORA)
        assert aperta["giocatori"] == [g.upper() for g in bt.GIOCATORI]

    def test_la_pubblicazione_non_solleva_e_non_riscrive_se_uguale(self, monkeypatch):
        scritte = []
        monkeypatch.setattr(bt, "scrivi_kv", lambda chiave, corpo: scritte.append((chiave, corpo)))
        monkeypatch.setattr(bt, "_ultima_giornata_aperta", {"corpo": None})
        partite = [partita(3, 11, "2026-11-07T14:00:00Z")]
        bt.pubblica_giornata_aperta(partite, ORA)
        bt.pubblica_giornata_aperta(partite, ORA)
        assert [c for c, _ in scritte] == ["giornata_aperta"]
        assert json.loads(scritte[0][1])["giornata"] == 11

        def guasto(*_):
            raise RuntimeError("Cloudflare giu'")
        monkeypatch.setattr(bt, "scrivi_kv", guasto)
        bt.pubblica_giornata_aperta(partite, ORA, forza=True)  # non deve sollevare


class TestPassword:
    def test_impronta_uguale_al_worker(self):
        assert bt.impronta_password("0123abcd", "tigre-42-lago") == \
            "71b6a864e3cb6769455b6fa10237087c06e08791ce6d6c6bc264955196ec3d15"

    def test_formato_facile_da_scrivere(self):
        for _ in range(50):
            assert re.fullmatch(r"[a-z]+-[a-z]+-[a-z]+-[1-9][0-9]", bt.genera_password())

    def _update(self, utente=ADMIN_DI_TEST):
        return SimpleNamespace(effective_user=SimpleNamespace(id=utente, full_name="Silvio", first_name="Silvio"))

    def test_password_solo_a_chi_la_chiede_e_avviso_agli_altri(self, monkeypatch):
        bt.ADMIN_IDS = [ADMIN_DI_TEST, 777]
        scritte, inviati = {}, []
        monkeypatch.setattr(bt, "pubblicazione_attiva", lambda: True)
        monkeypatch.setattr(bt, "scrivi_kv", lambda chiave, corpo: scritte.update({chiave: json.loads(corpo)}))

        async def send_message(chat_id, text, **_):
            inviati.append((chat_id, text))
        contesto = SimpleNamespace(args=["Davide"], bot=SimpleNamespace(send_message=send_message))
        asyncio.run(bt.password_command(self._update(), contesto))

        salvata = scritte["password_DAVIDE"]
        a_chi_chiede = [t for c, t in inviati if c == ADMIN_DI_TEST]
        agli_altri = [t for c, t in inviati if c == 777]
        password = re.search(r"\n\n(\S+)\n\n", a_chi_chiede[0]).group(1)
        assert bt.impronta_password(salvata["sale"], password) == salvata["impronta"]
        assert "password" not in salvata
        assert agli_altri and all(password not in t for t in agli_altri)
        assert "DAVIDE" in agli_altri[0]

    def test_nome_sconosciuto_e_non_admin(self, monkeypatch):
        scritte, inviati = [], []
        monkeypatch.setattr(bt, "pubblicazione_attiva", lambda: True)
        monkeypatch.setattr(bt, "scrivi_kv", lambda *a: scritte.append(a))

        async def send_message(chat_id, text, **_):
            inviati.append((chat_id, text))
        bot = SimpleNamespace(send_message=send_message)
        asyncio.run(bt.password_command(self._update(), SimpleNamespace(args=["pippo"], bot=bot)))
        asyncio.run(bt.password_command(self._update(), SimpleNamespace(args=[], bot=bot)))
        asyncio.run(bt.password_command(self._update(utente=555), SimpleNamespace(args=["davide"], bot=bot)))
        assert scritte == []
        assert len(inviati) == 2 and all(t.startswith("Uso: /password") for _, t in inviati)

    def test_comando_registrato(self):
        import inspect
        assert "password" in [c for c, _ in bt.COMANDI_ADMIN]
        assert 'CommandHandler("password", password_command)' in inspect.getsource(bt.main)
