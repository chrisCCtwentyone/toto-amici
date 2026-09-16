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
