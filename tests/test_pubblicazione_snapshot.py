"""
Test della PUBBLICAZIONE dello snapshot su Cloudflare KV (Fase 1B del restyling).

Il bot costruisce lo snapshot (statistiche.py, gia' testato) e lo scrive su due
chiavi KV: `snapshot` (solo se l'impronta e' cambiata) e `segnale` (a ogni
controllo). Qui si blocca tutto cio' che sta attorno, SENZA rete: Sheets,
Football-Data e Cloudflare sono finti.

Le proprieta' che contano:

1. **Senza le tre variabili d'ambiente non succede niente**: niente chiamate,
   niente errori, niente avvisi.
2. **La pubblicazione non e' mai piu' importante del lavoro**: qualunque
   eccezione (HTTP, timeout, Sheets, dati illeggibili) si ferma li'.
3. **Snapshot solo se cambia, segnale sempre** — e se qualcosa non va il segnale
   NON si scrive (§4: dire «allineato» mentre non lo e' nasconderebbe il guasto).
4. **Il job dei 15 minuti non gira nella pausa notturna.**
5. **Gli avvisi arrivano una volta**, deduplicati sul foglio Stato, e la chiave
   si azzera con l'archiviazione della stagione.
6. `/pubblica` e' solo per gli admin e risponde a chi l'ha lanciato.
"""
import asyncio
import copy
import inspect
import json
import os
import re
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytz
import requests

import bot_telegram as bt
import dati_finti as dati

TOKEN, ACCOUNT, NAMESPACE = "tok-SEGRETO-xyz", "acc123abc", "ns456def"


# ---------------------------------------------------------------------------
# Finti
# ---------------------------------------------------------------------------
class _Esec:
    def __init__(self, dati): self._d = dati
    def execute(self, **kw): return self._d


class FakeSheets:
    """Solo letture (batchGet): una scrittura qui e' un errore del test."""

    def __init__(self, classifica, cassa, giocate):
        self.fogli = [classifica, cassa, giocate]
        self.chiamate = 0
        self.rotto = False
        self.client_costruiti = []   # sola_lettura di ogni nuovo_client_sheets()
        self.chiusure = 0

    def close(self): self.chiusure += 1
    def spreadsheets(self): return self
    def values(self): return self

    def batchGet(self, spreadsheetId, ranges):
        self.chiamate += 1
        assert ranges == ["Classifica", "Cassa!A:D", "Giocate!A:I"], "range inattesi"
        if self.rotto:
            raise RuntimeError("Sheets non risponde")
        return _Esec({"valueRanges": [{"values": f} for f in self.fogli]})

    def __getattr__(self, nome):
        raise AssertionError(f"la pubblicazione non deve scrivere su Sheets ({nome})")


class FakeRete:
    """Sostituisce richiedi_con_retry: registra le chiamate, niente rete."""

    def __init__(self, partite):
        self.partite = partite
        self.chiamate = []
        self.put_rotto = None       # eccezione da sollevare sui PUT
        self.put_rotto_su = None    # solo per questa chiave, se indicata
        self.fd_rotto = None

    def __call__(self, url, headers=None, timeout=10, tentativi=3, backoff_base=1.5, metodo="GET", dati=None):
        self.chiamate.append({"metodo": metodo, "url": url, "headers": headers, "timeout": timeout, "dati": dati})
        if metodo == "PUT":
            chiave = url.rsplit("/", 1)[1]
            if self.put_rotto is not None and self.put_rotto_su in (None, chiave):
                raise self.put_rotto
            return SimpleNamespace(status_code=200)
        assert "football-data.org/v4/competitions/SA/matches" in url and "matchday" not in url
        if self.fd_rotto is not None:
            raise self.fd_rotto
        return SimpleNamespace(json=lambda: copy.deepcopy(self.partite))

    def put(self, chiave=None):
        return [c for c in self.chiamate if c["metodo"] == "PUT" and (chiave is None or c["url"].endswith("/" + chiave))]

    def fd(self):
        return [c for c in self.chiamate if c["metodo"] == "GET"]

    def corpo(self, chiave):
        return json.loads(self.put(chiave)[-1]["dati"].decode("utf-8"))


class FakeJobQueue:
    def __init__(self): self.programmati = []
    def run_once(self, callback, when): self.programmati.append((callback.__name__, when))


class FakeMessaggio:
    def __init__(self): self.risposte = []
    async def reply_text(self, testo, **kw): self.risposte.append(testo)


class Ambiente:
    pass


@pytest.fixture
def amb(monkeypatch):
    """Pubblicazione ATTIVA con tutto finto. I test che vogliono altro lo cambiano."""
    a = Ambiente()
    classifica, cassa, giocate, partite, adesso = dati.dataset_base()
    a.sheets = FakeSheets(classifica, cassa, giocate)
    a.rete = FakeRete(partite)
    a.stato = {}
    a.notifiche = []      # (testo, destinatari, parse_mode)
    a.job_queue = FakeJobQueue()
    a.context = SimpleNamespace(job_queue=a.job_queue, bot=None)
    a.istante = adesso    # l'ora "adesso" del bot

    class DatetimeFinto(datetime):
        @classmethod
        def now(cls, tz=None):
            return a.istante.astimezone(tz) if tz else a.istante.replace(tzinfo=None)

    async def avvisa(context, testo, destinatari=None, escludi=None, parse_mode="Markdown", **kw):
        a.notifiche.append((testo, destinatari, parse_mode))
        return 1

    monkeypatch.setattr(bt, "CLOUDFLARE_API_TOKEN", TOKEN)
    monkeypatch.setattr(bt, "CLOUDFLARE_ACCOUNT_ID", ACCOUNT)
    monkeypatch.setattr(bt, "CLOUDFLARE_KV_NAMESPACE_ID", NAMESPACE)
    monkeypatch.setattr(bt, "_ultima_pubblicazione", {"impronta": None, "generato_il": None})
    monkeypatch.setattr(bt, "_cache_partite_fd", {"quando": 0.0, "matches": None})
    monkeypatch.setattr(bt, "_avvisi_visti", None)
    monkeypatch.setattr(bt, "_fallimenti_consecutivi", 0)
    monkeypatch.setattr(bt, "_pubblicazione_programmata", False)
    monkeypatch.setattr(bt, "_lock_pubblicazione", None)
    monkeypatch.setattr(bt, "_lock_salvataggio", None)
    a.usi_client_globale = []

    def client_globale():
        a.usi_client_globale.append(1)
        raise AssertionError("la pubblicazione non deve usare il client Sheets globale del bot")

    def client_privato(sola_lettura=True):
        a.sheets.client_costruiti.append(sola_lettura)
        return a.sheets

    monkeypatch.setattr(bt, "connetti_sheets", client_globale)
    monkeypatch.setattr(bt, "nuovo_client_sheets", client_privato)
    monkeypatch.setattr(bt, "richiedi_con_retry", a.rete)
    def leggi(chiave, default=None, service=None):
        assert service is not None, "lo Stato della pubblicazione va letto col client privato"
        return a.stato.get(chiave) or default

    def scrivi(chiave, valore, service=None):
        assert service is not None, "lo Stato della pubblicazione va scritto col client privato"
        a.stato[chiave] = str(valore)

    monkeypatch.setattr(bt, "leggi_stato", leggi)
    monkeypatch.setattr(bt, "scrivi_stato", scrivi)
    monkeypatch.setattr(bt, "avvisa_admin", avvisa)
    monkeypatch.setattr(bt, "datetime", DatetimeFinto)
    return a


def pubblica(a, forza=False):
    return asyncio.run(bt.pubblica_snapshot(a.context, forza=forza))


def con_riga_non_abbinata(a):
    """Una riga di Giocate con una partita che non esiste: costruisci_snapshot la
    pubblica come non ufficiale e produce un avviso."""
    a.sheets.fogli[2] = a.sheets.fogli[2] + [dati.riga_giocata(3, "PAOLO", "Pippo - Pluto")]


# ---------------------------------------------------------------------------
# 1. Variabili mancanti: spenta, in silenzio
# ---------------------------------------------------------------------------
class TestSenzaVariabili:

    @pytest.mark.parametrize("mancante", ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_KV_NAMESPACE_ID"])
    def test_basta_una_variabile_mancante_per_spegnere(self, amb, monkeypatch, mancante):
        monkeypatch.setattr(bt, mancante, "")
        assert bt.pubblicazione_attiva() is False
        asyncio.run(bt.task_pubblica_snapshot(amb.context))
        bt.programma_pubblicazione(amb.context)
        assert amb.rete.chiamate == [] and amb.sheets.chiamate == 0
        assert amb.job_queue.programmati == [] and amb.notifiche == []

    def test_tutte_presenti_e_attiva(self, amb):
        assert bt.pubblicazione_attiva() is True

    def test_pubblica_command_lo_dice_a_chi_l_ha_lanciato_senza_chiamate(self, amb, monkeypatch):
        monkeypatch.setattr(bt, "CLOUDFLARE_API_TOKEN", "")
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "x")
        monkeypatch.setenv("CLOUDFLARE_KV_NAMESPACE_ID", "y")
        update = SimpleNamespace(effective_user=SimpleNamespace(id=424242), message=FakeMessaggio())
        asyncio.run(bt.pubblica_command(update, amb.context))
        assert amb.rete.chiamate == [] and amb.sheets.chiamate == 0
        testo, destinatari, _ = amb.notifiche[0]
        assert destinatari == 424242
        assert "CLOUDFLARE_API_TOKEN" in testo and "CLOUDFLARE_ACCOUNT_ID" not in testo


# ---------------------------------------------------------------------------
# 2. Cosa viene scritto, dove, con quali header
# ---------------------------------------------------------------------------
class TestRichiestaKV:

    def test_put_con_url_header_e_timeout_giusti(self, amb):
        esito = pubblica(amb)
        assert esito["stato"] == "pubblicato" and esito["errore"] is None
        put = amb.rete.put("snapshot")[0]
        assert put["url"] == (f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}"
                              f"/storage/kv/namespaces/{NAMESPACE}/values/snapshot")
        assert put["headers"]["Authorization"] == f"Bearer {TOKEN}"
        assert put["headers"]["Content-Type"] == "application/octet-stream"
        assert put["timeout"] == bt.TIMEOUT_CLOUDFLARE_S and 0 < bt.TIMEOUT_CLOUDFLARE_S <= 30
        assert isinstance(put["dati"], bytes)

    def test_snapshot_prima_del_segnale_e_contenuti_validi(self, amb):
        pubblica(amb)
        assert [c["url"].rsplit("/", 1)[1] for c in amb.rete.put()] == ["snapshot", "segnale"]
        snap, seg = amb.rete.corpo("snapshot"), amb.rete.corpo("segnale")
        assert snap["versione_schema"] == 1 and snap["stagione"] == "2026-27"
        assert seg["generato_il"] == snap["generato_il"]
        assert seg["impronta"] == bt.impronta_snapshot(snap)
        assert seg["ultimo_controllo_il"] == "2026-10-04T15:30:12Z"
        assert set(seg) == {"versione_schema", "ultimo_controllo_il", "generato_il", "impronta",
                            "soglia_allarme_minuti", "pausa_notturna"}

    def test_la_dimensione_riportata_e_quella_del_corpo(self, amb):
        esito = pubblica(amb)
        assert esito["byte"] == len(amb.rete.put("snapshot")[0]["dati"])

    def test_nessun_segreto_nello_snapshot(self, amb):
        pubblica(amb)
        corpo = amb.rete.put("snapshot")[0]["dati"].decode()
        for riservato in (TOKEN, ACCOUNT, NAMESPACE, str(bt.SPREADSHEET_ID or "assente")):
            assert riservato not in corpo


# ---------------------------------------------------------------------------
# 3. Snapshot solo se cambia, segnale sempre
# ---------------------------------------------------------------------------
class TestImpronta:

    def test_impronta_uguale_solo_segnale(self, amb):
        pubblica(amb)
        amb.rete.chiamate.clear()
        amb.istante += timedelta(minutes=15)
        esito = pubblica(amb)
        assert esito["stato"] == "invariato"
        assert [c["url"].rsplit("/", 1)[1] for c in amb.rete.put()] == ["segnale"]

    def test_il_segnale_dell_invariato_dice_quando_hai_controllato_e_quale_snapshot_c_e(self, amb):
        pubblica(amb)
        generato = amb.rete.corpo("snapshot")["generato_il"]
        amb.istante += timedelta(minutes=15)
        pubblica(amb)
        seg = amb.rete.corpo("segnale")
        assert seg["ultimo_controllo_il"] == "2026-10-04T15:45:12Z"
        assert seg["generato_il"] == generato, "deve restare quello dello snapshot GIA' pubblicato"

    def test_impronta_diversa_snapshot_e_segnale(self, amb):
        pubblica(amb)
        impronta_prima = amb.rete.corpo("segnale")["impronta"]
        amb.rete.chiamate.clear()
        amb.sheets.fogli[1] = amb.sheets.fogli[1] + [["Giornata 3", "MARIO chiude la schedina!", "150,00€", "950,00€"]]
        amb.istante += timedelta(minutes=15)
        esito = pubblica(amb)
        assert esito["stato"] == "pubblicato"
        assert [c["url"].rsplit("/", 1)[1] for c in amb.rete.put()] == ["snapshot", "segnale"]
        assert amb.rete.corpo("segnale")["impronta"] != impronta_prima
        assert amb.rete.corpo("segnale")["generato_il"] == amb.rete.corpo("snapshot")["generato_il"]

    def test_forza_riscrive_anche_se_uguale(self, amb):
        pubblica(amb)
        amb.rete.chiamate.clear()
        assert pubblica(amb, forza=True)["stato"] == "pubblicato"
        assert len(amb.rete.put("snapshot")) == 1

    def test_dopo_un_riavvio_si_ripubblica_una_volta(self, amb, monkeypatch):
        pubblica(amb)
        monkeypatch.setattr(bt, "_ultima_pubblicazione", {"impronta": None, "generato_il": None})
        amb.rete.chiamate.clear()
        assert pubblica(amb)["stato"] == "pubblicato"


# ---------------------------------------------------------------------------
# 4. Errori: nessuna eccezione propagata, nessun segnale bugiardo
# ---------------------------------------------------------------------------
ERRORI = [
    requests.exceptions.HTTPError("403 Client Error for url: https://api.cloudflare.com/client/v4/accounts/"
                                  f"{ACCOUNT}/storage/kv/namespaces/{NAMESPACE}/values/snapshot"),
    requests.exceptions.Timeout("lento"),
    requests.exceptions.ConnectionError("giu'"),
]


class TestErrori:

    @pytest.mark.parametrize("errore", ERRORI)
    def test_put_rotto_nessuna_eccezione_e_nessun_segnale(self, amb, errore):
        amb.rete.put_rotto = errore
        esito = pubblica(amb)          # se propagasse, il test cadrebbe qui
        assert esito["stato"] == "errore" and esito["errore"]
        assert amb.rete.put("segnale") == [], "il segnale non va scritto se lo snapshot non e' stato pubblicato"
        assert bt._ultima_pubblicazione["impronta"] is None, "il prossimo giro deve riprovare"

    @pytest.mark.parametrize("errore", ERRORI)
    def test_l_errore_non_contiene_ne_token_ne_id(self, amb, errore):
        amb.rete.put_rotto = errore
        testo = pubblica(amb)["errore"]
        for riservato in (TOKEN, ACCOUNT, NAMESPACE):
            assert riservato not in testo

    def test_il_giro_dopo_riprova_e_pubblica(self, amb):
        amb.rete.put_rotto = requests.exceptions.Timeout("lento")
        pubblica(amb)
        amb.rete.put_rotto = None
        assert pubblica(amb)["stato"] == "pubblicato"

    def test_segnale_rotto_dopo_lo_snapshot(self, amb):
        amb.rete.put_rotto, amb.rete.put_rotto_su = requests.exceptions.Timeout("lento"), "segnale"
        esito = pubblica(amb)
        assert esito["stato"] == "pubblicato" and "segnale" in esito["errore"]
        # il prossimo giro: snapshot gia' pubblicato (stessa impronta), riprova solo il segnale
        amb.rete.put_rotto = None
        amb.rete.chiamate.clear()
        assert pubblica(amb)["stato"] == "invariato"
        assert [c["url"].rsplit("/", 1)[1] for c in amb.rete.put()] == ["segnale"]

    def test_sheets_rotto(self, amb):
        amb.sheets.rotto = True
        esito = pubblica(amb)
        assert esito["stato"] == "errore" and amb.rete.put() == []

    def test_football_data_rotto_senza_copia_non_si_pubblica(self, amb):
        amb.rete.fd_rotto = requests.exceptions.ConnectionError("giu'")
        esito = pubblica(amb)
        assert esito["stato"] == "errore" and amb.rete.put() == []

    def test_dati_illeggibili_non_si_pubblica_nemmeno_il_segnale(self, amb):
        amb.sheets.fogli[2] = []     # Giocate vuoto
        esito = pubblica(amb)
        assert esito["stato"] == "dati_illeggibili"
        assert amb.rete.put() == [], "ne' snapshot ne' segnale: il sito deve poter invecchiare e avvisare"
        assert len(amb.notifiche) == 1 and "NON pubblicato" in amb.notifiche[0][0]

    def test_dati_illeggibili_avviso_una_volta_sola(self, amb):
        amb.sheets.fogli[2] = []
        pubblica(amb); pubblica(amb); pubblica(amb)
        assert len(amb.notifiche) == 1

    def test_errore_inatteso_nel_costruttore_non_si_propaga(self, amb, monkeypatch):
        def bomba(*a, **k): raise KeyError("bug imprevisto")
        monkeypatch.setattr(bt, "costruisci_snapshot_con_avvisi", bomba)
        assert pubblica(amb)["stato"] == "dati_illeggibili"
        assert amb.rete.put() == []

    def test_un_blip_isolato_non_disturba_gli_admin_un_guasto_si(self, amb):
        amb.rete.put_rotto = requests.exceptions.Timeout("lento")
        for _ in range(bt.FALLIMENTI_PER_AVVISO - 1):
            pubblica(amb)
        assert amb.notifiche == []
        pubblica(amb)
        assert len(amb.notifiche) == 1
        pubblica(amb); pubblica(amb)
        assert len(amb.notifiche) == 1, "un solo messaggio, non uno a ogni giro"

    def test_un_successo_azzera_il_conteggio(self, amb):
        amb.rete.put_rotto = requests.exceptions.Timeout("lento")
        for _ in range(bt.FALLIMENTI_PER_AVVISO - 1):
            pubblica(amb)
        amb.rete.put_rotto = None
        pubblica(amb)
        amb.rete.put_rotto = requests.exceptions.Timeout("lento")
        for _ in range(bt.FALLIMENTI_PER_AVVISO - 1):
            pubblica(amb)
        assert amb.notifiche == []


# ---------------------------------------------------------------------------
# 5. Football-Data: una chiamata, cache di 60 minuti
# ---------------------------------------------------------------------------
class TestCacheFootballData:

    def test_una_sola_chiamata_per_piu_pubblicazioni(self, amb):
        for _ in range(4):
            amb.istante += timedelta(minutes=15)
            pubblica(amb)
        assert len(amb.rete.fd()) == 1

    def test_dopo_un_ora_si_riscarica(self, amb, monkeypatch):
        orologio = [1_000_000.0]
        monkeypatch.setattr(bt.time, "time", lambda: orologio[0])
        pubblica(amb)
        orologio[0] += bt.CACHE_PARTITE_FD_S - 1
        pubblica(amb)
        assert len(amb.rete.fd()) == 1
        orologio[0] += 2
        pubblica(amb)
        assert len(amb.rete.fd()) == 2

    def test_se_football_data_cade_si_usa_la_copia(self, amb, monkeypatch):
        orologio = [1_000_000.0]
        monkeypatch.setattr(bt.time, "time", lambda: orologio[0])
        pubblica(amb)
        orologio[0] += bt.CACHE_PARTITE_FD_S + 60
        amb.rete.fd_rotto = requests.exceptions.ConnectionError("giu'")
        assert pubblica(amb)["errore"] is None

    def test_ma_non_una_copia_troppo_vecchia(self, amb, monkeypatch):
        orologio = [1_000_000.0]
        monkeypatch.setattr(bt.time, "time", lambda: orologio[0])
        pubblica(amb)
        orologio[0] += bt.CACHE_PARTITE_FD_MAX_VECCHIA_S + 1
        amb.rete.fd_rotto = requests.exceptions.ConnectionError("giu'")
        assert pubblica(amb)["stato"] == "errore"

    def test_forza_rilegge_football_data(self, amb):
        pubblica(amb)
        pubblica(amb, forza=True)
        assert len(amb.rete.fd()) == 2

    def test_in_cache_restano_solo_i_campi_che_servono(self, amb):
        pubblica(amb)
        partita = bt._cache_partite_fd["matches"][0]
        assert set(partita) == {"id", "matchday", "utcDate", "homeTeam", "awayTeam", "season"}
        assert "score" not in partita and "id" not in partita["homeTeam"]


# ---------------------------------------------------------------------------
# 6. Quando: job dei 15 minuti, pausa notturna, dopo una scrittura
# ---------------------------------------------------------------------------
class TestQuando:

    def _alle(self, amb, ora, minuto=0):
        amb.istante = pytz.timezone("Europe/Rome").localize(datetime(2026, 10, 5, ora, minuto)).astimezone(pytz.UTC)

    @pytest.mark.parametrize("ora, minuto", [(2, 0), (4, 30), (7, 29)])
    def test_in_pausa_notturna_il_job_non_pubblica(self, amb, ora, minuto):
        self._alle(amb, ora, minuto)
        asyncio.run(bt.task_pubblica_snapshot(amb.context))
        assert amb.rete.chiamate == [] and amb.sheets.chiamate == 0

    @pytest.mark.parametrize("ora, minuto", [(1, 59), (7, 30), (15, 0), (23, 45)])
    def test_fuori_dalla_pausa_il_job_pubblica(self, amb, ora, minuto):
        self._alle(amb, ora, minuto)
        asyncio.run(bt.task_pubblica_snapshot(amb.context))
        assert len(amb.rete.put("segnale")) == 1

    def test_dopo_una_scrittura_si_programma_una_sola_pubblicazione(self, amb):
        for _ in range(3):
            bt.programma_pubblicazione(amb.context)
        assert amb.job_queue.programmati == [("task_pubblica_dopo_scrittura", bt.RITARDO_PUBBLICAZIONE_S)]

    def test_la_pubblicazione_programmata_libera_il_flag_e_pubblica(self, amb):
        bt.programma_pubblicazione(amb.context)
        asyncio.run(bt.task_pubblica_dopo_scrittura(amb.context))
        assert bt._pubblicazione_programmata is False
        assert len(amb.rete.put("snapshot")) == 1
        bt.programma_pubblicazione(amb.context)   # ora se ne puo' programmare un'altra
        assert len(amb.job_queue.programmati) == 2

    def test_il_job_queue_rotto_non_fa_fallire_la_scrittura(self, amb):
        bt.programma_pubblicazione(SimpleNamespace(job_queue=None))   # non solleva
        bt.programma_pubblicazione(None)
        assert bt._pubblicazione_programmata is False

    def test_due_pubblicazioni_insieme_non_si_sovrappongono(self, amb, monkeypatch):
        in_corso, massimo = [0], [0]
        originale = bt.pubblica_snapshot_bloccante

        def lenta(forza=False):
            in_corso[0] += 1
            massimo[0] = max(massimo[0], in_corso[0])
            import time as t; t.sleep(0.05)
            try:
                return originale(forza)
            finally:
                in_corso[0] -= 1

        monkeypatch.setattr(bt, "pubblica_snapshot_bloccante", lenta)

        async def due():
            await asyncio.gather(bt.pubblica_snapshot(amb.context), bt.pubblica_snapshot(amb.context))

        asyncio.run(due())
        assert massimo[0] == 1

    def test_la_memoria_viene_restituita_dopo_la_costruzione(self, amb, monkeypatch):
        chiamate = []
        monkeypatch.setattr(bt, "libera_memoria_al_sistema_operativo", lambda: chiamate.append(1))
        pubblica(amb)
        assert chiamate == [1]


# ---------------------------------------------------------------------------
# 7. Avvisi agli admin: una volta, via foglio Stato
# ---------------------------------------------------------------------------
class TestAvvisi:

    def test_gli_avvisi_arrivano_una_volta(self, amb):
        con_riga_non_abbinata(amb)
        for _ in range(3):
            pubblica(amb)
        assert len(amb.notifiche) == 1
        testo, destinatari, parse_mode = amb.notifiche[0]
        assert destinatari is None, "una notifica schedulata va a tutti gli admin"
        assert "Pippo - Pluto" in testo
        assert amb.stato[bt.CHIAVE_AVVISI_SNAPSHOT]

    def test_dopo_un_riavvio_non_li_rimanda(self, amb, monkeypatch):
        con_riga_non_abbinata(amb)
        pubblica(amb)
        monkeypatch.setattr(bt, "_avvisi_visti", None)       # processo nuovo: la RAM e' vuota
        monkeypatch.setattr(bt, "_ultima_pubblicazione", {"impronta": None, "generato_il": None})
        pubblica(amb)
        assert len(amb.notifiche) == 1, "lo Stato sul foglio protegge dal doppio invio"

    def test_risolto_si_azzera_e_se_ritorna_si_rimanda(self, amb):
        giocate_ok = list(amb.sheets.fogli[2])
        con_riga_non_abbinata(amb)
        pubblica(amb)
        amb.sheets.fogli[2] = giocate_ok          # il problema e' stato corretto sul foglio
        pubblica(amb)
        assert amb.stato[bt.CHIAVE_AVVISI_SNAPSHOT] == ""
        con_riga_non_abbinata(amb)                # ritorna
        pubblica(amb)
        assert len(amb.notifiche) == 2

    def test_un_avviso_diverso_viene_mandato(self, amb):
        con_riga_non_abbinata(amb)
        pubblica(amb)
        amb.sheets.fogli[2] = amb.sheets.fogli[2] + [dati.riga_giocata(3, "DARIO", "Altro - Boh")]
        pubblica(amb)
        assert len(amb.notifiche) == 2

    def test_nessun_avviso_nessun_messaggio(self, amb):
        pubblica(amb)
        assert amb.notifiche == []

    def test_il_testo_passa_da_escape_markdown(self, amb, monkeypatch):
        """Un underscore dispari fa rifiutare a Telegram l'intero messaggio (Sessione 15)."""
        monkeypatch.setattr(bt, "costruisci_snapshot_con_avvisi",
                            lambda *a, **k: ({"generato_il": "x", "versione_schema": 1}, ["pronostico OVER_2.5 *strano*"]))
        monkeypatch.setattr(bt, "impronta_snapshot", lambda s: "i")
        monkeypatch.setattr(bt, "costruisci_segnale", lambda s, a: {"x": 1})
        pubblica(amb)
        testo = amb.notifiche[0][0]
        assert "OVER\\_2.5" in testo and "\\*strano\\*" in testo

    def test_stato_non_scrivibile_il_messaggio_parte_lo_stesso(self, amb, monkeypatch):
        def rotta(chiave, valore, service=None): raise RuntimeError("Stato non scrivibile")
        monkeypatch.setattr(bt, "scrivi_stato", rotta)
        con_riga_non_abbinata(amb)
        esito = pubblica(amb)
        assert len(amb.notifiche) == 1 and esito["stato"] == "pubblicato"

    def test_l_invio_usa_avvisa_admin_che_ha_il_fallback_senza_formattazione(self):
        """Il fallback senza parse_mode e' dentro avvisa_admin: qui si blocca che
        la segnalazione ci passi, e non usi send_message diretto."""
        sorgente = inspect.getsource(bt.segnala_avvisi_snapshot)
        assert "avvisa_admin(" in sorgente and "send_message" not in sorgente and "escape_markdown" in sorgente

    def test_archivia_stagione_azzera_la_chiave(self, amb, monkeypatch):
        scritti = []
        monkeypatch.setattr(bt, "scrivi_stato", lambda chiave, valore: scritti.append((chiave, valore)))
        monkeypatch.setattr(bt, "_avvisi_visti", "abc")

        class Sheets:
            def spreadsheets(self): return self
            def values(self): return self
            def get(self, spreadsheetId, range=None):
                if range is None:
                    return _Esec({"sheets": [{"properties": {"title": t, "sheetId": i}} for i, t in enumerate(bt.FOGLI_STAGIONE)]})
                return _Esec({"values": [["intestazione"]]})
            def batchUpdate(self, spreadsheetId, body):
                for r in body["requests"]:
                    self.titoli_extra = getattr(self, "titoli_extra", []) + [r["duplicateSheet"]["newSheetName"]]
                return _Esec({})

        s = Sheets()
        orig_get = s.get
        def get(spreadsheetId, range=None):
            if range is None and hasattr(s, "titoli_extra"):
                titoli = list(bt.FOGLI_STAGIONE) + s.titoli_extra
                return _Esec({"sheets": [{"properties": {"title": t, "sheetId": i}} for i, t in enumerate(titoli)]})
            return orig_get(spreadsheetId, range)
        s.get = get
        monkeypatch.setattr(bt, "connetti_sheets", lambda: s)

        bt.archivia_stagione("2026-27")
        assert (bt.CHIAVE_AVVISI_SNAPSHOT, "") in scritti
        assert bt._avvisi_visti is None


# ---------------------------------------------------------------------------
# 8. /pubblica
# ---------------------------------------------------------------------------
class TestComandoPubblica:

    def _update(self, utente):
        return SimpleNamespace(effective_user=SimpleNamespace(id=utente), message=FakeMessaggio())

    def test_rifiutato_ai_non_admin(self, amb):
        update = self._update(999)
        asyncio.run(bt.pubblica_command(update, amb.context))
        assert update.message.risposte == [] and amb.notifiche == []
        assert amb.rete.chiamate == [] and amb.sheets.chiamate == 0

    def test_l_admin_forza_e_la_risposta_va_a_lui(self, amb):
        update = self._update(424242)
        asyncio.run(bt.pubblica_command(update, amb.context))
        assert len(amb.rete.put("snapshot")) == 1
        testo, destinatari, parse_mode = amb.notifiche[-1]
        assert destinatari == 424242 and parse_mode is None
        assert "pubblicato" in testo and " KB" in testo

    def test_forza_anche_se_l_impronta_e_uguale(self, amb):
        pubblica(amb)
        amb.rete.chiamate.clear()
        asyncio.run(bt.pubblica_command(self._update(424242), amb.context))
        assert len(amb.rete.put("snapshot")) == 1

    def test_riferisce_gli_avvisi_e_gli_errori(self, amb):
        con_riga_non_abbinata(amb)
        asyncio.run(bt.pubblica_command(self._update(424242), amb.context))
        risposta = [n for n in amb.notifiche if n[1] == 424242][-1][0]
        assert "Pippo - Pluto" in risposta

        amb.rete.put_rotto = requests.exceptions.Timeout("lento")
        asyncio.run(bt.pubblica_command(self._update(424242), amb.context))
        assert "non pubblicato" in amb.notifiche[-1][0].lower() and amb.notifiche[-1][1] == 424242

    def test_e_nell_elenco_dei_comandi_e_registrato(self):
        assert "pubblica" in [c for c, _ in bt.COMANDI_ADMIN]
        assert "pubblica" in [c for c, _ in bt.COMANDI_OWNER]
        assert 'CommandHandler("pubblica", pubblica_command)' in inspect.getsource(bt.main)

    def test_il_comando_non_usa_ADMIN_ID(self):
        sorgente = inspect.getsource(bt.pubblica_command) + inspect.getsource(bt.pubblica_snapshot)
        assert not re.search(r"\bADMIN_ID\b", sorgente)


# ---------------------------------------------------------------------------
# 9. I punti di aggancio: dopo ogni scrittura che cambia dati visibili
# ---------------------------------------------------------------------------
class TestPuntiDiAggancio:

    @pytest.mark.parametrize("funzione", [
        "scegli_giornata_update",                 # Aggiorna Risultati (menu)
        "task_aggiornamento_automatico",          # i 5 job giornalieri
        "esegui_conferma_risultato_manuale",      # risultato inserito a mano
        "esegui_salvataggio_ia",                  # salvataggio schedina
        "verifica_codice_archiviazione",          # archiviazione stagione
    ])
    def test_programma_la_pubblicazione(self, funzione):
        assert "programma_pubblicazione(context)" in inspect.getsource(getattr(bt, funzione))

    def test_il_salvataggio_programma_solo_se_ha_scritto(self):
        sorgente = inspect.getsource(bt.esegui_salvataggio_ia)
        assert re.search(r"if successo:\s+programma_pubblicazione\(context\)", sorgente)

    def test_il_job_periodico_e_registrato_ogni_15_minuti(self):
        sorgente = inspect.getsource(bt.main)
        assert "run_repeating(task_pubblica_snapshot, interval=INTERVALLO_PUBBLICAZIONE_S" in sorgente
        assert bt.INTERVALLO_PUBBLICAZIONE_S == 900

    def test_la_scrittura_su_sheets_non_viene_toccata_da_programma_pubblicazione(self, amb):
        """Programmare non legge ne' scrive nulla: aggiunge solo un job."""
        bt.programma_pubblicazione(amb.context)
        assert amb.sheets.chiamate == 0 and amb.rete.chiamate == []


# ---------------------------------------------------------------------------
# 10. Client Sheets PRIVATO (httplib2 non e' thread-safe)
# ---------------------------------------------------------------------------
class TestClientSheetsPrivato:
    """La pubblicazione gira in un thread e puo' sovrapporsi al calcolo risultati.
    Se usasse il client condiviso del bot, due thread sullo stesso httplib2 potrebbero
    mescolare le risposte proprio sul percorso che scrive punti e Cassa."""

    def test_la_pubblicazione_non_usa_mai_il_client_globale(self, amb):
        """Il mock globale solleva se chiamato: percorso normale, con avvisi (Stato), con errori, con /pubblica."""
        con_riga_non_abbinata(amb)               # percorso con Stato
        pubblica(amb)
        pubblica(amb, forza=True)
        amb.rete.put_rotto = requests.exceptions.Timeout("lento")
        pubblica(amb)
        amb.sheets.fogli[2] = []                 # dati illeggibili
        pubblica(amb)
        update = SimpleNamespace(effective_user=SimpleNamespace(id=424242), message=FakeMessaggio())
        asyncio.run(bt.pubblica_command(update, amb.context))
        assert amb.usi_client_globale == []
        assert amb.sheets.chiamate > 0, "il test deve aver letto davvero i fogli"

    def test_il_percorso_dei_15_minuti_e_del_dopo_scrittura_non_usano_il_globale(self, amb):
        asyncio.run(bt.task_pubblica_snapshot(amb.context))
        asyncio.run(bt.task_pubblica_dopo_scrittura(amb.context))
        assert amb.usi_client_globale == []

    def test_le_letture_sono_in_sola_lettura_e_il_client_viene_rilasciato(self, amb, monkeypatch):
        monkeypatch.setattr(bt, "_avvisi_visti", "")      # processo gia' avviato: lo Stato non serve
        pubblica(amb)
        assert amb.sheets.client_costruiti == [True]
        assert amb.sheets.chiusure == 1

    def test_il_client_si_rilascia_anche_se_la_lettura_fallisce(self, amb):
        amb.sheets.rotto = True
        pubblica(amb)
        assert amb.sheets.chiusure == 1

    def test_lo_stato_usa_un_client_a_parte_con_scope_completo_e_lo_rilascia(self, amb):
        con_riga_non_abbinata(amb)
        pubblica(amb)
        assert amb.sheets.client_costruiti == [True, False]
        assert amb.sheets.chiusure == 2

    def test_senza_avvisi_e_con_ram_allineata_non_si_costruisce_il_client_dello_stato(self, amb):
        pubblica(amb)                      # primo giro dopo l'avvio: lo Stato si legge una volta
        costruiti = len(amb.sheets.client_costruiti)
        pubblica(amb)
        assert len(amb.sheets.client_costruiti) == costruiti + 1, "il secondo giro costruisce solo il client di lettura"

    def test_se_il_client_dello_stato_non_si_costruisce_l_avviso_parte_comunque(self, amb, monkeypatch):
        def client(sola_lettura=True):
            if not sola_lettura:
                raise RuntimeError("credenziali illeggibili")
            return amb.sheets
        monkeypatch.setattr(bt, "nuovo_client_sheets", client)
        con_riga_non_abbinata(amb)
        esito = pubblica(amb)
        assert esito["stato"] == "pubblicato" and len(amb.notifiche) == 1
        assert amb.usi_client_globale == []

    def test_nuovo_client_sheets_scope_e_cache_discovery(self, monkeypatch):
        visti = []

        class Creds:
            @staticmethod
            def from_service_account_file(percorso, scopes):
                visti.append(("creds", scopes)); return "creds"

        monkeypatch.undo()   # serve la vera nuovo_client_sheets: l'autouse dell'admin non c'entra
        monkeypatch.setattr(bt, "Credentials", Creds)
        monkeypatch.setattr(bt, "build", lambda *a, **k: visti.append(("build", a, k)) or "client")
        assert bt.nuovo_client_sheets() == "client"
        assert bt.nuovo_client_sheets(sola_lettura=False) == "client"
        assert visti[0] == ("creds", ["https://www.googleapis.com/auth/spreadsheets.readonly"])
        assert visti[2] == ("creds", ["https://www.googleapis.com/auth/spreadsheets"])
        assert visti[1][2]["cache_discovery"] is False and visti[1][2]["credentials"] == "creds"

    def test_leggi_e_scrivi_stato_senza_service_restano_come_prima(self, monkeypatch):
        """Retrocompatibilita': gli altri chiamanti non passano `service`."""
        letto = []

        class S:
            def spreadsheets(self): return self
            def values(self): return self
            def get(self, **kw): letto.append(1); return _Esec({"values": [["Chiave", "Valore"], ["k", "v"]]})

        monkeypatch.setattr(bt, "connetti_sheets", lambda: S())
        assert bt.leggi_stato("k") == "v" and letto == [1]


# ---------------------------------------------------------------------------
# 11. Orari del job e attesa dei salvataggi (due picchi di memoria mai insieme)
# ---------------------------------------------------------------------------
class TestOrariEAttesa:

    def test_i_calcoli_vengono_dal_codice_e_main_li_usa(self):
        assert bt.ORARI_CALCOLO_RISULTATI == [(1, 0), (8, 0), (17, 30), (20, 30), (23, 0)]
        assert "for h, m in ORARI_CALCOLO_RISULTATI:" in inspect.getsource(bt.main)

    @pytest.mark.parametrize("partenza", [
        datetime(2026, 10, 5, 7, 30, 0, tzinfo=pytz.UTC),     # il risveglio delle 07:30 italiane no: e' 05:30 UTC
        datetime(2026, 10, 5, 5, 29, 59, tzinfo=pytz.UTC),
        datetime(2026, 10, 5, 5, 30, 0, tzinfo=pytz.UTC),
        datetime(2026, 10, 5, 12, 6, 30, tzinfo=pytz.UTC),
        datetime(2026, 10, 5, 12, 7, 0, tzinfo=pytz.UTC),     # a ridosso di :07: deve slittare a :22
        datetime(2026, 10, 24, 22, 55, 0, tzinfo=pytz.UTC),
    ])
    def test_nessuna_esecuzione_del_job_entro_5_minuti_da_un_calcolo(self, partenza):
        """Su 3 giorni, a cavallo del cambio all'ora solare del 25/10/2026."""
        roma = pytz.timezone("Europe/Rome")
        primo = bt.prossimo_orario_pubblicazione(partenza)
        assert primo.minute in bt.MINUTI_PUBBLICAZIONE and primo - partenza >= timedelta(seconds=60)
        istanti = [primo + timedelta(seconds=bt.INTERVALLO_PUBBLICAZIONE_S * k) for k in range(3 * 96)]
        assert all(i.minute in bt.MINUTI_PUBBLICAZIONE and i.second == 0 for i in istanti)
        for istante in istanti:
            locale = istante.astimezone(roma)
            for h, m in bt.ORARI_CALCOLO_RISULTATI:
                for giorno in (-1, 0, 1):
                    calcolo = roma.localize(datetime(locale.year, locale.month, locale.day, h, m)) + timedelta(days=giorno)
                    assert abs(istante - calcolo) > timedelta(minutes=5), f"job alle {locale} vicino al calcolo {calcolo}"

    def test_main_usa_l_orario_allineato(self):
        sorgente = inspect.getsource(bt.main)
        assert "first=prossimo_orario_pubblicazione(" in sorgente

    def test_la_pubblicazione_aspetta_un_salvataggio_in_corso_senza_tenerne_il_lock(self, amb):
        async def scenario():
            lock = bt.lock_salvataggio_schedina()
            await lock.acquire()                         # un admin sta salvando
            compito = asyncio.create_task(bt.pubblica_snapshot(amb.context))
            await asyncio.sleep(0.05)
            ferma_in_attesa = amb.sheets.chiamate == 0 and not compito.done()
            lock.release()                               # il salvataggio finisce
            await compito
            # e dopo la pubblicazione il lock dei salvataggi e' libero
            libero = not lock.locked()
            return ferma_in_attesa, libero

        ferma_in_attesa, libero = asyncio.run(scenario())
        assert ferma_in_attesa, "la pubblicazione e' partita durante il salvataggio"
        assert libero and len(amb.rete.put("segnale")) == 1

    def test_durante_la_pubblicazione_un_salvataggio_non_e_bloccato(self, amb, monkeypatch):
        originale = bt.pubblica_snapshot_bloccante

        async def scenario():
            visto = []

            def lenta(forza=False):
                import time as t; t.sleep(0.1)
                return originale(forza)

            monkeypatch.setattr(bt, "pubblica_snapshot_bloccante", lenta)
            compito = asyncio.create_task(bt.pubblica_snapshot(amb.context))
            await asyncio.sleep(0.03)
            visto.append(bt.lock_salvataggio_schedina().locked())
            await compito
            return visto

        assert asyncio.run(scenario()) == [False]
