"""
Test di statistiche.py — il timer "Tempo passato dall'ultima schedina vinta"
la statistica "Per un soffio" e la colonna "Scelta del gruppo" del Confronto Giocate.

Timer: il punto delicato non e' il conteggio ma il momento di partenza: i fogli non
hanno una colonna data, quindi va ricavato da Cassa (chi ha chiuso, e in quale
giornata) e dagli orari delle partite. Un errore qui non fa crashare niente:
mostra semplicemente un tempo sbagliato, ed e' il tipo di errore che nessuno nota.
"""
from datetime import datetime, timedelta

import pytz

from statistiche import (
    DURATA_STIMATA_PARTITA,
    leggi_orario_utc,
    momento_fine_schedina,
    numero_giornata,
    schedine_chiuse_ultima_giornata,
    scomponi_durata,
)


def _utc(anno, mese, giorno, ora, minuto=0):
    return datetime(anno, mese, giorno, ora, minuto, tzinfo=pytz.UTC)


# --- numero_giornata ---

def test_numero_giornata_legge_solo_etichette_complete():
    assert numero_giornata("Giornata 1") == 1
    assert numero_giornata("  giornata 12 ") == 12
    assert numero_giornata("Giornata") is None
    assert numero_giornata("") is None
    assert numero_giornata("Giornata 1 bis") is None


# --- schedine_chiuse_ultima_giornata ---

def test_nessuna_schedina_chiusa():
    assert schedine_chiuse_ultima_giornata([]) is None
    assert schedine_chiuse_ultima_giornata([("Giornata 3", "Versamento manuale")]) is None


def test_caso_reale_paolo_giornata_1():
    # Riga reale del foglio Cassa al 14/09/2026.
    assert schedine_chiuse_ultima_giornata([("Giornata 1", "PAOLO chiude la schedina!")]) == (1, ["PAOLO"])


def test_ultima_giornata_per_numero_non_alfabetica():
    # Alfabeticamente "Giornata 9" viene dopo "Giornata 10": deve vincere la 10.
    righe = [("Giornata 10", "MARCO chiude la schedina!"), ("Giornata 9", "PAOLO chiude la schedina!")]
    assert schedine_chiuse_ultima_giornata(righe) == (10, ["MARCO"])


def test_righe_fuori_ordine_nel_foglio():
    righe = [("Giornata 5", "LUCA chiude la schedina!"), ("Giornata 2", "PAOLO chiude la schedina!")]
    assert schedine_chiuse_ultima_giornata(righe) == (5, ["LUCA"])


def test_piu_vincitori_nella_stessa_giornata_senza_doppioni():
    righe = [
        ("Giornata 4", "PAOLO chiude la schedina!"),
        ("Giornata 4", "GIULIA chiude la schedina!"),
        ("Giornata 4", "paolo chiude la schedina!"),
    ]
    assert schedine_chiuse_ultima_giornata(righe) == (4, ["PAOLO", "GIULIA"])


def test_descrizioni_senza_nome_o_giornata_malformata_ignorate():
    righe = [("Giornata 7", "chiude la schedina!"), ("G7", "PAOLO chiude la schedina!")]
    assert schedine_chiuse_ultima_giornata(righe) is None


# --- momento_fine_schedina ---

def test_fine_schedina_e_ultima_partita_piu_durata():
    orari = {
        "Juventus - Milan": _utc(2026, 8, 23, 16),
        "Inter - Napoli": _utc(2026, 8, 24, 18, 45),
        "Roma - Lazio": _utc(2026, 8, 22, 18, 45),
    }
    atteso = _utc(2026, 8, 24, 18, 45) + DURATA_STIMATA_PARTITA
    assert momento_fine_schedina(list(orari), orari) == atteso


def test_partita_ripetuta_nella_schedina_conta_una_volta():
    orari = {"Juventus - Milan": _utc(2026, 8, 23, 16)}
    assert momento_fine_schedina(["Juventus - Milan"] * 3, orari) == _utc(2026, 8, 23, 18)


def test_orario_mancante_non_si_stima_sulle_altre():
    # La partita senza orario potrebbe essere proprio l'ultima: meglio nessun
    # timer che un timer partito dal momento sbagliato.
    orari = {"Juventus - Milan": _utc(2026, 8, 23, 16), "Inter - Napoli": None}
    assert momento_fine_schedina(["Juventus - Milan", "Inter - Napoli"], orari) is None
    assert momento_fine_schedina(["Juventus - Milan", "Partita sconosciuta"], orari) is None


def test_schedina_vuota():
    assert momento_fine_schedina([], {"Juventus - Milan": _utc(2026, 8, 23, 16)}) is None


# --- leggi_orario_utc ---

def test_leggi_orario_utc():
    assert leggi_orario_utc("2026-08-23T18:45:00Z") == _utc(2026, 8, 23, 18, 45)
    assert leggi_orario_utc("") is None
    assert leggi_orario_utc(None) is None
    assert leggi_orario_utc("23/08 20:45") is None


# --- scomponi_durata ---

def test_scomponi_durata():
    secondi = 2 * 604800 + 3 * 86400 + 4 * 3600 + 5 * 60 + 6
    assert scomponi_durata(secondi) == (2, 3, 4, 5, 6)
    assert scomponi_durata(59) == (0, 0, 0, 0, 59)
    assert scomponi_durata(timedelta(days=7).total_seconds()) == (1, 0, 0, 0, 0)


def test_scomponi_durata_negativa_resta_a_zero():
    # Succede se il bot chiude la schedina prima della fine *stimata* (partita
    # durata meno di 2 ore): il timer deve restare a zero, non contare all'indietro.
    assert scomponi_durata(-120) == (0, 0, 0, 0, 0)


# --- schedine_perse_per_un_soffio ---

from statistiche import schedine_perse_per_un_soffio


def _riga(giornata, giocatore, partita, esito, pronostico="1", quota="1,50"):
    return {"Giornata": giornata, "Giocatore": giocatore, "Partita": partita,
            "Pronostico": pronostico, "Quota": quota, "Esito": esito}


def test_soffio_caso_reale_vincenzo_giornata_3():
    righe = [_riga("Giornata 3", "VINCENZO", f"Partita {i}", "✅ VINTA") for i in range(9)]
    righe.append(_riga("Giornata 3", "VINCENZO", "Fiorentina - Torino", "❌ PERSA", "X", "3,2"))
    assert schedine_perse_per_un_soffio(righe) == [{
        "giocatore": "VINCENZO", "giornata": 3, "partita": "Fiorentina - Torino",
        "pronostico": "X", "quota": "3,2",
    }]


def test_soffio_due_perse_non_conta():
    righe = [_riga("Giornata 2", "PAOLO", "A - B", "✅ VINTA"),
             _riga("Giornata 2", "PAOLO", "C - D", "❌ PERSA"),
             _riga("Giornata 2", "PAOLO", "E - F", "❌ PERSA")]
    assert schedine_perse_per_un_soffio(righe) == []


def test_soffio_schedina_non_ancora_decisa_esclusa():
    # Una sola persa ma una partita ancora da giocare/verificare/recuperare:
    # la schedina non e' ancora "persa per un soffio", potrebbe bruciarsi ancora.
    for esito_aperto in ("⏳ IN CORSO", "⚠️ DA VERIFICARE", "⏸️ RINVIATA", ""):
        righe = [_riga("Giornata 2", "PAOLO", "A - B", "✅ VINTA"),
                 _riga("Giornata 2", "PAOLO", "C - D", "❌ PERSA"),
                 _riga("Giornata 2", "PAOLO", "E - F", esito_aperto)]
        assert schedine_perse_per_un_soffio(righe) == [], esito_aperto


def test_soffio_annullata_non_blocca():
    righe = [_riga("Giornata 2", "PAOLO", "A - B", "✅ VINTA"),
             _riga("Giornata 2", "PAOLO", "C - D", "ANNULLATA ECCESSO"),
             _riga("Giornata 2", "PAOLO", "E - F", "❌ PERSA")]
    assert [s["partita"] for s in schedine_perse_per_un_soffio(righe)] == ["E - F"]


def test_soffio_serve_almeno_una_vinta():
    righe = [_riga("Giornata 2", "PAOLO", "A - B", "ANNULLATA ECCESSO"),
             _riga("Giornata 2", "PAOLO", "C - D", "❌ PERSA")]
    assert schedine_perse_per_un_soffio(righe) == []


def test_soffio_giornate_separate_per_numero():
    # Giornata 1 e Giornata 12 non vanno mescolate (bug della sottostringa, Sessione 13):
    # insieme sarebbero due perse e nessuna delle due comparirebbe.
    righe = [_riga("Giornata 1", "PAOLO", "A - B", "✅ VINTA"),
             _riga("Giornata 1", "PAOLO", "C - D", "❌ PERSA"),
             _riga("Giornata 12", "PAOLO", "E - F", "✅ VINTA"),
             _riga("Giornata 12", "PAOLO", "G - H", "❌ PERSA")]
    assert [(s["giornata"], s["partita"]) for s in schedine_perse_per_un_soffio(righe)] == [(12, "G - H"), (1, "C - D")]


def test_soffio_stesso_giocatore_scritto_diverso_e_ordinamento():
    righe = [_riga("Giornata 4", "paolo ", "A - B", "✅ VINTA"),
             _riga("Giornata 4", "PAOLO", "C - D", "❌ PERSA"),
             _riga("Giornata 4", "ANNA", "E - F", "✅ VINTA"),
             _riga("Giornata 4", "ANNA", "G - H", "❌ PERSA"),
             _riga("Giornata", "ANNA", "X - Y", "❌ PERSA")]
    assert [s["giocatore"].upper() for s in schedine_perse_per_un_soffio(righe)] == ["ANNA", "PAOLO"]


# --- scelta_del_gruppo (Confronto Giocate) ---

from statistiche import scelta_del_gruppo


def test_scelta_del_gruppo_caso_reale_como_parma():
    # Giornata 4, dati veri: 5 su 7 hanno giocato "1", due la combo con OVER.
    giocate = {"CECILIA": ["1"], "DARIO": ["1"], "DAVIDE": ["1"], "FAZIO": ["1"],
               "GAETANO": ["1+OVER_2.5"], "GIACOMO": ["1+OVER_2.5"], "GIOVANNI": ["1"]}
    assert scelta_del_gruppo(giocate) == "1 · 5 su 7"


def test_scelta_del_gruppo_parita():
    giocate = {"A": ["X"], "B": ["1"], "C": ["X"], "D": ["1"], "E": ["2"]}
    assert scelta_del_gruppo(giocate) == "1 / X · 2 su 5"


def test_scelta_del_gruppo_tutti_diversi():
    assert scelta_del_gruppo({"A": ["1"], "B": ["X"], "C": ["GOAL"]}) == "Tutti diversi"


def test_scelta_del_gruppo_stesso_pronostico_ripetuto_conta_una_volta():
    # Un giocatore con lo stesso pronostico su due righe non vale doppio.
    giocate = {"A": ["1", " 1 "], "B": ["x"], "C": ["X"]}
    assert scelta_del_gruppo(giocate) == "X · 2 su 3"


def test_scelta_del_gruppo_casi_limite():
    assert scelta_del_gruppo({}) == "—"
    assert scelta_del_gruppo({"A": [""], "B": []}) == "—"
    assert scelta_del_gruppo({"A": ["1"]}) == "1 · 1 su 1"


# ---------------------------------------------------------------------------
# Giocatori ritirati (Sessione 20)
# ---------------------------------------------------------------------------
import pytest

from statistiche import e_ritirato, nome_senza_ritiro


@pytest.mark.parametrize("nome", ["PULIZZER (RITIRATO)", " pulizzer (ritirato) ", "Pulizzer (Ritirato)"])
def test_riconosce_il_ritirato(nome):
    assert e_ritirato(nome)
    assert nome_senza_ritiro(nome).upper() == "PULIZZER"


@pytest.mark.parametrize("nome", ["PULIZZER", "SIRACUSA", "", "RITIRATO MARIO"])
def test_un_attivo_non_e_ritirato(nome):
    assert not e_ritirato(nome)
    assert nome_senza_ritiro(nome) == nome.strip()


from statistiche import righe_del_ritirato, ultima_giornata_con_punti


def test_ultima_giornata_con_punti_ignora_le_colonne_vuote():
    riga = {"Giocatore": "PULIZZER (RITIRATO)", "Punti Totali": "90",
            "Giornata 1": "16", "Giornata 4": "14", "Giornata 5": "", "Giornata 12": " "}
    assert ultima_giornata_con_punti(riga) == 4
    assert ultima_giornata_con_punti({"Giocatore": "X", "Giornata 1": ""}) is None


def test_il_ritirato_prende_solo_le_giornate_prima_del_ritiro():
    righe = [
        {"Giornata": "Giornata 1", "Giocatore": "SIRACUSA"},
        {"Giornata": "Giornata 4", "Giocatore": "SIRACUSA"},
        {"Giornata": "Giornata 5", "Giocatore": "SIRACUSA"},   # gia' di Siracusa
        {"Giornata": "Giornata 12", "Giocatore": "SIRACUSA"},  # 12 > 4: mai per sottostringa
        {"Giornata": "Giornata 1", "Giocatore": "MARIO"},
        {"Giornata": "Giornata", "Giocatore": "SIRACUSA"},     # intestazione ripetuta
    ]
    scelte = righe_del_ritirato(righe, "PULIZZER (RITIRATO)", 4)
    assert [r["Giornata"] for r in scelte] == ["Giornata 1", "Giornata 4"]


def test_ritirato_senza_sostituto_noto_non_ha_righe():
    righe = [{"Giornata": "Giornata 1", "Giocatore": "SIRACUSA"}]
    assert righe_del_ritirato(righe, "SCONOSCIUTO (RITIRATO)", 4) == []
    assert righe_del_ritirato(righe, "PULIZZER (RITIRATO)", None) == []


# --- tabellone_ottavi (Coppa) ---

from statistiche import tabellone_ottavi

CLASSIFICA_16 = [f"G{i}" for i in range(1, 17)]


def test_tabellone_accoppiamenti_1_contro_16():
    ottavi = tabellone_ottavi(CLASSIFICA_16)
    coppie = [(a[0], b[0]) for a, b in ottavi]
    assert coppie == [(1, 16), (8, 9), (5, 12), (4, 13), (6, 11), (3, 14), (7, 10), (2, 15)]
    # Ogni sfida somma a 17: il migliore contro il peggiore, e cosi' via.
    assert all(a + b == 17 for a, b in coppie)
    # Il nome corrisponde alla posizione.
    assert all(nome == f"G{pos}" for sfida in ottavi for pos, nome in sfida)


def test_tabellone_ogni_giocatore_una_volta():
    nomi = [nome for sfida in tabellone_ottavi(CLASSIFICA_16) for _, nome in sfida]
    assert sorted(nomi) == sorted(CLASSIFICA_16)


def test_tabellone_primi_due_solo_in_finale():
    # Prima meta' del tabellone = sfide 0-3, seconda = 4-7.
    ottavi = tabellone_ottavi(CLASSIFICA_16)
    meta = lambda pos: next(i for i, sfida in enumerate(ottavi) if pos in (sfida[0][0], sfida[1][0])) // 4
    assert meta(1) != meta(2)
    # 1 e 4 si possono incontrare in semifinale, non prima: stessa meta', quarti diversi.
    quarto = lambda pos: next(i for i, sfida in enumerate(ottavi) if pos in (sfida[0][0], sfida[1][0])) // 2
    assert meta(1) == meta(4) and quarto(1) != quarto(4)
    assert quarto(1) == quarto(8)


def test_tabellone_caso_reale_16_settembre():
    # Classifica vera al 16/09/2026, ritirato escluso, spareggi gia' applicati.
    classifica = ["PAOLO", "VILLARI", "FAZIO", "SIRACUSA", "GIOVANNI", "MIRKO", "VINCENZO", "DARIO",
                  "MARIO", "SILVIO", "DAVIDE", "GAETANO", "GIACOMO", "CECILIA", "MICHELE", "NICO"]
    ottavi = tabellone_ottavi(classifica)
    assert ottavi[0] == ((1, "PAOLO"), (16, "NICO"))
    assert ottavi[-1] == ((2, "VILLARI"), (15, "MICHELE"))


def test_tabellone_non_si_indovina_con_partecipanti_sbagliati():
    assert tabellone_ottavi(CLASSIFICA_16[:15]) is None
    assert tabellone_ottavi(CLASSIFICA_16 + ["G17"]) is None
    assert tabellone_ottavi([]) is None
    # Righe vuote non contano come partecipanti.
    assert tabellone_ottavi(CLASSIFICA_16[:15] + ["  "]) is None


# --- Coppa: tabellone fisso dalla 34ª e passaggi di turno ---

from statistiche import (
    PRIMA_GIORNATA_COPPA,
    ULTIMA_GIORNATA_TABELLONE,
    classifica_per_coppa,
    giornate_concluse,
    punti_per_giornata,
    turni_coppa,
)


def test_calendario_coppa_ultime_quattro_giornate():
    assert (ULTIMA_GIORNATA_TABELLONE, PRIMA_GIORNATA_COPPA) == (34, 35)


def _classifica(**punti_per_nome):
    # punti_per_nome: NOME={giornata: punti}
    return [{"Giocatore": nome, "Punti Totali": sum(p.values()),
             **{f"Giornata {g}": str(v) for g, v in p.items()}}
            for nome, p in punti_per_nome.items()]


def test_classifica_coppa_ignora_punti_dopo_la_34():
    # Con i 40 punti della 35ª BRUNO sarebbe primo: non contano, ANNA resta davanti (15 a 12).
    righe = _classifica(ANNA={1: 10, 34: 5}, BRUNO={1: 12, 35: 40})
    assert classifica_per_coppa(righe, []) == ["ANNA", "BRUNO"]
    # La 34ª invece conta: senza i suoi 5 punti ANNA (10) sarebbe dietro a BRUNO (14).
    righe = _classifica(ANNA={1: 10, 34: 5}, BRUNO={1: 14, 36: 40})
    assert classifica_per_coppa(righe, []) == ["ANNA", "BRUNO"]


def test_classifica_coppa_esclude_ritirati_e_celle_non_numeriche():
    righe = _classifica(ANNA={1: 10}, BRUNO={1: 8})
    righe.append({"Giocatore": "PULIZZER (RITIRATO)", "Giornata 1": "90"})
    righe.append({"Giocatore": "CARLO", "Giornata 1": "n/d"})
    assert classifica_per_coppa(righe, []) == ["ANNA", "BRUNO", "CARLO"]


def test_classifica_coppa_spareggio_vittorie_fino_alla_34():
    righe = _classifica(ANNA={1: 10}, BRUNO={1: 10})
    giocate = [
        {"Giornata": "Giornata 1", "Giocatore": "ANNA", "Esito": "✅ VINTA"},
        {"Giornata": "Giornata 35", "Giocatore": "BRUNO", "Esito": "✅ VINTA"},
        {"Giornata": "Giornata 35", "Giocatore": "BRUNO", "Esito": "✅ VINTA"},
    ]
    # Le vittorie di BRUNO sono della 35ª: non valgono per lo spareggio.
    assert classifica_per_coppa(righe, giocate) == ["ANNA", "BRUNO"]
    # A parita' completa resta l'ordine del foglio.
    assert classifica_per_coppa(_classifica(ZETA={1: 3}, ALFA={1: 3}), []) == ["ZETA", "ALFA"]


def test_classifica_coppa_coincide_con_la_classifica_prima_della_35():
    # Dati veri al 16/09/2026 (solo punti totali, spareggio SILVIO/DAVIDE e
    # GIACOMO/CECILIA dai pronostici vinti): stesso ordine della scheda Classifica.
    punti = {"GIOVANNI": 88, "MIRKO": 87, "FAZIO": 93, "GAETANO": 75, "GIACOMO": 72,
             "VINCENZO": 86, "VILLARI": 99, "DARIO": 81, "SILVIO": 76, "PAOLO": 118,
             "SIRACUSA": 90, "CECILIA": 72, "DAVIDE": 76, "MICHELE": 69, "MARIO": 79, "NICO": 66}
    righe = [{"Giocatore": n, "Giornata 1": str(p)} for n, p in punti.items()]
    righe.append({"Giocatore": "PULIZZER (RITIRATO)", "Giornata 1": "90"})
    giocate = ([{"Giornata": "Giornata 1", "Giocatore": "SILVIO", "Esito": "✅ VINTA"}]
               + [{"Giornata": "Giornata 1", "Giocatore": "GIACOMO", "Esito": "✅ VINTA"}])
    assert classifica_per_coppa(righe, giocate) == [
        "PAOLO", "VILLARI", "FAZIO", "SIRACUSA", "GIOVANNI", "MIRKO", "VINCENZO", "DARIO",
        "MARIO", "SILVIO", "DAVIDE", "GAETANO", "GIACOMO", "CECILIA", "MICHELE", "NICO"]


def test_punti_per_giornata_cella_vuota_non_e_zero():
    righe = [{"Giocatore": "ANNA", "Punti Totali": 7, "Giornata 35": "7", "Giornata 36": ""},
             {"Giocatore": "BRUNO", "Giornata 35": "0"}]
    assert punti_per_giornata(righe) == {35: {"ANNA": 7, "BRUNO": 0}}


def test_giornate_concluse():
    giocate = [
        {"Giornata": "Giornata 35", "Giocatore": "ANNA", "Esito": "✅ VINTA"},
        {"Giornata": "Giornata 35", "Giocatore": "BRUNO", "Esito": "ANNULLATA ECCESSO"},
        {"Giornata": "Giornata 35", "Giocatore": "BRUNO", "Esito": "❌ PERSA"},
        {"Giornata": "Giornata 36", "Giocatore": "ANNA", "Esito": "✅ VINTA"},
        {"Giornata": "Giornata 36", "Giocatore": "BRUNO", "Esito": "⏳ IN CORSO"},
    ]
    assert giornate_concluse(giocate) == {35}
    for aperto in ("⚠️ DA VERIFICARE", "⏸️ RINVIATA", ""):
        assert giornate_concluse([{"Giornata": "Giornata 37", "Giocatore": "ANNA", "Esito": aperto}]) == set()
    # Giornata 3 e Giornata 35 restano distinte (niente sottostringhe).
    assert giornate_concluse([
        {"Giornata": "Giornata 3", "Giocatore": "ANNA", "Esito": "✅ VINTA"},
        {"Giornata": "Giornata 35", "Giocatore": "ANNA", "Esito": "⏳ IN CORSO"},
    ]) == {3}


NOMI_16 = [f"G{i}" for i in range(1, 17)]


def _turni(punti_giornate, concluse):
    return turni_coppa(tabellone_ottavi(NOMI_16), punti_giornate, concluse)


def test_turni_prima_della_coppa_solo_ottavi_noti():
    turni = _turni({}, set())
    assert [len(t) for t in turni] == [8, 4, 2, 1]
    assert [t[0]["giornata"] for t in turni] == [35, 36, 37, 38]
    assert all(s["vincente"] is None for t in turni for s in t)
    assert all(s["giocatori"] == [None, None] for t in turni[1:] for s in t)


def test_ottavi_in_corso_mostrano_punti_senza_vincente():
    turni = _turni({35: {"G1": 4, "G16": 9}}, set())
    primo = turni[0][0]
    assert primo["punti"] == [4, 9] and primo["vincente"] is None
    assert turni[1][0]["giocatori"] == [None, None]


def test_passa_chi_fa_piu_punti_e_a_parita_il_meglio_piazzato():
    punti = {35: {f"G{i}": 5 for i in range(1, 17)}}
    punti[35]["G16"] = 9        # G16 batte G1
    punti[35]["G9"] = 5         # G8 e G9 pari: passa G8
    turni = _turni(punti, {35})
    assert turni[0][0]["vincente"] == 1
    assert turni[0][1]["giocatori"] == [(8, "G8"), (9, "G9")] and turni[0][1]["vincente"] == 0
    assert turni[1][0]["giocatori"] == [(16, "G16"), (8, "G8")]


def test_senza_punti_in_giornata_conclusa_valgono_zero():
    turni = _turni({35: {"G16": 1}}, {35})
    assert turni[0][0]["vincente"] == 1          # G16 (1 pt) batte G1 (nessun punto = 0)
    assert turni[0][1]["vincente"] == 0          # G8 e G9 entrambi a 0: passa G8


def test_coppa_completa_fino_al_campione():
    # Vince sempre il meglio piazzato: in finale G1 contro G2, campione G1.
    concluse = {35, 36, 37, 38}
    turni = _turni({}, concluse)
    finale = turni[3][0]
    assert finale["giocatori"] == [(1, "G1"), (2, "G2")]
    assert finale["giocatori"][finale["vincente"]] == (1, "G1")
    # Semifinali: 1 contro 4, 3 contro 2 (schema classico).
    assert [[v[0] for v in s["giocatori"]] for s in turni[2]] == [[1, 4], [3, 2]]


def test_turno_successivo_non_concluso_non_dichiara_nulla():
    turni = _turni({36: {"G1": 3, "G8": 7}}, {35})
    quarto = turni[1][0]
    assert quarto["giocatori"] == [(1, "G1"), (8, "G8")]
    assert quarto["punti"] == [3, 7] and quarto["vincente"] is None
    assert turni[2][0]["giocatori"] == [None, None]


# --- ordina_partite_per_orario (Confronto Giocate) ---

from statistiche import ordina_partite_per_orario


def test_ordine_cronologico_non_alfabetico():
    orari = {
        "Juventus - Inter": _utc(2026, 9, 19, 16, 0),    # venerdi', prima partita
        "Atalanta - Como": _utc(2026, 9, 20, 12, 30),
        "Roma - Lazio": _utc(2026, 9, 21, 18, 45),       # lunedi', ultima
    }
    assert ordina_partite_per_orario(sorted(orari), orari) == [
        "Juventus - Inter", "Atalanta - Como", "Roma - Lazio"]


def test_stesso_orario_ordine_alfabetico():
    orari = {"Milan - Napoli": _utc(2026, 9, 20, 15), "Cagliari - Parma": _utc(2026, 9, 20, 15)}
    assert ordina_partite_per_orario(["Milan - Napoli", "Cagliari - Parma"], orari) == [
        "Cagliari - Parma", "Milan - Napoli"]


def test_partite_senza_orario_in_fondo_mai_perse():
    orari = {"Roma - Lazio": _utc(2026, 9, 21, 18, 45), "Squadra X - Squadra Y": None}
    partite = ["Zeta - Alfa", "Squadra X - Squadra Y", "Roma - Lazio"]
    assert ordina_partite_per_orario(partite, orari) == [
        "Roma - Lazio", "Squadra X - Squadra Y", "Zeta - Alfa"]


def test_nessun_orario_disponibile_resta_alfabetico():
    # API non raggiungibile: nessun orario, la tabella non deve sparire.
    partite = ["Roma - Lazio", "Atalanta - Como"]
    assert ordina_partite_per_orario(partite, {}) == ["Atalanta - Como", "Roma - Lazio"]
    assert ordina_partite_per_orario([], {}) == []
