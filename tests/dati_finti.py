"""
Dati finti con la FORMA di quelli veri, per i test dello snapshot.

Non e' un file di test (pytest non lo raccoglie): lo importano
test_statistiche_nuove.py, test_snapshot.py e test_invarianti.py.

Le righe imitano i fogli di Google Sheets come li restituisce l'API: liste di
stringhe, intestazione in testa, numeri in formato italiano ("1,85"),
righe corte senza le celle vuote finali. Le partite imitano
/competitions/SA/matches di Football-Data.
"""
from datetime import datetime, timedelta

import pytz

ADESSO = datetime(2026, 10, 4, 15, 30, 12, tzinfo=pytz.UTC)

# (name, shortName) come Football-Data
SQUADRE = [
    ("AC Milan", "Milan"), ("FC Internazionale Milano", "Inter"), ("Juventus FC", "Juventus"),
    ("SSC Napoli", "Napoli"), ("AS Roma", "Roma"), ("SS Lazio", "Lazio"),
    ("Bologna FC 1909", "Bologna"), ("Como 1907", "Como 1907"), ("ACF Fiorentina", "Fiorentina"),
    ("Atalanta BC", "Atalanta"), ("Torino FC", "Torino"), ("Genoa CFC", "Genoa"),
    ("Udinese Calcio", "Udinese"), ("US Lecce", "Lecce"), ("Cagliari Calcio", "Cagliari"),
    ("Parma Calcio 1913", "Parma"), ("US Sassuolo Calcio", "Sassuolo"), ("Venezia FC", "Venezia FC"),
    ("Frosinone Calcio", "Frosinone"), ("AC Monza", "Monza"),
]

INTESTAZIONE_GIOCATE = ["Giornata", "Giocatore", "Partita", "Tipologia Giocata", "Pronostico",
                        "Quota", "Esito", "Vincita Potenziale", "Punti Partita"]
INTESTAZIONE_CASSA = ["Giornata", "Descrizione", "Entrate", "Saldo Totale"]
INTESTAZIONE_CLASSIFICA = ["Giocatore", "Punti Totali"] + [f"Giornata {n}" for n in range(1, 39)]

VINTA, PERSA, IN_CORSO, ANNULLATA = "✅ VINTA", "❌ PERSA", "⏳ IN CORSO", "➖ ANNULLATA"
DA_VERIFICARE, RINVIATA = "⚠️ DA VERIFICARE", "⏸️ RINVIATA"


def calendario(giornata):
    """Le 10 coppie (casa, ospite) di una giornata: circle method su 20 squadre."""
    posti = list(range(20))
    resto = posti[1:]
    k = (giornata - 1) % 19
    resto = resto[-k:] + resto[:-k] if k else resto
    posti = [0] + resto
    coppie = [(posti[i], posti[19 - i]) for i in range(10)]
    return [(a, b) if (giornata + i) % 2 == 0 else (b, a) for i, (a, b) in enumerate(coppie)]


def partite_fd(giornate=range(1, 39), stati=None):
    """Risposta di /competitions/SA/matches: 10 partite per giornata, id = 1000*G + indice.
    Le prime 5 partite di ogni giornata iniziano alla stessa ora (per provare i pari orario)."""
    stati = stati or {}
    matches = []
    for g in giornate:
        for i, (casa, ospite) in enumerate(calendario(g)):
            inizio = datetime(2026, 8, 22, tzinfo=pytz.UTC) + timedelta(days=7 * (g - 1) + i // 5, hours=15 if i < 5 else 18 + i % 3)
            matches.append({
                "id": 1000 * g + i, "matchday": g,
                "utcDate": inizio.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": stati.get((g, i), "FINISHED"),
                "season": {"startDate": "2026-08-23", "currentMatchday": 6},
                "homeTeam": {"id": casa, "name": SQUADRE[casa][0], "shortName": SQUADRE[casa][1]},
                "awayTeam": {"id": ospite, "name": SQUADRE[ospite][0], "shortName": SQUADRE[ospite][1]},
                "score": {"fullTime": {"home": 1, "away": 0}},
            })
    return {"filters": {}, "resultSet": {"count": len(matches)}, "competition": {"code": "SA"}, "matches": matches}


def nome_foglio(giornata, indice):
    """Come il foglio scrive la partita: shortName casa - shortName ospite."""
    casa, ospite = calendario(giornata)[indice]
    return f"{SQUADRE[casa][1]} - {SQUADRE[ospite][1]}"


def riga_giocata(giornata, giocatore, partita, tipologia="Fisse", pronostico="1", quota="1,50",
                 esito=VINTA, vincita="", punti=None):
    """Una riga di Giocate!A:I. `punti` None = come il bot: 4 se vinta, 0 altrimenti."""
    if punti is None:
        punti = 4 if esito == VINTA else 0
    return [f"Giornata {giornata}", giocatore, partita, tipologia, pronostico, quota, esito, vincita, str(punti)]


def schedina(giornata, giocatore, esiti=None, vincita="100,00", pronostici=None, quote=None):
    """Una schedina da 10 righe (1 Combo, 4 Fisse, 2 Doppie Chance, 3 Variabili) sulle 10 partite
    della giornata. esiti: lista di 10 testi (default tutte vinte)."""
    tipologie = ["Combo"] + ["Fisse"] * 4 + ["Doppie Chance"] * 2 + ["Variabili"] * 3
    default = ["1+OVER_2.5"] + ["1"] * 4 + ["1X"] * 2 + ["OVER_2.5"] * 3
    esiti = esiti or [VINTA] * 10
    pronostici = pronostici or default
    quote = quote or ["1,50"] * 10
    righe = []
    for i in range(10):
        punti = {"Combo": 6, "Fisse": 4, "Doppie Chance": 1, "Variabili": 2}[tipologie[i]] if esiti[i] == VINTA else 0
        righe.append(riga_giocata(giornata, giocatore, nome_foglio(giornata, i), tipologie[i], pronostici[i],
                                  quote[i], esiti[i], vincita if i == 0 else "", punti))
    return righe


def classifica_valori(giocatori):
    """giocatori: lista di (nome, [punti per giornata]) -> values di Classifica con intestazione.
    Le celle vuote finali sono omesse come fa Sheets. Una cella None e' vuota ("")."""
    valori = [list(INTESTAZIONE_CLASSIFICA)]
    for nome, celle in giocatori:
        totale = sum(c for c in celle if c is not None)
        valori.append([nome, str(totale)] + ["" if c is None else str(c) for c in celle])
    return valori


def cassa_valori(movimenti=()):
    """movimenti: lista di (giornata, descrizione, entrata_testo, saldo_testo)."""
    return [list(INTESTAZIONE_CASSA)] + [list(m) for m in movimenti]


def dataset_base():
    """Quattro giocatori attivi, un ritirato col sostituto, 3 giornate giocate, una schedina chiusa.
    Ritorna (classifica, cassa, giocate, fd, adesso)."""
    giocate = [list(INTESTAZIONE_GIOCATE)]
    for g in (1, 2, 3):
        giocate += schedina(g, "PAOLO", vincita="800,00")  # tutta vinta: chiude
        esiti = [VINTA] * 6 + [PERSA] * 4
        giocate += schedina(g, "DARIO", esiti=esiti, vincita="500,00")
        esiti = [VINTA] * 9 + [PERSA]
        giocate += schedina(g, "MARIO", esiti=esiti, vincita="300,00")
        giocate += schedina(g, "SIRACUSA", esiti=[VINTA, PERSA] + [VINTA] * 4 + [PERSA] * 4, vincita="200,00")
    classifica = classifica_valori([
        ("PAOLO", [34, 34, 34]), ("DARIO", [15, 15, 15]), ("MARIO", [20, 20, 20]),
        ("SIRACUSA", [12, 12, 12]), ("PULIZZER (RITIRATO)", [30, 20]),
    ])
    cassa = cassa_valori([("Giornata 1", "PAOLO chiude la schedina!", "400,00€", "400,00€"),
                          ("Giornata 3", "PAOLO chiude la schedina!", "400,00€", "800,00€")])
    return classifica, cassa, giocate, partite_fd(range(1, 39)), ADESSO


# Le scritture REALI della Giornata 1 del foglio (29 scritture per 10 partite, estratte il 04/10/2026)
# e le 10 partite ufficiali di Football-Data: la prova di fuoco dell'abbinamento.
G1_UFFICIALI = [
    ("AS Roma", "Roma", "ACF Fiorentina", "Fiorentina"), ("Atalanta BC", "Atalanta", "US Sassuolo Calcio", "Sassuolo"),
    ("Bologna FC 1909", "Bologna", "SS Lazio", "Lazio"), ("FC Internazionale Milano", "Inter", "AC Monza", "Monza"),
    ("Frosinone Calcio", "Frosinone", "Juventus FC", "Juventus"), ("Genoa CFC", "Genoa", "SSC Napoli", "Napoli"),
    ("Parma Calcio 1913", "Parma", "Cagliari Calcio", "Cagliari"), ("Torino FC", "Torino", "AC Milan", "Milan"),
    ("Udinese Calcio", "Udinese", "Como 1907", "Como 1907"), ("Venezia FC", "Venezia FC", "US Lecce", "Lecce"),
]
G1_SCRITTURE = {
    0: ["ROMA - FIORENTINA", "Roma - Fiorentina"],
    1: ["ATALANTA - SASSUOLO", "ATALANTA - SASSUOLO CALCIO", "Atalanta - Sassuolo", "Atalanta - Sassuolo Calcio"],
    2: ["BOLOGNA - LAZIO", "BOLOGNA FC - LAZIO", "Bologna - Lazio", "Bologna FC - Lazio"],
    3: ["INTER - AC MONZA", "INTER - MONZA", "Inter - AC Monza", "Inter - Monza"],
    4: ["FROSINONE - JUVENTUS", "Frosinone - Juventus", "Frosinone Calcio - Juventus"],
    5: ["GENOA - NAPOLI", "Genoa - Napoli"],
    6: ["PARMA - CAGLIARI", "PARMA CALCIO - CAGLIARI", "Parma - Cagliari", "Parma Calcio - Cagliari Calcio"],
    7: ["TORINO - MILAN", "Torino - Milan"],
    8: ["UDINESE - COMO", "Udinese - Como"],
    9: ["VENEZIA - LECCE", "Venezia - Lecce"],
}


def partite_fd_g1():
    """La risposta di Football-Data con le sole 10 partite della Giornata 1 (nomi veri)."""
    matches = []
    for i, (c, sc, o, so) in enumerate(G1_UFFICIALI):
        matches.append({
            "id": 100 + i, "matchday": 1, "utcDate": f"2026-08-2{2 + i // 5}T{16 + i % 3}:00:00Z", "status": "FINISHED",
            "season": {"startDate": "2026-08-23"},
            "homeTeam": {"name": c, "shortName": sc}, "awayTeam": {"name": o, "shortName": so},
            "score": {"fullTime": {"home": 1, "away": 0}},
        })
    return {"matches": matches}


NOMI_16 = ["ALFA", "BETA", "CARLO", "DARIO", "ENZO", "FAZIO", "GINO", "HUGO", "IVAN", "JACK",
           "KIKO", "LUCA", "MARIO", "NICO", "OSCAR", "PAOLO"]


def dataset_stagione(giornate=38, nomi=NOMI_16, ritirato=True, seed=7):
    """Una stagione intera, COERENTE: i punti della Classifica sono quelli che il bot scriverebbe
    (punti delle righe vinte + 10 di bonus a schedina chiusa) e Cassa ha un movimento per ogni
    schedina chiusa. Ritorna (classifica, cassa, giocate, fd, adesso)."""
    import random
    caso = random.Random(seed)
    giocate = [list(INTESTAZIONE_GIOCATE)]
    punti = {n: [] for n in nomi}
    movimenti, saldo = [], 0.0
    for g in range(1, giornate + 1):
        for nome in nomi:
            esiti = [VINTA if caso.random() < 0.6 else PERSA for _ in range(10)]
            quote = [f"{caso.uniform(1.2, 4.5):.2f}".replace(".", ",") for _ in range(10)]
            vincita = f"{caso.uniform(50, 2000):.2f}".replace(".", ",")
            righe = schedina(g, nome, esiti=esiti, vincita=vincita, quote=quote)
            giocate += righe
            p = sum(int(r[8]) for r in righe)
            if all(e == VINTA for e in esiti):
                p += 10
                entrata = float(vincita.replace(",", ".")) / 2
                saldo += entrata
                movimenti.append((f"Giornata {g}", f"{nome} chiude la schedina!",
                                  f"{entrata:.2f} €".replace(".", ","), f"{saldo:.2f} €".replace(".", ",")))
            punti[nome].append(p)
    elenco = [(n, punti[n]) for n in nomi]
    if ritirato:
        elenco.append(("PULIZZER (RITIRATO)", [30, 20, 25][:giornate]))
    return classifica_valori(elenco), cassa_valori(movimenti), giocate, partite_fd(range(1, giornate + 1)), ADESSO
