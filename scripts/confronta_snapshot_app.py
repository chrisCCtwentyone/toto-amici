#!/usr/bin/env python3
"""
Confronto SNAPSHOT <-> dashboard Streamlit di oggi, sui dati VERI. Non scrive nulla.

PERCHE' ESISTE
--------------
Il sito nuovo non calcola niente: mostra lo snapshot. Questo script verifica che
lo snapshot dica le stesse cose che app.py mostra oggi, schermata per schermata,
e che ogni differenza sia una di quelle ATTESE (restyling/snapshot-schema.md §13).
Una differenza non spiegata e' un bug: o dello snapshot o di app.py.

COME FUNZIONA
-------------
Esegue il VERO app.py con il framework di test di Streamlit (AppTest) sui dati
veri, ne legge metriche, tabelle e testi, e li confronta con lo snapshot
costruito dagli stessi fogli. Le schede Schedine Live e Confronto Giocate si
confrontano per ogni giornata (e, per la Live, per ogni giocatore).

USO
---
    python3 scripts/confronta_snapshot_app.py

Serve lo stesso .env di genera_snapshot_locale.py. Esce con 0 se ogni
differenza e' attesa, 1 se ce n'e' una NON spiegata.

SICUREZZA
---------
app.py legge i fogli con scope di sola lettura, il resto e' lettura di
Football-Data. Lo script non scrive niente da nessuna parte.
"""
import html as modulo_html
import os
import re
import sys
from collections import Counter
from datetime import datetime

import pytz

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RADICE)
sys.path.insert(0, os.path.join(RADICE, "scripts"))

import genera_snapshot_locale as gen  # noqa: E402
import statistiche as st  # noqa: E402

ROMA = pytz.timezone("Europe/Rome")
differenze = []   # (area, dettaglio, codice §13 oppure None)
controlli = Counter()


def ok(area):
    controlli[area] += 1


def diff(area, dettaglio, codice=None):
    differenze.append((area, dettaglio, codice))


def confronta(area, app, snap, codice=None, dettaglio=""):
    """Registra un controllo: uguale = ok, diverso = differenza (attesa se c'e' il codice)."""
    if app == snap:
        ok(area)
    else:
        diff(area, f"{dettaglio} app={app!r} snapshot={snap!r}".strip(), codice)


def num(testo):
    """'1.030,30 €' -> 1030.3 (formato italiano)."""
    return round(st.estrai_numero(testo), 2)


def in_roma(iso):
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC).astimezone(ROMA)
    return dt


# ----------------------------------------------------------------------
# Lettura dell'app
# ----------------------------------------------------------------------
def avvia_app():
    from streamlit.testing.v1 import AppTest
    os.chdir(RADICE)
    app = AppTest.from_file(os.path.join(RADICE, "app.py"), default_timeout=180)
    app.run()
    if app.exception:
        sys.exit(f"app.py ha sollevato un'eccezione: {[e.value for e in app.exception]}")
    return app


def tabella_html(corpo):
    """Dalla tabella dello Styler (Confronto Giocate): (colonne, righe) dove
    ogni riga e' (intestazione, [(testo, colore)])."""
    colori = {}
    for selettori, dichiarazioni in re.findall(r"([^{}]+)\{([^}]*)\}", corpo.split("</style>")[1] if "</style>" in corpo else ""):
        colore = None
        if "rgba(0, 180, 0" in dichiarazioni:
            colore = "verde"
        elif "rgba(220, 0, 0" in dichiarazioni:
            colore = "rosso"
        if colore:
            for id_cella in re.findall(r"#(T_\w+)", selettori):
                colori[id_cella] = colore
    colonne = [modulo_html.unescape(t) for _, t in re.findall(r'<th id="[^"]*level0_col(\d+)"[^>]*>(.*?)</th>', corpo)]
    righe = {}
    for r, t in re.findall(r'<th id="[^"]*level0_row(\d+)"[^>]*>(.*?)</th>', corpo):
        righe[int(r)] = [modulo_html.unescape(t), {}]
    for idc, r, c, t in re.findall(r'<td id="([^"]*_row(\d+)_col(\d+))"[^>]*>(.*?)</td>', corpo, re.S):
        righe[int(r)][1][int(c)] = (modulo_html.unescape(t), colori.get(idc))
    return colonne, [(righe[i][0], [righe[i][1][j] for j in sorted(righe[i][1])]) for i in sorted(righe)]


# ----------------------------------------------------------------------
# Confronti per scheda
# ----------------------------------------------------------------------
def confronta_classifica(app, snap):
    scheda = app.tabs[0]
    classifica = snap["classifica"]

    # Podio: etichetta, punti, delta
    podio = scheda.metric[:3]
    for i, m in enumerate(podio):
        riga = classifica["giocatori"][i]
        confronta("Classifica/podio nome", m.label.split(" ", 1)[1], riga["nome"])
        confronta("Classifica/podio punti", num(m.value), riga["punti_totali"])
        # Il delta "+N pt ultima giornata" oggi non compare mai (D1): lo snapshot lo ha.
        if m.delta in ("", None) and riga["punti_ultima_giornata"]:
            diff("Classifica/podio delta", f"{riga['nome']}: app senza delta, snapshot +{riga['punti_ultima_giornata']} pt", "A1")
        else:
            ok("Classifica/podio delta")

    # Classifica completa
    tabella = scheda.table[0].value.reset_index()
    attivi = tabella[~tabella["Pos."].isin(["—", "Ritirato"])]
    confronta("Classifica/righe", len(attivi), len(classifica["giocatori"]))
    posizioni_snapshot = Counter(r["posizione"] for r in classifica["giocatori"])
    punti_prima = {}  # per spiegare P9a
    for i, (_, r_app) in enumerate(attivi.iterrows()):
        r = next((x for x in classifica["giocatori"] if x["nome"] == r_app["Giocatore"]), None)
        if r is None:
            diff("Classifica/righe", f"{r_app['Giocatore']} non nello snapshot")
            continue
        confronta("Classifica/punti", num(r_app["Punti Totali"]), r["punti_totali"], dettaglio=r["nome"])
        pos_app = i + 1  # l'app numera per ordine di riga
        if pos_app == r["posizione"]:
            ok("Classifica/posizione")
        elif posizioni_snapshot[r["posizione"]] > 1:
            diff("Classifica/posizione", f"{r['nome']}: app {pos_app}° snapshot {r['posizione']}° (pari merito)", "A10")
        else:
            diff("Classifica/posizione", f"{r['nome']}: app {pos_app}° snapshot {r['posizione']}°")
        # tendenza
        t = r_app.get("Tend.", "")
        snap_t = r["variazione_posizione"]
        atteso = "" if snap_t is None else ("⚪ –" if snap_t == 0 else (f"🟢 ▲{snap_t}" if snap_t > 0 else f"🔴 ▼{-snap_t}"))
        if t == atteso:
            ok("Classifica/tendenza")
        else:
            # P9a: la classifica precedente dell'app non ha spareggio. Una freccia puo' differire
            # SOLO per chi era a pari punti con qualcuno prima dell'ultima giornata.
            ultima = classifica["ultima_giornata_giocata"]
            prima = {x["nome"]: sum(c or 0 for c in x["punti_per_giornata"][:ultima - 1]) for x in classifica["giocatori"]}
            a_pari = [n for n, v in prima.items() if v == prima[r["nome"]] and n != r["nome"]]
            diff("Classifica/tendenza", f"{r['nome']}: app {t!r} snapshot {atteso!r} (a pari punti prima: {a_pari})",
                 "P9a" if a_pari else None)
    ritirati_app = tabella[tabella["Pos."] == "Ritirato"]
    confronta("Classifica/ritirati", [(x["Giocatore"], num(x["Punti Totali"])) for _, x in ritirati_app.iterrows()],
              [(x["nome"], x["punti_totali"]) for x in classifica["ritirati"]])

    # Storico per giornata
    storico = scheda.table[1].value
    for _, x in storico.reset_index().iterrows():
        nome = x["Giocatore"].replace(" (ritirato)", "")
        voce = next((v for v in classifica["giocatori"] + classifica["ritirati"] if v["nome"] == nome), None)
        if voce is None:
            diff("Classifica/storico", f"{nome} non nello snapshot")
            continue
        app_riga = [None if str(x[f"Giornata {n}"]).strip() == "" else int(x[f"Giornata {n}"])
                    for n in range(1, len(voce["punti_per_giornata"]) + 1)]
        confronta("Classifica/storico", app_riga, voce["punti_per_giornata"], dettaglio=nome)
    colonne_app = [c for c in storico.columns if c.startswith("Giornata")]
    confronta("Classifica/storico colonne", len(colonne_app), len(classifica["giocatori"][0]["punti_per_giornata"]))


def confronta_cassa(app, snap):
    scheda = app.tabs[0]
    cassa = snap["cassa"]
    saldo, obiettivo, completamento = scheda.metric[3:6]
    confronta("Cassa/saldo", num(saldo.value), cassa["saldo"])
    confronta("Cassa/obiettivo", num(obiettivo.value.replace(",", "")), cassa["obiettivo"])
    confronta("Cassa/completamento", completamento.value, f"{cassa['completamento'] * 100:.1f}%")
    righe_app = [(str(r["Giornata"]), r["Descrizione"], num(r["Entrate"]), num(r["Saldo Totale"]))
                 for _, r in scheda.table[2].value.reset_index().iterrows()]
    righe_snap = [(f"Giornata {m['giornata']}", m["descrizione"], m["entrata"], m["saldo"]) for m in cassa["movimenti"]]
    confronta("Cassa/movimenti", righe_app, righe_snap)
    import pyarrow as pa
    grafico = pa.ipc.open_stream(scheda.get("vega_lite_chart")[0].proto.datasets[0].data.data).read_all().to_pandas()
    confronta("Cassa/versamenti", [(int(r.Giornata), round(float(r.Versato), 2)) for r in grafico.itertuples()],
              [(v["giornata"], v["versato"]) for v in cassa["versamenti_per_giornata"]])


def leggi_carte_live(scheda):
    """Le carte della scheda Live: dizionari partita, data, tipo+pronostico+quota, esito, punti."""
    carte, corrente = [], None
    didascalie = [c.value for c in scheda.caption][1:]
    for md in scheda.markdown:
        v = md.value
        if v.startswith("**:material/sports_soccer:"):
            testo = v.split("**")[1].replace(":material/sports_soccer: ", "")
            data = v.split("🗓️ ")[1] if "🗓️" in v else ""
            corrente = {"partita": testo, "data": data, "score": None}
            carte.append(corrente)
        elif v.startswith(":blue-badge"):
            corrente["score"] = v
        elif "-badge[" in v and corrente is not None and "esito" not in corrente:
            corrente["esito"] = v.split("]")[0].split(": ", 1)[1] if ": " in v else v
        elif v.startswith("<div") and corrente is not None:
            corrente["punti"] = int(re.search(r"\+(\d+) pt", v).group(1))
    for carta, d in zip(carte, didascalie):
        m = re.search(r"Pronostico: \*\*(.*?)\*\* · Quota: \*\*@(.*?)\*\*", d)
        carta["pronostico"], carta["quota"] = m.group(1), m.group(2)
        carta["tipologia_app"] = d.split("· Pronostico")[0].strip()
    return carte


def confronta_live(app, snap):
    partite = {p["id"]: p for p in snap["partite"]}
    giornate = [o for o in app.tabs[1].selectbox[0].options]
    giocatori = list(snap["giocatori"])
    for etichetta in giornate:
        n = st.numero_giornata(etichetta)
        app.tabs[1].selectbox[0].set_value(etichetta).run()
        for giocatore in giocatori:
            app.tabs[1].get("button_group")[0].set_value(giocatore).run()
            scheda = app.tabs[1]
            if any("Dati live non disponibili" in w.value for w in scheda.warning):
                # Football-Data ha un limite di 10 richieste/minuto, condiviso con questo script: se l'app non
                # ha ricevuto i dati di una giornata, i nomi e gli orari non sono confrontabili.
                sys.exit(f"\n  INCONCLUSIVO: Football-Data non ha risposto all'app per la Giornata {n} "
                         "(limite 10 richieste/minuto). Riprova fra un minuto.\n")
            schedina = next((s for s in snap["schedine"] if s["giornata"] == n and s["giocatore"] == giocatore), None)
            area = "Live"
            if schedina is None:
                diff(area, f"G{n} {giocatore}: schedina non nello snapshot")
                continue
            m_vinte, m_perse, m_corso, m_vincita = scheda.metric
            confronta("Live/riepilogo", (int(m_vinte.value), int(m_perse.value), int(m_corso.value)),
                      (schedina["riepilogo"]["vinte"], schedina["riepilogo"]["perse"], schedina["riepilogo"]["in_corso"]),
                      dettaglio=f"G{n} {giocatore}")
            confronta("Live/vincita", num(m_vincita.value), schedina["vincita_potenziale"], dettaglio=f"G{n} {giocatore}")
            carte = leggi_carte_live(scheda)
            confronta("Live/numero carte", len(carte), len(schedina["righe"]), dettaglio=f"G{n} {giocatore}")
            # Le carte dell'app e le righe dello snapshot si abbinano per contenuto (pronostico+quota+punti+esito):
            # l'ORDINE puo' differire (A5), il contenuto no.
            chiavi_app = Counter((c["pronostico"], num(c["quota"]), c["punti"], st.esito_da_testo(c["esito"])) for c in carte)
            chiavi_snap = Counter((r["pronostico"], r["quota"], r["punti"], r["esito"]) for r in schedina["righe"])
            confronta("Live/contenuto carte", chiavi_app, chiavi_snap, dettaglio=f"G{n} {giocatore}")
            # Nome partita e orario, carta per carta nell'ordine dell'app: stessa carta = stessa partita?
            nomi_app = [c["partita"] for c in carte]
            nomi_snap = [partite[r["partita_id"]]["nome"] for r in schedina["righe"]]
            if nomi_app == nomi_snap:
                ok("Live/ordine e nomi")
            elif Counter(nomi_app) == Counter(nomi_snap) and \
                    [c["data"] for c in carte] == [in_roma(partite[r["partita_id"]]["inizio_il"]).strftime("%d/%m %H:%M")
                                                   for r in schedina["righe"]]:
                # stessa sequenza di orari: l'ordine cambia solo fra partite che iniziano insieme
                diff("Live/ordine", f"G{n} {giocatore}: stesse partite, ordine diverso solo fra partite con lo stesso orario", "A5")
            else:
                diff("Live/nomi", f"G{n} {giocatore}: {sorted(set(nomi_app) ^ set(nomi_snap))}", "A6")
            orari_app = sorted(c["data"] for c in carte)
            orari_snap = sorted(in_roma(partite[r["partita_id"]]["inizio_il"]).strftime("%d/%m %H:%M")
                                if partite[r["partita_id"]]["inizio_il"] else "" for r in schedina["righe"])
            confronta("Live/orari", orari_app, orari_snap, dettaglio=f"G{n} {giocatore}")
            # La tipologia (era sempre vuota nell'app: leggeva 'Tipologia' invece di 'Tipologia Giocata', corretto)
            confronta("Live/tipologia",
                      Counter((st.tipologia_da_testo(c["tipologia_app"]), c["pronostico"], num(c["quota"])) for c in carte),
                      Counter((r["tipologia"], r["pronostico"], r["quota"]) for r in schedina["righe"]),
                      dettaglio=f"G{n} {giocatore}")


def formatta_scelta(sg):
    if sg["tipo"] == "nessuna":
        return "—"
    if sg["tipo"] == "tutti_diversi":
        return "Tutti diversi"
    return f"{' / '.join(sg['pronostici'])} · {sg['voti']} su {sg['su']}"


def confronta_confronto(app, snap):
    partite_snap = {p["id"]: p for p in snap["partite"]}
    for etichetta in list(app.tabs[2].selectbox[0].options):
        n = st.numero_giornata(etichetta)
        app.tabs[2].selectbox[0].set_value(etichetta).run()
        colonne, righe = tabella_html(app.tabs[2].get("html")[0].proto.body)
        giocatori_app = colonne[:-1]
        partite_g = [p for p in snap["partite"] if p["giornata"] == n]
        nomi_app = [r[0] for r in righe[:-1]]
        nomi_snap = [p["nome"] for p in partite_g]
        if nomi_app == nomi_snap:
            ok("Confronto/righe")
        elif Counter(nomi_app) == Counter(nomi_snap):
            diff("Confronto/righe", f"G{n}: stesse partite, ordine diverso", "A5")
        else:
            diff("Confronto/righe", f"G{n}: {sorted(set(nomi_app) ^ set(nomi_snap))}", "A6")
        schedine_g = {s["giocatore"]: s for s in snap["schedine"] if s["giornata"] == n}
        confronta("Confronto/giocatori", sorted(giocatori_app), sorted(schedine_g), dettaglio=f"G{n}")
        for nome_partita, celle in righe[:-1]:
            partita = next((p for p in partite_g if p["nome"] == nome_partita), None)
            if partita is None:
                continue
            for giocatore, (testo, colore) in zip(giocatori_app + ["Scelta del gruppo"], celle):
                if giocatore == "Scelta del gruppo":
                    confronta("Confronto/scelta del gruppo", testo, formatta_scelta(partita["scelta_gruppo"]),
                              codice="A11", dettaglio=f"G{n} {nome_partita}")
                    continue
                rr = [r for r in schedine_g[giocatore]["righe"] if r["partita_id"] == partita["id"]]
                atteso = " | ".join(
                    f"{r['pronostico']} (@{str(r['quota']).replace('.', ',')}{'*' if r['quota'] and r['quota'] >= snap['regole']['soglia_quota_doppia'] else ''})"
                    for r in rr) or "—"
                # il testo dell'app riporta la quota COME SCRITTA nel foglio ("2,1", "1,5"): si confronta il numero
                def normalizza(t):
                    return re.sub(r"@([\d,.]+)", lambda m: "@" + str(num(m.group(1))), t)
                confronta("Confronto/celle", normalizza(testo), normalizza(atteso), dettaglio=f"G{n} {giocatore} {nome_partita}")
                colore_snap = {"vinta": "verde", "persa": "rosso"}.get(rr[0]["esito"]) if rr else None
                # con piu' righe sulla stessa partita l'app colora per l'ultima (pivot di testo concatenato): si controlla solo il caso a riga singola
                if len(rr) <= 1:
                    confronta("Confronto/colori", colore, colore_snap, dettaglio=f"G{n} {giocatore} {nome_partita}")
        vincite_app = {g: num(t) for g, (t, _) in zip(giocatori_app, righe[-1][1])}
        confronta("Confronto/vincite", vincite_app, {g: s["vincita_potenziale"] for g, s in schedine_g.items()}, dettaglio=f"G{n}")


def confronta_statistiche(app, snap):
    scheda = app.tabs[3]
    premi = snap["statistiche"]["premi"]
    metriche = {m.label.split(" ·")[0].split(" →")[0]: m for m in scheda.metric}
    m = scheda.metric
    cecchino, benedizione, folle, conservatore, incorniciare, fedelta, amuleto, maledetta = m[:8]

    def pari(area, voce_app, lista, formatta, codice="A9"):
        if len(lista) == 1:
            confronta(area, voce_app, formatta(lista[0]))
        elif formatta(lista[0]) == voce_app or voce_app in [formatta(x) for x in lista]:
            diff(area, f"app mostra uno solo ({voce_app}), lo snapshot tutti i pari merito ({len(lista)})", codice)
        else:
            diff(area, f"app {voce_app} snapshot {[formatta(x) for x in lista]}")

    pari("Stat/cecchino", (cecchino.label, cecchino.value, cecchino.delta), premi["cecchino"],
         lambda x: (x["giocatore"], f"{x['win_rate']:.1f}% win rate", f"{x['vinte']}/{x['totali']} pronostici presi"))
    pari("Stat/benedizione", (benedizione.label, benedizione.value, benedizione.delta), premi["benedizione"],
         lambda x: (x["giocatore"], f"{x['win_rate']:.1f}% win rate", f"{x['vinte']}/{x['totali']} pronostici presi"))
    pari("Stat/folle", (folle.label, folle.value), premi["folle"], lambda x: (x["giocatore"], f"Quota media {x['quota_media']:.2f}"))
    pari("Stat/conservatore", (conservatore.label, conservatore.value), premi["conservatore"],
         lambda x: (x["giocatore"], f"Quota media {x['quota_media']:.2f}"))
    pari("Stat/giornata da incorniciare", (incorniciare.label, incorniciare.value), premi["giornata_da_incorniciare"],
         lambda x: (f"{x['giocatore']} · Giornata {x['giornata']}", f"{x['punti']} pt"))
    sf = premi["semper_fidelis"]
    if sf and len(sf) == 1:
        confronta("Stat/semper fidelis", (fedelta.label, fedelta.value), (f"{sf[0]['giocatore']} → {sf[0]['squadra'].upper()}", f"{sf[0]['volte']}× puntato sulla squadra"))
    elif sf:
        voce = (fedelta.label, fedelta.value)
        if any(voce == (f"{x['giocatore']} → {x['squadra'].upper()}", f"{x['volte']}× puntato sulla squadra") for x in sf):
            diff("Stat/semper fidelis", f"app mostra uno solo ({fedelta.label}), lo snapshot {len(sf)} pari merito", "A9")
        else:
            diff("Stat/semper fidelis", f"app {voce} snapshot {sf}", "A12")
    # Amuleto e maledetta: nome squadra (testo del foglio vs ufficiale) e conteggio (entrambe le squadre vs solo la scelta)
    for area, voce, lista, chiave in (("Stat/amuleto", amuleto, premi["squadra_amuleto"], "vittorie_portate"),
                                      ("Stat/maledetta", maledetta, premi["squadra_maledetta"], "pronostici_bruciati")):
        atteso = [(x["squadra"].upper(), x[chiave]) for x in lista]
        app_voce = (voce.label, int(voce.value.split()[0]))
        if app_voce in atteso and len(lista) == 1:
            ok(area)
        else:
            diff(area, f"app {app_voce} snapshot {atteso}", "A13/P9b")

    # Timer: ultima vinta
    didascalie = [c.value for c in scheda.caption]
    ultima = snap["statistiche"]["ultima_schedina_vinta"]
    riga_timer = next((d for d in didascalie if d.startswith("Ultima vinta")), "")
    if ultima:
        fine = in_roma(ultima["inizio_il"])
        atteso = f"Ultima vinta: **{', '.join(ultima['vincitori'])}** · Giornata {ultima['giornata']}, chiusa il {fine:%d/%m} verso le {fine:%H:%M} (fine dell'ultima partita). Si azzera alla prossima schedina vinta."
        confronta("Stat/timer", riga_timer, atteso)

    # Per un soffio
    tabelle = scheda.table
    soffi_app = [(r["Giocatore"], int(r["Giornata"]), r["Evento sbagliato"], r["Pronostico"], num(r["Quota"]))
                 for _, r in tabelle[0].value.reset_index().iterrows() if "Evento sbagliato" in tabelle[0].value.columns]
    soffi_snap = [(s["giocatore"], s["giornata"], s["partita"], s["pronostico"], s["quota"]) for s in snap["statistiche"]["per_un_soffio"]]
    if soffi_app == soffi_snap:
        ok("Stat/per un soffio")
    elif [x[:2] + x[3:] for x in soffi_app] == [x[:2] + x[3:] for x in soffi_snap]:
        diff("Stat/per un soffio", f"solo il nome partita: app (testo del foglio) {[x[2] for x in soffi_app]} "
             f"snapshot (nome ufficiale) {[x[2] for x in soffi_snap]}", "A15")
    else:
        diff("Stat/per un soffio", f"app {soffi_app} snapshot {soffi_snap}")

    # Tabella completa
    tab = tabelle[-1].value.reset_index()
    righe_app = {}
    for _, r in tab.iterrows():
        if r["Giocatore"] == "—":
            continue
        righe_app[r["Giocatore"].replace(" (ritirato)", "")] = (float(r["Win Rate %"].rstrip("%")), float(r["Quota Media"]), int(r["Vinte"]), int(r["Totali"]))
    righe_snap = {s["nome"]: (s["win_rate"], s["quota_media"], s["vinte"], s["totali"])
                  for s in snap["statistiche"]["giocatori"] + snap["statistiche"]["ritirati"]}
    confronta("Stat/tabella completa valori", righe_app, righe_snap)
    ordine_app = [r["Giocatore"].replace(" (ritirato)", "") for _, r in tab.iterrows() if r["Giocatore"] != "—"]
    ordine_snap = [s["nome"] for s in snap["statistiche"]["giocatori"] + snap["statistiche"]["ritirati"]]
    if ordine_app == ordine_snap:
        ok("Stat/tabella completa ordine")
    else:
        diff("Stat/tabella completa ordine", f"ordine diverso a parita' di win rate: app {ordine_app[:6]} snapshot {ordine_snap[:6]}", "A7")


def confronta_coppa(app, snap):
    scheda = app.tabs[4]
    corpo = scheda.get("html")[0].proto.body
    coppa = snap["coppa"]
    sfide_app = re.findall(r'<div class="coppa-sfida">(.*?)</div></div>', corpo)
    voci = re.findall(r'<span class="coppa-pos">(\d+)°</span>([^<]*)', corpo)
    voci_snap = [(g["posizione"], g["nome"]) for s in coppa["turni"][0]["sfide"] for g in s["giocatori"] if g]
    if [(int(p), n) for p, n in voci[:len(voci_snap)]] == voci_snap:
        ok("Coppa/ottavi")
    elif Counter(n for _, n in voci[:16]) == Counter(n for _, n in voci_snap):
        diff("Coppa/ottavi", "stessi 16 giocatori ma accoppiamenti/posizioni diversi a parita' (ordine del foglio vs alfabetico)", "A7")
    else:
        diff("Coppa/ottavi", f"app {voci[:16]} snapshot {voci_snap}")
    provvisorio = "provvisorio" in " ".join(c.value for c in scheda.caption)
    confronta("Coppa/definitiva", not provvisorio, coppa["definitiva"], codice="A14")
    confronta("Coppa/giornate turni", re.findall(r"(\d+)ª giornata", corpo), [str(t["giornata"]) for t in coppa["turni"]])


def confronta_regolamento(app, snap):
    scheda = app.tabs[5]
    regole = snap["regole"]
    esempio = " ".join(m.value for m in scheda.markdown)
    app_giocatori = int(re.search(r"\((\d+) giocatori", esempio).group(1))
    if app_giocatori != regole["giocatori"]:
        diff("Regolamento/giocatori", f"app {app_giocatori} snapshot {regole['giocatori']}", "P9d")
    premi_app = [float(r["Premio"].replace("€", "").replace(".", "").strip()) for _, r in scheda.table[1].value.iterrows()]
    premi_snap = [regole["obiettivo_cassa"] * x["percentuale"] / 100 for x in regole["ripartizione_premi"]]
    if premi_app != premi_snap:
        diff("Regolamento/premi", f"app {premi_app} snapshot {premi_snap}", "P9d")
    punti_app = scheda.table[0].value
    atteso = {"Combo": "combo", "Doppie Chance": "doppie_chance", "Variabili (O/U, ecc.)": "variabili", "Fisse": "fisse"}
    for etichetta, chiave in atteso.items():
        riga = punti_app.loc[etichetta]
        confronta("Regolamento/punti", (int(riga["Punti base"]), int(riga["Con quota ≥ 3.50"])),
                  (regole["punti"][chiave]["base"], regole["punti"][chiave]["quota_alta"]), dettaglio=etichetta)


def main():
    gen.carica_env()
    classifica, cassa, giocate, partite = gen.leggi_dati_veri()
    snap, avvisi = st.costruisci_snapshot_con_avvisi(classifica, cassa, giocate, partite, datetime.now(pytz.UTC))
    print(f"\n  snapshot costruito ({len(snap['partite'])} partite, {len(snap['schedine'])} schedine, {len(avvisi)} avvisi)")
    print("  avvio app.py con i dati veri (qualche minuto: giornate x giocatori)...")
    app = avvia_app()
    for nome, f in (("Classifica", confronta_classifica), ("Cassa", confronta_cassa), ("Live", confronta_live),
                    ("Confronto", confronta_confronto), ("Statistiche", confronta_statistiche),
                    ("Coppa", confronta_coppa), ("Regolamento", confronta_regolamento)):
        f(app, snap)
        print(f"    {nome}: fatto")

    print(f"\n  controlli identici: {sum(controlli.values())}")
    for area, n in sorted(controlli.items()):
        print(f"    {area}: {n}")
    per_codice = Counter(c or "NON SPIEGATA" for _, _, c in differenze)
    print(f"\n  differenze: {len(differenze)}  ->  {dict(per_codice)}")
    viste = set()
    for area, dettaglio, codice in differenze:
        if (area, codice) in viste and codice:
            continue  # una sola riga per area e codice, il resto e' lo stesso fenomeno
        viste.add((area, codice))
        print(f"    [{codice or 'NON SPIEGATA'}] {area}: {dettaglio}")
    non_spiegate = [d for d in differenze if d[2] is None]
    print("\n  " + ("OK: ogni differenza e' una voce di §13." if not non_spiegate else f"ATTENZIONE: {len(non_spiegate)} differenze NON spiegate.") + "\n")
    return 1 if non_spiegate else 0


if __name__ == "__main__":
    sys.exit(main())
