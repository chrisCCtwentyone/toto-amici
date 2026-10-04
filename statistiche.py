"""
Logica pura delle statistiche della dashboard, separata da app.py.

app.py esegue Streamlit gia' al momento dell'import, quindi i test non possono
importarlo: qui stanno solo funzioni senza effetti collaterali (niente rete,
niente Sheets), che app.py chiama passando i dati gia' caricati.
"""
import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime, timedelta

import pytz

# Descrizione che il bot scrive in Cassa quando una schedina chiude
# ("PAOLO chiude la schedina!", vedi esegui_calcolo_risultati in bot_telegram.py).
# E' il verdetto gia' verificato: il bot la scrive solo se la schedina non ha
# righe perse, in corso, rinviate o da verificare. La dashboard non ricalcola
# nulla da sola, per non dichiarare vinta una schedina che il bot non ha chiuso.
MARCATORE_SCHEDINA_CHIUSA = "chiude la schedina"

# I fogli non registrano l'ora della vittoria: la si stima come fine dell'ultima
# partita della schedina. 90' + 15' di intervallo + recupero fanno circa 1h55.
DURATA_STIMATA_PARTITA = timedelta(hours=2)

_RE_GIORNATA = re.compile(r"^\s*giornata\s+(\d+)\s*$", re.IGNORECASE)

# Un giocatore uscito dal torneo resta in Classifica con questo suffisso nel
# nome ("PULIZZER (RITIRATO)"): i punti restano congelati, perche' il bot
# aggiorna solo le righe il cui nome coincide con un giocatore in Giocate.
# Il ritiro sta nel nome e non in una riga vuota di separazione: il bot
# riscrive l'intera Classifica e una riga vuota lo manderebbe in errore.
# La separazione visiva la fanno la dashboard e il riepilogo WhatsApp.
SUFFISSO_RITIRATO = "(RITIRATO)"


# --- Funzioni spostate da bot_telegram.py (Fase 1 del restyling) ---
# Il bot le importa da qui: servono anche allo snapshot, e l'import inverso
# (statistiche -> bot_telegram) sarebbe circolare.

def etichetta_stagione(data_inizio):
    """Da "2026-08-23" ricava "2026-27".

    La Serie A va da agosto a maggio, quindi una stagione sta a cavallo di due
    anni solari e non basta l'anno della data.
    """
    # Deve essere una data ISO tipo "2026-08-23": un input malformato deve dare
    # None, non un'etichetta plausibile ma sbagliata usata poi per nominare fogli.
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(data_inizio or "")):
        return None
    anno = int(str(data_inizio)[:4])
    return f"{anno}-{str(anno + 1)[2:]}"


def estrai_numero(testo):
    """Legge un numero scritto in formato italiano ("1.674,56" = milleseicento...).

    ATTENZIONE: questa funzione legge anche le vincite che finiscono in Cassa.
    La versione precedente faceva solo replace(',', '.'), quindi "1.674,56"
    diventava "1.674.56" e il match si fermava a 1.674 -> in Cassa sarebbe finito
    0,84 EUR invece di 837,28 EUR. Nessun dato storico ne e' stato intaccato
    (l'unica schedina chiusa valeva 855,70, sotto i mille), ma sarebbe successo
    alla prima vincita a quattro cifre. Vedi PROJECT_LOG.md, Sessione 8.
    """
    try:
        s = re.sub(r'[^\d.,]', '', str(testo))
        if ',' in s:
            # Formato italiano: il punto separa le migliaia, la virgola i decimali.
            s = s.replace('.', '').replace(',', '.')
        match = re.search(r'\d+(?:\.\d+)?', s)
        return float(match.group()) if match else 0.0
    except: return 0.0


def e_ritirato(nome):
    return str(nome).strip().upper().endswith(SUFFISSO_RITIRATO)


def nome_senza_ritiro(nome):
    """"PULIZZER (RITIRATO)" -> "PULIZZER". Gli altri nomi restano invariati."""
    nome = str(nome).strip()
    if e_ritirato(nome):
        return nome[: -len(SUFFISSO_RITIRATO)].strip()
    return nome


# Chi ha preso il posto di un ritirato. Le schedine del ritirato in Giocate
# sono state rinominate col nome del sostituto (Sessione 20), quindi le
# statistiche del ritirato si ricavano dalle schedine del sostituto fino
# all'ultima giornata che ha punti nella riga congelata della Classifica.
SOSTITUTI_DEI_RITIRATI = {"PULIZZER": "SIRACUSA"}


def ultima_giornata_con_punti(riga_classifica):
    """Numero dell'ultima colonna "Giornata N" non vuota di una riga di
    Classifica (dict colonna -> valore). None se non ce n'e' nessuna."""
    numeri = [
        numero_giornata(col) for col, valore in riga_classifica.items()
        if numero_giornata(col) is not None and str(valore).strip() != ""
    ]
    return max(numeri) if numeri else None


def righe_del_ritirato(righe_giocate, nome_ritirato, ultima_giornata):
    """Le righe di Giocate (dict con "Giornata" e "Giocatore") che
    appartengono al ritirato: quelle del sostituto fino a ultima_giornata.
    Lista vuota se il ritirato non ha un sostituto noto."""
    sostituto = SOSTITUTI_DEI_RITIRATI.get(nome_senza_ritiro(nome_ritirato).upper())
    if not sostituto or ultima_giornata is None:
        return []
    righe = []
    for r in righe_giocate:
        n = numero_giornata(r.get("Giornata"))
        if (str(r.get("Giocatore", "")).strip().upper() == sostituto
                and n is not None and n <= ultima_giornata):
            righe.append(r)
    return righe


def numero_giornata(etichetta):
    """"Giornata 12" -> 12. Qualsiasi altra forma -> None.

    Confronto per numero, mai per sottostringa: "1" dentro "Giornata 12" ha gia'
    causato un bug che riscriveva 13 giornate (PROJECT_LOG.md, Sessione 13).
    """
    m = _RE_GIORNATA.match(str(etichetta))
    return int(m.group(1)) if m else None


def schedine_chiuse_ultima_giornata(righe_cassa):
    """Dalle righe di Cassa ricava l'ultima giornata con almeno una schedina chiusa.

    righe_cassa: sequenza di coppie (giornata, descrizione).
    Restituisce (numero_giornata, [giocatori]) oppure None se nessuna schedina
    e' mai stata chiusa. L'ordine delle righe nel foglio non conta: una
    correzione manuale puo' metterle fuori sequenza.
    """
    per_giornata = {}
    for giornata, descrizione in righe_cassa:
        descrizione = str(descrizione)
        pos = descrizione.lower().find(MARCATORE_SCHEDINA_CHIUSA)
        n = numero_giornata(giornata)
        if pos <= 0 or n is None:
            continue
        giocatore = descrizione[:pos].strip()
        if giocatore and giocatore.lower() not in [g.lower() for g in per_giornata.get(n, [])]:
            per_giornata.setdefault(n, []).append(giocatore)
    if not per_giornata:
        return None
    ultima = max(per_giornata)
    return ultima, per_giornata[ultima]


def leggi_orario_utc(utc_date_str):
    """"2026-08-23T18:45:00Z" (formato Football-Data) -> datetime UTC, oppure None."""
    try:
        return datetime.strptime(str(utc_date_str), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
    except ValueError:
        return None


def momento_fine_schedina(partite_schedina, orari_inizio):
    """Momento stimato in cui la schedina e' stata vinta: fine dell'ultima partita.

    partite_schedina: nomi ufficiali delle partite giocate nella schedina.
    orari_inizio: dict nome ufficiale -> datetime di inizio (aware).

    Se anche una sola partita non ha un orario noto restituisce None invece di
    stimare sulle altre: proprio quella potrebbe essere l'ultima, e il timer
    partirebbe da un momento sbagliato senza che nessuno se ne accorga.
    """
    partite = set(partite_schedina)
    if not partite or any(orari_inizio.get(p) is None for p in partite):
        return None
    return max(orari_inizio[p] for p in partite) + DURATA_STIMATA_PARTITA


def scomponi_durata(secondi_totali):
    """Secondi -> (settimane, giorni, ore, minuti, secondi). Negativo = zero.

    Il riquadro in app.py fa lo stesso conto in JavaScript ogni secondo; questa
    versione esiste per fissarne il comportamento nei test.
    """
    s = max(0, int(secondi_totali))
    settimane, s = divmod(s, 7 * 24 * 3600)
    giorni, s = divmod(s, 24 * 3600)
    ore, s = divmod(s, 3600)
    minuti, s = divmod(s, 60)
    return settimane, giorni, ore, minuti, s


def schedine_perse_per_un_soffio(righe):
    """Schedine perse per un solo evento: esattamente una riga PERSA, tutte le
    altre VINTA (o ANNULLATA, che non conta ne' a favore ne' contro).

    righe: dizionari con le colonne di Giocate (Giornata, Giocatore, Partita,
    Pronostico, Quota, Esito). Esito puo' essere il testo del foglio o l'enum
    di esito_da_testo; Quota il testo o un numero.

    Serve una schedina gia' decisa del tutto: basta una riga in corso, rinviata
    o da verificare per escluderla. Altrimenti una schedina ancora aperta
    comparirebbe come "persa per un soffio" e magari si brucia alla partita dopo.
    Restituisce una lista di dizionari, dalla giornata piu' recente. La quota
    e' un numero (None se vuota o illeggibile); quota_testo e' come scritta nel
    foglio, per chi la mostra cosi' com'e' (la dashboard Streamlit).
    """
    schedine = {}
    for riga in righe:
        n = numero_giornata(riga.get("Giornata", ""))
        giocatore = str(riga.get("Giocatore", "")).strip()
        if n is None or not giocatore:
            continue
        schedine.setdefault((n, giocatore.lower()), (giocatore, []))[1].append(riga)

    risultato = []
    for (n, _), (giocatore, righe_schedina) in schedine.items():
        esiti = [esito_da_testo(r.get("Esito", "")) for r in righe_schedina]
        perse = [i for i, e in enumerate(esiti) if e == "persa"]
        if len(perse) != 1:
            continue
        altre = [e for i, e in enumerate(esiti) if i != perse[0]]
        if "vinta" not in altre:
            continue
        if not all(e in ("vinta", "annullata") for e in altre):
            continue
        persa = righe_schedina[perse[0]]
        quota_grezza = persa.get("Quota", "")
        risultato.append({
            "giocatore": giocatore,
            "giornata": n,
            "partita": str(persa.get("Partita", "")).strip(),
            "pronostico": str(persa.get("Pronostico", "")).strip(),
            "quota": _quota_o_none(quota_grezza),
            "quota_testo": str(quota_grezza).strip(),
        })
    return sorted(risultato, key=lambda s: (-s["giornata"], s["giocatore"].lower()))


def scelta_del_gruppo_dati(pronostici_per_giocatore):
    """Il pronostico piu' giocato su una partita, come dati (per lo snapshot).

    pronostici_per_giocatore: dict giocatore -> pronostici giocati su quella
    partita. Chi chiama passa solo i voti validi: le selezioni annullate non
    votano. Ogni giocatore conta una volta per pronostico, anche se lo ha su
    piu' righe. Conta solo il pronostico identico: "1+OVER_2.5" non vale come "1".

    Restituisce {"tipo", "pronostici", "voti", "su"}:
    - "maggioranza": i pronostici a pari voti piu' alto (in ordine alfabetico);
    - "tutti_diversi": nessun pronostico scelto da almeno due giocatori (con
      piu' di un giocatore);
    - "nessuna": nessun pronostico valido.
    """
    conteggi = {}
    giocatori = 0
    for pronostici in pronostici_per_giocatore.values():
        distinti = {str(p).strip().upper() for p in pronostici if str(p).strip()}
        if not distinti:
            continue
        giocatori += 1
        for p in distinti:
            conteggi[p] = conteggi.get(p, 0) + 1
    if not conteggi:
        return {"tipo": "nessuna", "pronostici": [], "voti": 0, "su": 0}
    massimo = max(conteggi.values())
    if massimo == 1 and giocatori > 1:
        return {"tipo": "tutti_diversi", "pronostici": [], "voti": 1, "su": giocatori}
    migliori = sorted(p for p, n in conteggi.items() if n == massimo)
    return {"tipo": "maggioranza", "pronostici": migliori, "voti": massimo, "su": giocatori}


def scelta_del_gruppo(pronostici_per_giocatore):
    """Il pronostico piu' giocato su una partita, per la colonna del Confronto Giocate.

    Formatta il risultato di scelta_del_gruppo_dati (stessa regola, stessi
    argomenti): "1 · 5 su 7", "1 / X · 3 su 7" in caso di parita', oppure
    "Tutti diversi" se nessun pronostico e' stato scelto da almeno due
    giocatori, "—" se non c'e' nessun pronostico.
    """
    dati = scelta_del_gruppo_dati(pronostici_per_giocatore)
    if dati["tipo"] == "nessuna":
        return "—"
    if dati["tipo"] == "tutti_diversi":
        return "Tutti diversi"
    return f"{' / '.join(dati['pronostici'])} · {dati['voti']} su {dati['su']}"


# Posizioni in classifica nell'ordine del tabellone degli ottavi (schema classico
# dei tornei a 16): 1 e 2 stanno in meta' opposte e si possono incontrare solo in
# finale, 1 e 4 al massimo in semifinale, 1 e 8 al massimo nei quarti.
ORDINE_TABELLONE_16 = [1, 16, 8, 9, 5, 12, 4, 13, 6, 11, 3, 14, 7, 10, 2, 15]


def tabellone_ottavi(giocatori_in_classifica):
    """Ottavi della Coppa dalla classifica attuale: 1° contro 16°, 2° contro 15°...

    giocatori_in_classifica: nomi gia' in ordine di classifica, senza ritirati
    (lo stesso elenco della scheda Classifica, spareggi compresi).
    Restituisce 8 sfide nell'ordine del tabellone, ciascuna come
    ((posizione, nome), (posizione, nome)); le sfide 1-2 vanno nel primo quarto,
    3-4 nel secondo e cosi' via. None se i partecipanti non sono esattamente 16:
    il tabellone e' fatto per 16 e non si indovina chi escludere o ripescare.
    """
    nomi = [str(g).strip() for g in giocatori_in_classifica if str(g).strip()]
    if len(nomi) != 16:
        return None
    posti = [(pos, nomi[pos - 1]) for pos in ORDINE_TABELLONE_16]
    return [(posti[i], posti[i + 1]) for i in range(0, 16, 2)]


# --- Coppa: calendario, tabellone definitivo, passaggi di turno ---
# La Coppa si gioca sulle ultime 4 giornate di Serie A (38): ottavi alla 35ª,
# quarti alla 36ª, semifinali alla 37ª, finale alla 38ª. Il tabellone segue la
# classifica fino alla 34ª e da li' resta fisso.
GIORNATE_CAMPIONATO = 38
TURNI_COPPA = ["Ottavi", "Quarti", "Semifinali", "Finale"]
PRIMA_GIORNATA_COPPA = GIORNATE_CAMPIONATO - len(TURNI_COPPA) + 1
ULTIMA_GIORNATA_TABELLONE = PRIMA_GIORNATA_COPPA - 1


def _punti_cella(valore):
    # Come il bot quando somma la Classifica: contano solo le celle numeriche.
    testo = str(valore).strip()
    return int(testo) if testo.isdigit() else 0


def classifica_per_coppa(righe_classifica, righe_giocate):
    """Nomi in ordine di classifica per il tabellone: punti delle giornate fino
    alla ULTIMA_GIORNATA_TABELLONE, a parita' piu' pronostici vinti nelle stesse
    giornate, a parita' ancora l'ordine del foglio. Ritirati esclusi.

    Fino alla 34ª giornata coincide con la scheda Classifica; dalla 35ª in poi
    ignora i punti nuovi, cosi' il tabellone non cambia a Coppa iniziata.
    righe_classifica / righe_giocate: dizionari con le colonne dei due fogli.
    """
    vittorie = {}
    for r in righe_giocate:
        n = numero_giornata(r.get("Giornata", ""))
        if n is not None and n <= ULTIMA_GIORNATA_TABELLONE and "VINTA" in str(r.get("Esito", "")):
            chi = str(r.get("Giocatore", ""))
            vittorie[chi] = vittorie.get(chi, 0) + 1

    voci = []
    for r in righe_classifica:
        nome = str(r.get("Giocatore", "")).strip()
        if not nome or e_ritirato(nome):
            continue
        punti = 0
        for colonna, valore in r.items():
            n = numero_giornata(colonna)
            if n is not None and n <= ULTIMA_GIORNATA_TABELLONE:
                punti += _punti_cella(valore)
        voci.append((nome, punti, vittorie.get(str(r.get("Giocatore", "")), 0)))
    voci.sort(key=lambda v: (-v[1], -v[2]))
    return [v[0] for v in voci]


def punti_per_giornata(righe_classifica):
    """{numero giornata: {nome: punti}} dalle colonne "Giornata N" della
    Classifica. Una cella vuota non compare: quel giocatore non ha ancora punti
    in quella giornata (diverso da 0 punti)."""
    risultato = {}
    for r in righe_classifica:
        nome = str(r.get("Giocatore", "")).strip()
        if not nome:
            continue
        for colonna, valore in r.items():
            n = numero_giornata(colonna)
            if n is not None and str(valore).strip() != "":
                risultato.setdefault(n, {})[nome] = _punti_cella(valore)
    return risultato


def giornate_concluse(righe_giocate):
    """Giornate con tutte le righe di Giocate gia' decise (VINTA, PERSA o
    ANNULLATA). Basta una riga in corso, rinviata, da verificare o senza esito
    perche' la giornata non sia conclusa: i punti potrebbero ancora cambiare,
    quindi nessun passaggio di turno va dichiarato."""
    stato = {}
    for r in righe_giocate:
        n = numero_giornata(r.get("Giornata", ""))
        if n is None or not str(r.get("Giocatore", "")).strip():
            continue
        esito = str(r.get("Esito", ""))
        decisa = any(t in esito for t in ("VINTA", "PERSA", "ANNULLATA"))
        stato[n] = stato.get(n, True) and decisa
    return {n for n, tutte_decise in stato.items() if tutte_decise}


def turni_coppa(ottavi, punti_giornate, concluse):
    """Il tabellone completo, turno per turno, a partire dagli ottavi.

    ottavi: risultato di tabellone_ottavi (8 sfide di (posizione, nome)).
    punti_giornate: risultato di punti_per_giornata.
    concluse: insieme delle giornate concluse (giornate_concluse).

    Restituisce 4 liste (ottavi, quarti, semifinali, finale) di sfide, ognuna
    {"giornata", "giocatori": [voce, voce], "punti": [int|None, int|None],
    "vincente": 0 | 1 | None}. Una voce e' (posizione, nome) oppure None se il
    giocatore non e' ancora noto (sfida precedente non conclusa).
    Passa chi fa piu' punti nella giornata del turno; a parita' chi era piu' in
    alto nella classifica del tabellone. Il vincente si dichiara solo a giornata
    conclusa; chi non ha punti in una giornata conclusa ne ha fatti 0.
    """
    partecipanti = [voce for sfida in ottavi for voce in sfida]
    turni = []
    for i in range(len(TURNI_COPPA)):
        giornata = PRIMA_GIORNATA_COPPA + i
        punti_g = punti_giornate.get(giornata, {})
        sfide, prossimi = [], []
        for k in range(0, len(partecipanti), 2):
            coppia = [partecipanti[k], partecipanti[k + 1]]
            punti = [punti_g.get(v[1]) if v else None for v in coppia]
            vincente = None
            if all(coppia) and giornata in concluse:
                (pos_a, _), (pos_b, _) = coppia
                pa, pb = (p or 0 for p in punti)
                vincente = 0 if (pa, -pos_a) > (pb, -pos_b) else 1
            sfide.append({"giornata": giornata, "giocatori": coppia, "punti": punti, "vincente": vincente})
            prossimi.append(coppia[vincente] if vincente is not None else None)
        turni.append(sfide)
        partecipanti = prossimi
    return turni


def ordina_partite_per_orario(partite, orari_inizio):
    """Partite in ordine di calcio d'inizio, per il Confronto Giocate.

    partite: nomi delle partite da ordinare (l'indice della tabella).
    orari_inizio: dict nome partita -> datetime di inizio (aware) o None.

    Chi ha un orario viene prima, dal piu' presto al piu' tardi; a parita' di
    orario l'ordine e' alfabetico. Le partite senza orario (nome non
    riconosciuto dall'API, o API non raggiungibile) non vengono buttate via:
    finiscono in fondo in ordine alfabetico, cosi' restano sempre visibili.
    """
    conosciute, sconosciute = [], []
    for partita in partite:
        (conosciute if orari_inizio.get(partita) else sconosciute).append(partita)
    conosciute.sort(key=lambda p: (orari_inizio[p], str(p)))
    sconosciute.sort(key=str)
    return conosciute + sconosciute


# ==========================================================================
# SNAPSHOT (Fase 1 del restyling, schema in restyling/snapshot-schema.md)
# ==========================================================================
# Tutto cio' che il sito nuovo mostra viene calcolato qui, con funzioni pure:
# niente rete, niente Sheets, niente pandas. Chi legge i fogli e chiama
# Football-Data e' il chiamante, che passa i dati gia' letti.
# Il numero delle funzioni (N1-N23) e' quello del §15 dello schema.

VERSIONE_SCHEMA = 1

ESITI = ("vinta", "persa", "in_corso", "annullata", "rinviata", "da_verificare", "da_giocare")

# Chiave del riepilogo di una schedina per ogni esito (§7.2).
_CHIAVE_RIEPILOGO = {
    "vinta": "vinte", "persa": "perse", "in_corso": "in_corso", "rinviata": "rinviate",
    "da_verificare": "da_verificare", "annullata": "annullate", "da_giocare": "da_giocare",
}

# Testo dell'esito come lo scrive il bot: serve solo a ridare alle funzioni
# vecchie (che leggono il testo del foglio) un dato nel formato che si aspettano.
_TESTO_ESITO = {
    "vinta": "✅ VINTA", "persa": "❌ PERSA", "in_corso": "⏳ IN CORSO",
    "annullata": "➖ ANNULLATA", "rinviata": "⏸️ RINVIATA",
    "da_verificare": "⚠️ DA VERIFICARE", "da_giocare": "",
}

# Pausa notturna del bot (bot_telegram.py: PAUSA_NOTTURNA_INIZIO/FINE). Un test
# tiene allineate le due copie.
PAUSA_NOTTURNA = {"inizio": "02:00", "fine": "07:30", "fuso": "Europe/Rome"}
SOGLIA_ALLARME_MINUTI = 120
OBIETTIVO_CASSA = 3200.0

# N20 — i numeri del Regolamento (§10). Un test li confronta con
# LIMITI_SCHEDINA e calcola_punteggio_partita del bot, cosi' le copie non si
# scollano.
REGOLE = {
    "costo_giornata": 5,
    "quota_partecipazione": 200,
    "scadenza_quota_giornata": 36,
    "quota_cassa_su_vincita": 0.5,
    "minuti_pubblicazione_prima_partita": 5,
    "soglia_quota_doppia": 3.5,
    "bonus_chiusura": 10,
    "giocatori": 16,
    "obiettivo_cassa": 3200,
    "composizione": {"combo": 1, "doppie_chance": 2, "variabili": 3, "fisse": 4},
    "punti": {
        "combo": {"base": 6, "quota_alta": 12},
        "doppie_chance": {"base": 1, "quota_alta": 2},
        "variabili": {"base": 2, "quota_alta": 4},
        "fisse": {"base": 4, "quota_alta": 8},
    },
    "ripartizione_premi": [
        {"posizione": 1, "percentuale": 40}, {"posizione": 2, "percentuale": 27},
        {"posizione": 3, "percentuale": 17}, {"posizione": 4, "percentuale": 10},
        {"posizione": 5, "percentuale": 6},
    ],
}


# --- Lettura dei fogli ---

def _riempi(riga, n):
    riga = list(riga)
    return riga + [""] * (n - len(riga))


def _vuota(valore):
    return str(valore if valore is not None else "").strip() == ""


def righe_da_valori(valori):
    """Da `values` di Sheets (prima riga = intestazione) a una lista di
    dizionari colonna -> valore, con le righe accorciate riempite di vuoti.
    Righe completamente vuote scartate."""
    if not valori:
        return []
    intestazione = [str(c).strip() for c in valori[0]]
    return [
        dict(zip(intestazione, _riempi(r, len(intestazione))))
        for r in valori[1:] if any(not _vuota(c) for c in r)
    ]


def _intero_o_errore(valore, dove, vuoto=0):
    """Un intero scritto in una cella. Cella vuota -> `vuoto`; qualsiasi altra
    cosa non numerica -> ValueError (mai 0 punti senza traccia, §16 D12)."""
    testo = str(valore if valore is not None else "").strip()
    if testo == "":
        return vuoto
    if re.fullmatch(r"-?\d+", testo):
        return int(testo)
    raise ValueError(f"{dove}: valore non numerico {testo!r}")


def _numero_o_errore(valore, dove):
    testo = str(valore if valore is not None else "").strip()
    if not re.search(r"\d", testo):
        raise ValueError(f"{dove}: importo non leggibile {testo!r}")
    return estrai_numero(testo)


def _quota_o_none(valore):
    """Quota come numero. Vuota, illeggibile o non positiva -> None: una quota
    mancante non e' una quota 0 e non deve entrare nelle medie (§16 D4)."""
    if isinstance(valore, bool):
        return None
    if isinstance(valore, (int, float)):
        q = float(valore)
    else:
        testo = str(valore if valore is not None else "").strip()
        if not re.search(r"\d", testo):
            return None
        q = estrai_numero(testo)
    return q if q > 0 else None


# --- N1, N2: enum ---

# Ordine delle sottostringhe identico a quello storico di app.py.
_ORDINE_ESITI = (
    ("VINTA", "vinta"), ("PERSA", "persa"), ("VERIFICARE", "da_verificare"),
    ("RINVIATA", "rinviata"), ("CORSO", "in_corso"), ("ANNULLATA", "annullata"),
)


def esito_da_testo(testo):
    """N1 — Testo dell'esito nel foglio ("✅ VINTA") -> enum minuscolo (§12).

    Cella vuota -> "da_giocare". Testo non riconosciuto -> "da_verificare",
    mai "vinta": il progetto non fa vincere per default. E' l'UNICO punto in
    cui si interpreta il testo dell'esito; idempotente sugli enum.
    """
    testo = str(testo if testo is not None else "").strip()
    if not testo:
        return "da_giocare"
    if testo.lower() in ESITI:
        return testo.lower()
    maiuscolo = testo.upper()
    for frammento, esito in _ORDINE_ESITI:
        if frammento in maiuscolo:
            return esito
    return "da_verificare"


_TIPOLOGIE = {"combo": "combo", "fisse": "fisse", "doppiechance": "doppie_chance", "variabili": "variabili"}


def tipologia_da_testo(testo):
    """N2 — "Doppie Chance" -> "doppie_chance". Sconosciuta -> None."""
    return _TIPOLOGIE.get(re.sub(r"[\s_]+", "", str(testo if testo is not None else "").strip().lower()))


# --- N3: Giocate pulita ---

def pulisci_giocate(valori):
    """N3 — Da `values` di Giocate!A:I (con intestazione) alle righe pulite.

    Ogni riga: {giornata:int, giocatore (MAIUSCOLO), partita_testo, tipologia,
    pronostico, quota:float|None, esito (enum), vincita:float, punti:int,
    riga_foglio:int}. Numeri veri, giornata intera: una conversione sola.

    Restituisce (righe, scartate): `scartate` e' una lista di (riga_foglio,
    motivo) per le righe ignorate (intestazione ripetuta, senza giocatore,
    giornata non valida). Non va nello snapshot ma nel log del bot. Le righe
    completamente vuote si saltano senza traccia.
    """
    righe, scartate = [], []
    if not valori:
        return righe, scartate
    prima = _riempi(valori[0], 2)
    inizio = 1 if (str(prima[0]).strip().lower() == "giornata" or str(prima[1]).strip().lower() == "giocatore") else 0
    for numero, r in enumerate(valori[inizio:], start=inizio + 1):
        r = _riempi(r, 9)
        if all(_vuota(c) for c in r):
            continue
        giocatore = str(r[1]).strip().upper()
        n = numero_giornata(r[0])
        if giocatore == "GIOCATORE":
            scartate.append((numero, "intestazione ripetuta"))
        elif not giocatore:
            scartate.append((numero, "riga senza giocatore"))
        elif n is None:
            scartate.append((numero, f"giornata non valida ({str(r[0]).strip()!r})"))
        else:
            righe.append({
                "giornata": n,
                "giocatore": giocatore,
                "partita_testo": str(r[2]).strip(),
                "tipologia": tipologia_da_testo(r[3]),
                "pronostico": str(r[4]).strip(),
                "quota": _quota_o_none(r[5]),
                "esito": esito_da_testo(r[6]),
                "vincita": estrai_numero(r[7]) if not _vuota(r[7]) else 0.0,
                "punti": int(estrai_numero(r[8])) if not _vuota(r[8]) else 0,
                "riga_foglio": numero,
            })
    return righe, scartate


# --- N4, N11, N12: Cassa ---

def movimenti_cassa(valori):
    """N4 — Da `values` di Cassa!A:D a [{giornata:int|None, descrizione,
    entrata:float|None, saldo:float|None}], nell'ordine del foglio.

    Un importo scritto ma illeggibile solleva ValueError: meglio non
    pubblicare che mostrare una Cassa sbagliata.
    """
    if not valori:
        return []
    inizio = 1 if str(_riempi(valori[0], 3)[2]).strip() == "Entrate" else 0
    movimenti = []
    for numero, r in enumerate(valori[inizio:], start=inizio + 1):
        r = _riempi(r, 4)
        if all(_vuota(c) for c in r):
            continue
        movimenti.append({
            "giornata": numero_giornata(r[0]),
            "descrizione": str(r[1]).strip(),
            "entrata": None if _vuota(r[2]) else _numero_o_errore(r[2], f"Cassa riga {numero} Entrate"),
            "saldo": None if _vuota(r[3]) else _numero_o_errore(r[3], f"Cassa riga {numero} Saldo Totale"),
        })
    return movimenti


def riepilogo_cassa(movimenti, obiettivo):
    """N11 — saldo (SOMMA delle entrate, come saldo_cassa del bot: l'ultima
    cella "Saldo Totale" puo' divergere dopo una correzione a mano),
    obiettivo, completamento (0..1) e movimenti."""
    saldo = round(math.fsum(m["entrata"] for m in movimenti if m["entrata"] is not None), 2)
    return {
        "saldo": saldo,
        "obiettivo": float(obiettivo),
        "completamento": min(saldo / obiettivo, 1.0) if obiettivo else 0.0,
        "obiettivo_raggiunto": saldo >= obiettivo,
        "movimenti": [dict(m) for m in movimenti],
    }


def versamenti_per_giornata(movimenti, giornate_giocate):
    """N12 — [{giornata, versato}] per ogni giornata presente in Cassa o in
    Giocate (anche a zero), per giornata crescente. Giornate intere: due
    scritture della stessa giornata sono una barra sola."""
    versato = {}
    for m in movimenti:
        if m["giornata"] is not None and m["entrata"] is not None:
            versato[m["giornata"]] = versato.get(m["giornata"], 0.0) + m["entrata"]
    giornate = {m["giornata"] for m in movimenti if m["giornata"] is not None} | set(giornate_giocate)
    return [{"giornata": g, "versato": round(versato.get(g, 0.0), 2)} for g in sorted(giornate)]


# --- N5, N6: Football-Data e abbinamento delle partite ---

def _iso_utc(dt):
    return dt.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def partite_della_stagione(matches):
    """N5 — Dalla risposta di UNA chiamata a Football-Data
    (/competitions/SA/matches, senza matchday) a
    {"stagione": "2026-27" | None, "per_giornata": {giornata: [partita]}}.

    partita = {id, nome ("casa - ospite" coi nomi completi), casa:{name,
    shortName}, ospite:{...}, inizio: datetime UTC | None}. `matches` e' la
    risposta intera o la sola lista. Le partite malformate si saltano; se non
    ne resta nessuna solleva ValueError.
    """
    if isinstance(matches, dict):
        matches = matches.get("matches", [])
    per_giornata, stagione = {}, None
    for m in matches or []:
        try:
            id_, giornata = int(m["id"]), int(m["matchday"])
            casa, ospite = m["homeTeam"], m["awayTeam"]
            nome_casa, nome_ospite = str(casa["name"]).strip(), str(ospite["name"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not nome_casa or not nome_ospite:
            continue
        if stagione is None:
            stagione = etichetta_stagione((m.get("season") or {}).get("startDate"))
        per_giornata.setdefault(giornata, []).append({
            "id": id_,
            "nome": f"{nome_casa} - {nome_ospite}",
            "casa": {"name": nome_casa, "shortName": str(casa.get("shortName") or "").strip()},
            "ospite": {"name": nome_ospite, "shortName": str(ospite.get("shortName") or "").strip()},
            "inizio": leggi_orario_utc(m.get("utcDate")),
        })
    if not per_giornata:
        raise ValueError("Football-Data: nessuna partita utilizzabile nella risposta")
    return {"stagione": stagione, "per_giornata": per_giornata}


# Suffissi societari che il foglio e Football-Data scrivono a volte si' e a volte no.
_SUFFISSI_SOCIETARI = {"fc", "ac", "as", "ss", "ssc", "us", "acf", "afc", "cfc", "bc", "cd", "sc", "calcio"}


def _forma_squadra(testo):
    """Nome squadra ridotto alla sostanza: minuscolo, senza accenti, senza
    suffissi societari ("FC", "AC", "Calcio") e senza anni di fondazione
    ("1907"). "Bologna FC 1909" e "Bologna" danno la stessa forma."""
    t = unicodedata.normalize("NFKD", str(testo)).encode("ascii", "ignore").decode().lower().replace(".", "")
    parole = [p for p in re.split(r"[^a-z0-9]+", t)
              if p and p not in _SUFFISSI_SOCIETARI and not re.fullmatch(r"\d{4}", p)]
    return " ".join(parole)


def _forme_squadra(squadra):
    return {f for f in (_forma_squadra(squadra.get("name", "")), _forma_squadra(squadra.get("shortName", ""))) if f}


def abbina_partita(nome_sheet, partite_giornata):
    """N6 — Abbina il testo del foglio ("Pisa - Cremo") a UNA delle partite
    della STESSA giornata, per uguaglianza delle forme normalizzate (non per
    sottostringa) con name e shortName di casa e ospite; prova anche le
    squadre invertite. None se nessuna partita corrisponde o se ne
    corrispondono due: il chiamante non indovina (§7.3 dello schema)."""
    parti = str(nome_sheet).split("-")
    if len(parti) != 2:
        return None
    a, b = _forma_squadra(parti[0]), _forma_squadra(parti[1])
    if not a or not b:
        return None
    trovate = []
    for p in partite_giornata:
        casa, ospite = _forme_squadra(p["casa"]), _forme_squadra(p["ospite"])
        if (a in casa and b in ospite) or (a in ospite and b in casa):
            trovate.append(p)
    return trovate[0] if len(trovate) == 1 else None


def abbina_righe_a_partite(righe, per_giornata):
    """Abbina ogni riga pulita a una partita (N6). Restituisce (righe_abbinate,
    info): le righe con in piu' `partita_id`, e {id: {id, giornata, nome,
    ufficiale, casa, ospite, inizio}}. Le righe senza partita trovata ricevono
    un id NEGATIVO (-1, -2...), valido solo dentro lo snapshot, assegnato in
    ordine di (giornata, testo) cosi' non dipende dall'ordine del foglio.
    """
    info, parziali, non_ufficiali = {}, [], {}
    for r in righe:
        giornata = r["giornata"]
        partita = abbina_partita(r["partita_testo"], per_giornata.get(giornata, []))
        if partita:
            info.setdefault(partita["id"], {
                "id": partita["id"], "giornata": giornata, "nome": partita["nome"], "ufficiale": True,
                "casa": partita["casa"]["name"], "ospite": partita["ospite"]["name"],
                "inizio": partita["inizio"],
            })
            parziali.append((r, partita["id"], None))
        else:
            chiave = (giornata, " ".join(r["partita_testo"].lower().split()))
            non_ufficiali.setdefault(chiave, r["partita_testo"])
            parziali.append((r, None, chiave))
    id_di = {}
    for i, chiave in enumerate(sorted(non_ufficiali), start=1):
        id_di[chiave] = -i
        info[-i] = {"id": -i, "giornata": chiave[0], "nome": non_ufficiali[chiave], "ufficiale": False,
                    "casa": None, "ospite": None, "inizio": None}
    abbinate = [{**r, "partita_id": pid if pid is not None else id_di[chiave]} for r, pid, chiave in parziali]
    return abbinate, info


# --- N7, N8: partite e schedine ---

def _voto_valido(riga):
    """Le selezioni annullate non votano (§17.18): ne' l'esito `annullata` ne'
    la dicitura "(ANNULLATA ECCESSO)" nel pronostico, che c'e' gia' prima del
    primo calcolo."""
    return riga["esito"] != "annullata" and "ANNULLATA" not in riga["pronostico"].upper()


def costruisci_partite_e_schedine(righe, per_giornata, abbinate=None):
    """N8 — (partite, schedine) come da §7 dello schema.

    `righe` sono le righe pulite (N3) e `per_giornata` il risultato di N5.
    `abbinate` e' il risultato gia' pronto di abbina_righe_a_partite, per non
    rifarlo. partite: giornata crescente e, dentro, calcio d'inizio (prima
    chi ha l'orario, poi i senza orario in ordine alfabetico); schedine:
    giornata crescente, poi giocatore.
    """
    righe_ab, info = abbinate if abbinate is not None else abbina_righe_a_partite(righe, per_giornata)

    per_g = {}
    for p in info.values():
        per_g.setdefault(p["giornata"], []).append(p)

    voti = {}
    for r in righe_ab:
        if _voto_valido(r):
            voti.setdefault(r["partita_id"], {}).setdefault(r["giocatore"], []).append(r["pronostico"])

    partite, posizione = [], {}
    for giornata in sorted(per_g):
        gettoni = {f"{p['nome']}\x00{p['id']}": p for p in per_g[giornata]}
        orari = {g: p["inizio"] for g, p in gettoni.items()}
        for gettone in ordina_partite_per_orario(list(gettoni), orari):
            p = gettoni[gettone]
            posizione[p["id"]] = len(posizione)
            partite.append({
                "id": p["id"], "giornata": p["giornata"], "nome": p["nome"], "ufficiale": p["ufficiale"],
                "inizio_il": _iso_utc(p["inizio"]) if p["inizio"] else None,
                "scelta_gruppo": scelta_del_gruppo_dati(voti.get(p["id"], {})),
            })

    gruppi = {}
    for r in righe_ab:
        gruppi.setdefault((r["giornata"], r["giocatore"]), []).append(r)
    schedine = []
    for (giornata, giocatore) in sorted(gruppi):
        # La vincita sta sulla prima riga della schedina NEL FOGLIO: si cerca prima del riordino.
        vincita = next((r["vincita"] for r in gruppi[(giornata, giocatore)] if r["vincita"] > 0), 0.0)
        rr = sorted(gruppi[(giornata, giocatore)], key=lambda r: posizione[r["partita_id"]])
        riepilogo = {chiave: 0 for chiave in _CHIAVE_RIEPILOGO.values()}
        for r in rr:
            riepilogo[_CHIAVE_RIEPILOGO[r["esito"]]] += 1
        schedine.append({
            "giornata": giornata,
            "giocatore": giocatore,
            "vincita_potenziale": vincita,
            "riepilogo": riepilogo,
            "righe": [{
                "partita_id": r["partita_id"], "tipologia": r["tipologia"], "pronostico": r["pronostico"],
                "quota": r["quota"], "esito": r["esito"], "punti": r["punti"],
            } for r in rr],
        })
    return partite, schedine


# --- N9, N10: classifica ---

def _leggi_classifica(righe_classifica):
    """Righe di Classifica (dizionari colonna -> valore) lette e validate.
    Un valore non numerico solleva ValueError (D12); un giocatore scritto due
    volte anche (non si indovina quale riga vale)."""
    voci, visti = [], set()
    for r in righe_classifica:
        nome = str(r.get("Giocatore", "")).strip()
        if not nome:
            continue
        chiave = nome.upper()
        if chiave in visti:
            raise ValueError(f"Classifica: il giocatore {nome!r} compare due volte")
        visti.add(chiave)
        celle = {}
        for colonna, valore in r.items():
            n = numero_giornata(colonna)
            if n is not None:
                celle[n] = None if _vuota(valore) else _intero_o_errore(valore, f"Classifica {nome} {colonna}")
        voci.append({
            "nome": nome_senza_ritiro(chiave), "ritirato": e_ritirato(chiave),
            "punti_totali": _intero_o_errore(r.get("Punti Totali", ""), f"Classifica {nome} Punti Totali"),
            "celle": celle,
        })
    return voci


def _vittorie_per_giocatore(righe_pulite, fino_a=None):
    """Pronostici vinti per giocatore (nome in maiuscolo), eventualmente solo
    nelle giornate < fino_a."""
    vittorie = {}
    for r in righe_pulite:
        if r["esito"] == "vinta" and (fino_a is None or r["giornata"] < fino_a):
            vittorie[r["giocatore"]] = vittorie.get(r["giocatore"], 0) + 1
    return vittorie


def _ranking_sportivo(punti, vittorie):
    """({nome: posizione}, nomi in ordine). Ordine: punti, poi pronostici
    vinti, poi nome. Stessa posizione a parita' di punti E pronostici vinti,
    e la successiva salta (4°, 4°, 6°) — §17.15."""
    ordine = sorted(punti, key=lambda g: (-punti[g], -vittorie.get(g, 0), g))
    posizione = {}
    for i, g in enumerate(ordine):
        if i > 0 and (punti[g], vittorie.get(g, 0)) == (punti[ordine[i - 1]], vittorie.get(ordine[i - 1], 0)):
            posizione[g] = posizione[ordine[i - 1]]
        else:
            posizione[g] = i + 1
    return posizione, ordine


def _variazioni(attive, righe_pulite):
    ultima = None
    for n in sorted({n for v in attive for n in v["celle"]}, reverse=True):
        if any(v["celle"].get(n) not in (None, 0) for v in attive):
            ultima = n
            break
    risultato = {v["nome"]: {"variazione": None, "punti_ultima": None} for v in attive}
    if ultima is None:
        return None, risultato
    for v in attive:
        risultato[v["nome"]]["punti_ultima"] = v["celle"].get(ultima) or 0
    if ultima > 1:
        pos_att, _ = _ranking_sportivo({v["nome"]: v["punti_totali"] for v in attive},
                                       _vittorie_per_giocatore(righe_pulite))
        pos_prec, _ = _ranking_sportivo(
            {v["nome"]: sum(c or 0 for n, c in v["celle"].items() if n < ultima) for v in attive},
            _vittorie_per_giocatore(righe_pulite, fino_a=ultima))
        for v in attive:
            risultato[v["nome"]]["variazione"] = pos_prec[v["nome"]] - pos_att[v["nome"]]
    return ultima, risultato


def variazioni_posizione(righe_classifica, righe_pulite):
    """N10 — (ultima_giornata, {nome: {"variazione", "punti_ultima"}}).

    L'ultima giornata e' l'ultima con almeno un punteggio diverso da 0 fra gli
    attivi. La classifica prima di quella giornata usa LO STESSO spareggio di
    quella attuale, con i pronostici vinti fino alla giornata precedente;
    variazione positiva = salito. None dove non c'e' una giornata precedente.
    """
    return _variazioni([v for v in _leggi_classifica(righe_classifica) if not v["ritirato"]], righe_pulite)


def classifica_ordinata(righe_classifica, righe_pulite):
    """N9 — sezione `classifica` dello snapshot (§5).

    righe_classifica: dizionari del foglio Classifica (righe_da_valori).
    Il nome del giocatore si confronta senza distinguere le maiuscole; i
    pronostici vinti si contano dalle righe pulite, quindi il sostituto
    (SIRACUSA) porta con se' quelli del ritirato (le sue schedine sono state
    rinominate in Giocate, §17.17).
    """
    voci = _leggi_classifica(righe_classifica)
    attive = [v for v in voci if not v["ritirato"]]
    ritirati = sorted((v for v in voci if v["ritirato"]), key=lambda v: (-v["punti_totali"], v["nome"]))
    posizione, ordine = _ranking_sportivo({v["nome"]: v["punti_totali"] for v in attive},
                                          _vittorie_per_giocatore(righe_pulite))
    ultima, variazioni = _variazioni(attive, righe_pulite)
    lunghezza = max((n for v in voci for n, c in v["celle"].items() if c is not None), default=0)

    def storico(v):
        return [v["celle"].get(n) for n in range(1, lunghezza + 1)]

    per_nome = {v["nome"]: v for v in attive}
    return {
        "ultima_giornata_giocata": ultima,
        "giocatori": [{
            "posizione": posizione[nome], "nome": nome, "punti_totali": per_nome[nome]["punti_totali"],
            "variazione_posizione": variazioni[nome]["variazione"],
            "punti_ultima_giornata": variazioni[nome]["punti_ultima"],
            "punti_per_giornata": storico(per_nome[nome]),
        } for nome in ordine],
        "ritirati": [{"nome": v["nome"], "punti_totali": v["punti_totali"], "punti_per_giornata": storico(v)}
                     for v in ritirati],
    }


# --- N13, N14, N15: statistiche per giocatore e premi ---

def statistiche_per_giocatore(righe_pulite):
    """N13 — Tabella `giocatori` (§8) in un solo giro sulle righe.

    Un giocatore compare se ha almeno una riga valutata (vinta o persa).
    win_rate (1 decimale) e quota_media (2 decimali) sono gia' arrotondati;
    win_rate_esatto e quota_media_esatta servono ai confronti dei premi e non
    vanno nello snapshot. La quota media esclude le quote illeggibili (None se
    non ne resta nessuna). Ordine: win rate esatto decrescente, poi partite
    valutate decrescenti, poi nome.
    """
    acc = {}
    for r in righe_pulite:
        if r["esito"] not in ("vinta", "persa"):
            continue
        a = acc.setdefault(r["giocatore"], {"vinte": 0, "totali": 0, "quote": []})
        a["totali"] += 1
        a["vinte"] += r["esito"] == "vinta"
        if r["quota"] is not None:
            a["quote"].append(r["quota"])
    risultato = []
    for nome, a in acc.items():
        win_rate = a["vinte"] / a["totali"] * 100
        quota_media = math.fsum(a["quote"]) / len(a["quote"]) if a["quote"] else None
        risultato.append({
            "nome": nome, "win_rate": round(win_rate, 1),
            "quota_media": None if quota_media is None else round(quota_media, 2),
            "vinte": a["vinte"], "totali": a["totali"],
            "win_rate_esatto": win_rate, "quota_media_esatta": quota_media,
        })
    return sorted(risultato, key=lambda s: (-s["win_rate_esatto"], -s["totali"], s["nome"]))


def statistiche_ritirati(righe_classifica, righe_pulite):
    """Statistiche congelate dei ritirati: le righe valutate del sostituto fino
    all'ultima giornata con punti nella riga congelata (righe_del_ritirato).
    Nome senza suffisso; fuori dai premi."""
    valutate = [{"Giornata": f"Giornata {r['giornata']}", "Giocatore": r["giocatore"], "_riga": r}
                for r in righe_pulite if r["esito"] in ("vinta", "persa")]
    ritirati = sorted((r for r in righe_classifica if str(r.get("Giocatore", "")).strip() and e_ritirato(r["Giocatore"])),
                      key=lambda r: (-_intero_o_errore(r.get("Punti Totali", ""), "Punti Totali ritirato"),
                                     nome_senza_ritiro(r["Giocatore"]).upper()))
    risultato = []
    for riga in ritirati:
        righe = righe_del_ritirato(valutate, riga["Giocatore"], ultima_giornata_con_punti(riga))
        stats = statistiche_per_giocatore([x["_riga"] for x in righe])
        if stats:
            risultato.append({**stats[0], "nome": nome_senza_ritiro(riga["Giocatore"]).upper()})
    return risultato


def _a_pari_merito(voci, valore, massimo=True):
    """Le voci con il valore piu' alto (o piu' basso), tutte, a pari merito.
    I confronti sono sui valori esatti; l'arrotondamento a 9 decimali assorbe
    solo il rumore dei float, non cambia nessun pareggio vero."""
    candidati = [v for v in voci if valore(v) is not None]
    if not candidati:
        return []
    migliore = (max if massimo else min)(round(valore(v), 9) for v in candidati)
    return [v for v in candidati if round(valore(v), 9) == migliore]


def premi_giocatori(stats):
    """N14 — cecchino, benedizione, folle, conservatore come liste di TUTTI i
    pari merito, in ordine alfabetico, senza minimo di pronostici (§17.14).
    Ogni chiave e' None se non c'e' nessun giocatore con partite valutate."""
    def lista(voci, campi):
        voci = sorted(voci, key=lambda v: v["nome"])
        return [{"giocatore": v["nome"], **{c: v[c] for c in campi}} for v in voci] or None

    esatto = lambda v: v["win_rate_esatto"]
    quota = lambda v: v["quota_media_esatta"]
    return {
        "cecchino": lista(_a_pari_merito(stats, esatto), ("win_rate", "vinte", "totali")),
        "benedizione": lista(_a_pari_merito(stats, esatto, massimo=False), ("win_rate", "vinte", "totali")),
        "folle": lista(_a_pari_merito(stats, quota), ("quota_media",)),
        "conservatore": lista(_a_pari_merito(stats, quota, massimo=False), ("quota_media",)),
    }


def giornata_da_incorniciare(righe_attivi):
    """N15 — Il punteggio piu' alto in una singola giornata, tutti i pari
    merito (anche lo stesso giocatore in due giornate). righe_attivi: elementi
    con "nome" e "punti_per_giornata" (le righe di classifica.giocatori).
    None se nessuno ha mai fatto piu' di 0."""
    punteggi = [(r["nome"], n, p) for r in righe_attivi
                for n, p in enumerate(r["punti_per_giornata"], start=1) if p]
    if not punteggi:
        return None
    massimo = max(p for _, _, p in punteggi)
    if massimo <= 0:
        return None
    return [{"giocatore": g, "giornata": n, "punti": p} for g, n, p in sorted(punteggi) if p == massimo]


# --- N16, N17, N23: squadre ---

def squadra_scelta(pronostico, partita):
    """N23 — La squadra ufficiale scelta da un pronostico: "1"/"1X" -> casa,
    "2"/"X2" -> ospite, primo segno prima del "+" nelle combo. None per tutto
    il resto ("X", "12", Over/Under, Gol/NoGol, Pari/Dispari) e per i
    pronostici annullati. partita: dizionario con "casa" e "ospite" (nomi, o
    dizionari con "name")."""
    p = str(pronostico).strip().upper()
    if "ANNULLATA" in p:
        return None
    segno = p.split("+")[0].strip()
    if segno in ("1", "1X"):
        squadra = partita.get("casa")
    elif segno in ("2", "X2"):
        squadra = partita.get("ospite")
    else:
        return None
    return squadra.get("name") if isinstance(squadra, dict) else squadra


def _partita_ufficiale(riga, partite):
    p = partite.get(riga["partita_id"])
    return p if p and p.get("ufficiale") else None


def semper_fidelis(righe, partite):
    """N16 — Per (giocatore, squadra ufficiale) conta le GIORNATE DISTINTE in
    cui c'e' almeno un pronostico su quella squadra (N23), solo su partite
    giocate (vinta/persa) e non annullate. Lista dei pari merito (alfabetica),
    None se il massimo e' < 2 (§17.19).

    righe: righe pulite con partita_id (abbina_righe_a_partite);
    partite: l'`info` di abbina_righe_a_partite.
    """
    giornate = {}
    for r in righe:
        partita = _partita_ufficiale(r, partite)
        if not partita or r["esito"] not in ("vinta", "persa"):
            continue
        squadra = squadra_scelta(r["pronostico"], partita)
        if squadra:
            giornate.setdefault((r["giocatore"], squadra), set()).add(r["giornata"])
    conteggi = {chiave: len(g) for chiave, g in giornate.items()}
    massimo = max(conteggi.values(), default=0)
    if massimo < 2:
        return None
    return [{"giocatore": g, "squadra": s, "volte": n} for (g, s), n in sorted(conteggi.items()) if n == massimo]


def squadre_amuleto_maledetta(righe, partite):
    """N17 — Squadra (nome ufficiale) con piu' pronostici `vinta` SU DI LEI
    (amuleto) e con piu' `persa` (maledetta); solo la squadra scelta dal
    pronostico (§17.20). Liste di pari merito alfabetiche; None se non c'e'
    nessuna riga. Le righe non ufficiali non contano."""
    vinte, perse = {}, {}
    for r in righe:
        partita = _partita_ufficiale(r, partite)
        if not partita or r["esito"] not in ("vinta", "persa"):
            continue
        squadra = squadra_scelta(r["pronostico"], partita)
        if squadra:
            bersaglio = vinte if r["esito"] == "vinta" else perse
            bersaglio[squadra] = bersaglio.get(squadra, 0) + 1

    def pari_merito(conteggi, chiave):
        massimo = max(conteggi.values(), default=0)
        return [{"squadra": s, chiave: n} for s, n in sorted(conteggi.items()) if n == massimo] or None

    return {"squadra_amuleto": pari_merito(vinte, "vittorie_portate"),
            "squadra_maledetta": pari_merito(perse, "pronostici_bruciati")}


# --- N18: ultima schedina vinta ---

def ultima_schedina_vinta(movimenti, righe, partite):
    """N18 — {"giornata", "vincitori", "inizio_il"} oppure None.

    Chi ha chiuso lo dice Cassa (schedine_chiuse_ultima_giornata, il verdetto
    verificato dal bot); `inizio_il` e' la fine stimata dell'ULTIMA partita fra
    le schedine dei vincitori (inizio + 2 ore), None se anche una sola non ha
    un orario noto o non e' stata abbinata (§8.1)."""
    chiusura = schedine_chiuse_ultima_giornata(
        (f"Giornata {m['giornata']}" if m["giornata"] is not None else "", m["descrizione"]) for m in movimenti)
    if chiusura is None:
        return None
    giornata, vincitori = chiusura
    orari = {p["id"]: p["inizio"] for p in partite.values()}
    momenti = []
    for vincitore in vincitori:
        ids = [r["partita_id"] for r in righe
               if r["giornata"] == giornata and r["giocatore"].lower() == vincitore.lower()]
        momenti.append(momento_fine_schedina(ids, orari))
    return {
        "giornata": giornata,
        "vincitori": [v.upper() for v in vincitori],
        "inizio_il": None if (not momenti or None in momenti) else _iso_utc(max(momenti)),
    }


# --- N19: Coppa ---

def _righe_giocate_legacy(righe):
    """Le righe pulite nel formato che le funzioni della Coppa si aspettano."""
    return [{"Giornata": f"Giornata {r['giornata']}", "Giocatore": r["giocatore"], "Esito": _TESTO_ESITO[r["esito"]]}
            for r in righe]


def coppa_snapshot(righe_classifica, righe_pulite):
    """N19 — sezione `coppa` (§9), componendo le funzioni della Coppa gia'
    esistenti. `definitiva` scatta quando la Giornata 34 e' CONCLUSA (§17.21).
    I nomi si confrontano in maiuscolo e a parita' resta l'ordine alfabetico:
    il tabellone e' deterministico."""
    classifica = sorted(
        ({**r, "Giocatore": str(r.get("Giocatore", "")).strip().upper()} for r in righe_classifica
         if str(r.get("Giocatore", "")).strip()),
        key=lambda r: r["Giocatore"])
    giocate = _righe_giocate_legacy(righe_pulite)
    partecipanti = classifica_per_coppa(classifica, giocate)
    ottavi = tabellone_ottavi(partecipanti)
    concluse = giornate_concluse(giocate)

    def voce(v):
        return None if v is None else {"posizione": v[0], "nome": v[1]}

    if ottavi:
        turni = turni_coppa(ottavi, punti_per_giornata(classifica), concluse)
    else:
        turni = [[{"giornata": PRIMA_GIORNATA_COPPA + i, "giocatori": [None, None], "punti": [None, None],
                   "vincente": None} for _ in range(8 >> i)] for i in range(len(TURNI_COPPA))]
    finale = turni[-1][0]
    return {
        "definitiva": ULTIMA_GIORNATA_TABELLONE in concluse,
        "partecipanti": len(partecipanti),
        "tabellone_disponibile": ottavi is not None,
        "prima_giornata": PRIMA_GIORNATA_COPPA,
        "ultima_giornata_tabellone": ULTIMA_GIORNATA_TABELLONE,
        "turni": [{
            "turno": nome.lower(), "giornata": sfide[0]["giornata"],
            "sfide": [{"giocatori": [voce(g) for g in s["giocatori"]], "punti": list(s["punti"]),
                       "vincente": s["vincente"]} for s in sfide],
        } for nome, sfide in zip(TURNI_COPPA, turni)],
        "campione": None if finale["vincente"] is None else voce(finale["giocatori"][finale["vincente"]]),
    }


# --- N21, N22: lo snapshot intero e il segnale di vita ---

def _snapshot_senza_orario(snapshot):
    return {k: v for k, v in snapshot.items() if k != "generato_il"}


def impronta_snapshot(snapshot):
    """N22 — SHA-256 del JSON canonico (chiavi ordinate, separatori compatti)
    dello snapshot SENZA `generato_il`: due snapshot con gli stessi dati hanno
    la stessa impronta anche se costruiti in momenti diversi."""
    canonico = json.dumps(_snapshot_senza_orario(snapshot), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def costruisci_segnale(snapshot, adesso_utc):
    """N22 — il documento `segnale` (§4), scritto a ogni controllo."""
    return {
        "versione_schema": VERSIONE_SCHEMA,
        "ultimo_controllo_il": _iso_utc(adesso_utc),
        "generato_il": snapshot["generato_il"],
        "impronta": impronta_snapshot(snapshot),
        "soglia_allarme_minuti": SOGLIA_ALLARME_MINUTI,
        "pausa_notturna": dict(PAUSA_NOTTURNA),
    }


def _avvisi_snapshot(righe_classifica, movimenti, scartate, abbinate, info):
    avvisi = [f"Giocate riga {n}: scartata ({motivo})" for n, motivo in scartate]
    visti = set()
    for r in abbinate:
        if r["partita_id"] < 0 and (chiave := (r["giornata"], r["giocatore"], r["partita_testo"])) not in visti:
            visti.add(chiave)
            avvisi.append(f"Giornata {r['giornata']}, {r['giocatore']}: la partita {r['partita_testo']!r} "
                          "non corrisponde a nessuna partita della giornata")
    for v in _leggi_classifica(righe_classifica):
        somma = sum(c for c in v["celle"].values() if c is not None)
        if somma != v["punti_totali"]:
            avvisi.append(f"Classifica: {v['nome']} ha Punti Totali {v['punti_totali']} ma le giornate sommano {somma}")
    if movimenti and movimenti[-1]["saldo"] is not None:
        somma = round(math.fsum(m["entrata"] for m in movimenti if m["entrata"] is not None), 2)
        if abs(movimenti[-1]["saldo"] - somma) > 0.005:
            avvisi.append(f"Cassa: l'ultimo Saldo Totale scritto e' {movimenti[-1]['saldo']:.2f} ma le entrate sommano {somma:.2f}")
    return avvisi


def costruisci_snapshot_con_avvisi(righe_classifica, righe_cassa, righe_giocate, partite_fd, adesso_utc):
    """Come costruisci_snapshot, ma restituisce anche gli avvisi: (snapshot,
    [testo]). Gli avvisi (righe scartate, partite non abbinate, totali che non
    tornano) vanno al log del bot e agli admin, mai nello snapshot (§17.29)."""
    if not righe_classifica:
        raise ValueError("Classifica vuota o illeggibile: nessuno snapshot")
    if not righe_giocate:
        raise ValueError("Giocate vuoto o illeggibile: nessuno snapshot")
    if getattr(adesso_utc, "tzinfo", None) is None:
        raise ValueError("adesso_utc deve essere un datetime con fuso orario")

    stagione = partite_della_stagione(partite_fd)
    if not stagione["stagione"]:
        raise ValueError("Football-Data: stagione non riconoscibile (startDate mancante o malformata)")
    classifica_righe = righe_da_valori(righe_classifica)
    righe, scartate = pulisci_giocate(righe_giocate)
    movimenti = movimenti_cassa(righe_cassa)

    abbinate = abbina_righe_a_partite(righe, stagione["per_giornata"])
    righe_ab, info = abbinate
    partite, schedine = costruisci_partite_e_schedine(righe, stagione["per_giornata"], abbinate=abbinate)
    classifica = classifica_ordinata(classifica_righe, righe)
    cassa = riepilogo_cassa(movimenti, OBIETTIVO_CASSA)
    cassa["versamenti_per_giornata"] = versamenti_per_giornata(movimenti, {r["giornata"] for r in righe})

    stats = statistiche_per_giocatore(righe)
    legacy_soffio = [{
        "Giornata": f"Giornata {r['giornata']}", "Giocatore": r["giocatore"], "Partita": info[r["partita_id"]]["nome"],
        "Pronostico": r["pronostico"], "Quota": r["quota"], "Esito": r["esito"],
    } for r in righe_ab]
    pulisci = lambda s: {k: v for k, v in s.items() if not k.endswith("_esatto") and not k.endswith("_esatta")}
    premi = premi_giocatori(stats)
    premi["giornata_da_incorniciare"] = giornata_da_incorniciare(classifica["giocatori"]) if stats else None
    premi["semper_fidelis"] = semper_fidelis(righe_ab, info)
    premi.update(squadre_amuleto_maledetta(righe_ab, info))

    snapshot = {
        "versione_schema": VERSIONE_SCHEMA,
        "generato_il": _iso_utc(adesso_utc),
        "stagione": stagione["stagione"],
        "giornata_corrente": max((r["giornata"] for r in righe), default=None),
        "giocatori": sorted({r["giocatore"] for r in righe}),
        "classifica": classifica,
        "cassa": cassa,
        "partite": partite,
        "schedine": schedine,
        "statistiche": {
            "ultima_schedina_vinta": ultima_schedina_vinta(movimenti, righe_ab, info),
            "premi": premi,
            "per_un_soffio": [
                {"giocatore": s["giocatore"], "giornata": s["giornata"], "partita": s["partita"],
                 "pronostico": s["pronostico"], "quota": s["quota"]}
                for s in schedine_perse_per_un_soffio(legacy_soffio)],
            "giocatori": [pulisci(s) for s in stats],
            "ritirati": [pulisci(s) for s in statistiche_ritirati(classifica_righe, righe)],
        },
        "coppa": coppa_snapshot(classifica_righe, righe),
        "regole": json.loads(json.dumps(REGOLE)),
    }
    return snapshot, _avvisi_snapshot(classifica_righe, movimenti, scartate, righe_ab, info)


def costruisci_snapshot(righe_classifica, righe_cassa, righe_giocate, partite_fd, adesso_utc):
    """N21 — Lo snapshot completo (§3, §5-§10) come dizionario pronto per
    json.dumps.

    righe_classifica, righe_cassa, righe_giocate: `values` dei tre fogli come
    li restituisce Sheets (liste di liste, intestazione compresa);
    partite_fd: la risposta di UNA chiamata /competitions/SA/matches (o la
    sola lista `matches`); adesso_utc: datetime con fuso.

    Solleva ValueError quando i dati sono vuoti o illeggibili (Classifica o
    Giocate senza intestazione, Football-Data senza partite, un punteggio non
    numerico, un importo di Cassa illeggibile): chi chiama NON pubblica, tiene
    lo snapshot precedente e avvisa gli admin (§17.13).
    """
    return costruisci_snapshot_con_avvisi(righe_classifica, righe_cassa, righe_giocate, partite_fd, adesso_utc)[0]
