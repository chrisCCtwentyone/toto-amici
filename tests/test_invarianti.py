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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
