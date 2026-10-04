"""
Test dello SNAPSHOT completo (costruisci_snapshot) contro lo schema APPROVATO
(restyling/snapshot-schema.md, versione 1).

Lo schema e' il contratto fra il bot (che produce lo snapshot) e il sito nuovo
(che lo legge e basta): qui sotto e' trascritto come dato (`SCHEMA`) e un
piccolo validatore lo applica. Il validatore e' a sua volta testato, perche'
uno che accetta tutto non proverebbe niente.

Contenuto:
1. Lo snapshot rispetta lo schema: chiavi esatte (nessuna in piu', nessuna in
   meno), tipi, enum, ordini garantiti, coerenza fra le sezioni.
2. Niente dati sensibili: mai ID Telegram, chiavi, SPREADSHEET_ID.
3. Dati illeggibili -> ValueError (decisione 13: il bot non pubblica).
4. Le decisioni di dominio del 04/10/2026, viste dallo snapshot intero.
5. Gli errori di app.py (§16) che non hanno una funzione sola: ognuno
   riproduce la logica vecchia e prova che sbagliava.
"""
import copy
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytz

import statistiche as st
import dati_finti as dati
from dati_finti import ADESSO

# ======================================================================
# Lo schema come dato + un validatore
# ======================================================================
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class Enum:
    def __init__(self, *valori):
        self.valori = valori


class Nullable:
    def __init__(self, schema):
        self.schema = schema


class Array:
    def __init__(self, schema):
        self.schema = schema


class Pattern:
    def __init__(self, regex):
        self.regex = regex


class Uguale:
    def __init__(self, valore):
        self.valore = valore


def valida(valore, schema, percorso="$"):
    """Lista di errori (vuota = valido). Gli oggetti devono avere ESATTAMENTE le chiavi dello schema."""
    if isinstance(schema, Nullable):
        return [] if valore is None else valida(valore, schema.schema, percorso)
    if isinstance(schema, Uguale):
        return [] if valore == schema.valore and not isinstance(valore, bool) else [f"{percorso}: atteso {schema.valore!r}, trovato {valore!r}"]
    if isinstance(schema, Enum):
        return [] if valore in schema.valori else [f"{percorso}: {valore!r} non e' in {schema.valori}"]
    if isinstance(schema, Pattern):
        return [] if isinstance(valore, str) and schema.regex.match(valore) else [f"{percorso}: {valore!r} non rispetta {schema.regex.pattern}"]
    if schema == "int":
        return [] if isinstance(valore, int) and not isinstance(valore, bool) else [f"{percorso}: atteso int, trovato {valore!r}"]
    if schema == "num":
        return [] if isinstance(valore, (int, float)) and not isinstance(valore, bool) and valore == valore else [f"{percorso}: atteso numero, trovato {valore!r}"]
    if schema == "str":
        return [] if isinstance(valore, str) else [f"{percorso}: atteso testo, trovato {valore!r}"]
    if schema == "bool":
        return [] if isinstance(valore, bool) else [f"{percorso}: atteso bool, trovato {valore!r}"]
    if isinstance(schema, Array):
        if not isinstance(valore, list):
            return [f"{percorso}: atteso array, trovato {type(valore).__name__}"]
        return [e for i, v in enumerate(valore) for e in valida(v, schema.schema, f"{percorso}[{i}]")]
    if isinstance(schema, dict):
        if not isinstance(valore, dict):
            return [f"{percorso}: atteso oggetto, trovato {type(valore).__name__}"]
        errori = []
        for chiave in sorted(set(schema) - set(valore)):
            errori.append(f"{percorso}.{chiave}: chiave mancante")
        for chiave in sorted(set(valore) - set(schema)):
            errori.append(f"{percorso}.{chiave}: chiave NON prevista dallo schema")
        for chiave in set(schema) & set(valore):
            errori += valida(valore[chiave], schema[chiave], f"{percorso}.{chiave}")
        return errori
    raise AssertionError(f"schema non gestito: {schema!r}")


ESITI = Enum("vinta", "persa", "in_corso", "annullata", "rinviata", "da_verificare", "da_giocare")
TIPOLOGIE = Enum("combo", "fisse", "doppie_chance", "variabili")
ORA = Pattern(ISO)

PREMIO_PERCENTUALE = {"giocatore": "str", "win_rate": "num", "vinte": "int", "totali": "int"}
PREMIO_QUOTA = {"giocatore": "str", "quota_media": "num"}
STAT = {"nome": "str", "win_rate": "num", "quota_media": Nullable("num"), "vinte": "int", "totali": "int"}
VOCE_COPPA = Nullable({"posizione": "int", "nome": "str"})

SCHEMA = {
    "versione_schema": Uguale(1),
    "generato_il": ORA,
    "stagione": Pattern(re.compile(r"^\d{4}-\d{2}$")),
    "giornata_corrente": Nullable("int"),
    "giocatori": Array("str"),
    "classifica": {
        "ultima_giornata_giocata": Nullable("int"),
        "giocatori": Array({
            "posizione": "int", "nome": "str", "punti_totali": "int",
            "variazione_posizione": Nullable("int"), "punti_ultima_giornata": Nullable("int"),
            "punti_per_giornata": Array(Nullable("int")),
        }),
        "ritirati": Array({"nome": "str", "punti_totali": "int", "punti_per_giornata": Array(Nullable("int"))}),
    },
    "cassa": {
        "saldo": "num", "obiettivo": "num", "completamento": "num", "obiettivo_raggiunto": "bool",
        "movimenti": Array({"giornata": Nullable("int"), "descrizione": "str", "entrata": Nullable("num"), "saldo": Nullable("num")}),
        "versamenti_per_giornata": Array({"giornata": "int", "versato": "num"}),
    },
    "partite": Array({
        "id": "int", "giornata": "int", "nome": "str", "ufficiale": "bool", "inizio_il": Nullable(ORA),
        "scelta_gruppo": {"tipo": Enum("maggioranza", "tutti_diversi", "nessuna"), "pronostici": Array("str"),
                          "voti": "int", "su": "int"},
    }),
    "schedine": Array({
        "giornata": "int", "giocatore": "str", "vincita_potenziale": "num",
        "riepilogo": {k: "int" for k in ("vinte", "perse", "in_corso", "rinviate", "da_verificare", "annullate", "da_giocare")},
        "righe": Array({"partita_id": "int", "tipologia": Nullable(TIPOLOGIE), "pronostico": "str",
                        "quota": Nullable("num"), "esito": ESITI, "punti": "int"}),
    }),
    "statistiche": {
        "ultima_schedina_vinta": Nullable({"giornata": "int", "vincitori": Array("str"), "inizio_il": Nullable(ORA)}),
        "premi": {
            "cecchino": Nullable(Array(PREMIO_PERCENTUALE)),
            "benedizione": Nullable(Array(PREMIO_PERCENTUALE)),
            "folle": Nullable(Array(PREMIO_QUOTA)),
            "conservatore": Nullable(Array(PREMIO_QUOTA)),
            "giornata_da_incorniciare": Nullable(Array({"giocatore": "str", "giornata": "int", "punti": "int"})),
            "semper_fidelis": Nullable(Array({"giocatore": "str", "squadra": "str", "volte": "int"})),
            "squadra_amuleto": Nullable(Array({"squadra": "str", "vittorie_portate": "int"})),
            "squadra_maledetta": Nullable(Array({"squadra": "str", "pronostici_bruciati": "int"})),
        },
        "per_un_soffio": Array({"giocatore": "str", "giornata": "int", "partita": "str", "pronostico": "str", "quota": Nullable("num")}),
        "giocatori": Array(STAT),
        "ritirati": Array(STAT),
    },
    "coppa": {
        "definitiva": "bool", "partecipanti": "int", "tabellone_disponibile": "bool",
        "prima_giornata": Uguale(35), "ultima_giornata_tabellone": Uguale(34),
        "turni": Array({
            "turno": Enum("ottavi", "quarti", "semifinali", "finale"), "giornata": "int",
            "sfide": Array({"giocatori": Array(VOCE_COPPA), "punti": Array(Nullable("int")), "vincente": Nullable(Enum(0, 1))}),
        }),
        "campione": VOCE_COPPA,
    },
    "regole": {
        "costo_giornata": "num", "quota_partecipazione": "num", "scadenza_quota_giornata": "int",
        "quota_cassa_su_vincita": "num", "minuti_pubblicazione_prima_partita": "int", "soglia_quota_doppia": "num",
        "bonus_chiusura": "int", "giocatori": "int", "obiettivo_cassa": "num",
        "composizione": {"combo": "int", "doppie_chance": "int", "variabili": "int", "fisse": "int"},
        "punti": {t: {"base": "int", "quota_alta": "int"} for t in ("combo", "doppie_chance", "variabili", "fisse")},
        "ripartizione_premi": Array({"posizione": "int", "percentuale": "int"}),
    },
}

SCHEMA_SEGNALE = {
    "versione_schema": Uguale(1), "ultimo_controllo_il": ORA, "generato_il": ORA,
    "impronta": Pattern(re.compile(r"^[0-9a-f]{64}$")), "soglia_allarme_minuti": "int",
    "pausa_notturna": {"inizio": Pattern(re.compile(r"^\d{2}:\d{2}$")), "fine": Pattern(re.compile(r"^\d{2}:\d{2}$")), "fuso": "str"},
}


def costruisci(classifica, cassa, giocate, fd, adesso=ADESSO):
    return st.costruisci_snapshot(classifica, cassa, giocate, fd, adesso)


@pytest.fixture(scope="module")
def base():
    return dati.dataset_base()


@pytest.fixture(scope="module")
def snap_base(base):
    return costruisci(*base)


@pytest.fixture(scope="module")
def stagione():
    return dati.dataset_stagione()


@pytest.fixture(scope="module")
def snap_stagione(stagione):
    return costruisci(*stagione)


# ======================================================================
# 1. Il validatore funziona
# ======================================================================
class TestValidatore:
    def test_accetta_un_documento_giusto(self, snap_base):
        assert valida(snap_base, SCHEMA) == []

    def test_scopre_chiavi_in_piu_e_in_meno(self, snap_base):
        s = copy.deepcopy(snap_base)
        s["campo_nuovo"] = 1
        del s["stagione"]
        errori = valida(s, SCHEMA)
        assert any("campo_nuovo" in e and "NON prevista" in e for e in errori)
        assert any("stagione" in e and "mancante" in e for e in errori)

    def test_scopre_tipi_sbagliati(self, snap_base):
        s = copy.deepcopy(snap_base)
        s["classifica"]["giocatori"][0]["punti_totali"] = "61"      # stringa invece di numero
        s["cassa"]["saldo"] = "1.674,56"                              # formato italiano
        s["cassa"]["obiettivo_raggiunto"] = 1                         # int al posto di bool
        s["giornata_corrente"] = True                                 # bool al posto di int
        errori = valida(s, SCHEMA)
        assert len(errori) == 4

    def test_scopre_enum_e_date_sbagliati(self, snap_base):
        s = copy.deepcopy(snap_base)
        s["schedine"][0]["righe"][0]["esito"] = "✅ VINTA"
        s["generato_il"] = "2026-10-04 15:30"
        assert len(valida(s, SCHEMA)) == 2

    def test_nan_non_e_un_numero(self, snap_base):
        s = copy.deepcopy(snap_base)
        s["cassa"]["saldo"] = float("nan")
        assert valida(s, SCHEMA)


# ======================================================================
# 2. Lo snapshot rispetta lo schema
# ======================================================================
class TestSchema:
    def test_dataset_base(self, snap_base):
        assert valida(snap_base, SCHEMA) == []

    def test_stagione_intera(self, snap_stagione):
        assert valida(snap_stagione, SCHEMA) == []

    def test_chiavi_della_radice_e_ordine(self, snap_base):
        assert list(snap_base) == ["versione_schema", "generato_il", "stagione", "giornata_corrente", "giocatori",
                                   "classifica", "cassa", "partite", "schedine", "statistiche", "coppa", "regole"]

    def test_giocate_con_la_sola_intestazione_e_valido(self):
        # Inizio stagione, dopo archivia_stagione: nessuna giocata. Lo snapshot e' valido e dice "niente".
        c = dati.classifica_valori([("PAOLO", []), ("DARIO", [])])
        s = costruisci(c, dati.cassa_valori(), [dati.INTESTAZIONE_GIOCATE], dati.partite_fd([1]))
        assert valida(s, SCHEMA) == []
        assert s["giornata_corrente"] is None and s["giocatori"] == [] and s["partite"] == [] and s["schedine"] == []
        assert s["classifica"]["ultima_giornata_giocata"] is None
        assert [g["variazione_posizione"] for g in s["classifica"]["giocatori"]] == [None, None]
        assert s["cassa"]["saldo"] == 0.0 and s["cassa"]["movimenti"] == [] and s["cassa"]["versamenti_per_giornata"] == []
        assert s["statistiche"]["ultima_schedina_vinta"] is None
        assert all(v is None for v in s["statistiche"]["premi"].values())
        assert s["statistiche"]["giocatori"] == [] and s["statistiche"]["per_un_soffio"] == []

    def test_cassa_vuota_e_valida(self, base):
        c, _, g, fd, a = base
        s = costruisci(c, [], g, fd, a)
        assert valida(s, SCHEMA) == [] and s["cassa"]["saldo"] == 0.0

    def test_il_segnale_rispetta_lo_schema(self, snap_base):
        assert valida(st.costruisci_segnale(snap_base, ADESSO + timedelta(minutes=15)), SCHEMA_SEGNALE) == []

    def test_e_serializzabile_in_json_senza_perdite(self, snap_stagione):
        testo = json.dumps(snap_stagione, allow_nan=False)  # allow_nan=False: NaN/Infinity non sono JSON
        assert json.loads(testo) == snap_stagione

    def test_deterministico(self, base):
        assert costruisci(*base) == costruisci(*base)
        assert st.impronta_snapshot(costruisci(*base)) == st.impronta_snapshot(costruisci(*base))

    def test_generato_il_e_l_adesso_in_utc(self, base):
        c, ca, g, fd, _ = base
        roma = pytz.timezone("Europe/Rome").localize(datetime(2026, 10, 4, 17, 30, 12))  # = 15:30:12 UTC
        s = costruisci(c, ca, g, fd, roma)
        assert s["generato_il"] == "2026-10-04T15:30:12Z"

    def test_ordini_garantiti(self, snap_stagione):
        s = snap_stagione
        assert s["giocatori"] == sorted(s["giocatori"])
        assert [(x["giornata"], x["giocatore"]) for x in s["schedine"]] == sorted((x["giornata"], x["giocatore"]) for x in s["schedine"])
        assert [p["giornata"] for p in s["partite"]] == sorted(p["giornata"] for p in s["partite"])
        for g in range(1, 39):  # dentro la giornata: per calcio d'inizio
            orari = [p["inizio_il"] for p in s["partite"] if p["giornata"] == g]
            assert orari == sorted(orari)
        punti = [(-x["punti_totali"], x["nome"]) for x in s["classifica"]["giocatori"]]
        assert [x["posizione"] for x in s["classifica"]["giocatori"]] == sorted(x["posizione"] for x in s["classifica"]["giocatori"])
        assert [x["giornata"] for x in s["cassa"]["versamenti_per_giornata"]] == sorted(x["giornata"] for x in s["cassa"]["versamenti_per_giornata"])
        assert len(punti) == 16

    def test_coerenza_fra_le_sezioni(self, snap_stagione):
        s = snap_stagione
        ids = {p["id"] for p in s["partite"]}
        assert len(ids) == len(s["partite"])  # id unici
        for p in s["partite"]:
            assert (p["id"] > 0) == p["ufficiale"]  # id negativo se e solo se non ufficiale
        for sc in s["schedine"]:
            assert sum(sc["riepilogo"].values()) == len(sc["righe"])
            for r in sc["righe"]:
                assert r["partita_id"] in ids
        assert s["giornata_corrente"] == 38
        assert len(s["partite"]) == 380 and len(s["schedine"]) == 38 * 16
        assert all(len(g["punti_per_giornata"]) == 38 for g in s["classifica"]["giocatori"])
        assert all(len(r["punti_per_giornata"]) == 38 for r in s["classifica"]["ritirati"])

    def test_partite_solo_quelle_giocate_da_qualcuno(self):
        # 38 giornate in Football-Data, ma solo la 2 in Giocate: lo snapshot ha le 10 partite della 2.
        c = dati.classifica_valori([("PAOLO", [None, 10])])
        g = [dati.INTESTAZIONE_GIOCATE] + dati.schedina(2, "PAOLO")
        s = costruisci(c, dati.cassa_valori(), g, dati.partite_fd())
        assert {p["giornata"] for p in s["partite"]} == {2} and len(s["partite"]) == 10

    def test_dimensione_a_fine_stagione(self, snap_stagione):
        # Lo schema stima ~810 KB grezzi per 38 giornate x 16 giocatori. Un tetto largo, per accorgersi
        # se un campo nuovo gonfia lo snapshot (il limite di un valore KV e' 25 MiB, ma la banda conta).
        grezzo = len(json.dumps(snap_stagione, separators=(",", ":"), ensure_ascii=False).encode())
        assert 500_000 < grezzo < 1_200_000, grezzo


# ======================================================================
# 3. Niente dati sensibili
# ======================================================================
class TestNienteDatiSensibili:
    def test_nessun_dato_tecnico(self, snap_stagione, monkeypatch):
        monkeypatch.setenv("SPREADSHEET_ID", "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789SEGRETO")
        monkeypatch.setenv("FOOTBALL_DATA_KEY", "chiave-segreta-football")
        testo = json.dumps(st.costruisci_snapshot(*dati.dataset_stagione()), ensure_ascii=False).lower()
        for vietato in ("segreto", "chiave-segreta", "spreadsheet", "token", "telegram", "chat_id", "api_key",
                        "football_data", "password", "credenziali", "docs.google", "x-auth"):
            assert vietato not in testo, vietato

    def test_la_struttura_non_lascia_spazio_a_campi_extra(self, snap_stagione):
        # La garanzia vera: le chiavi sono esattamente quelle dello schema (test dello schema sopra),
        # quindi un ID Telegram o una chiave non hanno dove stare. Qui la conferma sui nomi.
        chiavi = set()

        def raccogli(v):
            if isinstance(v, dict):
                chiavi.update(v)
                for x in v.values():
                    raccogli(x)
            elif isinstance(v, list):
                for x in v:
                    raccogli(x)
        raccogli(snap_stagione)
        assert not [c for c in chiavi if re.search(r"id_?telegram|chat|token|key|chiave|secret|url|sheet", c)]

    def test_i_nomi_dei_fogli_e_le_righe_scartate_restano_fuori(self, base):
        c, ca, g, fd, a = base
        g = g + [["Giornata 9", "", "X - Y"], dati.INTESTAZIONE_GIOCATE]
        s, avvisi = st.costruisci_snapshot_con_avvisi(c, ca, g, fd, a)
        assert len(avvisi) == 2
        assert all(a_ not in json.dumps(s) for a_ in ("scartata", "riga senza giocatore", "intestazione ripetuta"))


# ======================================================================
# 4. Dati illeggibili -> eccezione chiara (decisione 13)
# ======================================================================
class TestDatiIllegibili:
    def test_classifica_vuota(self, base):
        c, ca, g, fd, a = base
        with pytest.raises(ValueError, match="Classifica"):
            costruisci([], ca, g, fd, a)

    def test_giocate_vuoto(self, base):
        c, ca, g, fd, a = base
        with pytest.raises(ValueError, match="Giocate"):
            costruisci(c, ca, [], fd, a)

    def test_football_data_vuoto(self, base):
        c, ca, g, fd, a = base
        for vuoto in ({"matches": []}, {}, []):
            with pytest.raises(ValueError, match="Football-Data"):
                costruisci(c, ca, g, vuoto, a)

    def test_stagione_non_riconoscibile(self, base):
        c, ca, g, fd, a = base
        fd = copy.deepcopy(fd)
        for m in fd["matches"]:
            m["season"] = {}
        with pytest.raises(ValueError, match="stagione"):
            costruisci(c, ca, g, fd, a)

    def test_adesso_senza_fuso(self, base):
        c, ca, g, fd, _ = base
        with pytest.raises(ValueError, match="fuso"):
            costruisci(c, ca, g, fd, datetime(2026, 10, 4, 15, 30))

    def test_cella_non_numerica_vale_zero_come_nel_bot_e_da_un_avviso(self, base):
        """Decisione 04/10/2026: come esegui_calcolo_risultati (conta solo le celle isdigit)
        la cella non numerica vale 0, niente ValueError, ma un avviso nomina giocatore e colonna."""
        c, ca, g, fd, a = base
        _, avvisi_base = st.costruisci_snapshot_con_avvisi(c, ca, g, fd, a)
        for riga, colonna, testo in ((1, 1, "n.d."), (1, 3, "-"), (1, 2, "12,5")):
            cc = copy.deepcopy(c)
            cc[riga][colonna] = testo
            s, avvisi = st.costruisci_snapshot_con_avvisi(cc, ca, g, fd, a)  # non solleva
            nuovi = [x for x in avvisi if x not in avvisi_base and "non numerico" in x]
            assert len(nuovi) == 1 and repr(testo) in nuovi[0] and repr(c[0][colonna]) in nuovi[0]
            assert cc[riga][0].strip().upper() in nuovi[0]
            assert st.costruisci_snapshot(cc, ca, g, fd, a)["giocatori"] == s["giocatori"]

    def test_importo_di_cassa_illeggibile(self, base):
        c, ca, g, fd, a = base
        ca = copy.deepcopy(ca)
        ca[1][3] = "???"
        with pytest.raises(ValueError, match="Cassa"):
            costruisci(c, ca, g, fd, a)

    def test_un_errore_non_diventa_uno_zero_silenzioso(self, base):
        # D3 / D17 / A3: il vecchio sito, davanti a un saldo illeggibile, mostrava "0,00 €" (except: nudo) e
        # carica_tutti_i_dati inghiottiva ogni eccezione restituendo tabelle vuote (con 180 secondi di cache).
        ultimo = "???"
        try:
            vecchio = float(ultimo.replace("€", "").replace(".", "").replace(",", ".").strip())
        except Exception:
            vecchio = 0.0
        assert vecchio == 0.0  # il vecchio comportamento: la cassa "vuota"
        c, ca, g, fd, a = base
        ca = copy.deepcopy(ca)
        ca[-1][3] = ultimo
        with pytest.raises(ValueError):  # il nuovo: non si pubblica
            costruisci(c, ca, g, fd, a)


# ======================================================================
# 5. Avvisi per il log e per gli admin (mai nello snapshot)
# ======================================================================
class TestAvvisi:
    def test_nessun_avviso_su_dati_coerenti(self, stagione):
        assert st.costruisci_snapshot_con_avvisi(*stagione)[1] == []

    def test_partita_non_abbinata(self, base):
        c, ca, g, fd, a = base
        g = g + [dati.riga_giocata(3, "MARIO", "Pisa - Cremo", "Fisse", "1", "2,00")]
        s, avvisi = st.costruisci_snapshot_con_avvisi(c, ca, g, fd, a)
        assert avvisi == ["Giornata 3, MARIO: la partita 'Pisa - Cremo' non corrisponde a nessuna partita della giornata"]
        nuova = [p for p in s["partite"] if not p["ufficiale"]]
        assert [(p["id"], p["nome"], p["inizio_il"]) for p in nuova] == [(-1, "Pisa - Cremo", None)]

    def test_stesso_avviso_non_si_ripete_per_ogni_riga(self, base):
        c, ca, g, fd, a = base
        g = g + [dati.riga_giocata(3, "MARIO", "Pisa - Cremo")] * 3
        assert len(st.costruisci_snapshot_con_avvisi(c, ca, g, fd, a)[1]) == 1

    def test_totale_di_classifica_diverso_dalla_somma_delle_giornate(self, base):
        c, ca, g, fd, a = base
        c = copy.deepcopy(c)
        c[1][1] = "999"
        avvisi = st.costruisci_snapshot_con_avvisi(c, ca, g, fd, a)[1]
        assert avvisi == ["Classifica: PAOLO ha Punti Totali 999 ma le giornate sommano 102"]

    def test_saldo_di_cassa_scritto_diverso_dalla_somma(self, base):
        c, ca, g, fd, a = base
        ca = copy.deepcopy(ca)
        ca[-1][3] = "5.000,00€"
        avvisi = st.costruisci_snapshot_con_avvisi(c, ca, g, fd, a)[1]
        assert len(avvisi) == 1 and "Cassa" in avvisi[0] and "800.00" in avvisi[0]


# ======================================================================
# 6. Le decisioni di dominio, viste dallo snapshot intero
# ======================================================================
def snapshot_da_righe(righe_foglio, giocatori_classifica, cassa=None):
    """Snapshot da poche righe di Giocate e una Classifica a punti piatti."""
    giocate = [dati.INTESTAZIONE_GIOCATE] + list(righe_foglio)
    classifica = dati.classifica_valori(giocatori_classifica)
    return costruisci(classifica, cassa or dati.cassa_valori(), giocate, dati.partite_fd())


class TestDecisioniDiDominio:
    def test_pari_merito_tutti_nelle_card(self):
        # §17.14: tutti i pari merito, nessun minimo. Con una sola partita valutata a testa e tutti
        # a pari merito, le card elencano tutti i giocatori in ordine alfabetico.
        righe = [dati.riga_giocata(1, n, dati.nome_foglio(1, 0), "Fisse", "1", "2,00", dati.VINTA) for n in ("ZETA", "ALFA", "MEDIO")]
        s = snapshot_da_righe(righe, [("ZETA", [4]), ("ALFA", [4]), ("MEDIO", [4])])
        premi = s["statistiche"]["premi"]
        for chiave in ("cecchino", "benedizione", "folle", "conservatore"):
            assert [x["giocatore"] for x in premi[chiave]] == ["ALFA", "MEDIO", "ZETA"], chiave
        assert premi["cecchino"][0] == {"giocatore": "ALFA", "win_rate": 100.0, "vinte": 1, "totali": 1}
        assert [x["giocatore"] for x in premi["giornata_da_incorniciare"]] == ["ALFA", "MEDIO", "ZETA"]

    def test_ranking_sportivo_nello_snapshot(self):
        righe = [dati.riga_giocata(1, "D", dati.nome_foglio(1, 0))]  # una vittoria a D, nessuna agli altri
        s = snapshot_da_righe(righe, [("A", [50]), ("B", [40]), ("C", [40]), ("D", [40]), ("E", [10])])
        # D ha una vittoria: sopra B e C, che restano pari merito (e il successivo salta)
        assert [(g["nome"], g["posizione"]) for g in s["classifica"]["giocatori"]] == [
            ("A", 1), ("D", 2), ("B", 3), ("C", 3), ("E", 5)]

    def test_semper_fidelis_giornate_distinte(self):
        # Inter in casa in G1 e G2 (partite costruite a mano su una stagione finta)
        fd = {"matches": [
            {"id": 1, "matchday": 1, "utcDate": "2026-08-22T15:00:00Z", "season": {"startDate": "2026-08-23"},
             "homeTeam": {"name": "FC Internazionale Milano", "shortName": "Inter"}, "awayTeam": {"name": "AC Milan", "shortName": "Milan"}},
            {"id": 2, "matchday": 2, "utcDate": "2026-08-29T15:00:00Z", "season": {"startDate": "2026-08-23"},
             "homeTeam": {"name": "FC Internazionale Milano", "shortName": "Inter"}, "awayTeam": {"name": "AS Roma", "shortName": "Roma"}}]}
        righe = [dati.riga_giocata(1, "PAOLO", "Inter - Milan", "Fisse", "1"), dati.riga_giocata(1, "PAOLO", "Inter - Milan", "Doppie Chance", "1X"),
                 dati.riga_giocata(2, "PAOLO", "Inter - Roma", "Fisse", "1"),
                 dati.riga_giocata(1, "DARIO", "Inter - Milan", "Fisse", "1"), dati.riga_giocata(1, "DARIO", "Inter - Milan", "Doppie Chance", "1X")]
        s = costruisci(dati.classifica_valori([("PAOLO", [8, 4]), ("DARIO", [8, 0])]), dati.cassa_valori(),
                       [dati.INTESTAZIONE_GIOCATE] + righe, fd)
        assert s["statistiche"]["premi"]["semper_fidelis"] == [{"giocatore": "PAOLO", "squadra": "FC Internazionale Milano", "volte": 2}]

    def test_amuleto_solo_la_squadra_scelta(self):
        fd = {"matches": [{"id": 1, "matchday": 1, "utcDate": "2026-08-22T15:00:00Z", "season": {"startDate": "2026-08-23"},
                           "homeTeam": {"name": "FC Internazionale Milano", "shortName": "Inter"},
                           "awayTeam": {"name": "AC Milan", "shortName": "Milan"}}]}
        # tre pronostici vinti sulla stessa partita: "1" (Inter), "OVER_2.5" e "X" (nessuna squadra)
        righe = [dati.riga_giocata(1, "A", "Inter - Milan", "Fisse", "1"), dati.riga_giocata(1, "B", "Inter - Milan", "Variabili", "OVER_2.5"),
                 dati.riga_giocata(1, "C", "Inter - Milan", "Fisse", "X")]
        s = costruisci(dati.classifica_valori([("A", [4]), ("B", [2]), ("C", [4])]), dati.cassa_valori(),
                       [dati.INTESTAZIONE_GIOCATE] + righe, fd)
        assert s["statistiche"]["premi"]["squadra_amuleto"] == [{"squadra": "FC Internazionale Milano", "vittorie_portate": 1}]
        assert s["statistiche"]["premi"]["squadra_maledetta"] is None

    def test_coppa_definitiva_a_giornata_34_conclusa(self):
        nomi = dati.NOMI_16
        classifica = dati.classifica_valori([(n, [30 - i] * 34) for i, n in enumerate(nomi)])
        fd = dati.partite_fd([33, 34, 35])
        giocate33 = [dati.INTESTAZIONE_GIOCATE] + dati.schedina(33, nomi[0])
        # 34 in corso e una riga gia' caricata della 35: il vecchio criterio avrebbe detto "definitiva"
        aperta = dati.schedina(34, nomi[0], esiti=[dati.VINTA] * 9 + [dati.IN_CORSO]) + dati.schedina(35, nomi[0], esiti=[""] * 10)
        s = costruisci(classifica, dati.cassa_valori(), giocate33 + aperta, fd)
        assert s["coppa"]["definitiva"] is False
        chiusa = dati.schedina(34, nomi[0]) + dati.schedina(35, nomi[0], esiti=[""] * 10)
        s = costruisci(classifica, dati.cassa_valori(), giocate33 + chiusa, fd)
        assert s["coppa"]["definitiva"] is True

    def test_il_sostituto_eredita_le_vittorie_del_ritirato(self):
        # Le schedine di PULIZZER sono state rinominate SIRACUSA (Sessione 20): sono righe di SIRACUSA.
        # SIRACUSA e ALFA hanno gli stessi punti; SIRACUSA ha piu' pronostici vinti grazie a quelle schedine.
        righe = [dati.riga_giocata(1, "SIRACUSA", dati.nome_foglio(1, i)) for i in range(3)] + [dati.riga_giocata(1, "ALFA", dati.nome_foglio(1, 0))]
        s = snapshot_da_righe(righe, [("ALFA", [40]), ("SIRACUSA", [40]), ("PULIZZER (RITIRATO)", [16])])
        assert [g["nome"] for g in s["classifica"]["giocatori"]] == ["SIRACUSA", "ALFA"]
        assert [(r["nome"], r["punti_totali"]) for r in s["classifica"]["ritirati"]] == [("PULIZZER", 16)]
        # e le sue statistiche congelate vengono dalle schedine del sostituto
        assert [r["nome"] for r in s["statistiche"]["ritirati"]] == ["PULIZZER"]

    def test_le_annullate_non_votano_nella_scelta_del_gruppo(self):
        p = dati.nome_foglio(1, 0)
        righe = [dati.riga_giocata(1, "A", p, pronostico="1"), dati.riga_giocata(1, "B", p, pronostico="1"),
                 dati.riga_giocata(1, "C", p, pronostico="X (ANNULLATA ECCESSO)", esito=dati.ANNULLATA)]
        s = snapshot_da_righe(righe, [("A", [4]), ("B", [4]), ("C", [0])])
        sg = next(x for x in s["partite"] if x["nome"].startswith(dati.SQUADRE[dati.calendario(1)[0][0]][0]))["scelta_gruppo"]
        assert sg == {"tipo": "maggioranza", "pronostici": ["1"], "voti": 2, "su": 2}

    def test_esito_sconosciuto_diventa_da_verificare_mai_vinta(self):
        righe = [dati.riga_giocata(1, "A", dati.nome_foglio(1, 0), esito="boh", punti=0)]
        s = snapshot_da_righe(righe, [("A", [0])])
        assert s["schedine"][0]["righe"][0]["esito"] == "da_verificare"
        assert s["schedine"][0]["riepilogo"]["da_verificare"] == 1 and s["schedine"][0]["riepilogo"]["vinte"] == 0

    def test_sul_giocatore_ritirato_non_si_calcolano_premi(self, snap_base):
        premi = snap_base["statistiche"]["premi"]
        quanti = [x["giocatore"] for k in ("cecchino", "benedizione", "folle", "conservatore") for x in premi[k]]
        assert "PULIZZER" not in quanti
        assert [r["nome"] for r in snap_base["statistiche"]["ritirati"]] == ["PULIZZER"]

    def test_ritirato_in_fondo_e_giocatori_senza_ritirato(self, snap_base):
        assert "PULIZZER" not in snap_base["giocatori"]
        assert [g["nome"] for g in snap_base["classifica"]["giocatori"]] == ["PAOLO", "MARIO", "DARIO", "SIRACUSA"]
        assert snap_base["classifica"]["ritirati"][0]["punti_per_giornata"] == [30, 20, None]

    def test_ultima_schedina_vinta_nel_dataset_base(self, snap_base, base):
        u = snap_base["statistiche"]["ultima_schedina_vinta"]
        assert u["giornata"] == 3 and u["vincitori"] == ["PAOLO"]
        # fine dell'ULTIMA partita fra quelle di PAOLO in G3, piu' 2 ore
        ultima = max(m["utcDate"] for m in base[3]["matches"] if m["matchday"] == 3)
        atteso = datetime.strptime(ultima, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=2)
        assert u["inizio_il"] == atteso.strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_cassa_nel_dataset_base(self, snap_base):
        c = snap_base["cassa"]
        assert c["saldo"] == 800.0 and c["completamento"] == 0.25 and c["obiettivo_raggiunto"] is False
        assert [(m["giornata"], m["entrata"], m["saldo"]) for m in c["movimenti"]] == [(1, 400.0, 400.0), (3, 400.0, 800.0)]
        assert c["versamenti_per_giornata"] == [{"giornata": 1, "versato": 400.0}, {"giornata": 2, "versato": 0.0}, {"giornata": 3, "versato": 400.0}]


# ======================================================================
# 7. Le scritture reali della Giornata 1 (29 per 10 partite)
# ======================================================================
class TestScrittureRealiGiornata1:
    def test_tutte_abbinate_e_nessuna_non_ufficiale(self):
        righe = []
        for indice, scritture in dati.G1_SCRITTURE.items():
            for k, testo in enumerate(scritture):
                righe.append(dati.riga_giocata(1, f"G{indice}{k}", testo, "Fisse", "1", "1,50", dati.VINTA))
        s, avvisi = st.costruisci_snapshot_con_avvisi(
            dati.classifica_valori([(r[1], [4]) for r in righe]), dati.cassa_valori(),
            [dati.INTESTAZIONE_GIOCATE] + righe, dati.partite_fd_g1(), ADESSO)
        assert avvisi == []
        assert len(righe) == 29 and len(s["partite"]) == 10
        assert all(p["ufficiale"] for p in s["partite"])
        # ogni partita raccoglie tutte le scritture della sua partita
        voti = {p["id"]: p["scelta_gruppo"]["su"] for p in s["partite"]}
        assert sorted(voti.values()) == sorted(len(v) for v in dati.G1_SCRITTURE.values())


# ======================================================================
# 8. Errori di app.py (§16) senza una funzione sola
# ======================================================================
class TestErroriDiAppCorretti:
    def test_d6_due_ordinamenti_ora_uno_con_l_anno(self):
        # Il vecchio ordine della scheda Live riconvertiva "dd/mm HH:MM" con strptime SENZA anno (1900, non
        # bisestile): una partita del 29 febbraio solleva e finiva in fondo. In un'annata bisestile succede davvero.
        with pytest.raises(ValueError):
            datetime.strptime("29/02 20:45", "%d/%m %H:%M")
        fd = {"matches": [
            {"id": 1, "matchday": 1, "utcDate": "2028-02-29T19:45:00Z", "season": {"startDate": "2027-08-22"},
             "homeTeam": {"name": "Alfa FC", "shortName": "Alfa"}, "awayTeam": {"name": "Beta FC", "shortName": "Beta"}},
            {"id": 2, "matchday": 1, "utcDate": "2028-03-01T14:00:00Z", "season": {"startDate": "2027-08-22"},
             "homeTeam": {"name": "Gamma FC", "shortName": "Gamma"}, "awayTeam": {"name": "Delta FC", "shortName": "Delta"}}]}
        righe = [dati.riga_giocata(1, "A", "Gamma - Delta"), dati.riga_giocata(1, "A", "Alfa - Beta")]
        s = costruisci(dati.classifica_valori([("A", [8])]), dati.cassa_valori(), [dati.INTESTAZIONE_GIOCATE] + righe, fd)
        assert [p["nome"] for p in s["partite"]] == ["Alfa FC - Beta FC", "Gamma FC - Delta FC"]  # il 29/02 viene prima del 1/03
        assert [r["partita_id"] for r in s["schedine"][0]["righe"]] == [1, 2]  # e la schedina segue lo stesso ordine

    def test_d7_vincita_potenziale_letta_in_un_modo_solo(self):
        # La scheda Live scartava solo "", "0", "0.0": "0,00" passava e si leggeva "0,00 €" come vincita;
        # il Confronto faceva un altro parse. Ora un parser solo (estrai_numero) e 0 = nessuna vincita.
        celle = ["", "0,00", "1.030,30"]
        vecchio_live = [v for v in celle if str(v).strip() not in ["", "0", "0.0"]][0]
        assert vecchio_live == "0,00"
        righe = [dati.riga_giocata(1, "A", dati.nome_foglio(1, i), vincita=v) for i, v in enumerate(celle)]
        s = snapshot_da_righe(righe, [("A", [12])])
        assert s["schedine"][0]["vincita_potenziale"] == 1030.30

    def test_d14_il_colore_non_viaggia_dentro_il_testo(self):
        # Il Confronto passava l'esito come "|||VINTA" appeso al testo della cella e lo toglieva dopo:
        # un testo che contenesse quella sequenza veniva mutilato. Ora l'esito e' un campo.
        testo = "X|||VINTA"
        vecchio = testo.replace("|||VINTA", "").replace("|||PERSA", "")
        assert vecchio == "X"
        righe = [dati.riga_giocata(1, "A", dati.nome_foglio(1, 0), pronostico=testo, esito=dati.PERSA)]
        riga_snap = snapshot_da_righe(righe, [("A", [0])])["schedine"][0]["righe"][0]
        assert riga_snap["pronostico"] == testo and riga_snap["esito"] == "persa"

    def test_d15_una_barra_sola_per_giornata(self):
        # Il grafico dei versamenti usava le ETICHETTE come chiave: "Giornata 5" e " Giornata 5" erano due barre.
        etichette = ["Giornata 5", " Giornata 5"]
        assert len(set(etichette)) == 2
        movimenti = st.movimenti_cassa([dati.INTESTAZIONE_CASSA, [etichette[0], "A chiude la schedina!", "10,00€", "10,00€"],
                                        [etichette[1], "B chiude la schedina!", "5,00€", "15,00€"]])
        assert st.versamenti_per_giornata(movimenti, {5}) == [{"giornata": 5, "versato": 15.0}]

    def test_d15_etichetta_non_numerica_non_diventa_giornata_zero(self):
        movimenti = st.movimenti_cassa([dati.INTESTAZIONE_CASSA, ["Extra", "Versamento", "10,00€", "10,00€"]])
        assert movimenti[0]["giornata"] is None
        assert st.versamenti_per_giornata(movimenti, set()) == []  # il vecchio grafico mostrava una barra "Giornata 0"

    def test_d16_giornata_come_intero_non_come_testo(self):
        # Il vecchio filtro: df['Giornata'] == "Giornata 12"; e str(g).replace("giornata","").strip() per la API.
        # Una scrittura leggermente diversa ("giornata 12", " Giornata 12") non trovava la giornata.
        assert ("giornata 12" == "Giornata 12") is False
        righe = [dati.riga_giocata(12, "A", dati.nome_foglio(12, 0))]
        righe[0][0] = " giornata 12 "
        s = snapshot_da_righe(righe, [("A", [0] * 12)])
        assert s["giornata_corrente"] == 12 and s["schedine"][0]["giornata"] == 12

    def test_giornata_corrente_e_la_piu_alta_non_l_ultima_del_foglio(self):
        # Il vecchio sito selezionava l'ULTIMA giornata per ordine di comparsa nel foglio.
        righe = dati.schedina(3, "A") + dati.schedina(1, "A")
        s = snapshot_da_righe(righe, [("A", [10, 0, 34])])
        assert s["giornata_corrente"] == 3

    def test_d23_nessuna_chiamata_di_rete(self, base, monkeypatch):
        # Football-Data si chiama UNA volta fuori da qui (e' il chiamante a passare la risposta):
        # costruisci_snapshot e' puro. Se qualcuno ci mette dentro un requests.get il test fallisce.
        import socket
        import requests

        def vietato(*a, **k):
            raise AssertionError("costruisci_snapshot non deve fare rete")
        monkeypatch.setattr(socket.socket, "connect", vietato)
        monkeypatch.setattr(requests, "get", vietato)
        monkeypatch.setattr(requests.Session, "request", vietato)
        assert costruisci(*base)

    def test_d21_d22_un_solo_giro_su_6000_righe(self, stagione):
        # I due iterrows e i filtri per giocatore del vecchio app.py costavano secondi su 6.000 righe.
        # Misura di riferimento 0,4 s su un Mac: il tetto largo serve a vedere una regressione di ordine di grandezza.
        inizio = time.perf_counter()
        costruisci(*stagione)
        assert time.perf_counter() - inizio < 5.0

    def test_d17_un_errore_non_produce_uno_snapshot_vuoto(self, base):
        # carica_tutti_i_dati restituiva 3 tabelle vuote su qualsiasi eccezione: qui l'eccezione arriva a chi chiama,
        # che tiene lo snapshot precedente.
        c, ca, g, fd, a = base
        with pytest.raises(ValueError):
            costruisci(c, ca, g, {"matches": []}, a)
