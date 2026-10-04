"""
Test di INVARIANTE: non verificano un caso specifico, ma regole che non devono
mai rompersi, provate su tutte le combinazioni sensate.

Perché esistono (Sessione 13): il bug della giornata confrontata per sottostringa
è passato inosservato per settimane pur avendo 145 test verdi, perché tutti i test
guardavano *un* caso alla volta e nessuno chiedeva «ricalcolare la giornata N può
toccare righe di un'altra giornata?». Un test di invariante lo avrebbe fatto
fallire subito, invece di lasciarlo esplodere alla Giornata 10 sui dati veri.

Regola pratica: quando si scopre un bug, oltre al test sul caso specifico
chiedersi se esiste una *proprietà* più generale da bloccare qui.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt


SQUADRE = [
    ("AC Milan", "Milan"), ("FC Internazionale Milano", "Inter"),
    ("Juventus FC", "Juventus"), ("SSC Napoli", "Napoli"),
    ("AS Roma", "Roma"), ("SS Lazio", "Lazio"),
]


class _Esec:
    def execute(self, **kwargs):
        return {}


class FakeValues:
    def __init__(self, righe):
        self._righe = righe
        self.celle_scritte = []
        self.cassa_scritta = []

    def get(self, spreadsheetId, range):
        dati = self._righe if "Giocate" in range else [["Giocatore", "Punti Totali"]]

        class _R:
            def execute(self_inner, **kwargs):
                return {"values": dati}
        return _R()

    def batchUpdate(self, spreadsheetId, body):
        for d in body["data"]:
            self.celle_scritte.append(d["range"])
        return _Esec()

    def update(self, spreadsheetId, range, valueInputOption, body):
        return _Esec()

    def append(self, spreadsheetId, range, valueInputOption, body):
        self.cassa_scritta.extend(body["values"])
        return _Esec()


class FakeService:
    def __init__(self, righe):
        self.values_obj = FakeValues(righe)

    def spreadsheets(self):
        return self

    def values(self):
        return self.values_obj

    def get(self, **kw):
        class _R:
            def execute(self_inner, **kwargs):
                return {"sheets": [{"properties": {"sheetId": 0, "title": "Giocate"}}]}
        return _R()

    def batchUpdate(self, **kw):
        return _Esec()


def _match(casa, ospite, gc, go, status="FINISHED"):
    return {
        "homeTeam": {"name": casa[0], "shortName": casa[1]},
        "awayTeam": {"name": ospite[0], "shortName": ospite[1]},
        "status": status,
        "score": {"fullTime": {"home": gc, "away": go}},
    }


def _stagione_completa():
    """Righe realistiche per 38 giornate: le stesse squadre si ripetono
    all'andata e al ritorno con casa/trasferta invertiti, che è esattamente
    la condizione in cui il bug della sottostringa faceva danni."""
    righe = [["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito", "Vincita", "Punti"]]
    for g in range(1, 39):
        # andata nella prima metà, ritorno (invertito) nella seconda
        casa, ospite = (SQUADRE[0], SQUADRE[1]) if g <= 19 else (SQUADRE[1], SQUADRE[0])
        righe.append([f"Giornata {g}", "MARIO", f"{casa[1]} - {ospite[1]}", "Fisse", "1", "1,50", "", "", ""])
    return righe


class TestIsolamentoGiornate:
    """INVARIANTE: ricalcolare la giornata N tocca solo righe della giornata N."""

    @pytest.mark.parametrize("giornata", list(range(1, 39)))
    def test_ricalcolo_tocca_solo_la_propria_giornata(self, giornata, monkeypatch):
        righe = _stagione_completa()
        service = FakeService(righe)
        monkeypatch.setattr(bt, "connetti_sheets", lambda: service)

        casa, ospite = (SQUADRE[0], SQUADRE[1]) if giornata <= 19 else (SQUADRE[1], SQUADRE[0])
        bt.esegui_calcolo_risultati(str(giornata), matches_api=[_match(casa, ospite, 2, 0)])

        # La riga della giornata N è alla posizione N+1 del foglio (1 = intestazione)
        riga_attesa = giornata + 1
        righe_toccate = {int(r.split("!")[1][1:]) for r in service.values_obj.celle_scritte}
        assert righe_toccate <= {riga_attesa}, (
            f"Ricalcolando la Giornata {giornata} sono state toccate anche le righe "
            f"{sorted(righe_toccate - {riga_attesa})}, che appartengono ad altre giornate"
        )

    def test_nessuna_giornata_ne_seleziona_un_altra(self):
        """La stessa invariante a livello di funzione di confronto: nessun numero
        di giornata deve mai riconoscere l'etichetta di un'altra giornata."""
        for g in range(1, 39):
            for altra in range(1, 39):
                atteso = (g == altra)
                risultato = bt.riga_e_della_giornata(f"Giornata {altra}", g)
                assert risultato is atteso, (
                    f"giornata {g} vs etichetta 'Giornata {altra}': "
                    f"atteso {atteso}, ottenuto {risultato}"
                )


class TestInvariantiPunteggio:
    """INVARIANTI sul calcolo dei punti, provate su tutti i risultati plausibili."""

    PRONOSTICI_VALIDI = ["1", "X", "2", "1X", "X2", "12", "GOAL", "NOGOAL",
                         "PARI", "DISPARI", "OVER_2.5", "UNDER_2.5"]

    @pytest.mark.parametrize("gc", range(0, 5))
    @pytest.mark.parametrize("go", range(0, 5))
    def test_ogni_pronostico_valido_ha_sempre_un_esito_deciso(self, gc, go):
        """Un pronostico riconosciuto non deve MAI finire in DA VERIFICARE:
        quello stato è riservato a ciò che il sistema non sa interpretare."""
        for p in self.PRONOSTICI_VALIDI:
            esito = bt.controlla_esito(p, gc, go)
            assert esito in ("✅ VINTA", "❌ PERSA"), (
                f"{p} su {gc}-{go} ha dato {esito}"
            )

    @pytest.mark.parametrize("gc", range(0, 4))
    @pytest.mark.parametrize("go", range(0, 4))
    def test_esiti_complementari_non_possono_vincere_entrambi(self, gc, go):
        """1/X/2 sono mutuamente esclusivi, come GOAL/NOGOAL e PARI/DISPARI:
        su uno stesso risultato ne può vincere esattamente uno."""
        for coppia in (["1", "X", "2"], ["GOAL", "NOGOAL"], ["PARI", "DISPARI"],
                       ["OVER_2.5", "UNDER_2.5"]):
            vincenti = [p for p in coppia if "VINTA" in bt.controlla_esito(p, gc, go)]
            assert len(vincenti) == 1, (
                f"su {gc}-{go} il gruppo {coppia} ha {len(vincenti)} vincenti: {vincenti}"
            )

    @pytest.mark.parametrize("gc", range(0, 4))
    @pytest.mark.parametrize("go", range(0, 4))
    def test_la_doppia_chance_vince_se_vince_una_delle_due(self, gc, go):
        """1X deve vincere esattamente quando vince 1 oppure X, e così le altre."""
        for doppia, singoli in (("1X", ["1", "X"]), ("X2", ["X", "2"]), ("12", ["1", "2"])):
            doppia_vince = "VINTA" in bt.controlla_esito(doppia, gc, go)
            singolo_vince = any("VINTA" in bt.controlla_esito(s, gc, go) for s in singoli)
            assert doppia_vince == singolo_vince, (
                f"su {gc}-{go}: {doppia} vince={doppia_vince} ma {singoli} vince={singolo_vince}"
            )

    @pytest.mark.parametrize("quota", ["1,50", "3,49", "3,50", "5,00"])
    def test_i_punti_non_sono_mai_negativi_ne_assurdi(self, quota):
        for p in self.PRONOSTICI_VALIDI + ["1+GOAL", "X2+OVER_2.5"]:
            punti = bt.calcola_punteggio_partita(p, bt.estrai_numero(quota))
            assert 0 <= punti <= 12, f"{p} @{quota} -> {punti} punti"


class TestInvariantiScritture:
    """INVARIANTI su cosa il bot può scrivere su Sheets."""

    def test_una_partita_non_giocata_non_paga_mai_la_cassa(self, monkeypatch):
        """Nessuno stato diverso da FINISHED può generare un movimento di cassa."""
        for stato in ("TIMED", "SCHEDULED", "IN_PLAY", "PAUSED", "POSTPONED", "SUSPENDED", "CANCELLED"):
            righe = [
                ["Giornata", "Giocatore", "Partita", "Tipologia", "Pronostico", "Quota", "Esito", "Vincita", "Punti"],
                ["Giornata 7", "MARIO", "Milan - Inter", "Fisse", "1", "1,50", "", "1.000,00", ""],
            ]
            service = FakeService(righe)
            monkeypatch.setattr(bt, "connetti_sheets", lambda: service)
            bt.esegui_calcolo_risultati(
                "7", matches_api=[_match(SQUADRE[0], SQUADRE[1], None, None, status=stato)]
            )
            assert service.values_obj.cassa_scritta == [], (
                f"stato {stato} ha generato un pagamento in Cassa"
            )


class _ValuesConClassifica(FakeValues):
    """Come FakeValues, ma con una Classifica vera e la riscrittura catturata."""

    def __init__(self, righe, classifica):
        super().__init__(righe)
        self._classifica = classifica
        self.classifica_scritta = None

    def get(self, spreadsheetId, range):
        if "Classifica" not in range:
            return super().get(spreadsheetId, range)
        dati = [list(r) for r in self._classifica]

        class _R:
            def execute(self_inner, **kwargs):
                return {"values": dati}
        return _R()

    def update(self, spreadsheetId, range, valueInputOption, body):
        if range.startswith("Classifica"):
            self.classifica_scritta = body["values"]
        return _Esec()


class TestInvariantiRitirati:
    """INVARIANTE (Sessione 20): la riga di un giocatore ritirato è congelata.
    Nessun ricalcolo può cambiarne i punti, neanche se il suo nome senza
    suffisso coincide con un giocatore attivo (è il caso reale: Siracusa ha
    ereditato le schedine di Pulizzer, e un domani potrebbe tornare lo stesso nome)."""

    @pytest.mark.parametrize("giornata", [1, 2, 20])
    def test_ricalcolo_non_tocca_la_riga_del_ritirato(self, giornata, monkeypatch):
        righe = _stagione_completa()
        classifica = [
            ["Giocatore", "Punti Totali", "Giornata 1", "Giornata 2"],
            ["MARIO", "25", "15", "10"],
            ["MARIO (RITIRATO)", "90", "60", "30"],
        ]
        service = FakeService(righe)
        service.values_obj = _ValuesConClassifica(righe, classifica)
        monkeypatch.setattr(bt, "connetti_sheets", lambda: service)

        casa, ospite = (SQUADRE[0], SQUADRE[1]) if giornata <= 19 else (SQUADRE[1], SQUADRE[0])
        bt.esegui_calcolo_risultati(str(giornata), matches_api=[_match(casa, ospite, 2, 0)])

        scritta = service.values_obj.classifica_scritta
        assert scritta is not None
        ritirato = [r for r in scritta if r and r[0] == "MARIO (RITIRATO)"]
        assert len(ritirato) == 1
        assert [str(x) for x in ritirato[0] if str(x) != ""] == ["MARIO (RITIRATO)", "90", "60", "30"]
        assert len(scritta) == 3, "il ricalcolo non deve creare righe nuove per un giocatore gia' presente"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# ---------------------------------------------------------------------------
# La Classifica cresce per COLONNE: Giocatore, Punti Totali, poi una colonna per
# giornata. 2 + 38 = 40 colonne, cioè fino ad AN. Un range "Classifica!A:Z"
# tiene solo le Giornate 1-24: dalla 25 il bot scrive in AA, rilegge senza AA e
# la Giornata 26 sovrascrive la 25 — perdendone i punti, senza nessun errore.
# ---------------------------------------------------------------------------
COLONNE_CLASSIFICA = 2 + 38


def _indice_colonna(lettere):
    n = 0
    for c in lettere:
        n = n * 26 + ord(c) - ord("A") + 1
    return n


@pytest.mark.parametrize("file", ["bot_telegram.py", "app.py"])
def test_ogni_lettura_della_classifica_contiene_38_giornate(file):
    import re
    percorso = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), file)
    with open(percorso, encoding="utf-8") as f:
        sorgente = f.read()
    # "Classifica!A:Z", "Classifica!A1:AN50"... "Classifica" da solo (foglio
    # intero) e "Classifica!A1" (punto di partenza di una scrittura) vanno bene.
    troppo_strette = [
        r for r in re.findall(r"Classifica![A-Z]*\d*:([A-Z]+)", sorgente)
        if _indice_colonna(r) < COLONNE_CLASSIFICA
    ]
    assert troppo_strette == [], (
        f"{file}: range della Classifica che si ferma alla colonna {troppo_strette}, "
        f"ne servono {COLONNE_CLASSIFICA}. Usa il foglio intero: range=\"Classifica\"."
    )


# ======================================================================
# SNAPSHOT del restyling (statistiche.costruisci_snapshot)
# ======================================================================
# Le stesse domande di sempre, fatte allo snapshot: ricalcolarlo puo' toccare cio' che non deve?
# L'ordine delle righe nel foglio puo' cambiare il risultato? I numeri tornano fra una sezione e l'altra?
import copy
import random

import statistiche as st
import dati_finti as dati


@pytest.fixture(scope="module")
def stagione_snapshot():
    return dati.dataset_stagione()


@pytest.fixture(scope="module")
def snapshot_intero(stagione_snapshot):
    return st.costruisci_snapshot(*stagione_snapshot)


class TestInvariantiSnapshot:
    def test_costruire_lo_snapshot_non_modifica_i_dati_in_ingresso(self, stagione_snapshot):
        """INVARIANTE: lo snapshot e' una lettura. Se modificasse le righe lette dal chiamante, il bot
        rischierebbe di riscrivere su Sheets dati alterati o di ripubblicare qualcosa di diverso al giro dopo."""
        classifica, cassa, giocate, fd, adesso = stagione_snapshot
        prima = copy.deepcopy((classifica, cassa, giocate, fd))
        st.costruisci_snapshot(classifica, cassa, giocate, fd, adesso)
        assert (classifica, cassa, giocate, fd) == prima

    def test_la_somma_dei_punti_per_giornata_e_il_totale(self, snapshot_intero):
        """INVARIANTE: per ogni giocatore, attivo o ritirato, i punti delle giornate sommano a Punti Totali."""
        for g in snapshot_intero["classifica"]["giocatori"] + snapshot_intero["classifica"]["ritirati"]:
            assert sum(p for p in g["punti_per_giornata"] if p is not None) == g["punti_totali"], g["nome"]

    def test_le_posizioni_sono_coerenti_con_i_punti(self, snapshot_intero):
        """INVARIANTE: chi ha piu' punti non sta mai sotto chi ne ha meno; la posizione non salta senza un pari merito."""
        righe = snapshot_intero["classifica"]["giocatori"]
        for sopra, sotto in zip(righe, righe[1:]):
            assert sopra["punti_totali"] >= sotto["punti_totali"]
            assert sopra["posizione"] <= sotto["posizione"]
        for r in righe:
            assert r["posizione"] == 1 + sum(1 for x in righe if x["posizione"] < r["posizione"])

    def test_l_ordine_delle_righe_nei_fogli_non_cambia_lo_snapshot(self, stagione_snapshot):
        """INVARIANTE (A7): niente nello snapshot dipende dall'ordine in cui le righe stanno nel foglio.
        Il vecchio sito risolveva i pari merito con l'ordine del foglio: una riga spostata a mano
        cambiava chi era "Il Cecchino"."""
        classifica, cassa, giocate, fd, adesso = stagione_snapshot
        atteso = st.impronta_snapshot(st.costruisci_snapshot(classifica, cassa, giocate, fd, adesso))
        for seme in (1, 2, 3):
            caso = random.Random(seme)
            c = [classifica[0]] + caso.sample(classifica[1:], len(classifica) - 1)  # intestazione sempre in testa
            g = [giocate[0]] + caso.sample(giocate[1:], len(giocate) - 1)
            f = copy.deepcopy(fd)
            caso.shuffle(f["matches"])
            assert st.impronta_snapshot(st.costruisci_snapshot(c, cassa, g, f, adesso)) == atteso, f"seme {seme}"

    @pytest.mark.parametrize("giornata", [1, 2, 10, 11, 12, 21, 38])
    def test_ricostruire_con_la_sola_giornata_n_non_cambia_la_giornata_n(self, giornata, stagione_snapshot, snapshot_intero):
        """INVARIANTE (Sessione 13, bug della sottostringa): "1" non e' contenuto in "Giornata 12". Lo snapshot
        costruito con le sole righe della giornata N contiene per quella giornata le stesse partite e le stesse
        schedine dello snapshot intero: nessuna giornata ne mescola un'altra."""
        classifica, cassa, giocate, fd, adesso = stagione_snapshot
        solo = [giocate[0]] + [r for r in giocate[1:] if r[0] == f"Giornata {giornata}"]
        parziale = st.costruisci_snapshot(classifica, cassa, solo, fd, adesso)
        assert [s for s in parziale["schedine"]] == [s for s in snapshot_intero["schedine"] if s["giornata"] == giornata]
        assert [p for p in parziale["partite"]] == [p for p in snapshot_intero["partite"] if p["giornata"] == giornata]
        assert len(parziale["schedine"]) == 16 and len(parziale["partite"]) == 10

    def test_ogni_schedina_ha_dieci_righe_e_ogni_riga_una_partita_della_sua_giornata(self, snapshot_intero):
        """INVARIANTE: una riga punta sempre a una partita della stessa giornata della schedina."""
        giornata_di = {p["id"]: p["giornata"] for p in snapshot_intero["partite"]}
        for s in snapshot_intero["schedine"]:
            assert len(s["righe"]) == 10
            assert {giornata_di[r["partita_id"]] for r in s["righe"]} == {s["giornata"]}

    def test_la_cassa_torna(self, snapshot_intero):
        """INVARIANTE: il saldo e' la somma delle entrate, i versamenti per giornata sommano al saldo
        e l'ultimo "Saldo Totale" scritto coincide (nessuna correzione a mano nei dati finti)."""
        c = snapshot_intero["cassa"]
        assert c["saldo"] == pytest.approx(sum(m["entrata"] for m in c["movimenti"]))
        assert sum(v["versato"] for v in c["versamenti_per_giornata"]) == pytest.approx(c["saldo"], abs=0.005)
        assert c["movimenti"][-1]["saldo"] == pytest.approx(c["saldo"], abs=0.005)

    def test_vinte_piu_perse_sono_le_righe_valutate_delle_statistiche(self, snapshot_intero):
        """INVARIANTE: la tabella delle statistiche e le schedine contano le stesse righe valutate."""
        per_giocatore = {}
        for s in snapshot_intero["schedine"]:
            r = per_giocatore.setdefault(s["giocatore"], [0, 0])
            r[0] += s["riepilogo"]["vinte"]
            r[1] += s["riepilogo"]["vinte"] + s["riepilogo"]["perse"]
        for stat in snapshot_intero["statistiche"]["giocatori"]:
            assert [stat["vinte"], stat["totali"]] == per_giocatore[stat["nome"]], stat["nome"]
