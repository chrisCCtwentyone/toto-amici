#!/usr/bin/env python3
"""Verificatore indipendente dei punteggi Toto-Amici.

Uso:
    python3 scripts/scarica_dati_verifica.py /tmp/dati.json     # sola lettura da Sheets + Football-Data
    python3 scripts/verifica_punteggi_indipendente.py /tmp/dati.json [rapporto.md]

Solo libreria standard. Implementa le regole del regolamento SENZA usare il codice
del bot (scritto il 20/10/2026 da un agente che non l'aveva letto): e' un secondo
parere, non una copia. Confronta ogni riga di Giocate, la Classifica e la Cassa
con i risultati attuali di Football-Data. Non tenerlo allineato al bot importando
le sue funzioni: perderebbe il motivo per cui esiste.
"""
import json
import re
import sys
from collections import defaultdict, OrderedDict
from decimal import Decimal

# ---------------------------------------------------------------- numeri
def num_it(s):
    """'1.674,56' -> Decimal('1674.56'); '2,1' -> 2.1; '430,00€' -> 430.00. None se illeggibile."""
    if s is None:
        return None
    s = str(s).replace("€", "").replace(" ", "").strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):  # solo punti migliaia: '1.674'
        s = s.replace(".", "")
    try:
        return Decimal(s)
    except Exception:
        return None


# ---------------------------------------------------------------- esito pronostico
DOPPIE = {"1X", "X1", "X2", "2X", "12", "21"}
FISSE = {"1", "X", "2"}
VARIABILI = {"GOAL", "NOGOAL", "OVER_2.5", "UNDER_2.5", "PARI", "DISPARI"}
ALIAS_RINOMINATI = {"OVER_1.5": "OVER_2.5", "UNDER_3.5": "UNDER_2.5"}  # per regolamento


def parte_vinta(p, h, a):
    """True/False per una parte di pronostico; None se non riconosciuta."""
    tot = h + a
    if p in FISSE or p in DOPPIE:
        esito = "1" if h > a else ("2" if a > h else "X")
        return esito in set(p) if p in DOPPIE else esito == p
    if p == "GOAL":
        return h > 0 and a > 0
    if p == "NOGOAL":
        return h == 0 or a == 0
    if p == "OVER_2.5":
        return tot >= 3
    if p == "UNDER_2.5":
        return tot <= 2
    if p == "PARI":
        return tot % 2 == 0
    if p == "DISPARI":
        return tot % 2 == 1
    return None


def valuta(pron, h, a):
    """Ritorna (stato, note): stato in vinta|persa|annullata|ND (non interpretabile). h/a None => 'non finita'."""
    note = []
    p = (pron or "").strip().upper()
    if "ANNULLATA" in p:
        return "annullata", note
    parti = [x.strip() for x in p.split("+")]
    norm = []
    for x in parti:
        if x in ALIAS_RINOMINATI:
            note.append(f"{x} trattato come {ALIAS_RINOMINATI[x]}")
            x = ALIAS_RINOMINATI[x]
        norm.append(x)
    if any(x not in FISSE | DOPPIE | VARIABILI for x in norm):
        return "ND", note
    if h is None:
        return "non finita", note
    ris = [parte_vinta(x, h, a) for x in norm]
    return ("vinta" if all(ris) else "persa"), note


def categoria(pron):
    p = (pron or "").strip().upper()
    if "+" in p:
        return "Combo"
    p = ALIAS_RINOMINATI.get(p, p)
    if p in FISSE:
        return "Fisse"
    if p in DOPPIE:
        return "Doppie Chance"
    if p in VARIABILI:
        return "Variabili"
    return None


def punti(pron, quota, stato):
    """Punti di una riga, in base a pronostico, quota ed esito atteso."""
    if stato != "vinta":
        return 0
    base = {"Combo": 6, "Fisse": 4, "Doppie Chance": 1, "Variabili": 2}[categoria(pron)]
    if quota is not None and quota >= Decimal("3.5"):
        base *= 2
    return base


# ---------------------------------------------------------------- abbinamento partite
STOP = {"fc", "calcio", "ac", "as", "ss", "ssc", "us", "bc", "cfc", "acf"}


def norm_nome(s):
    s = (s or "").lower().replace("-", " ").replace(".", " ")
    toks = [t for t in re.split(r"\s+", s) if t and t not in STOP and not t.isdigit()]
    return " ".join(toks)


def varianti_squadra(t):
    v = {norm_nome(t.get("name")), norm_nome(t.get("shortName")), (t.get("tla") or "").lower()}
    return {x for x in v if x}


def abbina(partita, matches_gg):
    """Ritorna (match, invertito) oppure (None, motivo)."""
    s = norm_nome(partita)
    trovati = []
    for m in matches_gg:
        for inv in (False, True):
            c, o = (m["awayTeam"], m["homeTeam"]) if inv else (m["homeTeam"], m["awayTeam"])
            if any(s == f"{x} {y}" for x in varianti_squadra(c) for y in varianti_squadra(o)):
                trovati.append((m["id"], m, inv))
    ids = {t[0] for t in trovati}
    if len(ids) == 1:
        return trovati[0][1], trovati[0][2]
    return None, ("nessuna partita corrispondente" if not ids else "abbinamento ambiguo")


# ---------------------------------------------------------------- self-check
def self_check():
    D = Decimal
    assert valuta("NOGOAL", 1, 3)[0] == "persa"
    assert valuta("NOGOAL", 0, 3)[0] == "vinta"
    assert valuta("GOAL", 1, 0)[0] == "persa"
    assert valuta("GOAL", 2, 2)[0] == "vinta"
    assert valuta("OVER_2.5", 2, 1)[0] == "vinta"
    assert valuta("OVER_2.5", 1, 1)[0] == "persa"
    assert valuta("UNDER_2.5", 1, 1)[0] == "vinta"
    assert valuta("UNDER_2.5", 2, 1)[0] == "persa"
    assert valuta("1+GOAL", 2, 0)[0] == "persa"
    assert valuta("1+GOAL", 2, 1)[0] == "vinta"
    assert valuta("X2", 0, 0)[0] == "vinta" and valuta("2X", 1, 0)[0] == "persa"
    assert valuta("12", 1, 1)[0] == "persa" and valuta("21", 0, 1)[0] == "vinta"
    assert valuta("PARI", 0, 0)[0] == "vinta" and valuta("DISPARI", 2, 1)[0] == "vinta"
    assert valuta("1", None, None)[0] == "non finita"
    assert valuta("BOH", 1, 1)[0] == "ND"
    assert valuta("1+ANNULLATA", 1, 1)[0] == "annullata"
    assert valuta("OVER_1.5", 1, 1)[0] == "persa"  # trattato come 2.5
    assert punti("1", D("1.5"), "vinta") == 4
    assert punti("1X", D("1.5"), "vinta") == 1
    assert punti("GOAL", D("1.5"), "vinta") == 2
    assert punti("1+GOAL", D("1.5"), "vinta") == 6
    assert punti("1", D("3.5"), "vinta") == 8          # 3,50 raddoppia
    assert punti("1", D("3.49"), "vinta") == 4
    assert punti("1+GOAL", D("5.5"), "vinta") == 12
    assert punti("1", D("5"), "persa") == 0
    assert num_it("1.674,56") == D("1674.56") and num_it("2,1") == D("2.1") and num_it("430,00€") == D("430.00")
    m = {"id": 1, "homeTeam": {"name": "Udinese Calcio", "shortName": "Udinese", "tla": "UDI"},
         "awayTeam": {"name": "Como 1907", "shortName": "Como 1907", "tla": "COM"}}
    assert abbina("Udinese - Como", [m]) == (m, False)
    assert abbina("COMO 1907 UDINESE", [m]) == (m, True)
    assert abbina("Udinese Como 1907", [m]) == (m, False)
    assert abbina("Udinese - Roma", [m])[0] is None


# ---------------------------------------------------------------- verifica
def cella(r, i):
    return r[i].strip() if len(r) > i and r[i] is not None else ""


def esito_scritto(s):
    u = s.upper()
    for k in ("VINTA", "PERSA", "IN CORSO", "ANNULLATA", "RINVIATA", "DA VERIFICARE"):
        if k in u:
            return k
    return "" if not s else "?" + s


def giorn_num(s):
    m = re.fullmatch(r"\s*Giornata\s+(\d+)\s*", s or "", re.I)
    return int(m.group(1)) if m else None


def main(path, out):
    d = json.load(open(path))
    matches = defaultdict(list)
    for m in d["matches"]:
        matches[m["matchday"]].append(m)

    righe = []        # dict per riga
    non_abb = []      # (riga, motivo)
    note_ris = []     # note regolamento (OVER_1.5 ecc.)
    vuote = 0
    for idx, r in enumerate(d["giocate"][1:], start=2):  # idx = numero di riga nel foglio
        if not any(c.strip() for c in r if c):
            vuote += 1
            continue
        gg = giorn_num(cella(r, 0))
        R = dict(riga=idx, gg=gg, giocatore=cella(r, 1).upper(), partita=cella(r, 2), tip=cella(r, 3),
                 pron=cella(r, 4), quota_s=cella(r, 5), esito_s=esito_scritto(cella(r, 6)),
                 vp_s=cella(r, 7), punti_s=cella(r, 8))
        R["quota"] = num_it(R["quota_s"])
        R["punti_w"] = None if R["punti_s"] == "" else (int(num_it(R["punti_s"])) if num_it(R["punti_s"]) is not None else None)
        R["vp"] = num_it(R["vp_s"])
        m, inv = abbina(R["partita"], matches.get(gg, [])) if gg else (None, "giornata illeggibile")
        R["match"], R["inv"], R["problemi"] = m, inv if m else None, []
        if m is None:
            R["stato"] = "NA"
            non_abb.append((R, inv))
        else:
            ft = m["score"]["fullTime"]
            fin = m["status"] == "FINISHED" and ft["home"] is not None and ft["away"] is not None
            h, a = (ft["home"], ft["away"]) if fin else (None, None)
            if inv and fin:
                h, a = a, h
            R["fd"] = f'{ft["home"]}-{ft["away"]}' if fin else f'non finita ({m["status"]})'
            R["fd_casa"] = f'{m["homeTeam"]["shortName"]}-{m["awayTeam"]["shortName"]}'
            st, nt = valuta(R["pron"], h, a)
            R["stato"] = st
            for n in nt:
                note_ris.append((R, n))
            if st == "ND":
                R["problemi"].append("pronostico non interpretabile")
        if R["quota"] is None:
            R["problemi"].append("quota illeggibile")
        R["cat"] = categoria(R["pron"])
        R["punti_a"] = punti(R["pron"], R["quota"], R["stato"]) if R["cat"] and R["stato"] in ("vinta", "persa", "annullata", "non finita") else None
        righe.append(R)

    # ---- (a) errori riga
    attesa_esito = {"vinta": "VINTA", "persa": "PERSA", "annullata": "ANNULLATA"}
    err_righe = []
    controllate = defaultdict(int)
    errate = defaultdict(int)
    per_gg_nonfinite = defaultdict(int)
    for R in righe:
        if R["stato"] in ("NA", "ND"):
            continue
        controllate[R["gg"]] += 1
        motivi = []
        if R["stato"] == "non finita":
            per_gg_nonfinite[R["gg"]] += 1
            if R["esito_s"] not in ("IN CORSO", "RINVIATA"):
                motivi.append(f'esito scritto "{R["esito_s"]}" ma partita non finita (atteso IN CORSO)')
            if (R["punti_w"] or 0) != 0:
                motivi.append(f'punti scritti {R["punti_w"]} ma partita non finita (atteso 0)')
        else:
            if R["esito_s"] != attesa_esito[R["stato"]]:
                motivi.append(f'esito scritto {R["esito_s"]} vs atteso {attesa_esito[R["stato"]]}')
            if R["punti_w"] is None and R["punti_s"] != "":
                motivi.append(f'punti illeggibili "{R["punti_s"]}"')
            elif (R["punti_w"] or 0) != R["punti_a"]:
                motivi.append(f'punti scritti {R["punti_w"] if R["punti_w"] is not None else "(vuoto)"} vs attesi {R["punti_a"]}')
        if R["cat"] and R["tip"] and R["tip"] != R["cat"]:
            motivi.append(f'tipologia scritta "{R["tip"]}" vs attesa "{R["cat"]}"')
        if motivi:
            errate[R["gg"]] += 1
            err_righe.append((R, motivi))

    # ---- schedine
    sched = OrderedDict()
    for R in righe:
        sched.setdefault((R["gg"], R["giocatore"]), []).append(R)

    def chiusa(rs, usa_scritto=False):
        stati = []
        for R in rs:
            if usa_scritto:
                stati.append({"VINTA": "vinta", "PERSA": "persa", "ANNULLATA": "annullata"}.get(R["esito_s"], "altro"))
            else:
                stati.append(R["stato"])
        if any(s == "persa" for s in stati):
            return False
        if any(s not in ("vinta", "annullata") for s in stati):
            return False
        return any(s == "vinta" for s in stati)

    # ---- (c) classifica
    cl = d["classifica"]
    intest = cl[0]
    col_gg = {giorn_num(h): i for i, h in enumerate(intest) if giorn_num(h)}
    class_rows = {}
    ritirati = set()
    for r in cl[1:]:
        if re.search(r"\(RITIRATO\)\s*$", r[0].upper()):
            ritirati.add(re.sub(r"\s*\(RITIRATO\)\s*$", "", r[0].strip().upper()))
        nome = re.sub(r"\s*\(RITIRATO\)\s*$", "", r[0].strip().upper())
        class_rows[nome] = r
    diff_class, diff_tot = [], []
    giocatori = sorted({k[1] for k in sched} | set(class_rows))
    punti_exp = defaultdict(dict)
    punti_exp_scritto = defaultdict(dict)
    anomalie_sched = []
    for (gg, g), rs in sched.items():
        ok = all(R["stato"] not in ("NA", "ND") for R in rs)
        if len(rs) != 10:
            anomalie_sched.append(f"Giornata {gg} {g}: {len(rs)} righe (attese 10)")
        chiavi = [R["match"]["id"] for R in rs if R["match"]]
        if len(set(chiavi)) != len(chiavi):
            anomalie_sched.append(f"Giornata {gg} {g}: stessa partita ripetuta nella schedina")
        somma = sum(R["punti_a"] or 0 for R in rs)
        ch = chiusa(rs)
        punti_exp[g][gg] = somma + (10 if ch else 0)
        punti_exp_scritto[g][gg] = (sum(R["punti_w"] or 0 for R in rs) + (10 if chiusa(rs, True) else 0))
        if not ok:
            anomalie_sched.append(f"Giornata {gg} {g}: contiene righe non abbinate/non interpretabili, punteggio non affidabile")
    for g in giocatori:
        if g not in class_rows:
            diff_class.append((g, None, None, None, "giocatore presente in Giocate ma non in Classifica"))
            continue
        r = class_rows[g]
        tot_exp = 0
        tot_w = 0
        for gg in sorted(col_gg):
            w = r[col_gg[gg]].strip() if len(r) > col_gg[gg] else ""
            e = punti_exp[g].get(gg)
            if e is None and w == "":
                continue
            wv = int(num_it(w)) if w != "" and num_it(w) is not None else None
            tot_exp += e or 0
            tot_w += wv or 0
            if e is None and g in ritirati:
                continue  # ritirato: righe non presenti in Giocate, non verificabile
            if e is None:
                diff_class.append((g, gg, wv, None, "giornata in Classifica senza schedina in Giocate"))
            elif wv is None:
                diff_class.append((g, gg, None, e, "giornata mancante in Classifica"))
            elif wv != e:
                diff_class.append((g, gg, wv, e, f"atteso dai punti scritti nelle righe + bonus: {punti_exp_scritto[g][gg]}"))
        pt = r[1].strip() if len(r) > 1 else ""
        ptv = int(num_it(pt)) if num_it(pt) is not None else None
        diff_tot.append((g, ptv, tot_w, tot_exp if g not in ritirati else None))

    # ---- (d) cassa
    cs = d["cassa"]
    cassa_righe = []
    for r in cs[1:]:
        if not any(c.strip() for c in r):
            continue
        m = re.fullmatch(r"\s*(.+?)\s+chiude la schedina!?\s*", cella(r, 1), re.I)
        cassa_righe.append(dict(gg=giorn_num(cella(r, 0)), nome=m.group(1).strip().upper() if m else None,
                                desc=cella(r, 1), entrata=num_it(cella(r, 2)), saldo=num_it(cella(r, 3))))
    attese = {}
    for (gg, g), rs in sched.items():
        if chiusa(rs):
            vps = [R["vp"] for R in rs if R["vp"] is not None]
            attese[(gg, g)] = vps
    diff_cassa = []
    viste = defaultdict(list)
    for c in cassa_righe:
        viste[(c["gg"], c["nome"])].append(c)
    for k, vps in attese.items():
        cs_ = viste.get(k, [])
        if not cs_:
            imp = (sum(vps) / 2) if len(vps) == 1 else None
            diff_cassa.append(("MANCANTE", k, f"schedina chiusa senza riga in Cassa (importo atteso {imp:.2f} da VP {vps[0]})" if imp is not None else f"schedina chiusa senza riga in Cassa (Vincita Potenziale: {vps})"))
        elif len(cs_) > 1:
            diff_cassa.append(("DOPPIA", k, f"{len(cs_)} righe in Cassa"))
        else:
            if len(vps) == 1:
                exp = vps[0] / 2
                if cs_[0]["entrata"] is None or abs(cs_[0]["entrata"] - exp) > Decimal("0.01"):
                    diff_cassa.append(("IMPORTO", k, f'Cassa {cs_[0]["entrata"]} vs atteso {exp:.2f} (VP {vps[0]})'))
            else:
                diff_cassa.append(("IMPORTO?", k, f"Vincita Potenziale presente su {len(vps)} righe: {vps}, importo Cassa {cs_[0]['entrata']}"))
    for k, cs_ in viste.items():
        if k not in attese:
            rs = sched.get(k)
            diff_cassa.append(("IN PIU'", k, "riga in Cassa ma schedina non chiusa" if rs else "riga in Cassa senza schedina corrispondente"))
    # saldo cumulativo
    saldo = Decimal(0)
    for c in cassa_righe:
        saldo += c["entrata"] or 0
        if c["saldo"] is not None and abs(c["saldo"] - saldo) > Decimal("0.01"):
            diff_cassa.append(("SALDO", (c["gg"], c["nome"]), f'saldo scritto {c["saldo"]} vs cumulato {saldo}'))

    # ---- rapporto
    L = []
    P = L.append
    n_ctrl = sum(controllate.values())
    P("# Rapporto di verifica indipendente - Toto-Amici")
    P("")
    P(f"- File dati: `{path}`")
    P(f"- Righe Giocate con contenuto: {len(righe)} (righe vuote ignorate: {vuote})")
    P(f"- Righe controllate (abbinate e interpretabili): **{n_ctrl}**; non abbinate: {len(non_abb)}; non interpretabili: {sum(1 for R in righe if R['stato'] == 'ND')}")
    P(f"- Righe con Esito o Punti diversi dall'atteso: **{len(err_righe)}**")
    P(f"- Righe con partita non ancora finita: {sum(per_gg_nonfinite.values())}")
    P("")
    P("## (a) Righe di Giocate diverse dall'atteso")
    P("")
    if not err_righe:
        P("Nessuna.")
    else:
        P("| Riga foglio | Gg | Giocatore | Partita | Pronostico | Quota | Risultato FD | Discrepanza |")
        P("|---|---|---|---|---|---|---|---|")
        for R, mot in err_righe:
            P(f"| {R['riga']} | {R['gg']} | {R['giocatore']} | {R['partita']} ({R['fd_casa']}{', invertita' if R['inv'] else ''}) | {R['pron']} | {R['quota_s']} | {R['fd']} | {'; '.join(mot)} |")
    P("")
    P("## (b) Righe non abbinate / non interpretabili / note di regolamento")
    P("")
    nd = [R for R in righe if R["stato"] == "ND"]
    if not non_abb and not nd:
        P("Nessuna riga non abbinata o non interpretabile.")
    for R, mot in non_abb:
        P(f"- NON ABBINATA riga {R['riga']} Gg {R['gg']} {R['giocatore']}: \"{R['partita']}\" ({mot})")
    for R in nd:
        P(f"- NON INTERPRETABILE riga {R['riga']} Gg {R['gg']} {R['giocatore']}: pronostico \"{R['pron']}\"")
    if note_ris:
        P("")
        P(f"Pronostici OVER_1.5/UNDER_3.5 trovati: {len(note_ris)}")
        for R, n in note_ris:
            P(f"- riga {R['riga']} Gg {R['gg']} {R['giocatore']} {R['partita']}: {n}")
    else:
        P("Nessun OVER_1.5 / UNDER_3.5 nel foglio.")
    if anomalie_sched:
        P("")
        P("Anomalie di struttura delle schedine:")
        for a in anomalie_sched:
            P(f"- {a}")
    else:
        P("")
        P("Struttura schedine: tutte 10 righe, nessuna partita ripetuta, nessuna riga inaffidabile.")
    # copertura: ogni schedina copre le 10 partite della giornata?
    P("")
    P("## (c) Classifica")
    P("")
    if not diff_class:
        P("Nessuna differenza nelle colonne di giornata.")
    else:
        P("| Giocatore | Gg | Scritto | Atteso | Nota |")
        P("|---|---|---|---|---|")
        for g, gg, w, e, n in diff_class:
            P(f"| {g} | {gg} | {w} | {e} | {n} |")
    P("")
    P("Punti Totali (scritto / somma colonne scritte / atteso):")
    P("")
    P("| Giocatore | Scritto | Somma colonne scritte | Atteso | Esito |")
    P("|---|---|---|---|---|")
    for g, ptv, tw, te in diff_tot:
        if te is None:
            P(f"| {g} (RITIRATO) | {ptv} | {tw} | n/v (nessuna riga in Giocate) | {'OK (totale = somma colonne)' if ptv == tw else 'DIFF totale != somma colonne'} |")
            continue
        flag = "OK" if ptv == tw == te else ("DIFF" + (" (totale scritto != somma colonne)" if ptv != tw else "") + (" (colonne != atteso)" if tw != te else ""))
        P(f"| {g} | {ptv} | {tw} | {te} | {flag} |")
    P("")
    P("## (d) Cassa")
    P("")
    P(f"Righe in Cassa: {len(cassa_righe)}; schedine chiuse attese: {len(attese)}")
    P("")
    if not diff_cassa:
        P("Nessuna differenza.")
    else:
        P("| Tipo | Gg | Giocatore | Dettaglio |")
        P("|---|---|---|---|")
        for t, k, n in sorted(diff_cassa, key=lambda x: (x[1][0] or 0, x[1][1] or "", x[0])):
            P(f"| {t} | {k[0]} | {k[1]} | {n} |")
    P("")
    P("Schedine chiuse attese per giornata: " + ", ".join(f"Gg{gg}: {sorted(g for (x, g) in attese if x == gg)}" for gg in sorted({k[0] for k in attese})))
    P("")
    P("## (e) Riepilogo per giornata")
    P("")
    P("| Giornata | Righe controllate | Righe errate | Partite non finite (righe) | Differenze Classifica | Schedine chiuse attese |")
    P("|---|---|---|---|---|---|")
    for gg in sorted(controllate):
        P(f"| {gg} | {controllate[gg]} | {errate[gg]} | {per_gg_nonfinite[gg]} | {sum(1 for x in diff_class if x[1] == gg)} | {sum(1 for (x, g) in attese if x == gg)} |")
    open(out, "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    self_check()
    print("self-check OK", file=sys.stderr)
    p = sys.argv[1]
    o = sys.argv[2] if len(sys.argv) > 2 else p.rsplit("/", 1)[0] + "/rapporto_verifica.md"
    main(p, o)
