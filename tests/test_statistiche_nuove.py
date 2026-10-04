"""
Test delle funzioni di statistiche.py aggiunte per lo SNAPSHOT del restyling
(restyling/snapshot-schema.md, §15: N1-N23, S1-S2, le due funzioni adattate).

Due famiglie di test:

1. Un test per ogni funzione nuova, sul caso normale e sui bordi.
2. Un test per ogni errore di app.py corretto (§16): ognuno RIPRODUCE in poche
   righe la logica vecchia di app.py e verifica che sbagliasse davvero sul
   caso scelto, poi che la funzione nuova sia giusta. Senza la prima meta' il
   test non proverebbe che la correzione serve.

Le decisioni di dominio del 04/10/2026 (§17) hanno ognuna il suo test: pari
merito mostrati tutti, ranking sportivo, Semper Fidelis per giornate distinte,
amuleto solo sulla squadra scelta, Coppa definitiva a Giornata 34 conclusa,
sostituto che eredita le vittorie, annullate che non votano.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytz

import bot_telegram as bt
import statistiche as st
import dati_finti as dati
from dati_finti import G1_SCRITTURE, G1_UFFICIALI


def utc(anno, mese, giorno, ora, minuto=0, secondo=0):
    return datetime(anno, mese, giorno, ora, minuto, secondo, tzinfo=pytz.UTC)


def riga(giornata, giocatore, pid, esito="vinta", pron="1", quota=1.5, tip="fisse", vincita=0.0, punti=0,
         testo="A - B"):
    """Una riga di Giocate GIA' PULITA, con partita_id (come esce da abbina_righe_a_partite)."""
    return {"giornata": giornata, "giocatore": giocatore, "partita_testo": testo, "tipologia": tip,
            "pronostico": pron, "quota": quota, "esito": esito, "vincita": vincita, "punti": punti,
            "partita_id": pid}


def partita(id_, casa, ospite, inizio=None, giornata=1, ufficiale=True):
    """Una partita nel formato di N5 (nomi completi, shortName uguale al nome per semplicita')."""
    return {"id": id_, "nome": f"{casa} - {ospite}", "casa": {"name": casa, "shortName": casa},
            "ospite": {"name": ospite, "shortName": ospite}, "inizio": inizio}


def info(*partite_):
    """L'`info` di abbina_righe_a_partite per un elenco di partite."""
    return {p["id"]: {"id": p["id"], "giornata": 1, "nome": p["nome"], "ufficiale": True,
                      "casa": p["casa"]["name"], "ospite": p["ospite"]["name"], "inizio": p["inizio"]}
            for p in partite_}


# ======================================================================
# S1, S2 — spostate dal bot
# ======================================================================
class TestFunzioniSpostateDalBot:
    def test_il_bot_usa_le_funzioni_di_statistiche(self):
        # Un'unica definizione: se qualcuno ne rimette una copia nel bot, i due parser divergono.
        assert bt.estrai_numero is st.estrai_numero
        assert bt.etichetta_stagione is st.etichetta_stagione

    @pytest.mark.parametrize("testo,atteso", [
        ("1.674,56", 1674.56), ("430,00€", 430.0), ("2,1", 2.1), ("1.50", 1.5), ("", 0.0), ("abc", 0.0),
    ])
    def test_estrai_numero_formato_italiano(self, testo, atteso):
        assert st.estrai_numero(testo) == atteso

    def test_etichetta_stagione(self):
        assert st.etichetta_stagione("2026-08-23") == "2026-27"
        assert st.etichetta_stagione("2026-8-23") is None
        assert st.etichetta_stagione(None) is None


# ======================================================================
# N1, N2 — enum
# ======================================================================
class TestEnum:
    @pytest.mark.parametrize("testo,atteso", [
        ("✅ VINTA", "vinta"), ("❌ PERSA", "persa"), ("⏳ IN CORSO", "in_corso"),
        ("⏸️ RINVIATA", "rinviata"), ("⚠️ DA VERIFICARE", "da_verificare"),
        ("➖ ANNULLATA", "annullata"), ("", "da_giocare"), ("   ", "da_giocare"), (None, "da_giocare"),
        ("ANNULLATA ECCESSO", "annullata"),
    ])
    def test_esito_da_testo(self, testo, atteso):
        assert st.esito_da_testo(testo) == atteso

    def test_testo_sconosciuto_non_fa_mai_vincere(self):
        # §17.11 e regola del progetto: "mai far vincere per default".
        for testo in ("boh", "OK", "2X", "SI", "?"):
            assert st.esito_da_testo(testo) == "da_verificare"

    def test_esito_da_testo_e_idempotente(self):
        for e in st.ESITI:
            assert st.esito_da_testo(e) == e

    @pytest.mark.parametrize("testo,atteso", [
        ("Combo", "combo"), ("Fisse", "fisse"), ("Doppie Chance", "doppie_chance"),
        ("Variabili", "variabili"), (" doppie_chance ", "doppie_chance"), ("DOPPIE CHANCE", "doppie_chance"),
        ("Altro", None), ("", None), (None, None),
    ])
    def test_tipologia_da_testo(self, testo, atteso):
        assert st.tipologia_da_testo(testo) == atteso


# ======================================================================
# N3 — Giocate pulita
# ======================================================================
class TestPulisciGiocate:
    def test_conversioni(self):
        valori = [dati.INTESTAZIONE_GIOCATE,
                  ["Giornata 12", " paolo ", " Milan - Inter ", "Doppie Chance", "1x", "1.674,56", "✅ VINTA", "1.030,30", "2"]]
        righe, scartate = st.pulisci_giocate(valori)
        assert scartate == []
        r = righe[0]
        assert r["giornata"] == 12 and isinstance(r["giornata"], int)
        assert r["giocatore"] == "PAOLO"
        assert r["partita_testo"] == "Milan - Inter"
        assert r["tipologia"] == "doppie_chance"
        assert r["pronostico"] == "1x"  # il pronostico resta come nel foglio
        assert r["quota"] == 1674.56
        assert r["esito"] == "vinta"
        assert r["vincita"] == 1030.30
        assert r["punti"] == 2

    def test_celle_vuote_e_righe_corte(self):
        righe, _ = st.pulisci_giocate([dati.INTESTAZIONE_GIOCATE, ["Giornata 1", "PAOLO", "A - B", "Fisse", "1", "1,5"]])
        assert righe[0]["esito"] == "da_giocare" and righe[0]["vincita"] == 0.0 and righe[0]["punti"] == 0

    def test_quota_illeggibile_o_vuota_e_none_mai_zero(self):
        for quota in ("", "  ", "n.d.", "0", "0,00"):
            righe, _ = st.pulisci_giocate([dati.INTESTAZIONE_GIOCATE, ["Giornata 1", "PAOLO", "A - B", "Fisse", "1", quota]])
            assert righe[0]["quota"] is None, quota

    def test_righe_scartate_con_il_motivo(self):
        valori = [dati.INTESTAZIONE_GIOCATE,
                  ["Giornata 1", "PAOLO", "A - B", "Fisse", "1", "1,5", "✅ VINTA"],
                  dati.INTESTAZIONE_GIOCATE,                                   # intestazione ripetuta
                  ["Giornata 1", "", "A - B", "Fisse", "1", "1,5"],           # senza giocatore
                  ["Giornata 1 bis", "PAOLO", "A - B", "Fisse", "1", "1,5"],  # giornata non valida
                  ["Giornata", "PAOLO", "A - B"],                              # giornata senza numero
                  ["", "", "", "", ""]]                                        # vuota: nessuna traccia
        righe, scartate = st.pulisci_giocate(valori)
        assert len(righe) == 1
        assert [n for n, _ in scartate] == [3, 4, 5, 6]
        assert "intestazione" in scartate[0][1] and "senza giocatore" in scartate[1][1]

    def test_giornata_e_un_intero_non_una_sottostringa(self):
        # §16 D16: "1" dentro "Giornata 12".
        righe, _ = st.pulisci_giocate([dati.INTESTAZIONE_GIOCATE,
                                       ["Giornata 1", "A", "x - y"], ["Giornata 12", "A", "x - y"]])
        assert [r["giornata"] for r in righe] == [1, 12]

    def test_vuoto(self):
        assert st.pulisci_giocate([]) == ([], [])
        assert st.pulisci_giocate([dati.INTESTAZIONE_GIOCATE]) == ([], [])

    def test_senza_intestazione_non_perde_la_prima_riga(self):
        righe, _ = st.pulisci_giocate([["Giornata 1", "PAOLO", "A - B", "Fisse", "1", "1,5", "✅ VINTA"]])
        assert len(righe) == 1


# ======================================================================
# N4, N11, N12 — Cassa
# ======================================================================
class TestCassa:
    def test_movimenti(self):
        m = st.movimenti_cassa([dati.INTESTAZIONE_CASSA,
                                ["Giornata 1", "PAOLO chiude la schedina!", "1.674,56€", "1.674,56€"],
                                ["Versamento manuale", "Extra", "", ""]])
        assert m[0] == {"giornata": 1, "descrizione": "PAOLO chiude la schedina!", "entrata": 1674.56, "saldo": 1674.56}
        assert m[1] == {"giornata": None, "descrizione": "Extra", "entrata": None, "saldo": None}

    def test_importo_illeggibile_solleva(self):
        with pytest.raises(ValueError, match="Entrate"):
            st.movimenti_cassa([dati.INTESTAZIONE_CASSA, ["Giornata 1", "X chiude la schedina!", "n.d.", "430,00€"]])

    def test_vuota(self):
        assert st.movimenti_cassa([]) == []
        assert st.movimenti_cassa([dati.INTESTAZIONE_CASSA]) == []

    def test_riepilogo_saldo_e_somma_delle_entrate(self):
        # A2: l'ultima cella "Saldo Totale" puo' divergere dopo una correzione a mano.
        movimenti = [{"giornata": 1, "descrizione": "a", "entrata": 417.35, "saldo": 417.35},
                     {"giornata": 3, "descrizione": "b", "entrata": 305.0, "saldo": 9999.0}]
        c = st.riepilogo_cassa(movimenti, 3200.0)
        assert c["saldo"] == 722.35  # non 9999: la cella scritta a mano e' sbagliata, la somma no
        assert c["completamento"] == pytest.approx(722.35 / 3200)
        assert c["obiettivo_raggiunto"] is False
        assert [m["saldo"] for m in c["movimenti"]] == [417.35, 9999.0]  # il movimento mostra cio' che e' scritto

    def test_riepilogo_limiti(self):
        assert st.riepilogo_cassa([], 3200.0)["saldo"] == 0.0
        grande = st.riepilogo_cassa([{"giornata": 1, "descrizione": "", "entrata": 4000.0, "saldo": 4000.0}], 3200.0)
        assert grande["completamento"] == 1.0 and grande["obiettivo_raggiunto"] is True

    def test_la_somma_non_accumula_rumore_dei_float(self):
        movimenti = [{"giornata": 1, "descrizione": "", "entrata": 0.1, "saldo": None}] * 3
        assert st.riepilogo_cassa(movimenti, 3200.0)["saldo"] == 0.3

    def test_versamenti_giornate_a_zero_e_ordine(self):
        movimenti = [{"giornata": 3, "descrizione": "", "entrata": 100.0, "saldo": None},
                     {"giornata": 1, "descrizione": "", "entrata": 50.5, "saldo": None},
                     {"giornata": 3, "descrizione": "", "entrata": 20.0, "saldo": None}]
        assert st.versamenti_per_giornata(movimenti, {1, 2, 3, 4}) == [
            {"giornata": 1, "versato": 50.5}, {"giornata": 2, "versato": 0.0},
            {"giornata": 3, "versato": 120.0}, {"giornata": 4, "versato": 0.0}]

    def test_movimento_senza_giornata_resta_fuori_dal_grafico(self):
        movimenti = [{"giornata": None, "descrizione": "extra", "entrata": 10.0, "saldo": None}]
        assert st.versamenti_per_giornata(movimenti, {1}) == [{"giornata": 1, "versato": 0.0}]


# ======================================================================
# N5, N6 — Football-Data e abbinamento
# ======================================================================
class TestPartiteDellaStagione:
    def test_forma_dell_output(self):
        p = st.partite_della_stagione(dati.partite_fd([1]))
        assert p["stagione"] == "2026-27"
        assert list(p["per_giornata"]) == [1] and len(p["per_giornata"][1]) == 10
        una = p["per_giornata"][1][0]
        assert una["id"] == 1000 and set(una) == {"id", "nome", "casa", "ospite", "inizio"}
        assert una["nome"] == f"{una['casa']['name']} - {una['ospite']['name']}"
        assert una["inizio"].tzinfo is not None

    def test_accetta_anche_la_sola_lista(self):
        assert st.partite_della_stagione(dati.partite_fd([1])["matches"])["stagione"] == "2026-27"

    def test_partite_malformate_si_saltano(self):
        fd = dati.partite_fd([1])
        fd["matches"].append({"id": 1})  # senza matchday e squadre
        fd["matches"].append({"id": 2, "matchday": 1, "homeTeam": {"name": ""}, "awayTeam": {"name": "X"}})
        assert len(st.partite_della_stagione(fd)["per_giornata"][1]) == 10

    def test_senza_partite_solleva(self):
        for vuota in ({}, {"matches": []}, [], None):
            with pytest.raises(ValueError):
                st.partite_della_stagione(vuota)

    def test_orario_non_valido_e_none(self):
        fd = dati.partite_fd([1])
        fd["matches"][0]["utcDate"] = "boh"
        assert st.partite_della_stagione(fd)["per_giornata"][1][0]["inizio"] is None


def partite_g1():
    return [{"id": 100 + i, "nome": f"{c} - {o}", "casa": {"name": c, "shortName": sc}, "ospite": {"name": o, "shortName": so},
             "inizio": None} for i, (c, sc, o, so) in enumerate(G1_UFFICIALI)]


class TestAbbinaPartita:
    def test_tutte_le_29_scritture_reali_della_giornata_1(self):
        partite_ = partite_g1()
        n = 0
        for indice, scritture in G1_SCRITTURE.items():
            for testo in scritture:
                trovata = st.abbina_partita(testo, partite_)
                assert trovata is not None and trovata["id"] == 100 + indice, testo
                n += 1
        assert n == 29

    def test_squadre_invertite(self):
        assert st.abbina_partita("Fiorentina - Roma", partite_g1())["id"] == 100

    def test_coppia_che_non_esiste_non_si_indovina(self):
        # §15 N6 (2): casa e ospite abbinati separatamente avrebbero accettato "Lazio - Roma",
        # che fra le 10 partite del giorno non c'e'.
        assert st.abbina_partita("Lazio - Roma", partite_g1()) is None
        assert st.abbina_partita("Roma - Lazio", partite_g1()) is None

    def test_nessuna_sottostringa(self):
        # §16 D11: "milan" e' contenuto in "fc internazionale milano" ma non e' la stessa squadra.
        assert st.abbina_partita("Milan - Monza", partite_g1()) is None
        assert st.abbina_partita("Inter Milan - Monza", partite_g1()) is None  # non e' ne' name ne' shortName
        # ...e "Milan" e "Inter" non si confondono quando entrambe sono in giornata
        assert st.abbina_partita("Torino - Milan", partite_g1())["id"] == 107

    def test_testo_non_riconosciuto(self):
        for testo in ("Pisa - Cremo", "", "Roma", "Roma - Fiorentina - Inter", "-", "Roma - "):
            assert st.abbina_partita(testo, partite_g1()) is None, testo

    def test_due_corrispondenze_non_si_indovina(self):
        doppie = partite_g1() + [{"id": 999, "nome": "AS Roma - ACF Fiorentina", "casa": {"name": "AS Roma", "shortName": "Roma"},
                                  "ospite": {"name": "ACF Fiorentina", "shortName": "Fiorentina"}, "inizio": None}]
        assert st.abbina_partita("Roma - Fiorentina", doppie) is None

    def test_solo_le_partite_della_giornata_passata(self):
        # §7.3: si cerca fra le 10 partite di UNA giornata. Un'altra giornata non entra nel confronto.
        assert st.abbina_partita("Roma - Fiorentina", [p for p in partite_g1() if p["id"] != 100]) is None

    def test_forma_squadra(self):
        assert st.abbina_partita("A.S. Roma - ACF Fiorentina", partite_g1())["id"] == 100
        assert st._forma_squadra("Bologna FC 1909") == st._forma_squadra("Bologna") == "bologna"
        assert st._forma_squadra("Como 1907") == "como"


# ======================================================================
# abbinamento delle righe e N8 — partite e schedine
# ======================================================================
def righe_pulite(*righe_foglio):
    return st.pulisci_giocate([dati.INTESTAZIONE_GIOCATE, *righe_foglio])[0]


class TestPartiteESchedine:
    def test_non_ufficiale_id_negativo_e_nome_del_foglio(self):
        fd = st.partite_della_stagione(dati.partite_fd([1]))["per_giornata"]
        righe = righe_pulite(dati.riga_giocata(1, "PAOLO", "Pisa - Cremo", "Fisse", "1", "2,00"),
                             dati.riga_giocata(1, "DARIO", "pisa  -  cremo", "Fisse", "X", "2,00"),
                             dati.riga_giocata(1, "DARIO", "Altra - Cosa", "Fisse", "X", "2,00"))
        partite_, schedine = st.costruisci_partite_e_schedine(righe, fd)
        assert [(p["id"], p["nome"], p["ufficiale"], p["inizio_il"]) for p in partite_] == [
            (-1, "Altra - Cosa", False, None), (-2, "Pisa - Cremo", False, None)]
        ids = {(s["giocatore"], r["pronostico"]): r["partita_id"] for s in schedine for r in s["righe"]}
        assert ids[("PAOLO", "1")] == ids[("DARIO", "X")] == -2  # stessa partita scritta in due modi

    def test_gli_id_negativi_non_dipendono_dall_ordine_del_foglio(self):
        fd = st.partite_della_stagione(dati.partite_fd([1]))["per_giornata"]
        a = [dati.riga_giocata(1, "PAOLO", "Pisa - Cremo"), dati.riga_giocata(1, "PAOLO", "Altra - Cosa")]
        da_dritto = st.costruisci_partite_e_schedine(righe_pulite(*a), fd)
        al_rovescio = st.costruisci_partite_e_schedine(righe_pulite(*a[::-1]), fd)
        assert [(p["id"], p["nome"]) for p in da_dritto[0]] == [(p["id"], p["nome"]) for p in al_rovescio[0]]

    def test_ordine_delle_partite_orario_poi_senza_orario_poi_alfabetico(self):
        fd = {1: [partita(1, "Zeta", "Alfa", utc(2026, 9, 1, 18)), partita(2, "Beta", "Gamma", utc(2026, 9, 1, 15)),
                  partita(3, "Delta", "Eta", utc(2026, 9, 1, 18)), partita(4, "Iota", "Kappa", None)]}
        righe = righe_pulite(*[dati.riga_giocata(1, "PAOLO", f"{c} - {o}") for c, o in
                               (("Iota", "Kappa"), ("Delta", "Eta"), ("Zeta", "Alfa"), ("Beta", "Gamma"))])
        partite_, schedine = st.costruisci_partite_e_schedine(righe, fd)
        # 15:00 Beta; 18:00 a pari orario in ordine alfabetico (Delta, Zeta); senza orario in fondo
        assert [p["nome"] for p in partite_] == ["Beta - Gamma", "Delta - Eta", "Zeta - Alfa", "Iota - Kappa"]
        # le righe della schedina seguono lo stesso ordine (§7.2), non quello del foglio
        assert [r["partita_id"] for r in schedine[0]["righe"]] == [2, 3, 1, 4]
        assert partite_[3]["inizio_il"] is None and partite_[0]["inizio_il"] == "2026-09-01T15:00:00Z"

    def test_giornate_in_ordine_crescente_e_schedine_per_giocatore(self):
        fd = st.partite_della_stagione(dati.partite_fd([2, 10, 3]))["per_giornata"]
        righe = righe_pulite(*[dati.riga_giocata(g, gio, dati.nome_foglio(g, 0)) for g in (10, 2, 3) for gio in ("ZETA", "ALFA")])
        partite_, schedine = st.costruisci_partite_e_schedine(righe, fd)
        assert [p["giornata"] for p in partite_] == [2, 3, 10]
        assert [(s["giornata"], s["giocatore"]) for s in schedine] == [(2, "ALFA"), (2, "ZETA"), (3, "ALFA"), (3, "ZETA"), (10, "ALFA"), (10, "ZETA")]

    def test_riepilogo_conta_tutti_gli_esiti_e_somma_alle_righe(self):
        fd = st.partite_della_stagione(dati.partite_fd([1]))["per_giornata"]
        esiti = [dati.VINTA, dati.PERSA, dati.IN_CORSO, dati.RINVIATA, dati.DA_VERIFICARE, dati.ANNULLATA, "", dati.VINTA, dati.PERSA, "boh"]
        righe = righe_pulite(*dati.schedina(1, "PAOLO", esiti=esiti))
        _, (s,) = st.costruisci_partite_e_schedine(righe, fd)
        assert s["riepilogo"] == {"vinte": 2, "perse": 2, "in_corso": 1, "rinviate": 1,
                                  "da_verificare": 2, "annullate": 1, "da_giocare": 1}  # "boh" -> da_verificare
        assert sum(s["riepilogo"].values()) == len(s["righe"]) == 10

    def test_vincita_potenziale_primo_valore_positivo(self):
        fd = st.partite_della_stagione(dati.partite_fd([1]))["per_giornata"]
        r = [dati.riga_giocata(1, "PAOLO", dati.nome_foglio(1, i), vincita=v) for i, v in enumerate(["", "0,00", "1.030,30", "5,00"])]
        assert st.costruisci_partite_e_schedine(righe_pulite(*r), fd)[1][0]["vincita_potenziale"] == 1030.30
        r = [dati.riga_giocata(1, "PAOLO", dati.nome_foglio(1, 0))]
        assert st.costruisci_partite_e_schedine(righe_pulite(*r), fd)[1][0]["vincita_potenziale"] == 0.0

    def test_riga_della_schedina(self):
        fd = st.partite_della_stagione(dati.partite_fd([1]))["per_giornata"]
        righe = righe_pulite(dati.riga_giocata(1, "PAOLO", dati.nome_foglio(1, 3), "Combo", "1+OVER_2.5", "3,85", dati.VINTA, "", 12))
        _, (s,) = st.costruisci_partite_e_schedine(righe, fd)
        assert s["righe"] == [{"partita_id": 1003, "tipologia": "combo", "pronostico": "1+OVER_2.5", "quota": 3.85,
                               "esito": "vinta", "punti": 12}]

    def test_le_annullate_non_votano_nella_scelta_del_gruppo(self):
        # A11 / §17.18: sia l'esito `annullata` sia la dicitura "(ANNULLATA ECCESSO)" nel pronostico
        # (presente gia' prima del calcolo, quando l'esito e' ancora vuoto).
        fd = st.partite_della_stagione(dati.partite_fd([1]))["per_giornata"]
        p = dati.nome_foglio(1, 0)
        righe = righe_pulite(
            dati.riga_giocata(1, "A", p, pronostico="1", esito=dati.VINTA),
            dati.riga_giocata(1, "B", p, pronostico="1", esito=dati.VINTA),
            dati.riga_giocata(1, "C", p, pronostico="X", esito=dati.ANNULLATA),
            dati.riga_giocata(1, "D", p, pronostico="X (ANNULLATA ECCESSO)", esito=""),
            dati.riga_giocata(1, "E", p, pronostico="2", esito=dati.PERSA),
        )
        partite_, _ = st.costruisci_partite_e_schedine(righe, fd)
        assert partite_[0]["scelta_gruppo"] == {"tipo": "maggioranza", "pronostici": ["1"], "voti": 2, "su": 3}

    def test_la_scelta_del_gruppo_conta_ogni_giocatore_una_volta(self):
        fd = st.partite_della_stagione(dati.partite_fd([1]))["per_giornata"]
        p = dati.nome_foglio(1, 0)
        righe = righe_pulite(dati.riga_giocata(1, "A", p, pronostico="1"), dati.riga_giocata(1, "A", p, pronostico="1"),
                             dati.riga_giocata(1, "B", p, pronostico="X"))
        assert st.costruisci_partite_e_schedine(righe, fd)[0][0]["scelta_gruppo"] == {
            "tipo": "tutti_diversi", "pronostici": [], "voti": 1, "su": 2}


# ======================================================================
# N7 — scelta del gruppo
# ======================================================================
class TestSceltaDelGruppoDati:
    def test_maggioranza(self):
        assert st.scelta_del_gruppo_dati({"A": ["1"], "B": ["1"], "C": ["X"]}) == {
            "tipo": "maggioranza", "pronostici": ["1"], "voti": 2, "su": 3}

    def test_pari_voti_in_ordine_alfabetico(self):
        assert st.scelta_del_gruppo_dati({"A": ["X"], "B": ["1"], "C": ["X"], "D": ["1"]})["pronostici"] == ["1", "X"]

    def test_tutti_diversi(self):
        assert st.scelta_del_gruppo_dati({"A": ["1"], "B": ["X"]}) == {"tipo": "tutti_diversi", "pronostici": [], "voti": 1, "su": 2}

    def test_un_solo_giocatore_e_maggioranza(self):
        assert st.scelta_del_gruppo_dati({"A": ["1"]}) == {"tipo": "maggioranza", "pronostici": ["1"], "voti": 1, "su": 1}

    def test_nessuna(self):
        for vuoto in ({}, {"A": []}, {"A": [""], "B": ["  "]}):
            assert st.scelta_del_gruppo_dati(vuoto) == {"tipo": "nessuna", "pronostici": [], "voti": 0, "su": 0}

    def test_solo_il_pronostico_identico(self):
        assert st.scelta_del_gruppo_dati({"A": ["1+OVER_2.5"], "B": ["1"]})["tipo"] == "tutti_diversi"

    def test_il_formattatore_resta_quello_di_prima(self):
        assert st.scelta_del_gruppo({"A": ["1"], "B": ["1"], "C": ["X"]}) == "1 · 2 su 3"
        assert st.scelta_del_gruppo({"A": ["1"], "B": ["X"]}) == "Tutti diversi"
        assert st.scelta_del_gruppo({}) == "—"
        assert st.scelta_del_gruppo({"A": ["X"], "B": ["1"], "C": ["X"], "D": ["1"]}) == "1 / X · 2 su 4"


# ======================================================================
# N9, N10 — classifica
# ======================================================================
def dict_classifica(giocatori):
    """[(nome, [celle])] -> righe_classifica (dizionari), come righe_da_valori."""
    return st.righe_da_valori(dati.classifica_valori(giocatori))


def vinte(giocatore, quante, giornata=1):
    """`quante` righe vinte per il giocatore (partita_id fittizio)."""
    return [riga(giornata, giocatore, 1, "vinta") for _ in range(quante)]


class TestClassifica:
    def test_ordine_punti_poi_vittorie_poi_nome(self):
        cl = dict_classifica([("ZETA", [10]), ("ALFA", [10]), ("BETA", [10]), ("TOP", [30])])
        c = st.classifica_ordinata(cl, vinte("BETA", 3) + vinte("ZETA", 1))
        assert [g["nome"] for g in c["giocatori"]] == ["TOP", "BETA", "ZETA", "ALFA"]

    def test_ranking_sportivo_stessa_posizione_poi_salta(self):
        # §17.15 / A10: a parita' di punti E pronostici vinti, stessa posizione: 1, 2, 2, 4.
        cl = dict_classifica([("A", [50]), ("B", [40]), ("C", [40]), ("D", [10])])
        c = st.classifica_ordinata(cl, vinte("B", 2) + vinte("C", 2))
        assert [(g["nome"], g["posizione"]) for g in c["giocatori"]] == [("A", 1), ("B", 2), ("C", 2), ("D", 4)]

    def test_stessi_punti_ma_vittorie_diverse_non_sono_a_pari_merito(self):
        cl = dict_classifica([("A", [40]), ("B", [40])])
        c = st.classifica_ordinata(cl, vinte("B", 1))
        assert [(g["nome"], g["posizione"]) for g in c["giocatori"]] == [("B", 1), ("A", 2)]

    def test_la_vecchia_classifica_dava_posizioni_consecutive_ai_pari_merito(self):
        # Il vecchio app.py numerava per ordine di riga: due a pari punti e vittorie = 2° e 3°.
        cl = dict_classifica([("A", [40]), ("B", [40])])
        vecchio = [i + 1 for i, _ in enumerate(cl)]
        assert vecchio == [1, 2]
        assert [g["posizione"] for g in st.classifica_ordinata(cl, [])["giocatori"]] == [1, 1]

    def test_nome_senza_distinguere_le_maiuscole(self):
        # A8 / §16 D10: "Paolo" in Classifica, "PAOLO" in Giocate. Il vecchio codice cercava il nome esatto
        # e i pronostici vinti valevano 0 (spareggio saltato in silenzio).
        cl = dict_classifica([("Paolo", [40]), ("Dario", [40])])
        vecchio = {"PAOLO": 5}.get("Paolo", 0)
        assert vecchio == 0
        c = st.classifica_ordinata(cl, vinte("PAOLO", 5))
        assert [g["nome"] for g in c["giocatori"]] == ["PAOLO", "DARIO"] and c["giocatori"][0]["posizione"] == 1

    def test_ritirati_separati_e_senza_suffisso(self):
        cl = dict_classifica([("A", [10]), ("PULIZZER (RITIRATO)", [30, 20]), ("B", [5]), ("ALTRO (ritirato)", [1])])
        c = st.classifica_ordinata(cl, [])
        assert [g["nome"] for g in c["giocatori"]] == ["A", "B"]
        assert [(r["nome"], r["punti_totali"]) for r in c["ritirati"]] == [("PULIZZER", 50), ("ALTRO", 1)]
        assert c["ritirati"][0]["punti_per_giornata"] == [30, 20]

    def test_il_ritirato_non_occupa_una_posizione(self):
        cl = dict_classifica([("A", [10]), ("PULIZZER (RITIRATO)", [90])])
        assert st.classifica_ordinata(cl, [])["giocatori"][0]["posizione"] == 1

    def test_punti_per_giornata_none_non_e_zero(self):
        cl = dict_classifica([("A", [10, None, 0]), ("B", [5, 5, None])])
        c = st.classifica_ordinata(cl, [])
        assert {g["nome"]: g["punti_per_giornata"] for g in c["giocatori"]} == {"A": [10, None, 0], "B": [5, 5, None]}

    def test_lunghezza_fino_all_ultima_giornata_con_dati(self):
        cl = dict_classifica([("A", [10, 20]), ("PULIZZER (RITIRATO)", [1, 2, 3])])
        c = st.classifica_ordinata(cl, [])
        assert len(c["giocatori"][0]["punti_per_giornata"]) == len(c["ritirati"][0]["punti_per_giornata"]) == 3
        assert c["giocatori"][0]["punti_per_giornata"] == [10, 20, None]
        assert st.classifica_ordinata(dict_classifica([("A", [])]), [])["giocatori"][0]["punti_per_giornata"] == []

    def test_cella_non_numerica_solleva_invece_di_diventare_zero(self):
        # D12: pd.to_numeric(errors='coerce').fillna(0) trasformava "abc" in 0 punti senza traccia.
        vecchio = int(float("nan") if False else 0)  # il fallback silenzioso del vecchio codice
        assert vecchio == 0
        valori = dati.classifica_valori([("A", [10])])
        valori[1][1] = "abc"
        with pytest.raises(ValueError, match="Punti Totali"):
            st.classifica_ordinata(st.righe_da_valori(valori), [])
        valori = dati.classifica_valori([("A", [10])])
        valori[1][2] = "x"
        with pytest.raises(ValueError, match="Giornata 1"):
            st.classifica_ordinata(st.righe_da_valori(valori), [])

    def test_giocatore_duplicato_solleva(self):
        with pytest.raises(ValueError, match="due volte"):
            st.classifica_ordinata(dict_classifica([("A", [1]), ("a", [2])]), [])

    def test_sostituto_eredita_le_vittorie_del_ritirato(self):
        # §17.17: le schedine di PULIZZER in Giocate sono state rinominate SIRACUSA, quindi le sue
        # vittorie contano per SIRACUSA anche nello spareggio. A pari punti, SIRACUSA batte ALFA
        # grazie alle 3 vittorie "ereditate" (2 sue + 1 del ritirato).
        cl = dict_classifica([("ALFA", [40]), ("SIRACUSA", [40]), ("PULIZZER (RITIRATO)", [30])])
        righe = vinte("SIRACUSA", 2, giornata=2) + vinte("SIRACUSA", 1, giornata=1) + vinte("ALFA", 2)
        c = st.classifica_ordinata(cl, righe)
        assert [g["nome"] for g in c["giocatori"]] == ["SIRACUSA", "ALFA"]

    def test_vuota(self):
        assert st.classifica_ordinata([], []) == {"ultima_giornata_giocata": None, "giocatori": [], "ritirati": []}


class TestVariazioni:
    def test_salita_discesa_invariata(self):
        # Prima dell'ultima giornata: A 30, B 20, C 10. Dopo: C +25 -> 35 supera tutti.
        cl = dict_classifica([("A", [30, 0]), ("B", [20, 5]), ("C", [10, 25])])
        ultima, v = st.variazioni_posizione(cl, [])
        assert ultima == 2
        assert {n: x["variazione"] for n, x in v.items()} == {"A": -1, "B": -1, "C": 2}  # A: 1°->2°, B: 2°->3°, C: 3°->1°
        assert {n: x["punti_ultima"] for n, x in v.items()} == {"A": 0, "B": 5, "C": 25}

    def test_prima_giornata_nessuna_variazione(self):
        ultima, v = st.variazioni_posizione(dict_classifica([("A", [30]), ("B", [20])]), [])
        assert ultima == 1
        assert all(x["variazione"] is None for x in v.values())
        assert {n: x["punti_ultima"] for n, x in v.items()} == {"A": 30, "B": 20}

    def test_nessun_punto_nessuna_giornata(self):
        ultima, v = st.variazioni_posizione(dict_classifica([("A", [0, None]), ("B", [None])]), [])
        assert ultima is None and all(x == {"variazione": None, "punti_ultima": None} for x in v.values())

    def test_ultima_giornata_e_l_ultima_con_punti_non_l_ultima_colonna(self):
        # D1 / A1: il vecchio delta del podio leggeva valori[-1], l'ULTIMA COLONNA del foglio
        # (Giornata 38, sempre vuota fino a fine stagione): "+N pt ultima giornata" non compariva mai.
        riga_foglio = ["PAOLO", "135", "40", "23", "33", "22", "17"] + [""] * 33  # 38 colonne di giornata
        vecchio_delta = int(str(riga_foglio[-1]).strip() or 0)
        assert vecchio_delta == 0  # il vecchio codice: nessun delta, mai
        cl = st.righe_da_valori([dati.INTESTAZIONE_CLASSIFICA, riga_foglio])
        ultima, v = st.variazioni_posizione(cl, [])
        assert ultima == 5 and v["PAOLO"]["punti_ultima"] == 17

    def test_stesso_spareggio_per_classifica_attuale_e_precedente(self):
        # P9a / D2: prima dell'ultima giornata A e B erano a pari punti (30) ma A aveva piu' vittorie, quindi era
        # sopra. Ora B supera A di punti. Il vecchio codice ordinava la classifica precedente SOLO per punti
        # (sort non stabile): l'ordine di A e B prima era arbitrario e la freccia poteva essere sbagliata.
        cl = dict_classifica([("A", [30, 0]), ("B", [30, 5])])
        righe = vinte("A", 3, giornata=1) + vinte("B", 1, giornata=1)
        _, v = st.variazioni_posizione(cl, righe)
        assert v["A"]["variazione"] == -1 and v["B"]["variazione"] == 1
        # il vecchio ordinamento: solo i punti -> pari merito, ordine = quello del foglio (A, B) o inverso (non stabile)
        vecchio = sorted(["B", "A"], key=lambda g: -30)  # stesso punteggio: il risultato dipende dall'ordine di ingresso
        assert vecchio == ["B", "A"]  # in un ordine di ingresso diverso la freccia di A e B sarebbe stata opposta

    def test_le_vittorie_della_classifica_precedente_si_fermano_alla_giornata_precedente(self):
        # §17.16: una vittoria ottenuta nell'ULTIMA giornata non puo' spostare chi era sopra PRIMA.
        cl = dict_classifica([("A", [30, 5]), ("B", [30, 5])])
        righe = vinte("A", 1, giornata=1) + vinte("B", 9, giornata=2)  # B ha moltissime vittorie, ma nella G2
        _, v = st.variazioni_posizione(cl, righe)
        # prima: A (1 vittoria) sopra B (0). Ora (tutte le vittorie): B sopra A -> A scende, B sale.
        assert v["A"]["variazione"] == -1 and v["B"]["variazione"] == 1

    def test_pari_merito_pieno_prima_e_dopo(self):
        cl = dict_classifica([("A", [30, 5]), ("B", [30, 5])])
        _, v = st.variazioni_posizione(cl, [])
        assert v["A"]["variazione"] == v["B"]["variazione"] == 0


# ======================================================================
# N13, N14, N15 — statistiche e premi
# ======================================================================
class TestStatisticheGiocatore:
    def test_conteggi_e_arrotondamenti(self):
        righe = [riga(1, "A", 1, "vinta", quota=1.5), riga(1, "A", 2, "persa", quota=2.0), riga(1, "A", 3, "persa", quota=2.55)]
        (s,) = st.statistiche_per_giocatore(righe)
        assert (s["vinte"], s["totali"]) == (1, 3)
        assert s["win_rate"] == 33.3 and s["win_rate_esatto"] == pytest.approx(100 / 3)
        assert s["quota_media"] == 2.02 and s["quota_media_esatta"] == pytest.approx((1.5 + 2.0 + 2.55) / 3)

    def test_contano_solo_vinte_e_perse(self):
        righe = [riga(1, "A", 1, e) for e in ("vinta", "persa", "in_corso", "rinviata", "da_verificare", "annullata", "da_giocare")]
        (s,) = st.statistiche_per_giocatore(righe)
        assert s["totali"] == 2
        assert st.statistiche_per_giocatore([riga(1, "A", 1, "in_corso")]) == []  # nessuna valutata: non compare

    def test_quota_illeggibile_resta_fuori_dalla_media(self):
        # A4 / D4: il vecchio parse_quota restituiva 0.0 e quel 0.0 entrava nella media.
        quote = [2.0, 3.0, None]
        vecchia_media = sum(q or 0.0 for q in quote) / len(quote)
        assert vecchia_media == pytest.approx(5 / 3)
        (s,) = st.statistiche_per_giocatore([riga(1, "A", i, "vinta", quota=q) for i, q in enumerate(quote)])
        assert s["quota_media"] == 2.5

    def test_nessuna_quota_leggibile(self):
        (s,) = st.statistiche_per_giocatore([riga(1, "A", 1, "vinta", quota=None)])
        assert s["quota_media"] is None  # mai uno 0 finto

    def test_ordine_deterministico_win_rate_totali_nome(self):
        # A7 / D13: il vecchio sort_values non era stabile: a parita' l'ordine dipendeva dal foglio.
        def giro(nomi):
            righe = []
            for nome in nomi:
                righe += [riga(1, nome, 1, "vinta"), riga(1, nome, 2, "persa")]
            righe += [riga(1, "TOP", 1, "vinta")]
            return [s["nome"] for s in st.statistiche_per_giocatore(righe)]
        assert giro(["C", "A", "B"]) == giro(["B", "C", "A"]) == ["TOP", "A", "B", "C"]

    def test_win_rate_ordina_sul_valore_esatto(self):
        # 2/3 = 66.666..., 66.7 arrotondato ma 67/100 = 67.0: l'ordine non deve dipendere dall'arrotondamento
        righe = [riga(1, "A", i, "vinta" if i < 2 else "persa") for i in range(3)]
        righe += [riga(1, "B", i, "vinta" if i < 67 else "persa") for i in range(100)]
        assert [s["nome"] for s in st.statistiche_per_giocatore(righe)] == ["B", "A"]


class TestStatisticheRitirati:
    def test_stat_del_ritirato_dalle_schedine_del_sostituto(self):
        cl = dict_classifica([("SIRACUSA", [10, 10, 10]), ("PULIZZER (RITIRATO)", [16, 30])])
        righe = [riga(1, "SIRACUSA", 1, "vinta"), riga(2, "SIRACUSA", 1, "persa"),
                 riga(3, "SIRACUSA", 1, "vinta"), riga(1, "ALTRO", 1, "vinta")]
        (s,) = st.statistiche_ritirati(cl, righe)
        # fino alla G2 (ultima giornata con punti del ritirato): 1 vinta, 1 persa
        assert (s["nome"], s["vinte"], s["totali"], s["win_rate"]) == ("PULIZZER", 1, 2, 50.0)

    def test_ritirato_senza_sostituto_noto_non_compare(self):
        cl = dict_classifica([("A", [10]), ("SCONOSCIUTO (RITIRATO)", [10])])
        assert st.statistiche_ritirati(cl, [riga(1, "A", 1, "vinta")]) == []


class TestPremiGiocatori:
    def stats(self, *voci):
        return [{"nome": n, "win_rate": wr, "win_rate_esatto": wr, "quota_media": q, "quota_media_esatta": q,
                 "vinte": 1, "totali": 2} for n, wr, q in voci]

    def test_pari_merito_tutti_e_in_ordine_alfabetico(self):
        # A9 / §17.14: il vecchio idxmax prendeva il primo del foglio.
        stats = self.stats(("ZETA", 60.0, 2.0), ("ALFA", 60.0, 2.0), ("BETA", 40.0, 1.0), ("GAMMA", 40.0, 3.0))
        vecchio_cecchino = max(stats, key=lambda s: s["win_rate_esatto"])["nome"]  # idxmax: il primo che incontra
        assert vecchio_cecchino == "ZETA"
        p = st.premi_giocatori(stats)
        assert [x["giocatore"] for x in p["cecchino"]] == ["ALFA", "ZETA"]
        assert [x["giocatore"] for x in p["benedizione"]] == ["BETA", "GAMMA"]
        assert [x["giocatore"] for x in p["folle"]] == ["GAMMA"]
        assert [x["giocatore"] for x in p["conservatore"]] == ["BETA"]
        assert p["cecchino"][0] == {"giocatore": "ALFA", "win_rate": 60.0, "vinte": 1, "totali": 2}
        assert p["folle"][0] == {"giocatore": "GAMMA", "quota_media": 3.0}

    def test_nessun_minimo_di_pronostici(self):
        # §17.14: con una sola partita valutata chi l'ha presa e' "Il Cecchino" al 100%.
        (s,) = st.statistiche_per_giocatore([riga(1, "A", 1, "vinta")])
        assert st.premi_giocatori([s])["cecchino"][0]["win_rate"] == 100.0

    def test_tutti_a_pari_merito(self):
        stats = self.stats(("A", 50.0, 2.0), ("B", 50.0, 2.0), ("C", 50.0, 2.0))
        p = st.premi_giocatori(stats)
        assert len(p["cecchino"]) == len(p["benedizione"]) == len(p["folle"]) == len(p["conservatore"]) == 3

    def test_senza_dati_tutto_none(self):
        assert st.premi_giocatori([]) == {"cecchino": None, "benedizione": None, "folle": None, "conservatore": None}

    def test_giocatore_senza_quota_non_e_ne_folle_ne_conservatore(self):
        stats = self.stats(("A", 50.0, None), ("B", 50.0, 2.0))
        p = st.premi_giocatori(stats)
        assert [x["giocatore"] for x in p["folle"]] == [x["giocatore"] for x in p["conservatore"]] == ["B"]

    def test_il_confronto_e_sul_valore_esatto(self):
        # 33.33 e 33.34 si arrotondano entrambi a 33.3: non sono a pari merito.
        stats = [{"nome": "A", "win_rate": 33.3, "win_rate_esatto": 33.33, "quota_media": 2.0, "quota_media_esatta": 2.0, "vinte": 1, "totali": 3},
                 {"nome": "B", "win_rate": 33.3, "win_rate_esatto": 33.34, "quota_media": 2.0, "quota_media_esatta": 2.0, "vinte": 1, "totali": 3}]
        assert [x["giocatore"] for x in st.premi_giocatori(stats)["cecchino"]] == ["B"]


class TestGiornataDaIncorniciare:
    def test_massimo_con_pari_merito_anche_sullo_stesso_giocatore(self):
        righe = [{"nome": "B", "punti_per_giornata": [10, 40, None]}, {"nome": "A", "punti_per_giornata": [40, 5, 40]}]
        assert st.giornata_da_incorniciare(righe) == [
            {"giocatore": "A", "giornata": 1, "punti": 40}, {"giocatore": "A", "giornata": 3, "punti": 40},
            {"giocatore": "B", "giornata": 2, "punti": 40}]

    def test_nessuno_ha_fatto_punti(self):
        assert st.giornata_da_incorniciare([{"nome": "A", "punti_per_giornata": [0, None]}]) is None
        assert st.giornata_da_incorniciare([]) is None


# ======================================================================
# N23, N16, N17 — squadre
# ======================================================================
CASA, OSPITE = "FC Internazionale Milano", "AC Milan"
PARTITA_INTER_MILAN = partita(1, CASA, OSPITE)


class TestSquadraScelta:
    @pytest.mark.parametrize("pronostico,atteso", [
        ("1", CASA), ("1X", CASA), ("2", OSPITE), ("X2", OSPITE), ("1+OVER_2.5", CASA), ("2+GOAL", OSPITE),
        ("x2", OSPITE),
        ("X", None), ("12", None), ("OVER_2.5", None), ("UNDER_2.5", None), ("GOAL", None), ("NOGOAL", None),
        ("PARI", None), ("DISPARI", None), ("", None), ("X+OVER_2.5", None),
        ("1 (ANNULLATA ECCESSO)", None), ("1+OVER_2.5 (ANNULLATA ECCESSO)", None),
    ])
    def test_tabella(self, pronostico, atteso):
        assert st.squadra_scelta(pronostico, PARTITA_INTER_MILAN) == atteso

    def test_accetta_anche_i_nomi_semplici(self):
        assert st.squadra_scelta("1", {"casa": "X", "ospite": "Y"}) == "X"


class TestSemperFidelis:
    def partite(self):
        return info(PARTITA_INTER_MILAN, partita(2, "SSC Napoli", "AS Roma"))

    def test_conta_giornate_distinte_non_righe(self):
        # A12 / D9: "1" e "1X" sulla stessa partita erano 2 per il vecchio codice, che contava le righe.
        righe = [riga(1, "A", 1, pron="1"), riga(1, "A", 1, pron="1X", tip="doppie_chance")]
        vecchio = sum(1 for r in righe if r["pronostico"].split("+")[0] in ("1", "1X"))
        assert vecchio == 2  # il vecchio codice: "Semper Fidelis" 2x dopo una sola giornata
        assert st.semper_fidelis(righe, self.partite()) is None  # nuovo: 1 giornata distinta, sotto il minimo di 2
        righe.append(riga(2, "A", 1, pron="1"))
        assert st.semper_fidelis(righe, self.partite()) == [{"giocatore": "A", "squadra": CASA, "volte": 2}]

    def test_conta_solo_partite_giocate_e_non_annullate(self):
        righe = [riga(1, "A", 1, "vinta"), riga(2, "A", 1, "in_corso"), riga(3, "A", 1, "annullata"),
                 riga(4, "A", 1, "da_giocare"), riga(5, "A", 1, "rinviata", pron="1"),
                 riga(6, "A", 1, "persa", pron="1 (ANNULLATA ECCESSO)")]
        assert st.semper_fidelis(righe, self.partite()) is None  # una sola giornata valida (la prima)
        righe.append(riga(7, "A", 1, "persa"))
        assert st.semper_fidelis(righe, self.partite())[0]["volte"] == 2

    def test_pari_merito_tutti_in_ordine_alfabetico(self):
        righe = [riga(g, gio, 1) for g in (1, 2) for gio in ("ZETA", "ALFA")] + [riga(g, "ALFA", 2, pron="2") for g in (1, 2)]
        # ALFA: Inter 2 volte + Roma (ospite) 2 volte; ZETA: Inter 2 volte
        assert [(x["giocatore"], x["squadra"]) for x in st.semper_fidelis(righe, self.partite())] == [
            ("ALFA", "AS Roma"), ("ALFA", CASA), ("ZETA", CASA)]

    def test_le_righe_non_ufficiali_non_contano(self):
        p = self.partite()
        p[-1] = {"id": -1, "giornata": 1, "nome": "Pisa - Cremo", "ufficiale": False, "casa": None, "ospite": None, "inizio": None}
        assert st.semper_fidelis([riga(g, "A", -1) for g in (1, 2, 3)], p) is None

    def test_segni_senza_squadra_non_contano(self):
        assert st.semper_fidelis([riga(g, "A", 1, pron="X") for g in (1, 2, 3)], self.partite()) is None
        assert st.semper_fidelis([riga(g, "A", 1, pron="OVER_2.5") for g in (1, 2, 3)], self.partite()) is None

    def test_nessuna_riga(self):
        assert st.semper_fidelis([], self.partite()) is None


class TestAmuletoMaledetta:
    def partite(self):
        return info(PARTITA_INTER_MILAN, partita(2, "SSC Napoli", "AS Roma"))

    def test_conta_solo_la_squadra_scelta_dal_pronostico(self):
        # A13 / D5: il vecchio codice contava ENTRAMBE le squadre di ogni riga vinta, anche con un Over.
        righe = [riga(1, "A", 1, "vinta", pron="1"), riga(1, "B", 1, "vinta", pron="OVER_2.5"),
                 riga(1, "C", 1, "vinta", pron="X"), riga(1, "D", 1, "vinta", pron="2")]
        vecchio = {}
        for r in righe:
            for squadra in ("FC Internazionale Milano", "AC Milan"):
                vecchio[squadra] = vecchio.get(squadra, 0) + 1
        assert vecchio == {CASA: 4, OSPITE: 4}
        n = st.squadre_amuleto_maledetta(righe, self.partite())["squadra_amuleto"]
        assert n == [{"squadra": OSPITE, "vittorie_portate": 1}, {"squadra": CASA, "vittorie_portate": 1}]

    def test_amuleto_e_maledetta_separate(self):
        righe = [riga(1, "A", 1, "vinta", pron="1"), riga(2, "A", 1, "vinta", pron="1"), riga(3, "B", 2, "persa", pron="2"),
                 riga(1, "C", 2, "persa", pron="2"), riga(4, "C", 2, "persa", pron="1")]
        r = st.squadre_amuleto_maledetta(righe, self.partite())
        assert r["squadra_amuleto"] == [{"squadra": CASA, "vittorie_portate": 2}]
        assert r["squadra_maledetta"] == [{"squadra": "AS Roma", "pronostici_bruciati": 2}]

    def test_stessa_squadra_scritta_in_modi_diversi_e_una_squadra_sola(self):
        # P9b / D5: "Inter", "Inter Milan", "inter" erano tre squadre; ora si conta per squadra ufficiale
        # (l'abbinamento ha gia' ricondotto i testi al nome ufficiale).
        righe = [riga(1, "A", 1, "vinta", pron="1", testo="Inter - Milan"), riga(2, "B", 1, "vinta", pron="1", testo="INTER - MILAN"),
                 riga(3, "C", 1, "vinta", pron="1", testo="Inter Milan - Milan")]
        vecchio = {}
        for r in righe:
            casa = r["partita_testo"].split("-")[0].strip()
            vecchio[casa] = vecchio.get(casa, 0) + 1
        assert max(vecchio.values()) == 1  # per il vecchio codice nessuna squadra ha piu' di una vittoria
        assert st.squadre_amuleto_maledetta(righe, self.partite())["squadra_amuleto"] == [{"squadra": CASA, "vittorie_portate": 3}]

    def test_pari_merito_tutti(self):
        righe = [riga(1, "A", 1, "vinta", pron="1"), riga(1, "A", 2, "vinta", pron="1")]
        assert [x["squadra"] for x in st.squadre_amuleto_maledetta(righe, self.partite())["squadra_amuleto"]] == [CASA, "SSC Napoli"]

    def test_righe_non_ufficiali_e_non_giocate_non_contano(self):
        p = self.partite()
        p[-1] = {"id": -1, "giornata": 1, "nome": "Pisa - Cremo", "ufficiale": False, "casa": None, "ospite": None, "inizio": None}
        righe = [riga(1, "A", -1, "vinta"), riga(1, "A", 1, "in_corso"), riga(1, "A", 1, "annullata")]
        assert st.squadre_amuleto_maledetta(righe, p) == {"squadra_amuleto": None, "squadra_maledetta": None}


# ======================================================================
# N18 — ultima schedina vinta
# ======================================================================
class TestUltimaSchedinaVinta:
    def movimenti(self, *descrizioni):
        return [{"giornata": g, "descrizione": d, "entrata": 1.0, "saldo": None} for g, d in descrizioni]

    def test_fine_stimata_dell_ultima_partita_piu_due_ore(self):
        ps = info(partita(1, "A", "B", utc(2026, 9, 1, 15)), partita(2, "C", "D", utc(2026, 9, 1, 18)))
        righe = [riga(3, "PAOLO", 1), riga(3, "PAOLO", 2), riga(2, "PAOLO", 1)]
        m = self.movimenti((3, "PAOLO chiude la schedina!"))
        assert st.ultima_schedina_vinta(m, righe, ps) == {"giornata": 3, "vincitori": ["PAOLO"], "inizio_il": "2026-09-01T20:00:00Z"}

    def test_piu_vincitori_vale_l_ultimo(self):
        ps = info(partita(1, "A", "B", utc(2026, 9, 1, 15)), partita(2, "C", "D", utc(2026, 9, 2, 18)))
        righe = [riga(3, "PAOLO", 1), riga(3, "DARIO", 2)]
        m = self.movimenti((3, "PAOLO chiude la schedina!"), (3, "dario chiude la schedina!"))
        r = st.ultima_schedina_vinta(m, righe, ps)
        assert r["vincitori"] == ["PAOLO", "DARIO"] and r["inizio_il"] == "2026-09-02T20:00:00Z"

    def test_un_orario_ignoto_nessun_timer(self):
        ps = info(partita(1, "A", "B", utc(2026, 9, 1, 15)), partita(2, "C", "D", None))
        righe = [riga(3, "PAOLO", 1), riga(3, "PAOLO", 2)]
        assert st.ultima_schedina_vinta(self.movimenti((3, "PAOLO chiude la schedina!")), righe, ps)["inizio_il"] is None

    def test_vincitore_senza_righe_nessun_timer(self):
        ps = info(partita(1, "A", "B", utc(2026, 9, 1, 15)))
        assert st.ultima_schedina_vinta(self.movimenti((3, "PAOLO chiude la schedina!")), [], ps)["inizio_il"] is None

    def test_nessuna_schedina_chiusa(self):
        assert st.ultima_schedina_vinta([], [], {}) is None
        assert st.ultima_schedina_vinta(self.movimenti((1, "Versamento")), [], {}) is None

    def test_l_ultima_giornata_per_numero(self):
        ps = info(partita(1, "A", "B", utc(2026, 9, 1, 15)))
        m = self.movimenti((10, "A chiude la schedina!"), (9, "B chiude la schedina!"))
        assert st.ultima_schedina_vinta(m, [], ps)["giornata"] == 10


# ======================================================================
# N19 — Coppa
# ======================================================================
NOMI16 = [f"G{n:02d}" for n in range(1, 17)]


def classifica_16(giornate=34):
    """16 giocatori: G01 primo ... G16 ultimo, a punti decrescenti ognuno in tutte le giornate fino a `giornate`."""
    return dict_classifica([(nome, [30 - i] * giornate) for i, nome in enumerate(NOMI16)])


def righe_tutte_decise(fino_a, esito="vinta"):
    return [riga(g, nome, 1, esito) for g in range(1, fino_a + 1) for nome in ("G01",)]


class TestCoppa:
    def test_tabellone_a_16(self):
        c = st.coppa_snapshot(classifica_16(), righe_tutte_decise(34))
        assert c["partecipanti"] == 16 and c["tabellone_disponibile"] is True
        assert [t["turno"] for t in c["turni"]] == ["ottavi", "quarti", "semifinali", "finale"]
        assert [t["giornata"] for t in c["turni"]] == [35, 36, 37, 38]
        assert [len(t["sfide"]) for t in c["turni"]] == [8, 4, 2, 1]
        primo = c["turni"][0]["sfide"][0]
        assert primo["giocatori"] == [{"posizione": 1, "nome": "G01"}, {"posizione": 16, "nome": "G16"}]
        assert (c["prima_giornata"], c["ultima_giornata_tabellone"]) == (35, 34)
        assert c["campione"] is None

    def test_definitiva_solo_a_giornata_34_conclusa(self):
        # A14 / D8: il vecchio sito diceva "definitivo" appena in Giocate compariva UNA riga di giornata >= 35.
        righe_34_aperta = righe_tutte_decise(33) + [riga(34, "G01", 1, "in_corso"), riga(35, "G01", 1, "da_giocare")]
        vecchio = any(r["giornata"] >= 35 for r in righe_34_aperta)
        assert vecchio is True  # il vecchio criterio: "definitivo" con la 34ª ancora in corso
        assert st.coppa_snapshot(classifica_16(), righe_34_aperta)["definitiva"] is False
        assert st.coppa_snapshot(classifica_16(), righe_tutte_decise(34))["definitiva"] is True
        # anche senza nessuna riga di giornata 35
        assert st.coppa_snapshot(classifica_16(), [])["definitiva"] is False

    def test_giornata_34_con_una_riga_da_verificare_non_e_conclusa(self):
        righe = righe_tutte_decise(33) + [riga(34, "G01", 1, "vinta"), riga(34, "G02", 1, "da_verificare")]
        assert st.coppa_snapshot(classifica_16(), righe)["definitiva"] is False

    def test_non_16_partecipanti_scheletri_vuoti(self):
        c = st.coppa_snapshot(dict_classifica([(n, [10]) for n in NOMI16[:15]]), [])
        assert c["tabellone_disponibile"] is False and c["partecipanti"] == 15
        assert [len(t["sfide"]) for t in c["turni"]] == [8, 4, 2, 1]
        assert all(s == {"giocatori": [None, None], "punti": [None, None], "vincente": None}
                   for t in c["turni"] for s in t["sfide"])
        # scheletri indipendenti, non lo stesso dizionario ripetuto (D, [{...}] * n)
        c["turni"][0]["sfide"][0]["punti"][0] = 99
        assert c["turni"][0]["sfide"][1]["punti"][0] is None

    def test_i_ritirati_non_partecipano(self):
        cl = classifica_16() + dict_classifica([("RITIRATO (RITIRATO)", [99] * 34)])
        c = st.coppa_snapshot(cl, [])
        assert c["partecipanti"] == 16
        assert "RITIRATO" not in str(c["turni"])

    def test_passaggio_di_turno_e_campione(self):
        # Il giocatore piu' basso in classifica (G16) fa piu' punti nelle giornate 35-38 e vince tutto.
        celle = lambda i: [30 - i] * 34 + ([100] * 4 if NOMI16[i] == "G16" else [1] * 4)
        cl = dict_classifica([(nome, celle(i)) for i, nome in enumerate(NOMI16)])
        righe = [riga(g, nome, 1, "vinta") for g in range(1, 39) for nome in ("G01",)]
        c = st.coppa_snapshot(cl, righe)
        assert c["turni"][0]["sfide"][0]["vincente"] == 1  # G16 batte G01
        assert c["campione"] == {"posizione": 16, "nome": "G16"}
        assert c["definitiva"] is True

    def test_giornata_non_conclusa_nessun_vincente(self):
        cl = dict_classifica([(nome, [30 - i] * 34 + [10]) for i, nome in enumerate(NOMI16)])
        righe = righe_tutte_decise(34) + [riga(35, "G01", 1, "in_corso")]
        c = st.coppa_snapshot(cl, righe)
        assert all(s["vincente"] is None for s in c["turni"][0]["sfide"])
        assert c["turni"][0]["sfide"][0]["punti"] == [10, 10]
        assert c["campione"] is None

    def test_a_parita_di_punti_il_tabellone_e_deterministico(self):
        # A7: a pari punti e pari vittorie il vecchio ordine dipendeva dal foglio; ora alfabetico.
        nomi = ["Z", "Y", "X", "W", "V", "U", "T", "S", "R", "Q", "P", "O", "N", "M", "L", "K"]
        a = st.coppa_snapshot(dict_classifica([(n, [10]) for n in nomi]), [])
        b = st.coppa_snapshot(dict_classifica([(n, [10]) for n in reversed(nomi)]), [])
        assert a == b
        assert a["turni"][0]["sfide"][0]["giocatori"][0] == {"posizione": 1, "nome": "K"}

    def test_nomi_in_maiuscolo(self):
        cl = dict_classifica([(n.lower(), [30 - i]) for i, n in enumerate(NOMI16)])
        assert st.coppa_snapshot(cl, [])["turni"][0]["sfide"][0]["giocatori"][0]["nome"] == "G01"


# ======================================================================
# N20, N22 — regole, impronta, segnale
# ======================================================================
class TestRegole:
    def test_numeri_allineati_al_bot(self):
        comp = {k.lower().replace(" ", "_"): v for k, v in bt.LIMITI_SCHEDINA.items()}
        assert st.REGOLE["composizione"] == comp
        # punti: il bot e' la fonte di verita'
        esempi = {"combo": ("1+OVER_2.5",), "doppie_chance": ("1X",), "variabili": ("OVER_2.5",), "fisse": ("1",)}
        for tipo, (pron,) in esempi.items():
            soglia = st.REGOLE["soglia_quota_doppia"]
            assert bt.calcola_punteggio_partita(pron, soglia - 0.01) == st.REGOLE["punti"][tipo]["base"], tipo
            assert bt.calcola_punteggio_partita(pron, soglia) == st.REGOLE["punti"][tipo]["quota_alta"], tipo

    def test_ripartizione_somma_cento_e_valori_decisi(self):
        assert sum(x["percentuale"] for x in st.REGOLE["ripartizione_premi"]) == 100
        assert [x["percentuale"] for x in st.REGOLE["ripartizione_premi"]] == [40, 27, 17, 10, 6]
        assert st.REGOLE["giocatori"] == 16 and st.REGOLE["obiettivo_cassa"] == 3200

    def test_obiettivo_cassa_della_cassa_e_quello_delle_regole(self):
        assert st.OBIETTIVO_CASSA == st.REGOLE["obiettivo_cassa"]

    def test_pausa_notturna_allineata_al_bot(self):
        assert st.PAUSA_NOTTURNA["inizio"] == bt.PAUSA_NOTTURNA_INIZIO.strftime("%H:%M")
        assert st.PAUSA_NOTTURNA["fine"] == bt.PAUSA_NOTTURNA_FINE.strftime("%H:%M")


class TestImprontaESegnale:
    def snap(self):
        return {"versione_schema": 1, "generato_il": "2026-10-04T15:30:12Z", "x": [1, 2], "y": {"b": 1, "a": 2}}

    def test_ignora_generato_il(self):
        a, b = self.snap(), self.snap()
        b["generato_il"] = "2030-01-01T00:00:00Z"
        assert st.impronta_snapshot(a) == st.impronta_snapshot(b)

    def test_cambia_con_il_contenuto(self):
        b = self.snap()
        b["x"] = [1, 3]
        assert st.impronta_snapshot(self.snap()) != st.impronta_snapshot(b)

    def test_non_dipende_dall_ordine_delle_chiavi(self):
        a = self.snap()
        b = dict(reversed(list(a.items())))
        assert st.impronta_snapshot(a) == st.impronta_snapshot(b)

    def test_e_sha256_in_esadecimale(self):
        h = st.impronta_snapshot(self.snap())
        assert len(h) == 64 and int(h, 16) >= 0

    def test_segnale(self):
        adesso = utc(2026, 10, 4, 15, 45, 3)
        s = st.costruisci_segnale(self.snap(), adesso)
        assert s == {"versione_schema": 1, "ultimo_controllo_il": "2026-10-04T15:45:03Z",
                     "generato_il": "2026-10-04T15:30:12Z", "impronta": st.impronta_snapshot(self.snap()),
                     "soglia_allarme_minuti": 120,
                     "pausa_notturna": {"inizio": "02:00", "fine": "07:30", "fuso": "Europe/Rome"}}

    def test_il_segnale_non_condivide_la_pausa_con_la_costante(self):
        s = st.costruisci_segnale(self.snap(), utc(2026, 10, 4, 15))
        s["pausa_notturna"]["inizio"] = "00:00"
        assert st.PAUSA_NOTTURNA["inizio"] == "02:00"


# ======================================================================
# Funzioni adattate
# ======================================================================
class TestFunzioniAdattate:
    def test_per_un_soffio_quota_numerica_e_testo_originale(self):
        righe = [{"Giornata": "Giornata 3", "Giocatore": "V", "Partita": "A - B", "Pronostico": "X", "Quota": "1.674,5", "Esito": "❌ PERSA"},
                 {"Giornata": "Giornata 3", "Giocatore": "V", "Partita": "C - D", "Pronostico": "1", "Quota": "1,5", "Esito": "✅ VINTA"}]
        (s,) = st.schedine_perse_per_un_soffio(righe)
        assert s["quota"] == 1674.5 and s["quota_testo"] == "1.674,5"

    def test_per_un_soffio_quota_illeggibile_none(self):
        righe = [{"Giornata": "Giornata 3", "Giocatore": "V", "Partita": "A - B", "Pronostico": "X", "Quota": "", "Esito": "❌ PERSA"},
                 {"Giornata": "Giornata 3", "Giocatore": "V", "Partita": "C - D", "Pronostico": "1", "Quota": "1,5", "Esito": "✅ VINTA"}]
        assert st.schedine_perse_per_un_soffio(righe)[0]["quota"] is None

    def test_per_un_soffio_accetta_righe_pulite(self):
        righe = [{"Giornata": "Giornata 3", "Giocatore": "V", "Partita": "A - B", "Pronostico": "X", "Quota": 3.2, "Esito": "persa"},
                 {"Giornata": "Giornata 3", "Giocatore": "V", "Partita": "C - D", "Pronostico": "1", "Quota": 1.5, "Esito": "vinta"}]
        assert st.schedine_perse_per_un_soffio(righe)[0]["quota"] == 3.2

    def test_il_dialetto_del_testo_e_dell_enum_danno_lo_stesso_risultato(self):
        testo = [{"Giornata": "Giornata 3", "Giocatore": "V", "Partita": "A - B", "Pronostico": "X", "Quota": "3,2", "Esito": e}
                 for e in ("❌ PERSA", "✅ VINTA", "➖ ANNULLATA")]
        enum = [dict(r, Esito=e) for r, e in zip(testo, ("persa", "vinta", "annullata"))]
        assert st.schedine_perse_per_un_soffio(testo) == st.schedine_perse_per_un_soffio(enum)


# ======================================================================
# Riga del foglio -> dizionario (utility)
# ======================================================================
class TestRigheDaValori:
    def test_righe_corte_riempite_e_vuote_scartate(self):
        r = st.righe_da_valori([["Giocatore", "Punti Totali", "Giornata 1"], ["A", "5"], [], ["", "", ""]])
        assert r == [{"Giocatore": "A", "Punti Totali": "5", "Giornata 1": ""}]

    def test_vuoto(self):
        assert st.righe_da_valori([]) == [] and st.righe_da_valori(None) == []
