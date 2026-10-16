"""La categoria di un evento la decide il pronostico (regolamento), non il modello.
Caso reale 16/10/2026: gemini-flash-lite-latest metteva GOAL in "Fisse"."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt


@pytest.mark.parametrize("pron,cat", [
    ("1", "Fisse"), ("X", "Fisse"), ("2", "Fisse"),
    ("1X", "Doppie Chance"), ("X2", "Doppie Chance"), ("12", "Doppie Chance"),
    ("OVER_2.5", "Variabili"), ("UNDER_2.5", "Variabili"), ("GOAL", "Variabili"),
    ("NOGOAL", "Variabili"), ("PARI", "Variabili"), ("DISPARI", "Variabili"),
    ("1+OVER_2.5", "Combo"), ("X+GOAL", "Combo"),
    ("BOH", None), ("", None),
])
def test_categoria_da_pronostico(pron, cat):
    assert bt.categoria_da_pronostico(pron) == cat


def _ev(p, pron="1"):
    return {"partita": p, "pronostico": pron, "quota": "1,50"}


def _vuoto(**kw):
    return {c: kw.get(c.replace(" ", "_"), []) for c in bt.CATEGORIE_SCHEDINA}


def test_goal_in_fisse_va_in_variabili_e_combo_in_fisse_va_in_combo():
    ev = _vuoto(Fisse=[_ev("A-B", "GOAL"), _ev("C-D", "1+OVER_2.5"), _ev("E-F", "2")])
    out = bt.riclassifica_eventi(ev)
    assert [e["partita"] for e in out["Variabili"]] == ["A-B"]
    assert [e["partita"] for e in out["Combo"]] == ["C-D"]
    assert [e["partita"] for e in out["Fisse"]] == ["E-F"]


def test_pronostico_non_riconosciuto_resta_dov_era():
    out = bt.riclassifica_eventi(_vuoto(Doppie_Chance=[_ev("A-B", "BOH")]))
    assert len(out["Doppie Chance"]) == 1


def test_alias_vengono_normalizzati_prima_di_classificare():
    out = bt.riclassifica_eventi(_vuoto(Fisse=[_ev("A-B", "GG"), _ev("C-D", "2X"), _ev("E-F", "O 2.5")]))
    assert [e["partita"] for e in out["Variabili"]] == ["A-B", "E-F"]
    assert [e["partita"] for e in out["Doppie Chance"]] == ["C-D"]


def test_schedina_regolare_torna_1_4_2_3_e_ordine_conservato():
    ev = _vuoto(
        Combo=[_ev("P1-P1", "1+OVER_2.5")],
        Fisse=[_ev("P2-P2", "1"), _ev("P3-P3", "GOAL"), _ev("P4-P4", "X"), _ev("P5-P5", "2"), _ev("P6-P6", "12"), _ev("P10-P10", "1")],
        Doppie_Chance=[_ev("P7-P7", "1X"), _ev("P8-P8", "NOGOAL")],
        Variabili=[_ev("P9-P9", "UNDER_2.5")],
    )
    out = bt.riclassifica_eventi(ev)
    assert [len(out[c]) for c in bt.CATEGORIE_SCHEDINA] == [1, 4, 2, 3]
    assert [e["partita"] for e in out["Fisse"]] == ["P2-P2", "P4-P4", "P5-P5", "P10-P10"]
    assert [e["partita"] for e in out["Doppie Chance"]] == ["P6-P6", "P7-P7"]
    assert [e["partita"] for e in out["Variabili"]] == ["P3-P3", "P8-P8", "P9-P9"]


def test_riclassifica_json_forma_schema_e_fallback():
    dati = {"vincita_potenziale": "10,5", "eventi": {"Fisse": [_ev("A-B", "GOAL")]}}
    out = json.loads(bt.riclassifica_json(json.dumps(dati)))
    assert out["vincita_potenziale"] == "10,5"
    assert [e["partita"] for e in out["eventi"]["Variabili"]] == ["A-B"]
    assert bt.riclassifica_json("non json") == "non json"
