"""
Test del LAVORO IN PARALLELO fra due admin (Sessione 24).

Il blocco anti-doppione (`SchedinaGiaPresente`) rilegge il foglio prima di
scrivere e rifiuta una schedina già presente. Copre il caso normale — «l'ha
caricata lui dieci minuti fa» — ma da solo lascia scoperti due casi che si
aprono proprio quando gli admin diventano due:

1. **Lo stesso istante.** Fra la rilettura del foglio e la scrittura passa
   circa un secondo. Due «Salva» premuti insieme trovano entrambi il posto
   libero e scrivono entrambi: il controllo non serve a niente proprio nel
   caso che doveva coprire. Lo chiude `lock_salvataggio_schedina()`.
2. **Nessuno dei due ha ancora salvato**, perché stanno entrambi caricando le
   foto. Su Sheets non c'è ancora niente da trovare, quindi nessun controllo
   può accorgersene: se ne accorgono alla fine, e chi perde ha buttato via la
   lettura IA. Lo copre il registro `LAVORAZIONI_IN_CORSO`, che avvisa prima.
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt

SILVIO, DARIO = 111, 222


@pytest.fixture(autouse=True)
def registro_pulito():
    bt.LAVORAZIONI_IN_CORSO.clear()
    yield
    bt.LAVORAZIONI_IN_CORSO.clear()


# ---------------------------------------------------------------------------
# 1. Il registro di chi sta lavorando a cosa
# ---------------------------------------------------------------------------
class TestRegistroLavorazioni:
    def test_l_altro_admin_vede_la_lavorazione(self):
        bt.segna_lavorazione("5", "mario", SILVIO, "Silvio")
        assert bt.lavorazione_altrui("5", "mario", DARIO) == ("Silvio", 0)

    def test_chi_sta_lavorando_non_avvisa_se_stesso(self):
        """Riaprire il proprio caricamento non deve dirti che sei occupato tu."""
        bt.segna_lavorazione("5", "mario", SILVIO, "Silvio")
        assert bt.lavorazione_altrui("5", "mario", SILVIO) is None

    def test_giornata_e_giocatore_diversi_non_si_toccano(self):
        bt.segna_lavorazione("5", "mario", SILVIO, "Silvio")
        assert bt.lavorazione_altrui("6", "mario", DARIO) is None
        assert bt.lavorazione_altrui("5", "luca", DARIO) is None

    def test_maiuscole_e_spazi_non_creano_due_lavorazioni_diverse(self):
        bt.segna_lavorazione("5", " Mario ", SILVIO, "Silvio")
        assert bt.lavorazione_altrui("5", "mario", DARIO) is not None

    def test_una_lavorazione_abbandonata_scade(self):
        """PROPRIETÀ: un flusso interrotto a metà (app chiusa, foto mai
        confermate) non deve tenere occupata una schedina per sempre."""
        vecchia = time.time() - bt.SCADENZA_LAVORAZIONE_S - 1
        bt.segna_lavorazione("5", "mario", SILVIO, "Silvio", adesso=vecchia)
        assert bt.lavorazione_altrui("5", "mario", DARIO) is None

    def test_le_lavorazioni_scadute_non_restano_in_memoria(self):
        bt.segna_lavorazione("5", "mario", SILVIO, "Silvio",
                             adesso=time.time() - bt.SCADENZA_LAVORAZIONE_S - 1)
        bt.segna_lavorazione("6", "luca", DARIO, "Dario")
        assert list(bt.LAVORAZIONI_IN_CORSO) == [bt.chiave_lavorazione("6", "luca")]

    def test_si_libera_solo_la_propria_lavorazione(self):
        """PROPRIETÀ: annullare il proprio caricamento non deve sbloccare
        quello di un altro, che sta ancora lavorando."""
        bt.segna_lavorazione("5", "mario", SILVIO, "Silvio")
        bt.libera_lavorazione("5", "mario", DARIO)
        assert bt.lavorazione_altrui("5", "mario", DARIO) is not None
        bt.libera_lavorazione("5", "mario", SILVIO)
        assert bt.lavorazione_altrui("5", "mario", DARIO) is None

    @pytest.mark.parametrize("secondi, atteso", [
        (0, "da meno di un minuto"), (59, "da meno di un minuto"),
        (60, "da 1 min"), (185, "da 3 min"),
    ])
    def test_da_quanto(self, secondi, atteso):
        assert bt.da_quanto(secondi) == atteso


# ---------------------------------------------------------------------------
# 2. Due salvataggi nello stesso istante
# ---------------------------------------------------------------------------
class _FoglioFinto:
    """Riproduce il «rileggi, controlla, scrivi» di scrivi_su_sheets_con_regole,
    con una finestra VERA fra il controllo e la scrittura — è quella finestra
    che il lock deve chiudere."""

    def __init__(self, ritardo=0.05):
        self.scritte = []
        self.ritardo = ritardo

    def scrivi(self, giocatore, giornata, _json):
        chiave = (str(giornata).strip(), str(giocatore).strip().lower())
        if chiave in self.scritte:
            raise bt.SchedinaGiaPresente(str(giocatore).upper(), giornata, [2, 9])
        time.sleep(self.ritardo)  # fra il controllo e la scrittura
        self.scritte.append(chiave)
        return True


class _Query:
    def __init__(self):
        self.data = "salva_ia_si"
        self.messaggi = []
    async def answer(self): pass
    async def edit_message_text(self, testo, **kw): self.messaggi.append(testo)


class _Utente:
    def __init__(self, user_id):
        self.id = user_id
        self.full_name = f"Admin {user_id}"


class _Update:
    def __init__(self, user_id):
        self.callback_query = _Query()
        self.effective_user = _Utente(user_id)


class _Context:
    def __init__(self, user_data):
        self.user_data = user_data
        self.bot = None


class TestSalvataggiSimultanei:
    def _salva(self, monkeypatch, foglio, admin_id):
        monkeypatch.setattr(bt, "scrivi_su_sheets_con_regole", foglio.scrivi)
        upd = _Update(admin_id)
        ctx = _Context({"giocatore": "mario", "giornata": "5", "risultato_json": "{}"})
        return upd, ctx

    def test_due_salvataggi_insieme_scrivono_una_volta_sola(self, monkeypatch):
        """PROPRIETÀ CENTRALE: senza il lock entrambi i controlli rileggono il
        foglio prima che l'altro abbia scritto, lo trovano libero, e la
        schedina finisce due volte — i punti verrebbero contati due volte
        (misurato altrove: 50 diventano 90)."""
        foglio = _FoglioFinto()
        upd_a, ctx_a = self._salva(monkeypatch, foglio, SILVIO)
        upd_b, ctx_b = self._salva(monkeypatch, foglio, DARIO)

        async def insieme():
            await asyncio.gather(
                bt.esegui_salvataggio_ia(upd_a, ctx_a),
                bt.esegui_salvataggio_ia(upd_b, ctx_b),
            )

        asyncio.run(insieme())

        assert len(foglio.scritte) == 1, "la schedina è stata scritta due volte"
        messaggi = upd_a.callback_query.messaggi + upd_b.callback_query.messaggi
        assert any("salvata" in m for m in messaggi), "uno dei due doveva riuscire"
        assert any("già presente" in m for m in messaggi), "l'altro doveva essere fermato"

    def test_un_salvataggio_da_solo_funziona_normalmente(self):
        """Il lock non deve rompere il caso normale, che è il 99%."""
        foglio = _FoglioFinto(ritardo=0)
        import unittest.mock as mock
        with mock.patch.object(bt, "scrivi_su_sheets_con_regole", foglio.scrivi):
            upd = _Update(SILVIO)
            ctx = _Context({"giocatore": "mario", "giornata": "5", "risultato_json": "{}"})
            asyncio.run(bt.esegui_salvataggio_ia(upd, ctx))
        assert foglio.scritte == [("5", "mario")]
        assert "salvata" in upd.callback_query.messaggi[-1]

    def test_il_registro_si_libera_a_fine_salvataggio(self, monkeypatch):
        foglio = _FoglioFinto(ritardo=0)
        monkeypatch.setattr(bt, "scrivi_su_sheets_con_regole", foglio.scrivi)
        bt.segna_lavorazione("5", "mario", SILVIO, "Silvio")

        upd = _Update(SILVIO)
        ctx = _Context({"giocatore": "mario", "giornata": "5", "risultato_json": "{}",
                        "lavorazione_admin_id": SILVIO})
        asyncio.run(bt.esegui_salvataggio_ia(upd, ctx))

        assert bt.lavorazione_altrui("5", "mario", DARIO) is None, \
            "finito il caricamento, la schedina deve tornare libera"


# ---------------------------------------------------------------------------
# 3. Il controllo anticipato, prima di spendere la chiamata all'IA
# ---------------------------------------------------------------------------
class _UpdateConferma(_Update):
    def __init__(self, user_id):
        super().__init__(user_id)
        self.callback_query.data = "conferma_si"


class TestControlloPrimaDellIA:
    def _contesto(self):
        return _Context({"giocatore": "mario", "giornata": "5", "foto_ricevute": []})

    def test_schedina_gia_presente_ferma_tutto_senza_chiamare_l_ia(self, monkeypatch):
        """Scoprire il doppione DOPO la lettura IA significa aver buttato via
        una chiamata a Gemini e una ventina di secondi di attesa."""
        chiamate_ia = []
        monkeypatch.setattr(bt, "schedina_gia_nel_foglio",
                            lambda g, n: asyncio.sleep(0, result=[2, 3, 4]))
        monkeypatch.setattr(bt, "analizza_schedine_multiple",
                            lambda foto: chiamate_ia.append(foto) or "{}")

        upd = _UpdateConferma(SILVIO)
        stato = asyncio.run(bt.esegui_conferma(upd, self._contesto()))

        assert chiamate_ia == [], "l'IA non doveva essere chiamata"
        assert stato == bt.ConversationHandler.END
        assert "già presente" in upd.callback_query.messaggi[-1]

    def test_se_il_foglio_non_risponde_si_procede_lo_stesso(self, monkeypatch):
        """PROPRIETÀ: questo controllo è un anticipo, non la guardia. Quella
        vera è dentro scrivi_su_sheets_con_regole e rifiuta comunque. Un errore
        di lettura qui deve al massimo far perdere il vantaggio dell'anticipo,
        mai impedire di caricare una schedina."""
        async def foglio_rotto(_g, _n):
            raise RuntimeError("Sheets non risponde")

        chiamate_ia = []
        monkeypatch.setattr(bt, "schedina_gia_nel_foglio", foglio_rotto)
        monkeypatch.setattr(bt, "analizza_schedine_multiple",
                            lambda foto: chiamate_ia.append(foto) or '{"eventi": {}}')
        monkeypatch.setattr(bt, "normalizza_nomi_partite", lambda j, g: j)

        asyncio.run(bt.esegui_conferma(_UpdateConferma(SILVIO), self._contesto()))
        assert chiamate_ia == [[]], "il caricamento doveva proseguire"

    def test_la_lavorazione_viene_registrata_quando_parte_l_ia(self, monkeypatch):
        monkeypatch.setattr(bt, "schedina_gia_nel_foglio", lambda g, n: asyncio.sleep(0, result=[]))
        monkeypatch.setattr(bt, "analizza_schedine_multiple", lambda foto: '{"eventi": {}}')
        monkeypatch.setattr(bt, "normalizza_nomi_partite", lambda j, g: j)

        ctx = self._contesto()
        asyncio.run(bt.esegui_conferma(_UpdateConferma(SILVIO), ctx))
        # La lettura IA vuota chiude il flusso e ripulisce: la schedina resta libera.
        assert bt.lavorazione_altrui("5", "mario", DARIO) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
