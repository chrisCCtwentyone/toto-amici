"""
Test di CONSISTENZA sui punti in cui un utente inserisce dati (Sessione 23).

Domanda dell'utente: «se carico una schedina per un giocatore che ce l'ha gia',
cosa succede? si sovrascrive? si blocca tutto?». Questi test rispondono con il
comportamento REALE, non con quello sperato, e lo bloccano perche' non cambi
per sbaglio.

I percorsi coperti, cioe' tutti quelli dove un input umano arriva ai dati:
1. caricamento schedina da foto (conferma IA -> scrittura su Sheets)
2. risultato inserito a mano
3. accessi da parte di chi non e' l'admin

⚠️ Il test test_doppio_caricamento_gonfia_i_punti documenta un RISCHIO REALE,
non un comportamento desiderato: caricare due volte la stessa schedina non
da' nessun errore e quasi raddoppia i punti. Se un giorno si aggiunge una
guardia contro i doppioni, quel test va aggiornato (e diventa la prova che la
guardia funziona).
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt


ID_ADMIN = 4242
ID_ESTRANEO = 9999


@pytest.fixture
def admin(monkeypatch):
    """Rende ID_ADMIN un amministratore riconosciuto.

    Il controllo d'accesso sta cambiando (un'altra sessione sta introducendo
    piu' amministratori): la fixture copre entrambe le forme, cosi' questi test
    restano validi comunque vada a finire.
    """
    monkeypatch.setattr(bt, "ADMIN_ID", ID_ADMIN, raising=False)
    monkeypatch.setattr(bt, "OWNER_ID", ID_ADMIN, raising=False)
    monkeypatch.setattr(bt, "ADMIN_IDS", [ID_ADMIN], raising=False)
    return ID_ADMIN


INTESTAZIONE = [["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito", "Vincita", "Punti"]]

MATCH_MILAN_INTER = [{
    "homeTeam": {"name": "AC Milan", "shortName": "Milan"},
    "awayTeam": {"name": "FC Internazionale Milano", "shortName": "Inter"},
    "status": "FINISHED",
    "score": {"fullTime": {"home": 2, "away": 0}},
}]


# ---------------------------------------------------------------------------
# Finti Google Sheets e Telegram
# ---------------------------------------------------------------------------
class _Esec:
    def execute(self, **kwargs):
        return {}


class FakeValues:
    def __init__(self, righe_giocate, righe_cassa=None):
        self.righe_giocate = righe_giocate
        self.righe_cassa = righe_cassa or [["Giornata", "Descrizione", "Entrate", "Saldo Totale"]]
        self.classifica_scritta = None
        self.righe_aggiunte = []

    def get(self, spreadsheetId, range):
        if "Giocate" in range:
            dati = self.righe_giocate
        elif "Cassa" in range:
            dati = self.righe_cassa
        else:
            dati = [["Giocatore", "Punti Totali"]]

        class _R:
            def execute(self_inner, **kwargs):
                # Copia: il bot aggiunge la riga nuova alla lista che riceve e
                # poi chiama append() sull'API. Restituendo la lista vera, il
                # finto foglio conterebbe due volte la stessa scrittura.
                return {"values": [list(r) for r in dati]}
        return _R()

    def batchUpdate(self, spreadsheetId, body):
        return _Esec()

    def update(self, spreadsheetId, range, valueInputOption, body):
        if "Classifica" in range:
            self.classifica_scritta = body["values"]
        return _Esec()

    def append(self, spreadsheetId, range, valueInputOption, body):
        self.righe_aggiunte.extend(body["values"])
        if "Cassa" in range:
            self.righe_cassa.extend(body["values"])
        else:
            self.righe_giocate.extend(body["values"])
        return _Esec()


class FakeService:
    def __init__(self, righe_giocate=None, righe_cassa=None):
        self.values_obj = FakeValues(righe_giocate if righe_giocate is not None else list(INTESTAZIONE), righe_cassa)

    def spreadsheets(self):
        return self

    def values(self):
        return self.values_obj

    def get(self, **kwargs):
        class _R:
            def execute(self_inner, **kw):
                return {"sheets": [{"properties": {"sheetId": 0, "title": "Giocate"}}]}
        return _R()

    def batchUpdate(self, **kwargs):
        return _Esec()


def schedina_json(n_fisse=4, n_combo=1, n_doppie=2, n_variabili=3, vincita="100,00", partita="Milan - Inter"):
    """Lettura IA di una schedina regolamentare: 1 combo, 4 fisse, 2 doppie, 3 variabili."""
    def eventi(n, pronostico):
        return [{"partita": partita, "pronostico": pronostico, "quota": "1.50"} for _ in range(n)]
    return json.dumps({
        "vincita_potenziale": vincita,
        "eventi": {
            "Combo": eventi(n_combo, "1+OVER_2.5"),
            "Fisse": eventi(n_fisse, "1"),
            "Doppie Chance": eventi(n_doppie, "1X"),
            "Variabili": eventi(n_variabili, "OVER_2.5"),
        },
    })


def righe_schedina_vincente(giocatore, giornata="Giornata 5", n=10, vincita="100,00"):
    """n righe tutte vincenti (segno 1, la partita finisce 2-0) per un giocatore."""
    righe = []
    for i in range(n):
        riga = [giornata, giocatore, "Milan - Inter", "Fisse", "1", "1,50", "", "", ""]
        if i == 0:
            riga[7] = vincita
        righe.append(riga)
    return righe


# ---------------------------------------------------------------------------
# 1. Doppio caricamento della stessa schedina
# ---------------------------------------------------------------------------
class TestDoppioCaricamentoSchedina:
    """Cosa succede se la stessa schedina viene caricata due volte."""

    def test_il_secondo_caricamento_aggiunge_righe_invece_di_sostituirle(self, monkeypatch):
        service = FakeService()
        monkeypatch.setattr(bt, "connetti_sheets", lambda: service)

        assert bt.scrivi_su_sheets_con_regole("mario", "5", schedina_json()) is True
        dopo_il_primo = len(service.values_obj.righe_aggiunte)
        assert bt.scrivi_su_sheets_con_regole("mario", "5", schedina_json()) is True

        righe = service.values_obj.righe_aggiunte
        assert len(righe) == dopo_il_primo * 2, "il secondo caricamento non sostituisce: accoda"
        assert all(r[0] == "Giornata 5" and r[1] == "MARIO" for r in righe)

    def test_doppio_caricamento_gonfia_i_punti(self, monkeypatch):
        """⚠️ RISCHIO DOCUMENTATO, non comportamento desiderato.

        Nessun errore, nessun avviso: la giornata viene semplicemente contata
        due volte. Misurato: 50 punti diventano 90 (20 eventi da 4 punti + 10
        di bonus chiusura, invece di 10 eventi + bonus).
        """
        def punti_di_mario(righe):
            service = FakeService(list(INTESTAZIONE) + righe)
            monkeypatch.setattr(bt, "connetti_sheets", lambda: service)
            bt.esegui_calcolo_risultati("5", matches_api=MATCH_MILAN_INTER)
            riga = next(r for r in service.values_obj.classifica_scritta if r[0] == "MARIO")
            return riga[1]

        una_volta = punti_di_mario(righe_schedina_vincente("MARIO"))
        due_volte = punti_di_mario(righe_schedina_vincente("MARIO") * 2)

        assert una_volta == 50
        assert due_volte == 90, "la schedina duplicata viene contata tutta una seconda volta"

    def test_la_cassa_non_paga_due_volte_la_stessa_schedina(self, monkeypatch):
        """INVARIANTE che regge: il pagamento in Cassa e' protetto dalla
        descrizione gia' presente, quindi ricalcolare non versa due volte."""
        cassa = [["Giornata", "Descrizione", "Entrate", "Saldo Totale"]]
        service = FakeService(list(INTESTAZIONE) + righe_schedina_vincente("MARIO"), cassa)
        monkeypatch.setattr(bt, "connetti_sheets", lambda: service)

        bt.esegui_calcolo_risultati("5", matches_api=MATCH_MILAN_INTER)
        movimenti_dopo_il_primo = len(service.values_obj.righe_cassa)
        bt.esegui_calcolo_risultati("5", matches_api=MATCH_MILAN_INTER)

        assert len(service.values_obj.righe_cassa) == movimenti_dopo_il_primo
        pagamenti = [r for r in service.values_obj.righe_cassa if "chiude la schedina" in str(r[1])]
        assert len(pagamenti) == 1, "un solo versamento per la stessa schedina chiusa"


# ---------------------------------------------------------------------------
# 2. Scrittura di una schedina: cosa viene accettato e cosa no
# ---------------------------------------------------------------------------
class TestScritturaSchedina:

    def _scrivi(self, monkeypatch, *args, **kwargs):
        service = FakeService()
        monkeypatch.setattr(bt, "connetti_sheets", lambda: service)
        esito = bt.scrivi_su_sheets_con_regole(*args, **kwargs)
        return esito, service.values_obj.righe_aggiunte

    def test_eventi_oltre_il_limite_marcati_annullati_e_non_scartati(self, monkeypatch):
        # 6 fisse dove il regolamento ne ammette 4: le due in piu' restano nel
        # foglio ma marcate, cosi' la bolletta resta leggibile e valgono 0 punti.
        _, righe = self._scrivi(monkeypatch, "mario", "5", schedina_json(n_fisse=6))
        fisse = [r for r in righe if r[3] == "Fisse"]
        assert len(fisse) == 6
        assert [("ANNULLATA ECCESSO" in r[4]) for r in fisse] == [False, False, False, False, True, True]
        for r in fisse:
            if "ANNULLATA ECCESSO" in r[4]:
                assert bt.calcola_punteggio_partita(r[4], 1.50) == 0

    def test_lettura_ia_vuota_non_scrive_nulla(self, monkeypatch):
        """Un risultato vuoto dell'IA non deve mai diventare una schedina vuota
        nel foglio: la funzione non scrive e dice di no (regola di Sessione 15)."""
        vuota = json.dumps({"vincita_potenziale": "0", "eventi": {}})
        esito, righe = self._scrivi(monkeypatch, "mario", "5", vuota)
        assert esito is False
        assert righe == []

    def test_json_malformato_solleva_errore_invece_di_scrivere_dati_a_meta(self, monkeypatch):
        service = FakeService()
        monkeypatch.setattr(bt, "connetti_sheets", lambda: service)
        with pytest.raises(json.JSONDecodeError):
            bt.scrivi_su_sheets_con_regole("mario", "5", "{non è json}")
        assert service.values_obj.righe_aggiunte == [], "niente scritture parziali"

    def test_il_nome_del_giocatore_viene_normalizzato_in_maiuscolo(self, monkeypatch):
        # Il nome e' la chiave che lega Giocate e Classifica: se cambia forma,
        # il bot non ritrova piu' il giocatore.
        _, righe = self._scrivi(monkeypatch, "mario", "5", schedina_json())
        assert {r[1] for r in righe} == {"MARIO"}

    def test_spazi_attorno_al_nome_restano_nel_foglio(self, monkeypatch):
        """⚠️ RISCHIO DOCUMENTATO: il nome viene messo in maiuscolo ma non
        ripulito dagli spazi, e ' MARIO ' non coincide con 'MARIO' in Classifica.
        Oggi non succede (i nomi arrivano da bottoni fissi), ma se un domani si
        potesse digitare il nome, questo test dice cosa aspettarsi."""
        _, righe = self._scrivi(monkeypatch, " mario ", "5", schedina_json())
        assert righe[0][1] == " MARIO "

    def test_vincita_non_numerica_diventa_zero_invece_di_far_fallire_il_salvataggio(self, monkeypatch):
        _, righe = self._scrivi(monkeypatch, "mario", "5", schedina_json(vincita="non leggibile"))
        assert righe[0][7] == "0,00"

    def test_la_vincita_compare_una_sola_volta_nella_schedina(self, monkeypatch):
        _, righe = self._scrivi(monkeypatch, "mario", "5", schedina_json())
        con_vincita = [r for r in righe if len(r) > 7 and str(r[7]).strip()]
        assert len(con_vincita) == 1, "la vincita potenziale sta solo sulla prima riga"


# ---------------------------------------------------------------------------
# 3. Risultato inserito a mano
# ---------------------------------------------------------------------------
class _MessaggioFinto:
    def __init__(self, testo):
        self.text = testo
        self.risposte = []

    async def reply_text(self, testo, **kwargs):
        self.risposte.append(testo)


class _UtenteFinto:
    def __init__(self, user_id):
        self.id = user_id


class _UpdateFinto:
    def __init__(self, testo, user_id=ID_ADMIN):
        self.message = _MessaggioFinto(testo)
        self.effective_user = _UtenteFinto(user_id)


class _BotFinto:
    def __init__(self):
        self.inviati = []

    async def send_message(self, chat_id, text, **kwargs):
        self.inviati.append(text)


class _ContextFinto:
    def __init__(self, dati=None):
        self.user_data = dati if dati is not None else {}
        self.bot = _BotFinto()


class TestRisultatoManuale:
    """Il risultato lo digita l'admin: e' l'unico testo libero che arriva vicino
    ai dati, quindi la validazione deve essere rigida."""

    def _invia(self, testo, user_id=ID_ADMIN):
        ctx = _ContextFinto({"manuale_casa": "Milan", "manuale_ospite": "Inter", "manuale_giornata": "5"})
        upd = _UpdateFinto(testo, user_id)
        stato = asyncio.run(bt.ricevi_risultato_manuale(upd, ctx))
        return stato, ctx, upd

    @pytest.mark.parametrize("testo, gol", [("2-1", (2, 1)), ("0-0", (0, 0)), (" 3-2 ", (3, 2)), ("10-0", (10, 0))])
    def test_formati_validi_accettati(self, admin, testo, gol):
        stato, ctx, _ = self._invia(testo)
        assert stato == bt.CONFERMA_RISULTATO_MANUALE
        assert (ctx.user_data["manuale_gol_casa"], ctx.user_data["manuale_gol_ospite"]) == gol

    @pytest.mark.parametrize("testo", ["=1+1", "2 - 1", "2:1", "due-uno", "", "2-1-0", "-1-2", "21-3", "0-99"])
    def test_formati_non_validi_rifiutati_senza_toccare_i_dati(self, admin, testo):
        stato, ctx, upd = self._invia(testo)
        assert stato == bt.ATTESA_RISULTATO_MANUALE, f"'{testo}' non doveva essere accettato"
        assert "manuale_gol_casa" not in ctx.user_data
        assert upd.message.risposte, "l'admin deve ricevere un messaggio che spiega il formato"

    def test_una_formula_di_foglio_non_passa_mai(self, admin):
        """USER_ENTERED interpreta le formule: un '=' non deve mai arrivare a Sheets."""
        for tentativo in ("=SOMMA(A1:A9)", "=1-1", "+2-1", "'2-1"):
            stato, ctx, _ = self._invia(tentativo)
            assert stato == bt.ATTESA_RISULTATO_MANUALE
            assert "manuale_gol_casa" not in ctx.user_data

    def test_chi_non_e_admin_non_puo_inserire_risultati(self, admin):
        stato, ctx, upd = self._invia("2-1", user_id=ID_ESTRANEO)
        assert stato is None, "per un non-admin la funzione esce subito"
        assert "manuale_gol_casa" not in ctx.user_data
        assert upd.message.risposte == [], "a un estraneo non si risponde nemmeno"


# ---------------------------------------------------------------------------
# 4. Foto: chi non e' admin non deve poterle caricare
# ---------------------------------------------------------------------------
class _FotoFinta:
    def __init__(self, scaricate):
        self._scaricate = scaricate

    async def get_file(self):
        return self

    async def download_to_drive(self, percorso):
        self._scaricate.append(percorso)


class _MessaggioConFoto:
    def __init__(self, scaricate):
        self.photo = [_FotoFinta(scaricate)]
        self.risposte = []

    async def reply_text(self, testo, **kwargs):
        self.risposte.append(testo)


class _UpdateConFoto:
    def __init__(self, scaricate, user_id):
        self.message = _MessaggioConFoto(scaricate)
        self.effective_user = _UtenteFinto(user_id)


class TestAccessoAllaCaricaFoto:

    def test_un_estraneo_non_scarica_nessuna_foto(self, admin):
        scaricate = []
        ctx = _ContextFinto()
        upd = _UpdateConFoto(scaricate, ID_ESTRANEO)
        asyncio.run(bt.ricevi_foto_multipla(upd, ctx))
        assert scaricate == [], "nessun file deve finire sul disco per un non-admin"
        assert ctx.user_data == {}
        assert upd.message.risposte == []
