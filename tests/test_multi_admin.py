"""
Test del MULTI-ADMIN (Sessione 24).

Il bot riconosceva un solo `ADMIN_ID`. Ora riconosce una lista (`ADMIN_IDS`)
con due livelli: l'OWNER, che resta `ADMIN_ID`, e gli altri admin, che fanno
tutta la gestione quotidiana ma non toccano la chiave API né archiviano la
stagione.

Le proprietà bloccate qui, più che i singoli casi:

1. **Un bot non configurato non autorizza nessuno.** Se `ADMIN_ID` manca, la
   lista è vuota e `e_admin` dice no a tutti — compreso l'id 0, che è il
   valore che `ADMIN_ID` assume proprio quando non è configurato.
2. **Un invio fallito non ferma gli altri.** Basta che un admin abbia bloccato
   il bot perché un `send_message` in cima al giro faccia sparire la notifica
   anche a chi l'avrebbe ricevuta.
3. **Le operazioni riservate restano riservate anche se il bottone sparisce.**
   Nascondere una voce dal menu non è un controllo d'accesso: il `callback_data`
   si può rimandare da un messaggio vecchio.
4. **Nessuna notifica torna a `ADMIN_ID` fisso.** È la regressione più facile da
   introdurre: si aggiunge un handler copiando una riga esistente e il secondo
   admin smette di ricevere quella notifica, senza nessun errore.
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt

OWNER = 111
SECONDO = 222
ESTRANEO = 999


@pytest.fixture
def due_admin(monkeypatch):
    """Sostituisce la configurazione a un solo admin del conftest."""
    monkeypatch.setattr(bt, "ADMIN_ID", OWNER)
    monkeypatch.setattr(bt, "OWNER_ID", OWNER)
    monkeypatch.setattr(bt, "ADMIN_IDS", [OWNER, SECONDO])


# ---------------------------------------------------------------------------
# Finti oggetti Telegram
# ---------------------------------------------------------------------------
class _MessaggioFinto:
    def __init__(self, testo=""):
        self.text = testo
        self.risposte = []
        self.tastiere = []

    async def reply_text(self, testo, **kwargs):
        self.risposte.append(testo)
        self.tastiere.append(kwargs.get("reply_markup"))

    def callback_data_dell_ultima_tastiera(self):
        markup = self.tastiere[-1]
        return [b.callback_data for riga in markup.inline_keyboard for b in riga]


class _UtenteFinto:
    def __init__(self, user_id, nome="Mario Rossi"):
        self.id = user_id
        self.full_name = nome


class _UpdateFinto:
    def __init__(self, user_id, testo="", nome="Mario Rossi"):
        self.message = _MessaggioFinto(testo)
        self.effective_user = _UtenteFinto(user_id, nome)
        self.effective_chat = _UtenteFinto(user_id)


class _BotFinto:
    """Registra (chat_id, testo, parse_mode) di ogni invio.

    `fallisce_per` elenca i chat_id che devono sollevare un'eccezione, per
    simulare un admin che ha bloccato il bot. `rifiuta_markdown` simula il
    rifiuto di Telegram su una formattazione non valida.
    """

    def __init__(self, fallisce_per=(), rifiuta_markdown=False):
        self.inviati = []
        self.fallisce_per = set(fallisce_per)
        self.rifiuta_markdown = rifiuta_markdown

    async def send_message(self, chat_id, text, **kwargs):
        if chat_id in self.fallisce_per:
            raise RuntimeError(f"Forbidden: bot was blocked by the user ({chat_id})")
        if self.rifiuta_markdown and kwargs.get("parse_mode"):
            raise RuntimeError("Can't parse entities: can't find end of the entity")
        self.inviati.append((chat_id, text, kwargs.get("parse_mode")))

    @property
    def destinatari(self):
        return [chat_id for chat_id, _, _ in self.inviati]


class _ContextFinto:
    def __init__(self, bot=None, user_data=None):
        self.bot = bot or _BotFinto()
        self.user_data = user_data if user_data is not None else {}
        self.args = []


# ---------------------------------------------------------------------------
# 1. Lettura della configurazione
# ---------------------------------------------------------------------------
class TestLeggiAdminIds:
    def test_solo_owner_se_admin_ids_e_vuoto(self):
        assert bt.leggi_admin_ids(111, "") == [111]
        assert bt.leggi_admin_ids(111, None) == [111]

    def test_owner_sempre_per_primo(self):
        """L'ordine è quello di invio delle notifiche: l'owner per primo."""
        assert bt.leggi_admin_ids(111, "222,333") == [111, 222, 333]

    def test_separatori_ammessi(self):
        atteso = [111, 222, 333]
        for grezzo in ["222,333", "222, 333", "222;333", "222 333", "222\n333", " 222 , 333 "]:
            assert bt.leggi_admin_ids(111, grezzo) == atteso, grezzo

    def test_nessun_duplicato_anche_se_si_ripete_l_owner(self):
        assert bt.leggi_admin_ids(111, "222,111,222") == [111, 222]

    def test_un_valore_non_numerico_viene_ignorato_senza_far_fallire_l_avvio(self):
        """Una virgola di troppo incollata su Render non deve impedire l'avvio:
        il bot resterebbe giù fino al prossimo intervento manuale, che è molto
        peggio di un admin in meno per un giro."""
        assert bt.leggi_admin_ids(111, "222,,pippo,333") == [111, 222, 333]

    def test_lo_zero_non_entra_mai_nella_lista(self):
        """0 è il valore di ADMIN_ID non configurato: non è un utente."""
        assert bt.leggi_admin_ids(0, "") == []
        assert bt.leggi_admin_ids(0, "0") == []
        assert bt.leggi_admin_ids(111, "0,222") == [111, 222]


# ---------------------------------------------------------------------------
# 2. Chi può fare cosa
# ---------------------------------------------------------------------------
class TestPermessi:
    def test_owner_e_admin_e_owner(self, due_admin):
        assert bt.e_admin(OWNER)
        assert bt.e_owner(OWNER)

    def test_secondo_admin_e_admin_ma_non_owner(self, due_admin):
        assert bt.e_admin(SECONDO)
        assert not bt.e_owner(SECONDO)

    def test_estraneo_non_e_niente(self, due_admin):
        assert not bt.e_admin(ESTRANEO)
        assert not bt.e_owner(ESTRANEO)

    def test_bot_non_configurato_non_autorizza_nessuno(self, monkeypatch):
        """PROPRIETÀ: senza ADMIN_ID la lista è vuota e non passa nessuno.
        In particolare non passa l'id 0, che è proprio il valore che ADMIN_ID
        assume quando la variabile d'ambiente manca."""
        monkeypatch.setattr(bt, "ADMIN_ID", 0)
        monkeypatch.setattr(bt, "OWNER_ID", 0)
        monkeypatch.setattr(bt, "ADMIN_IDS", bt.leggi_admin_ids(0, ""))
        for utente in (0, OWNER, SECONDO, ESTRANEO):
            assert not bt.e_admin(utente), utente
            assert not bt.e_owner(utente), utente


# ---------------------------------------------------------------------------
# 3. Destinatari e invio
# ---------------------------------------------------------------------------
class TestDestinatari:
    def test_none_significa_tutti(self, due_admin):
        assert bt.destinatari_notifica() == [OWNER, SECONDO]

    def test_un_singolo_id(self, due_admin):
        assert bt.destinatari_notifica(SECONDO) == [SECONDO]

    def test_escludi_toglie_chi_ha_gia_l_esito(self, due_admin):
        assert bt.destinatari_notifica(escludi=SECONDO) == [OWNER]

    def test_con_un_solo_admin_escludere_lui_non_lascia_nessuno(self):
        """Caso normale finché il secondo admin non c'è: le righe di
        tracciabilità non devono mandare messaggi a vuoto."""
        assert bt.destinatari_notifica(escludi=bt.ADMIN_IDS[0]) == []


class TestAvvisaAdmin:
    def test_arriva_a_tutti_gli_admin(self, due_admin):
        bot = _BotFinto()
        inviati = asyncio.run(bt.avvisa_admin(_ContextFinto(bot), "ciao"))
        assert inviati == 2
        assert bot.destinatari == [OWNER, SECONDO]

    def test_un_admin_irraggiungibile_non_blocca_gli_altri(self, due_admin):
        """PROPRIETÀ: basta che UN admin abbia bloccato il bot perché un invio
        in cima al giro faccia sparire la notifica anche agli altri."""
        bot = _BotFinto(fallisce_per=[OWNER])
        inviati = asyncio.run(bt.avvisa_admin(_ContextFinto(bot), "anomalia"))
        assert inviati == 1
        assert bot.destinatari == [SECONDO]

    def test_se_falliscono_tutti_restituisce_zero_senza_sollevare(self, due_admin):
        bot = _BotFinto(fallisce_per=[OWNER, SECONDO])
        assert asyncio.run(bt.avvisa_admin(_ContextFinto(bot), "anomalia")) == 0

    def test_markdown_rifiutato_il_testo_parte_lo_stesso_senza_formattazione(self, due_admin):
        """Sessione 15: un underscore dispari (OVER_2.5) fa rifiutare a Telegram
        l'intero messaggio. Un errore di formattazione non deve far buttare via
        il contenuto."""
        bot = _BotFinto(rifiuta_markdown=True)
        inviati = asyncio.run(bt.avvisa_admin(_ContextFinto(bot), "1+OVER_2.5 vinto"))
        assert inviati == 2
        assert [p for _, _, p in bot.inviati] == [None, None]
        assert all("OVER_2.5" in t for _, t, _ in bot.inviati)

    def test_senza_parse_mode_non_lo_passa_affatto(self, due_admin):
        """Il riepilogo WhatsApp va inviato senza parse_mode: la chiamata deve
        restare identica a un send_message normale."""
        bot = _BotFinto()
        asyncio.run(bt.avvisa_admin(_ContextFinto(bot), "testo", parse_mode=None))
        assert [p for _, _, p in bot.inviati] == [None, None]


class TestTracciaAzione:
    def test_avvisa_gli_altri_e_non_chi_ha_agito(self, due_admin):
        bot = _BotFinto()
        upd = _UpdateFinto(SECONDO, nome="Dario")
        asyncio.run(bt.traccia_azione(upd, _ContextFinto(bot), "ha fatto una cosa."))
        assert bot.destinatari == [OWNER]
        assert "Dario" in bot.inviati[0][1]

    def test_con_un_solo_admin_non_manda_niente(self):
        bot = _BotFinto()
        upd = _UpdateFinto(bt.ADMIN_IDS[0])
        assert asyncio.run(bt.traccia_azione(upd, _ContextFinto(bot), "ha fatto una cosa.")) == 0
        assert bot.inviati == []


# ---------------------------------------------------------------------------
# 4. Le operazioni riservate all'owner
# ---------------------------------------------------------------------------
class TestOperazioniRiservate:
    def test_setkey_rifiutato_al_secondo_admin_e_la_chiave_non_viene_scritta(self, due_admin, monkeypatch):
        """PROPRIETÀ: il rifiuto non deve solo rispondere male, deve NON scrivere."""
        scritture = []
        monkeypatch.setattr(bt, "open", lambda *a, **k: scritture.append(a) or (_ for _ in ()).throw(AssertionError("non deve scrivere")), raising=False)

        upd = _UpdateFinto(SECONDO)
        ctx = _ContextFinto()
        ctx.args = ["chiave-segreta"]
        asyncio.run(bt.set_api_key_command(upd, ctx))

        assert scritture == []
        assert len(upd.message.risposte) == 1
        assert "riservato" in upd.message.risposte[0].lower()

    def test_setkey_funziona_per_l_owner(self, due_admin, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        upd = _UpdateFinto(OWNER)
        ctx = _ContextFinto()
        ctx.args = ["chiave-nuova"]
        asyncio.run(bt.set_api_key_command(upd, ctx))
        assert (tmp_path / "chiave_api.txt").read_text() == "chiave-nuova"

    def test_un_estraneo_non_riceve_nemmeno_la_spiegazione(self, due_admin):
        """A chi non è admin il bot resta muto: spiegare a uno sconosciuto che
        esiste un «amministratore principale» non serve a niente."""
        upd = _UpdateFinto(ESTRANEO)
        ctx = _ContextFinto()
        ctx.args = ["chiave"]
        asyncio.run(bt.set_api_key_command(upd, ctx))
        assert upd.message.risposte == []

    def test_archiviastagione_rifiutata_al_secondo_admin_senza_toccare_i_dati(self, due_admin, monkeypatch):
        archiviate = []
        monkeypatch.setattr(bt, "archivia_stagione", lambda e: archiviate.append(e))
        monkeypatch.setattr(bt, "stagione_corrente", lambda: "2026-27")

        upd = _UpdateFinto(SECONDO)
        ctx = _ContextFinto()
        stato = asyncio.run(bt.archivia_stagione_command(upd, ctx))

        assert archiviate == []
        assert stato is None, "non deve entrare nella conversazione di conferma"
        assert "riservato" in upd.message.risposte[0].lower()
        assert "codice_conferma_archiviazione" not in ctx.user_data

    def test_il_menu_non_mostra_la_chiave_api_al_secondo_admin(self, due_admin):
        upd_owner, upd_secondo = _UpdateFinto(OWNER), _UpdateFinto(SECONDO)
        asyncio.run(bt.start(upd_owner, _ContextFinto()))
        asyncio.run(bt.start(upd_secondo, _ContextFinto()))

        bottoni_owner = upd_owner.message.callback_data_dell_ultima_tastiera()
        bottoni_secondo = upd_secondo.message.callback_data_dell_ultima_tastiera()

        assert "menu_cambia_key" in bottoni_owner
        assert "menu_cambia_key" not in bottoni_secondo
        # tutto il resto del menu deve restare identico
        assert [b for b in bottoni_owner if b != "menu_cambia_key"] == bottoni_secondo

    def test_il_ramo_chiave_api_e_protetto_anche_arrivando_da_un_bottone_vecchio(self, due_admin):
        """PROPRIETÀ: nascondere un bottone non è un controllo d'accesso — un
        callback_data si può rimandare da un messaggio di ieri."""
        class _Query:
            def __init__(self, dati):
                self.data = dati
                self.testo = None
            async def answer(self): pass
            async def edit_message_text(self, testo, **kw): self.testo = testo

        class _UpdCb:
            def __init__(self, user_id):
                self.callback_query = _Query("menu_cambia_key")
                self.effective_user = _UtenteFinto(user_id)

        upd = _UpdCb(SECONDO)
        stato = asyncio.run(bt.gestisci_menu(upd, _ContextFinto()))
        assert stato != bt.ATTESA_NUOVA_KEY
        assert "amministratore principale" in upd.callback_query.testo

    def test_gestisci_testo_chiave_rifiuta_il_secondo_admin(self, due_admin, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        upd = _UpdateFinto(SECONDO, testo="chiave-rubata")
        asyncio.run(bt.gestisci_testo_chiave(upd, _ContextFinto()))
        assert not (tmp_path / "chiave_api.txt").exists()


# ---------------------------------------------------------------------------
# 5. I comandi quotidiani restano aperti a tutti gli admin
# ---------------------------------------------------------------------------
class TestComandiQuotidiani:
    def test_il_secondo_admin_puo_inserire_un_risultato_a_mano(self, due_admin):
        upd = _UpdateFinto(SECONDO, testo="2-1")
        ctx = _ContextFinto(user_data={"manuale_casa": "Inter", "manuale_ospite": "Roma"})
        stato = asyncio.run(bt.ricevi_risultato_manuale(upd, ctx))
        assert stato == bt.CONFERMA_RISULTATO_MANUALE

    def test_un_estraneo_no(self, due_admin):
        upd = _UpdateFinto(ESTRANEO, testo="2-1")
        ctx = _ContextFinto(user_data={"manuale_casa": "Inter", "manuale_ospite": "Roma"})
        assert asyncio.run(bt.ricevi_risultato_manuale(upd, ctx)) is None
        assert upd.message.risposte == []

    def test_i_comandi_riservati_non_compaiono_nel_menu_degli_admin(self):
        riservati = {"setkey", "archiviastagione"}
        assert riservati & {c for c, _ in bt.COMANDI_OWNER} == riservati
        assert riservati & {c for c, _ in bt.COMANDI_ADMIN} == set()


class TestUnAvvisoFallitoNonFaSembrareFallitoIlLavoro:
    """PROPRIETÀ: la tracciabilità viene chiamata subito dopo operazioni che
    hanno GIÀ scritto su Sheets. Se stava dentro il `try` dell'operazione, un
    problema nell'avvisare gli altri admin veniva riportato a chi ha agito come
    «archiviazione fallita» o «errore nell'applicazione del risultato» — con i
    dati invece perfettamente scritti. È la stessa regola per cui un errore di
    formattazione non deve far buttare via un lavoro riuscito (Sessione 15)."""

    def test_traccia_azione_non_solleva_mai(self, due_admin):
        class _BotRotto:
            async def send_message(self, *a, **kw):
                raise RuntimeError("Telegram irraggiungibile")

        upd = _UpdateFinto(SECONDO)
        assert asyncio.run(bt.traccia_azione(upd, _ContextFinto(_BotRotto()), "ha fatto una cosa.")) == 0

    def test_risultato_manuale_scritto_non_viene_dichiarato_fallito(self, due_admin, monkeypatch):
        monkeypatch.setattr(bt, "applica_risultato_manuale",
                            lambda *a: "✅ Risultato applicato, 3 schedine aggiornate")

        class _BotCheFallisceSoloSullaTracciabilita:
            """Risponde a chi ha agito, ma non riesce a raggiungere l'altro admin."""
            def __init__(self):
                self.inviati = []
            async def send_message(self, chat_id, text, **kw):
                if chat_id != SECONDO:
                    raise RuntimeError("Forbidden: bot was blocked by the user")
                self.inviati.append(text)

        class _Query:
            def __init__(self):
                self.data = "confermamanuale_si"
                self.testo = None
            async def answer(self): pass
            async def edit_message_text(self, testo, **kw): self.testo = testo

        class _UpdCb:
            def __init__(self):
                self.callback_query = _Query()
                self.effective_user = _UtenteFinto(SECONDO, "Dario")

        bot = _BotCheFallisceSoloSullaTracciabilita()
        ctx = _ContextFinto(bot, user_data={
            "manuale_giornata": "5", "manuale_casa_full": "Inter", "manuale_ospite_full": "Roma",
            "manuale_gol_casa": 2, "manuale_gol_ospite": 1,
        })
        asyncio.run(bt.esegui_conferma_risultato_manuale(_UpdCb(), ctx))

        assert len(bot.inviati) == 1
        assert "applicato" in bot.inviati[0]
        assert not any("errore" in t.lower() for t in bot.inviati), \
            "un avviso non consegnato non deve diventare un errore sull'operazione"


# ---------------------------------------------------------------------------
# 6. Invariante sul sorgente
# ---------------------------------------------------------------------------
class TestInvarianteSorgente:
    """La regressione più facile: si aggiunge un handler copiando una riga
    esistente, e il secondo admin smette di ricevere quella notifica — senza
    nessun errore, senza niente nei log. Questi due controlli la intercettano
    a livello di sorgente, dove i test sul comportamento non arrivano perché
    l'handler nuovo non ce l'ha ancora nessuno."""

    @pytest.fixture
    def sorgente(self):
        percorso = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot_telegram.py")
        with open(percorso, encoding="utf-8") as f:
            return f.read()

    def test_nessuna_notifica_va_a_admin_id_fisso(self, sorgente):
        colpevoli = [r.strip() for r in sorgente.splitlines() if "chat_id=ADMIN_ID" in r]
        assert colpevoli == [], (
            "Usa avvisa_admin(...) per le notifiche a tutti, o destinatari=<id> "
            "per rispondere a chi ha agito:\n" + "\n".join(colpevoli)
        )

    def test_nessun_controllo_d_accesso_confronta_con_admin_id(self, sorgente):
        colpevoli = [r.strip() for r in sorgente.splitlines()
                     if re.search(r"effective_user\.id\s*[!=]=\s*ADMIN_ID", r)]
        assert colpevoli == [], (
            "Usa e_admin(...) o e_owner(...):\n" + "\n".join(colpevoli)
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
