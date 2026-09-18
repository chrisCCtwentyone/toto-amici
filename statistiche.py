"""
Logica pura delle statistiche della dashboard, separata da app.py.

app.py esegue Streamlit gia' al momento dell'import, quindi i test non possono
importarlo: qui stanno solo funzioni senza effetti collaterali (niente rete,
niente Sheets), che app.py chiama passando i dati gia' caricati.
"""
import re
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
    Pronostico, Quota, Esito).

    Serve una schedina gia' decisa del tutto: basta una riga in corso, rinviata
    o da verificare per escluderla. Altrimenti una schedina ancora aperta
    comparirebbe come "persa per un soffio" e magari si brucia alla partita dopo.
    Restituisce una lista di dizionari, dalla giornata piu' recente.
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
        esiti = [str(r.get("Esito", "")) for r in righe_schedina]
        perse = [i for i, e in enumerate(esiti) if "PERSA" in e]
        if len(perse) != 1:
            continue
        altre = [e for i, e in enumerate(esiti) if i != perse[0]]
        if not any("VINTA" in e for e in altre):
            continue
        if not all("VINTA" in e or "ANNULLATA" in e for e in altre):
            continue
        persa = righe_schedina[perse[0]]
        risultato.append({
            "giocatore": giocatore,
            "giornata": n,
            "partita": str(persa.get("Partita", "")).strip(),
            "pronostico": str(persa.get("Pronostico", "")).strip(),
            "quota": str(persa.get("Quota", "")).strip(),
        })
    return sorted(risultato, key=lambda s: (-s["giornata"], s["giocatore"].lower()))


def scelta_del_gruppo(pronostici_per_giocatore):
    """Il pronostico piu' giocato su una partita, per la colonna del Confronto Giocate.

    pronostici_per_giocatore: dict giocatore -> pronostici giocati su quella partita.
    Ogni giocatore conta una volta per pronostico, anche se lo ha su piu' righe.
    Conta solo il pronostico identico: "1+OVER_2.5" non vale come "1".

    Restituisce "1 · 5 su 7", "1 / X · 3 su 7" in caso di parita', oppure
    "Tutti diversi" se nessun pronostico e' stato scelto da almeno due giocatori.
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
        return "—"
    massimo = max(conteggi.values())
    if massimo == 1 and giocatori > 1:
        return "Tutti diversi"
    migliori = sorted(p for p, n in conteggi.items() if n == massimo)
    return f"{' / '.join(migliori)} · {massimo} su {giocatori}"


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
