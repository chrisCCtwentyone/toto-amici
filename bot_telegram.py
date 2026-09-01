import os
import json
import logging
import re
import asyncio
import requests
from api_utils import richiedi_con_retry
from datetime import time as dt_time, datetime, timedelta
import pytz
import threading
from flask import Flask
from PIL import Image
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# ==========================================
# VARIABILI D'AMBIENTE (SICUREZZA CLOUD)
# ==========================================
TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
FOOTBALL_DATA_KEY = os.environ.get("FOOTBALL_DATA_KEY")
SERVICE_ACCOUNT_FILE = 'credenziali.json'

# Fogli di lavoro della stagione IN CORSO. Le stagioni passate restano nello
# stesso spreadsheet con il suffisso dell'annata (es. "Giocate 2026-27"),
# create da /archiviastagione. Vedi PROJECT_LOG.md, Sessione 13.
FOGLI_STAGIONE = ("Giocate", "Classifica", "Cassa")

GIOCATORI = [
    "cecilia", "dario", "davide", "fazio", 
    "gaetano", "giacomo", "giovanni", "mario", 
    "michele", "mirko", "nico", "paolo", 
    "pulizzer", "silvio", "villari", "vincenzo"
]

LIMITI_SCHEDINA = {"Combo": 1, "Fisse": 4, "Doppie Chance": 2, "Variabili": 3}

# Stati Conversazione
(MENU, ATTESA_FOTO_MULTIPLE, SCELTA_GIORNATA, SCELTA_GIOCATORE, CONFERMA, CONFERMA_LETTURA_IA,
 SCELTA_GIORNATA_UPDATE, ATTESA_NUOVA_KEY, SCELTA_GIORNATA_MANUALE, SCELTA_PARTITA_MANUALE,
 ATTESA_RISULTATO_MANUALE, CONFERMA_RISULTATO_MANUALE, CONFERMA_ARCHIVIA_STAGIONE) = range(13)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

if not TOKEN or not SPREADSHEET_ID or not FOOTBALL_DATA_KEY or ADMIN_ID == 0:
    logging.warning("⚠️ ATTENZIONE: Variabili d'ambiente mancanti. Il bot potrebbe non funzionare correttamente!")

last_ping_time = None
ultime_anomalie_segnalate = set()  # chiavi stabili delle anomalie dell'ultimo avviso inviato (per non ripetere lo stesso avviso ad ogni controllo)
ultima_giornata_riepilogo_inviata = None  # per non rimandare due volte il riepilogo della stessa giornata

# ==========================================
# SERVER WEB PER MANTENERE IL BOT SVEGLIO (TRUCCO RENDER)
# ==========================================
app_web = Flask(__name__)

@app_web.route('/')
def home():
    """Endpoint di keep-alive. Render spegne un servizio gratuito dopo 15 MINUTI
    senza traffico HTTP IN ENTRATA: i ping esterni (cron-job.org) servono a questo.

    Ogni ping viene registrato nel log con l'intervallo dal precedente: senza
    questa riga, dai log non si distingueva un servizio spento da Render per
    mancanza di ping da un crash del bot (incidente del 01/09/2026, in cui
    l'assenza di richieste in entrata nei log e' stata l'indizio decisivo).
    """
    global last_ping_time
    from datetime import datetime
    now = datetime.now()
    if last_ping_time is None:
        logging.info("PING keep-alive ricevuto (primo dall'avvio)")
    else:
        logging.info(f"PING keep-alive ricevuto ({int((now - last_ping_time).total_seconds())}s dal precedente)")
    if last_ping_time is not None:
        delta = (now - last_ping_time).total_seconds()
        if delta > 900:  # > 15 minuti: oltre questa soglia Render spegne il servizio
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                    json={
                        "chat_id": ADMIN_ID,
                        "text": f"⚠️ **ALLARME KEEP-ALIVE**\nSono passati {int(delta/60)} minuti dall'ultimo ping (Render spegne il servizio dopo 15).\nControlla che il job su cron-job.org sia attivo e riuscito.",
                        "parse_mode": "Markdown"
                    }
                )
            except Exception as e:
                logging.error(f"Errore invio alert Telegram: {e}")
    last_ping_time = now
    return "✅ Il Bot Toto-Amici è online e sta funzionando perfettamente 24/7!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

# ==========================================
# FUNZIONI CORE DEL BOT
# ==========================================
def leggi_chiave_api():
    """Chiave Gemini: prima la variabile d'ambiente, poi il file locale.

    Su Render il filesystem e' effimero e i Secret File sono in sola lettura:
    una chiave cambiata con /setkey vive solo fino al riavvio successivo, poi
    si torna silenziosamente a quella vecchia. Con GEMINI_API_KEY impostata
    come variabile d'ambiente il valore e' invece stabile fra i riavvii; il
    file resta come fallback per l'uso in locale e per /setkey al volo.
    """
    chiave_env = os.environ.get("GEMINI_API_KEY", "").strip()
    if chiave_env:
        return chiave_env
    try:
        with open('chiave_api.txt', 'r') as f: return f.read().strip()
    except: return ""

def chiave_api_da_env():
    """True se la chiave in uso arriva dalla variabile d'ambiente (quindi /setkey
    non ha effetto pratico finche' quella variabile resta impostata)."""
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())

def get_gemini_client():
    chiave = leggi_chiave_api()
    return genai.Client(api_key=chiave) if chiave else None

_sheets_service_cache = None

def connetti_sheets():
    """Client Sheets riusato invece di ricostruito ad ogni chiamata.

    Prima si rifaceva Credentials.from_service_account_file() + build() ogni
    volta — chiamato da job schedulati fino a ~20+ volte/giorno (monitoraggio
    ogni 2h, calcolo risultati 5x/giorno, /status, ecc.). Ogni build() rilegge
    il file di credenziali e ricostruisce l'intero client scoprendo l'API da
    zero: costoso su un piano Render da 512MB. Il token OAuth del service
    account si rinnova comunque da solo quando serve, quindi riusare
    l'istanza e' sicuro (stesso pattern gia' in uso in app.py per la web app).
    Vedi PROJECT_LOG.md, Sessione 9 (riavvio inatteso su Render, 31/08/2026).
    """
    global _sheets_service_cache
    if _sheets_service_cache is None:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        _sheets_service_cache = build('sheets', 'v4', credentials=creds)
    return _sheets_service_cache

def analizza_schedine_multiple(lista_percorsi_foto):
    client = get_gemini_client()
    if not client: raise Exception("Chiave API Gemini non configurata o vuota!")
    
    immagini_ottimizzate = []
    for percorso in lista_percorsi_foto:
        img = Image.open(percorso)
        if img.mode != 'RGB': img = img.convert('RGB')
        img.thumbnail((1000, 1000))
        immagini_ottimizzate.append(img)
        
    prompt = """
    Sei un assistente esperto nell'analisi di schedine di scommesse sportive. Analizza queste immagini con estrema attenzione (potrebbero essere più schermate della stessa bolletta).

    1. **VINCITA POTENZIALE ("vincita_potenziale"):**
       - Cerca la dicitura relativa alla vincita totale stimata, vincita massima, o potenziale rimborso in fondo alla schedina.
       - Restituisci SOLO IL VALORE NUMERICO FINALE IN EURO (es. "72.50"). Niente simboli o testo.

    2. **EVENTI DELLA SCHEDINA:**
       Estrai la lista di TUTTI gli eventi presenti nelle immagini dividendola tassativamente in queste 4 categorie: "Combo", "Fisse", "Doppie Chance", "Variabili".
       Per ogni evento fornisci le chiavi esatte: "partita", "pronostico", "quota".
       
       **IMPORTANTE: REGOLE PER IL CAMPO "pronostico":**
       Devi normalizzare i pronostici restituendo ESCLUSIVAMENTE uno dei seguenti valori esatti: `1`, `X`, `2`, `1X`, `X2`, `12`, `OVER_2.5`, `UNDER_2.5`, `GOAL`, `NOGOAL`, `PARI`, `DISPARI`.
       Per le combo usa il formato esatto unendo con `+`, ad esempio: `1+OVER_2.5`, `X2+GOAL`, `2+UNDER_2.5`.
       - NON INCLUDERE MAI prefissi o diciture lunghe come 'ESITO FINALE:', 'DOPPIA CHANCE:', '1X2:', 'U/OVER_2.5:'.
       - NON INCLUDERE MAI i nomi delle squadre (es. 'MILAN', 'ROMA') nel pronostico. Sostituisci il nome con il segno `1` o `2` corrispondente, o `X` se c'è scritto 'PAREGGIO'.
       - Converti qualsiasi abbreviazione come 'O' o 'U' in 'OVER_2.5' o 'UNDER_2.5'.
       - Converti 'GG' o 'G' in 'GOAL', e 'NG' in 'NOGOAL'.
       - NON RESTITUIRE MAI un pronostico bare come 'SI', 'SÌ' o 'NO': alcuni bookmaker mostrano il mercato "Entrambe le squadre segnano" come una domanda con risposta Sì/No. In quel caso guarda il nome del mercato nella schermata e converti: 'Sì' → `GOAL`, 'No' → `NOGOAL`. Applica lo stesso ragionamento per qualsiasi altro mercato mostrato come Sì/No: individua a cosa si riferisce e restituisci sempre uno dei valori esatti elencati sopra, mai la risposta letterale.
    """
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=[prompt] + immagini_ottimizzate,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return response.text

def normalizza_nomi_partite(dati_json, giornata_num):
    try:
        url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata_num}"
        matches = richiedi_con_retry(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
        if not matches: return dati_json
        
        dati = json.loads(dati_json)
        for cat in ["Combo", "Fisse", "Doppie Chance", "Variabili"]:
            for ev in dati.get("eventi", dati).get(cat, []):
                partita = ev.get("partita", "")
                if "-" in partita:
                    c_sh, o_sh = [s.strip()[:5].lower() for s in partita.split('-')]
                    for m in matches:
                        ac, ao = str(m["homeTeam"]["name"]).lower(), str(m["awayTeam"]["name"]).lower()
                        sc, so = str(m["homeTeam"].get("shortName","")).lower(), str(m["awayTeam"].get("shortName","")).lower()
                        if ((c_sh in ac or c_sh in sc) and (o_sh in ao or o_sh in so)) or ((c_sh in ao or c_sh in so) and (o_sh in ac or o_sh in sc)):
                            ev["partita"] = f"{m['homeTeam'].get('shortName', m['homeTeam']['name'])} - {m['awayTeam'].get('shortName', m['awayTeam']['name'])}"
                            break
        return json.dumps(dati)
    except: return dati_json

def normalizza_pronostico(pronostico_raw):
    """
    Pulisce e standardizza le diciture dei pronostici per evitare discrepanze.
    """
    p = str(pronostico_raw).upper().strip()
    
    # Rimuovi spazi extra tra simboli e numeri (es "O 2.5" -> "O2.5", "1 +" -> "1+")
    p = re.sub(r'\s+', ' ', p)
    
    # Alias GOAL / NOGOAL
    if p in ["GG", "GOAL/GOAL", "G/G", "G", "GOL", "SI", "SÌ"]:
        p = "GOAL"
    elif p in ["NG", "NOGOAL", "NO GOAL", "NO/GOAL", "N/G", "NO"]:
        p = "NOGOAL"

    # Alias doppie chance scritte in ordine invertito (es. "2X" -> "X2")
    if p == "2X":
        p = "X2"
    elif p == "X1":
        p = "1X"
    elif p == "21":
        p = "12"
        
    # Alias OVER / UNDER
    # Mappa roba tipo "PIU DI 2.5", "O2.5", "+2.5", "OVER 2,5" in "OVER_2.5"
    p = p.replace(",", ".")
    p = re.sub(r'(?:O|OVER|PI[UÙ]\s*DI|\+)\s*2\.5', 'OVER_2.5', p)
    p = re.sub(r'(?:U|UNDER|MENO\s*DI|\-)\s*2\.5', 'UNDER_2.5', p)
    
    # Sostituzioni classiche di "buona fede" (over 1.5 e under 3.5 = 2.5)
    p = re.sub(r'(?:O|OVER|PI[UÙ]\s*DI|\+)\s*1\.5', 'OVER_2.5', p)
    p = re.sub(r'(?:U|UNDER|MENO\s*DI|\-)\s*3\.5', 'UNDER_2.5', p)

    # Gestione Combo (es "1+O2.5" -> "1+OVER_2.5")
    # Facciamo una passata per espandere componenti comuni
    if "+" in p or "&" in p or " E " in p:
        p = p.replace("&", "+").replace(" E ", "+")
        parti = [part.strip() for part in p.split("+")]
        nuove_parti = []
        for part in parti:
            if part in ["GG", "G"]: part = "GOAL"
            elif part in ["NG"]: part = "NOGOAL"
            elif part in ["O2.5", "O 2.5", "+2.5"]: part = "OVER_2.5"
            elif part in ["U2.5", "U 2.5", "-2.5"]: part = "UNDER_2.5"
            elif part == "2X": part = "X2"
            elif part == "X1": part = "1X"
            elif part == "21": part = "12"
            nuove_parti.append(part)
        p = "+".join(nuove_parti)

    return p

def scrivi_su_sheets_con_regole(nome_giocatore, giornata_num, json_data):
    sheets_service = connetti_sheets()
    dati = json.loads(json_data)
    
    vincita_raw = str(dati.get("vincita_potenziale", "0")).replace(',', '.')
    try:
        vincita = f"{float(vincita_raw):.2f}".replace('.', ',')
    except: vincita = "0,00"

    eventi = dati.get("eventi", dati) 
    righe_da_inserire = []
    prima_riga = True
    
    for categoria in ["Combo", "Fisse", "Doppie Chance", "Variabili"]:
        eventi_cat = eventi.get(categoria, [])
        for idx, evento in enumerate(eventi_cat):
            pronostico = normalizza_pronostico(evento.get("pronostico", ""))
            
            if idx >= LIMITI_SCHEDINA[categoria]:
                pronostico += " (ANNULLATA ECCESSO)"
                
            quota_raw = str(evento.get("quota", "")).replace('.', ',')
            
            riga = [f"Giornata {giornata_num}", nome_giocatore.upper(), evento.get("partita", ""), categoria, pronostico, quota_raw]
            
            if prima_riga:
                riga.extend(["", vincita])
                prima_riga = False
            righe_da_inserire.append(riga)

    if righe_da_inserire:
        body = {'values': righe_da_inserire}
        sheets_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="Giocate!A:I",
            valueInputOption="USER_ENTERED", body=body
        ).execute(num_retries=3)
        return True
    return False

# ==========================================
# CALCOLO RISULTATI E API
# ==========================================
def riga_e_della_giornata(valore_cella, giornata):
    """True solo se la cella "Giornata" di una riga si riferisce ESATTAMENTE a quella giornata.

    NON usare `str(giornata) in str(cella)`: e' una ricerca per sottostringa, quindi
    la giornata "1" verrebbe trovata anche dentro "Giornata 12", "Giornata 13",
    "Giornata 21"... Con quel confronto, ricalcolare la Giornata 1 riscriveva gli
    esiti di 13 giornate diverse (dimostrato: una riga gia' vinta della Giornata 12
    diventava PERSA con 0 punti, perche' agganciata al risultato della Giornata 1
    tramite il fallback sull'ordine invertito, dato che andata e ritorno hanno le
    stesse due squadre). Il problema sarebbe esploso dalla Giornata 10 in poi.
    Vedi PROJECT_LOG.md, Sessione 13.
    """
    testo = str(valore_cella).strip().lower()
    if not testo.startswith("giornata"):
        return False
    return testo.replace("giornata", "").strip() == str(giornata).strip()

def ottieni_giornata_corrente():
    """Giornata corrente secondo Football-Data, o None se l'API non risponde.

    Ritorna None (non 1) di proposito: prima un errore di rete faceva ripiegare
    sulla Giornata 1, e i job schedulati finivano per ricalcolare/controllare la
    giornata sbagliata. Ogni chiamante deve gestire il None saltando il giro.
    """
    try:
        res = richiedi_con_retry("https://api.football-data.org/v4/competitions/SA", headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json()
        giornata = res.get('currentSeason', {}).get('currentMatchday')
        return giornata if giornata else None
    except Exception:
        logging.error("ottieni_giornata_corrente: API non raggiungibile, giro saltato")
        return None

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

def stagione_corrente():
    """Etichetta della stagione in corso secondo Football-Data, o None."""
    try:
        res = richiedi_con_retry(
            "https://api.football-data.org/v4/competitions/SA",
            headers={"X-Auth-Token": FOOTBALL_DATA_KEY}
        ).json()
        return etichetta_stagione(res.get("currentSeason", {}).get("startDate"))
    except Exception:
        return None

def archivia_stagione(etichetta):
    """Congela la stagione conclusa e prepara i fogli per quella nuova.

    Per ogni foglio di lavoro: ne crea una copia rinominata "<Nome> <etichetta>"
    e poi svuota l'originale lasciando la riga di intestazione.

    L'ordine conta: prima si duplicano TUTTI i fogli e si verifica che le copie
    esistano davvero, e solo dopo si cancella qualcosa. Se una duplicazione
    fallisce si interrompe senza aver toccato i dati.

    Ritorna un riepilogo testuale di cosa e' stato fatto.
    """
    service = connetti_sheets()
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute(num_retries=3)
    fogli = {f["properties"]["title"]: f["properties"]["sheetId"] for f in meta.get("sheets", [])}

    # 1) Controlli preliminari: niente sovrascritture accidentali
    for nome in FOGLI_STAGIONE:
        if nome not in fogli:
            raise Exception(f"Foglio '{nome}' non trovato: archiviazione annullata.")
        if f"{nome} {etichetta}" in fogli:
            raise Exception(f"Esiste gia' un foglio '{nome} {etichetta}': archiviazione gia' fatta?")

    # 2) Duplicazione di tutti i fogli
    richieste = [{
        "duplicateSheet": {
            "sourceSheetId": fogli[nome],
            "newSheetName": f"{nome} {etichetta}",
        }
    } for nome in FOGLI_STAGIONE]
    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID, body={"requests": richieste}
    ).execute(num_retries=3)

    # 3) Verifica che le copie ci siano DAVVERO prima di cancellare
    meta_dopo = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute(num_retries=3)
    titoli_dopo = {f["properties"]["title"] for f in meta_dopo.get("sheets", [])}
    mancanti = [f"{n} {etichetta}" for n in FOGLI_STAGIONE if f"{n} {etichetta}" not in titoli_dopo]
    if mancanti:
        raise Exception(f"Copie non create ({', '.join(mancanti)}): NON ho cancellato nulla.")

    # 4) Solo ora si svuotano i fogli di lavoro, mantenendo l'intestazione
    righe_archiviate = {}
    for nome in FOGLI_STAGIONE:
        valori = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range=f"{nome}!A:Z"
        ).execute(num_retries=3).get("values", [])
        righe_archiviate[nome] = max(0, len(valori) - 1)
        if len(valori) > 1:
            service.spreadsheets().values().clear(
                spreadsheetId=SPREADSHEET_ID, range=f"{nome}!A2:Z", body={}
            ).execute(num_retries=3)

    dettaglio = "\n".join(f"- {n}: {righe_archiviate[n]} righe → «{n} {etichetta}»" for n in FOGLI_STAGIONE)
    return f"✅ *Stagione {etichetta} archiviata.*\n\n{dettaglio}\n\nI fogli di lavoro sono ora vuoti e pronti per la nuova stagione."

def saldo_cassa(righe_cassa):
    """Saldo del fondo cassa, RICALCOLATO sommando tutte le entrate.

    Prima si leggeva il saldo dall'ultima riga ("Saldo Totale") e ci si sommava
    sopra il nuovo movimento. Funziona finche' nessuno tocca il foglio a mano: ma
    basta una riga inserita fuori ordine, una correzione manuale di un importo
    (come i 430 EUR di Paolo, arrotondati rispetto ai 427,85 calcolati) o un
    riordino delle righe perche' il saldo diverga in silenzio, e da li' in poi
    ogni movimento successivo eredita l'errore.

    Ricalcolarlo dalla somma delle entrate lo rende autocorrettivo: se una riga
    viene corretta a mano, il saldo si riallinea da solo al movimento dopo.
    Vedi PROJECT_LOG.md, Sessione 13.
    """
    totale = 0.0
    for i, riga in enumerate(righe_cassa):
        if i == 0 and len(riga) > 2 and str(riga[2]).strip() == "Entrate":
            continue  # riga di intestazione
        if len(riga) > 2 and str(riga[2]).strip():
            totale += estrai_numero(riga[2])
    return totale

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

ESITO_DA_VERIFICARE = "⚠️ DA VERIFICARE"
ESITO_RINVIATA = "⏸️ RINVIATA"
# Stati Football-Data che indicano una partita non giocata e rimandata: il
# regolamento dice di aspettare il recupero per assegnare i punti.
STATI_PARTITA_RINVIATA = ("POSTPONED", "SUSPENDED", "CANCELLED")

def valuta_singolo_segno(p, gol_casa, gol_ospite):
    """Valuta UN singolo segno (senza '+'). Ritorna:
       True  = vinto
       False = perso
       None  = segno NON riconosciuto (non si indovina: va segnalato all'admin)

    Il valore None e' il punto centrale di questa funzione. La versione precedente
    di controlla_esito() considerava vinto tutto cio' che non riconosceva, quindi
    un pronostico mai visto ("SI", "2X", una lettura IA vuota...) diventava punti
    regalati in silenzio. Vedi PROJECT_LOG.md, Sessione 8.
    """
    tot = gol_casa + gol_ospite
    segno = "1" if gol_casa > gol_ospite else ("2" if gol_ospite > gol_casa else "X")
    entrambe = "GOAL" if (gol_casa > 0 and gol_ospite > 0) else "NOGOAL"

    if p in ("1", "X", "2"): return p == segno
    if p == "1X": return segno in ("1", "X")
    if p == "X2": return segno in ("X", "2")
    if p == "12": return segno in ("1", "2")
    if p == "GOAL": return entrambe == "GOAL"
    if p == "NOGOAL": return entrambe == "NOGOAL"
    if p == "PARI": return (tot % 2) == 0
    if p == "DISPARI": return (tot % 2) != 0

    # OVER_x / UNDER_x con soglia esplicita. Le soglie in uso sono .5 (mai pareggio
    # esatto col totale gol); si mantengono >= e <= per replicare esattamente il
    # comportamento storico anche su eventuali soglie intere.
    m = re.match(r'^(OVER|UNDER)_(\d+(?:\.\d+)?)$', p)
    if m:
        soglia = float(m.group(2))
        return tot >= soglia if m.group(1) == "OVER" else tot <= soglia

    return None

def controlla_esito(pronostico, gol_casa, gol_ospite):
    """Esito di un pronostico completo (eventualmente combo con '+').
    Se anche un solo segno non e' riconosciuto, l'intero pronostico finisce in
    DA VERIFICARE: mai assegnare punti su qualcosa che non sappiamo interpretare."""
    if "ANNULLATA" in str(pronostico): return "➖ ANNULLATA"

    segni = [p.strip() for p in str(pronostico).split('+')]
    if not any(segni): return ESITO_DA_VERIFICARE

    vinta = True
    for p in segni:
        risultato = valuta_singolo_segno(p, gol_casa, gol_ospite)
        if risultato is None:
            return ESITO_DA_VERIFICARE
        if not risultato:
            vinta = False
    return "✅ VINTA" if vinta else "❌ PERSA"

def calcola_punteggio_partita(pronostico, quota):
    if "ANNULLATA" in pronostico: return 0
    punti = 6 if "+" in pronostico else (4 if pronostico in ["1","X","2"] else (1 if pronostico in ["1X","X2","12"] else 2))
    return punti * 2 if quota >= 3.50 else punti

def esegui_calcolo_risultati(giornata, matches_api=None):
    """Se matches_api non e' fornita, la scarica da Football-Data come sempre.
    Un chiamante puo' passarla gia' pronta (es. applica_risultato_manuale) per
    forzare il risultato di una partita specifica senza duplicare tutta la logica
    di matching/punteggio/scrittura sottostante."""
    service = connetti_sheets()
    if matches_api is None:
        url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata}"
        try: matches_api = richiedi_con_retry(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
        except: return "Errore di connessione a Football-Data API."

    if not matches_api: return "Nessuna partita trovata per questa giornata."

    righe_giocate = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Giocate!A:I").execute(num_retries=3).get('values', [])
    classifica, aggiornamenti_testo, richieste_stile = {}, [], []
    da_verificare_dettaglio = []
    colore_verde, colore_rosso, colore_grigio = {"red":0.85,"green":0.95,"blue":0.85}, {"red":0.95,"green":0.85,"blue":0.85}, {"red":0.90,"green":0.90,"blue":0.90}
    colore_giallo = {"red":1.0,"green":0.95,"blue":0.70}
    sheet_id_giocate = next(s['properties']['sheetId'] for s in service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute(num_retries=3).get('sheets', []) if s['properties']['title'].lower() == 'giocate')

    for idx, riga in enumerate(righe_giocate):
        if len(riga) < 6 or not riga_e_della_giornata(riga[0], giornata): continue
        gio, partita, pron, quota = str(riga[1]).strip(), str(riga[2]).strip(), str(riga[4]).strip().upper(), estrai_numero(riga[5])
        vincita = estrai_numero(riga[7]) if len(riga) > 7 else 0.0
        esito_salvato = str(riga[6]).strip() if len(riga) > 6 else ""

        if gio not in classifica: classifica[gio] = {"punti": 0, "vinte": 0, "perse": 0, "in_corso": 0, "da_verificare": 0, "rinviate": 0, "cassa": vincita}
        elif vincita > 0: classifica[gio]["cassa"] = vincita

        casa_sh, ospite_sh = [s.strip()[:5] for s in partita.lower().split('-')]
        match = next((m for m in matches_api if (casa_sh in str(m["homeTeam"]["name"]).lower() or casa_sh in str(m.get("homeTeam",{}).get("shortName","")).lower()) and (ospite_sh in str(m["awayTeam"]["name"]).lower() or ospite_sh in str(m.get("awayTeam",{}).get("shortName","")).lower())), None)
        ordine_invertito = False
        if not match:
            # La partita in bolletta potrebbe essere stata scritta con le squadre invertite
            # rispetto all'ordine ufficiale casa/trasferta (es. normalizzazione fallita
            # all'upload). Si ritenta con l'ordine scambiato invece di lasciare la riga
            # bloccata su IN CORSO per sempre senza nessun avviso.
            match = next((m for m in matches_api if (casa_sh in str(m["awayTeam"]["name"]).lower() or casa_sh in str(m.get("awayTeam",{}).get("shortName","")).lower()) and (ospite_sh in str(m["homeTeam"]["name"]).lower() or ospite_sh in str(m.get("homeTeam",{}).get("shortName","")).lower())), None)
            ordine_invertito = True

        punti_partita = 0
        if match:
            # Se l'esito era gia stato finalizzato (VINTA/PERSA/ANNULLATA) in un run precedente
            # e l'API ora dice che la partita non e' FINISHED, non ci si fida del regresso:
            # l'API a volte torna indietro su partite gia concluse (visto il 30/08/2026 su
            # Giornata 2, football-data.org). Si mantiene il dato gia salvato e non si riscrive nulla.
            gia_finalizzato = any(tag in esito_salvato for tag in ("VINTA", "PERSA", "ANNULLATA"))

            if match["status"] != "FINISHED" and gia_finalizzato:
                punti_partita = int(estrai_numero(riga[8])) if len(riga) > 8 else 0
                if "VINTA" in esito_salvato: classifica[gio]["punti"] += punti_partita; classifica[gio]["vinte"] += 1
                elif "PERSA" in esito_salvato: classifica[gio]["perse"] += 1
                continue  # nessuna scrittura su Sheets: la riga resta com'era

            if match["status"] in STATI_PARTITA_RINVIATA:
                # Regolamento: "per i punti si aspetta il recupero". Distinta da
                # IN CORSO perche' l'attesa puo' durare settimane: se restasse
                # IN CORSO, il riepilogo di fine giornata non partirebbe mai.
                testo_esito, col = ESITO_RINVIATA, colore_grigio
                classifica[gio]["rinviate"] += 1
            elif match["status"] != "FINISHED":
                testo_esito, col = "⏳ IN CORSO", colore_grigio
                classifica[gio]["in_corso"] += 1
            else:
                gol_home, gol_away = match["score"]["fullTime"]["home"], match["score"]["fullTime"]["away"]
                gol_casa_riga, gol_ospite_riga = (gol_away, gol_home) if ordine_invertito else (gol_home, gol_away)
                testo_esito = controlla_esito(pron, gol_casa_riga, gol_ospite_riga)
                if "VINTA" in testo_esito: col, punti_partita = colore_verde, calcola_punteggio_partita(pron, quota); classifica[gio]["punti"] += punti_partita; classifica[gio]["vinte"] += 1
                elif "ANNULLATA" in testo_esito: col = colore_grigio
                elif testo_esito == ESITO_DA_VERIFICARE:
                    # Pronostico non interpretabile: 0 punti, e NON conta come persa
                    # (altrimenti marcherebbe la schedina come "bruciata" senza motivo).
                    col = colore_giallo
                    classifica[gio]["da_verificare"] += 1
                    da_verificare_dettaglio.append(f"{gio.upper()} · {partita} · pronostico: `{pron or '(vuoto)'}`")
                else: col = colore_rosso; classifica[gio]["perse"] += 1

            aggiornamenti_testo.extend([{'range': f"Giocate!G{idx+1}", 'values': [[testo_esito]]}, {'range': f"Giocate!I{idx+1}", 'values': [[punti_partita]]}])
            richieste_stile.append({"repeatCell": {"range": {"sheetId": sheet_id_giocate, "startRowIndex": idx, "endRowIndex": idx+1, "startColumnIndex": 6, "endColumnIndex": 7}, "cell": {"userEnteredFormat": {"backgroundColor": col}}, "fields": "userEnteredFormat.backgroundColor"}})

    if aggiornamenti_testo:
        service.spreadsheets().values().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={'valueInputOption': 'USER_ENTERED', 'data': aggiornamenti_testo}).execute(num_retries=3)
        service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": richieste_stile}).execute(num_retries=3)

    vincitori, report = [], f"📊 *REPORT GIORNATA {giornata}*\n\n"
    for gio, dati in classifica.items():
        if (dati["vinte"] + dati["perse"] + dati["in_corso"] + dati["da_verificare"] + dati["rinviate"]) == 0: continue
        if dati["perse"] > 0: stato = "❌ Bruciata"
        # Una schedina con righe non interpretabili NON puo' essere dichiarata chiusa:
        # bloccherebbe +10 punti e un pagamento in Cassa su dati non verificati.
        elif dati["da_verificare"] > 0: stato = f"⚠️ Da verificare ({dati['da_verificare']})"
        elif dati["rinviate"] > 0: stato = f"⏸️ In attesa di recupero ({dati['rinviate']})"
        elif dati["in_corso"] > 0: stato = f"⏳ In attesa ({dati['in_corso']})"
        else:
            stato, dati["punti"] = "🏆 CHIUSA! (+10 Pt)", dati["punti"] + 10
            v_euro = dati["cassa"] / 2.0
            if v_euro > 0: vincitori.append({"nome": gio, "importo": v_euro})
        report += f"👤 *{gio.upper()}* - {dati['punti']} Pt\n({dati['vinte']} V | {dati['perse']} P | {dati['in_corso']} C) -> {stato}\n\n"

    if da_verificare_dettaglio:
        report += "\n⚠️ *PRONOSTICI NON INTERPRETABILI — nessun punto assegnato:*\n"
        report += "\n".join(f"- {d}" for d in da_verificare_dettaglio)
        report += "\n\nIl bot non sa interpretare questi pronostici, quindi non ha assegnato nulla. Correggili sul foglio Giocate (colonna Pronostico) e poi rilancia *Aggiorna Risultati*.\n"

    righe_class = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Classifica!A:Z").execute(num_retries=3).get('values', [["Giocatore", "Punti Totali"]])
    col_g = f"Giornata {giornata}"
    if col_g not in righe_class[0]: righe_class[0].append(col_g)
    idx_g = righe_class[0].index(col_g)
    mappa = {str(r[0]).strip().lower(): i for i, r in enumerate(righe_class) if i > 0}
    
    for gio, dati in classifica.items():
        if gio.lower() not in mappa:
            righe_class.append([gio.upper(), 0] + [""] * (len(righe_class[0]) - 2))
            mappa[gio.lower()] = len(righe_class) - 1
        while len(righe_class[mappa[gio.lower()]]) <= idx_g: righe_class[mappa[gio.lower()]].append("")
        righe_class[mappa[gio.lower()]][idx_g] = dati['punti']
        righe_class[mappa[gio.lower()]][1] = sum([int(str(x)) for x in righe_class[mappa[gio.lower()]][2:] if str(x).isdigit()])
    service.spreadsheets().values().update(spreadsheetId=SPREADSHEET_ID, range="Classifica!A1", valueInputOption="USER_ENTERED", body={"values": righe_class}).execute(num_retries=3)

    if vincitori:
        res_cassa = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Cassa!A:D").execute(num_retries=3)
        righe_cassa = res_cassa.get('values', []) or [["Giornata", "Descrizione", "Entrate", "Saldo Totale"]]
        saldo = saldo_cassa(righe_cassa)
        nuove = []
        for v in vincitori:
            descr = f"{v['nome'].upper()} chiude la schedina!"
            if not any(len(r) > 1 and r[0] == f"Giornata {giornata}" and r[1] == descr for r in righe_cassa):
                saldo += v["importo"]
                nuove.append([f"Giornata {giornata}", descr, f"{v['importo']:.2f} €".replace(".", ","), f"{saldo:.2f} €".replace(".", ",")])
                righe_cassa.append(nuove[-1])
        if nuove:
            service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range="Cassa!A:D", valueInputOption="USER_ENTERED", body={"values": nuove}).execute(num_retries=3)
            report += "💰 *Vincite registrate in Cassa!*\n"
    return report

def applica_risultato_manuale(giornata, casa_nome, ospite_nome, gol_casa, gol_ospite):
    """Inserisce a mano il risultato di UNA partita (quando Football-Data non lo
    riporta correttamente) senza perdere lo stato delle altre partite della
    stessa giornata: scarica comunque l'elenco reale delle partite (serve per non
    toccare quelle gia' segnate correttamente altrove) e sostituisce solo quella
    indicata con il risultato forzato, poi riusa esegui_calcolo_risultati cosi'
    com'e' — stessa logica, stessa protezione anti-regressione, nessuna scorciatoia."""
    url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata}"
    try:
        matches_reali = richiedi_con_retry(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
    except Exception:
        matches_reali = []

    match_forzato = {
        "homeTeam": {"name": casa_nome, "shortName": casa_nome},
        "awayTeam": {"name": ospite_nome, "shortName": ospite_nome},
        "status": "FINISHED",
        "score": {"fullTime": {"home": gol_casa, "away": gol_ospite}}
    }
    matches_finali = [
        m for m in matches_reali
        if not (
            casa_nome.lower() in str(m.get("homeTeam", {}).get("name", "")).lower()
            and ospite_nome.lower() in str(m.get("awayTeam", {}).get("name", "")).lower()
        )
    ]
    matches_finali.append(match_forzato)

    return esegui_calcolo_risultati(giornata, matches_api=matches_finali)

# ==========================================
# GESTIONE TELEGRAM E MENU CON PULSANTE KEY
# ==========================================
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riepilogo rapido: giornata corrente e chi non ha ancora caricato la schedina."""
    if update.effective_user.id != ADMIN_ID: return
    try:
        giornata = await asyncio.to_thread(ottieni_giornata_corrente)
        if giornata is None:
            await update.message.reply_text("⚠️ Non riesco a contattare Football-Data per sapere la giornata corrente. Riprova fra poco.")
            return
        service = await asyncio.to_thread(connetti_sheets)
        righe = await asyncio.to_thread(
            lambda: service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range="Giocate!A:B"
            ).execute(num_retries=3).get('values', [])
        )

        giocatori_presenti = set()
        for riga in righe:
            if len(riga) >= 2 and riga_e_della_giornata(riga[0], giornata):
                giocatori_presenti.add(str(riga[1]).strip().lower())

        mancanti = [g.capitalize() for g in GIOCATORI if g.lower() not in giocatori_presenti]

        msg = f"📊 *Status Toto-Amici*\n\n📅 Giornata corrente: *{giornata}*\n"
        if mancanti:
            msg += f"⚠️ Schedine mancanti ({len(mancanti)}):\n" + "\n".join(f"- {n}" for n in mancanti)
        else:
            msg += "✅ Tutte le schedine caricate per questa giornata."
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore durante il controllo dello status: {e}")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Esporta subito Giocate/Classifica/Cassa e le manda come documento —
    stessa logica del backup automatico del lunedì, richiamabile a mano."""
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("⏳ Preparo il backup...")
    await task_backup_periodico(context)

async def archivia_stagione_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia l'archiviazione della stagione. Operazione che SVUOTA i fogli di
    lavoro, quindi: backup automatico prima, poi conferma esplicita."""
    if update.effective_user.id != ADMIN_ID: return

    etichetta = await asyncio.to_thread(stagione_corrente)
    if not etichetta:
        await update.message.reply_text("⚠️ Non riesco a determinare la stagione corrente (API non raggiungibile). Riprova più tardi.")
        return

    context.user_data['stagione_da_archiviare'] = etichetta
    await update.message.reply_text("💾 Prima di tutto ti mando un backup di sicurezza...")
    await task_backup_periodico(context)

    kb = [
        [InlineKeyboardButton(f"✅ Sì, archivia la {etichetta}", callback_data="archivia_si")],
        [InlineKeyboardButton("❌ Annulla", callback_data="archivia_no")],
    ]
    await update.message.reply_text(
        f"⚠️ *Archiviazione stagione {etichetta}*\n\n"
        f"Farò una copia di Giocate, Classifica e Cassa nei fogli «... {etichetta}», "
        f"poi *svuoterò i fogli di lavoro* per la nuova stagione.\n\n"
        f"I dati storici restano consultabili nello spreadsheet, e hai appena ricevuto il backup qui sopra.\n\n"
        f"Procedo?",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )
    return CONFERMA_ARCHIVIA_STAGIONE

async def esegui_archivia_stagione(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "archivia_no":
        context.user_data.pop('stagione_da_archiviare', None)
        await query.edit_message_text("❌ Archiviazione annullata. Nessun dato è stato toccato.")
        return ConversationHandler.END

    etichetta = context.user_data.get('stagione_da_archiviare')
    await query.edit_message_text(f"⏳ Archivio la stagione {etichetta}...")
    try:
        esito = await asyncio.to_thread(archivia_stagione, etichetta)
        await context.bot.send_message(chat_id=ADMIN_ID, text=esito, parse_mode="Markdown")
    except Exception as e:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Archiviazione fallita: {e}")
    context.user_data.pop('stagione_da_archiviare', None)
    return ConversationHandler.END

AVVISO_CHIAVE_SALVATA = (
    "✅ **Chiave API Gemini salvata.**\n\n"
    "⚠️ Su Render questo file può essere azzerato al prossimo riavvio: se vuoi che "
    "la chiave resti per sempre, impostala anche come variabile d'ambiente "
    "`GEMINI_API_KEY` nel pannello Render (ha la precedenza su questo file)."
)

async def set_api_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ Uso corretto: `/setkey <tua_chiave_api>`", parse_mode="Markdown")
        return
    nuova_chiave = args[0].strip()
    try:
        with open('chiave_api.txt', 'w') as f: f.write(nuova_chiave)
        await update.message.reply_text(AVVISO_CHIAVE_SALVATA, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}\n\nSe il filesystem è in sola lettura, aggiorna la variabile d'ambiente `GEMINI_API_KEY` su Render.", parse_mode="Markdown")

async def gestisci_testo_chiave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    nuova_chiave = update.message.text.strip()
    try:
        with open('chiave_api.txt', 'w') as f: f.write(nuova_chiave)
        await update.message.reply_text(AVVISO_CHIAVE_SALVATA + "\n\nScrivi /start per tornare al menu.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}\n\nSe il filesystem è in sola lettura, aggiorna la variabile d'ambiente `GEMINI_API_KEY` su Render.", parse_mode="Markdown")
    return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    kb = [
        [InlineKeyboardButton("📥 Carica Schedina", callback_data="menu_carica")],
        [InlineKeyboardButton("⚽ Aggiorna Risultati & Punteggi", callback_data="menu_aggiorna")],
        [InlineKeyboardButton("✍️ Inserisci Risultato Manuale", callback_data="menu_manuale")],
        [InlineKeyboardButton("⚙️ Cambia Chiave API", callback_data="menu_cambia_key")]
    ]
    await update.message.reply_text("👋 *Menu Principale Toto-Amici*\nCosa vuoi fare?", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return MENU

async def gestisci_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "menu_carica":
        context.user_data['foto_ricevute'] = []
        kb = [[InlineKeyboardButton("✅ Finito / Avanti", callback_data="fine_invio_foto")], [InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")]]
        await query.edit_message_text("📸 **Invio Foto Multiple**\nMandami pure una o più foto della bolletta. Quando hai finito, clicca su **Finito / Avanti**!", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return ATTESA_FOTO_MULTIPLE
    elif query.data == "menu_aggiorna":
        kb = [[InlineKeyboardButton(str(i), callback_data=f"update_{i}") for i in range(r, r+5)] for r in range(1, 39, 5)]
        kb[-1] = [InlineKeyboardButton(str(i), callback_data=f"update_{i}") for i in range(36, 39)]
        kb.append([InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")])
        await query.edit_message_text("📅 Quale **Giornata** vuoi aggiornare e calcolare?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return SCELTA_GIORNATA_UPDATE
    elif query.data == "menu_cambia_key":
        kb = [[InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")]]
        await query.edit_message_text("🔑 **Cambio Chiave API**\nIncolla qui sotto la tua nuova chiave API di Google AI Studio (Gemini) come un normale messaggio di testo:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return ATTESA_NUOVA_KEY
    elif query.data == "menu_manuale":
        kb = [[InlineKeyboardButton(str(i), callback_data=f"manualeg_{i}") for i in range(r, r+5)] for r in range(1, 39, 5)]
        kb[-1] = [InlineKeyboardButton(str(i), callback_data=f"manualeg_{i}") for i in range(36, 39)]
        kb.append([InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")])
        await query.edit_message_text("✍️ **Inserimento Risultato Manuale**\nPer quale **Giornata**?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return SCELTA_GIORNATA_MANUALE

async def ricevi_foto_multipla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    photo_file = await update.message.photo[-1].get_file()
    if not os.path.exists("temp_telegram"): os.makedirs("temp_telegram")
    
    percorso_foto = f"temp_telegram/schedina_{len(context.user_data.get('foto_ricevute', [])) + 1}.jpg"
    await photo_file.download_to_drive(percorso_foto)
    
    if 'foto_ricevute' not in context.user_data: context.user_data['foto_ricevute'] = []
    context.user_data['foto_ricevute'].append(percorso_foto)
    
    tot = len(context.user_data['foto_ricevute'])
    kb = [
        [InlineKeyboardButton(f"✅ Finito (Inviate {tot} foto)", callback_data="fine_invio_foto")],
        [InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")]
    ]
    await update.message.reply_text(f"📸 Foto #{tot} ricevuta! Mandane altre oppure clicca **Finito**.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def fine_invio_foto_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if not context.user_data.get('foto_ricevute'):
        await query.edit_message_text("⚠️ Non hai inviato nessuna foto! Mandane almeno una.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")]]))
        return ATTESA_FOTO_MULTIPLE
        
    kb = [[InlineKeyboardButton(str(i), callback_data=f"giornata_{i}") for i in range(r, r+5)] for r in range(1, 39, 5)]
    kb[-1] = [InlineKeyboardButton(str(i), callback_data=f"giornata_{i}") for i in range(36, 39)]
    kb.append([InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")])
    await query.edit_message_text("📅 A quale **Giornata** si riferisce questa bolletta?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return SCELTA_GIORNATA

async def scegli_giornata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    context.user_data['giornata'] = query.data.split('_')[1]
    
    kb = [[InlineKeyboardButton(GIOCATORI[i].capitalize(), callback_data=f"giocatore_{GIOCATORI[i]}") for i in range(r, r+4)] for r in range(0, len(GIOCATORI), 4)]
    kb.append([InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")])
    await query.edit_message_text(text=f"✅ Giornata: {context.user_data['giornata']}\n\n👤 Di chi è?", reply_markup=InlineKeyboardMarkup(kb))
    return SCELTA_GIOCATORE

async def scegli_giocatore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    context.user_data['giocatore'] = query.data.split('_')[1]
    
    kb = [[InlineKeyboardButton("✅ Conferma", callback_data="conferma_si")], [InlineKeyboardButton("❌ Annulla", callback_data="conferma_no")]]
    await query.edit_message_text(text=f"⚠️ Vuoi elaborare:\n👤 **{context.user_data['giocatore'].capitalize()}** - 📅 **Giornata {context.user_data['giornata']}** ({len(context.user_data.get('foto_ricevute', []))} foto)?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return CONFERMA

async def esegui_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "conferma_no":
        await pulisci_dati(context)
        await query.edit_message_text("❌ Operazione annullata. Scrivi /start per riaprire il menu.")
        return ConversationHandler.END

    gio, giorn, foto_lista = context.user_data['giocatore'], context.user_data['giornata'], context.user_data.get('foto_ricevute', [])
    await query.edit_message_text(f"⏳ L'IA Gemini sta analizzando le foto ({len(foto_lista)}) di {gio.capitalize()}...")
    
    try:
        risultato_json_raw = await asyncio.to_thread(analizza_schedine_multiple, foto_lista)
        risultato_json = await asyncio.to_thread(normalizza_nomi_partite, risultato_json_raw, giorn)
        
        # Salva in sessione per dopo
        context.user_data['risultato_json'] = risultato_json
        
        # Genera riepilogo per admin
        dati = json.loads(risultato_json)
        vincita = dati.get("vincita_potenziale", "0")
        eventi = dati.get("eventi", dati)
        
        msg_riepilogo = f"🤖 **Lettura IA Completata!**\n\n"
        msg_riepilogo += f"💰 **Vincita Potenziale:** {vincita} €\n"
        
        # Avvisi intelligenti
        avvisi = []
        totale_eventi = 0
        try:
            vincita_num = float(str(vincita).replace(',', '.'))
        except:
            vincita_num = 0.0
        if vincita_num == 0:
            avvisi.append("⚠️ Vincita potenziale non rilevata — foto sfocata?")
        
        for categoria in ["Combo", "Fisse", "Doppie Chance", "Variabili"]:
            evs = eventi.get(categoria, [])
            totale_eventi += len(evs)
            limite = LIMITI_SCHEDINA.get(categoria, 0)
            if evs:
                msg_riepilogo += f"\n📌 **{categoria} ({len(evs)}/{limite}):**\n"
                for ev in evs:
                    msg_riepilogo += f"- {ev.get('partita', '???')} -> {ev.get('pronostico', '')} (@{ev.get('quota', '')})\n"
            if len(evs) > limite:
                avvisi.append(f"⚠️ {categoria}: trovati {len(evs)} eventi su {limite} consentiti — {len(evs) - limite} verranno annullati")
            elif len(evs) < limite:
                avvisi.append(f"⚠️ {categoria}: trovati solo {len(evs)} su {limite} previsti — potrebbe mancare qualcosa")
        
        if totale_eventi < 10:
            avvisi.append(f"⚠️ Trovati solo {totale_eventi} eventi su 10 totali previsti")
        
        if avvisi:
            msg_riepilogo += "\n🚨 **ATTENZIONE:**\n"
            for a in avvisi:
                msg_riepilogo += f"{a}\n"

        kb = [
            [InlineKeyboardButton("✅ Conferma e Salva su Sheets", callback_data="salva_ia_si")],
            [InlineKeyboardButton("❌ Annulla (Lettura Errata)", callback_data="salva_ia_no")]
        ]
        await query.edit_message_text(msg_riepilogo, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return CONFERMA_LETTURA_IA
        
    except Exception as e:
        await query.edit_message_text(f"❌ Errore durante l'elaborazione IA: {e}")
        await pulisci_dati(context)
        return ConversationHandler.END

async def esegui_salvataggio_ia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "salva_ia_no":
        await pulisci_dati(context)
        await query.edit_message_text("❌ Salvataggio annullato. Carica foto più chiare o correggi a mano.")
        return ConversationHandler.END
        
    gio, giorn = context.user_data['giocatore'], context.user_data['giornata']
    risultato_json = context.user_data.get('risultato_json')
    
    await query.edit_message_text("⏳ Scrittura su Google Sheets in corso...")
    try:
        successo = await asyncio.to_thread(scrivi_su_sheets_con_regole, gio, giorn, risultato_json)
        msg = f"✅ Schedina salvata definitivamente nel Database!" if successo else "⚠️ Errore durante la scrittura su Sheets."
        await query.edit_message_text(msg)
    except Exception as e:
        await query.edit_message_text(f"❌ Errore durante la scrittura: {e}")
        
    await pulisci_dati(context)
    return ConversationHandler.END

async def scegli_giornata_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    giornata = query.data.split('_')[1]
    await query.edit_message_text(f"⏳ Aggiornamento manuale Giornata {giornata}...")
    report = await asyncio.to_thread(esegui_calcolo_risultati, giornata)
    await context.bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode="Markdown")
    return ConversationHandler.END

async def scegli_giornata_manuale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    giornata = query.data.split('_')[1]
    context.user_data['manuale_giornata'] = giornata
    await query.edit_message_text(f"⏳ Recupero le partite della Giornata {giornata}...")

    url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata}"
    try:
        matches = await asyncio.to_thread(
            lambda: richiedi_con_retry(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
        )
    except Exception:
        matches = []

    if not matches:
        kb = [[InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")]]
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text="⚠️ Non riesco a recuperare l'elenco partite per questa giornata (l'API non risponde). Riprova più tardi.",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return ConversationHandler.END

    context.user_data['manuale_matches'] = matches
    kb = []
    for i, m in enumerate(matches):
        casa = m['homeTeam'].get('shortName') or m['homeTeam']['name']
        ospite = m['awayTeam'].get('shortName') or m['awayTeam']['name']
        kb.append([InlineKeyboardButton(f"{casa} - {ospite}", callback_data=f"manualep_{i}")])
    kb.append([InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")])
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"✍️ Giornata {giornata} — quale partita vuoi inserire?",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return SCELTA_PARTITA_MANUALE

async def scegli_partita_manuale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    idx = int(query.data.split('_')[1])
    m = context.user_data['manuale_matches'][idx]
    casa = m['homeTeam'].get('shortName') or m['homeTeam']['name']
    ospite = m['awayTeam'].get('shortName') or m['awayTeam']['name']
    context.user_data['manuale_casa'] = casa
    context.user_data['manuale_ospite'] = ospite
    context.user_data['manuale_casa_full'] = m['homeTeam']['name']
    context.user_data['manuale_ospite_full'] = m['awayTeam']['name']

    kb = [[InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")]]
    await query.edit_message_text(
        f"✍️ **{casa} - {ospite}**\n\n"
        f"Scrivimi il risultato finale in **questo formato esatto**, solo numeri e un trattino, senz'altro testo:\n\n"
        f"`gol{casa}-gol{ospite}`\n\n"
        f"Esempio: se {casa} ha vinto 2 a 1, scrivi `2-1`",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
    )
    return ATTESA_RISULTATO_MANUALE

async def ricevi_risultato_manuale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    casa = context.user_data.get('manuale_casa', '')
    ospite = context.user_data.get('manuale_ospite', '')
    testo = update.message.text.strip()

    # Validazione rigida: SOLO cifre-trattino-cifre. Niente altro viene mai accettato,
    # quindi niente rischio che un testo scritto male (es. che inizia con "=") finisca
    # su una cella di Sheets con valueInputOption=USER_ENTERED e venga letto come formula.
    match_formato = re.match(r'^(\d{1,2})-(\d{1,2})$', testo)
    if not match_formato:
        await update.message.reply_text(
            f"⚠️ Formato non valido. Scrivi **solo** due numeri separati da un trattino, es. `2-1`.\n\n"
            f"Riprova per **{casa} - {ospite}**:",
            parse_mode='Markdown'
        )
        return ATTESA_RISULTATO_MANUALE

    gol_casa, gol_ospite = int(match_formato.group(1)), int(match_formato.group(2))
    if gol_casa > 20 or gol_ospite > 20:
        await update.message.reply_text(
            f"⚠️ Numero di gol non plausibile. Riprova per **{casa} - {ospite}**:",
            parse_mode='Markdown'
        )
        return ATTESA_RISULTATO_MANUALE

    context.user_data['manuale_gol_casa'] = gol_casa
    context.user_data['manuale_gol_ospite'] = gol_ospite
    giornata = context.user_data.get('manuale_giornata')

    kb = [
        [InlineKeyboardButton("✅ Conferma", callback_data="confermamanuale_si")],
        [InlineKeyboardButton("❌ Annulla", callback_data="confermamanuale_no")]
    ]
    await update.message.reply_text(
        f"⚠️ Stai per registrare:\n\n**{casa} {gol_casa} - {gol_ospite} {ospite}**\n📅 Giornata {giornata}\n\n"
        f"Verranno segnate tutte le schedine con questa partita ancora IN CORSO. Le partite di questa giornata già segnate non verranno toccate.\n\n"
        f"Confermi?",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
    )
    return CONFERMA_RISULTATO_MANUALE

async def esegui_conferma_risultato_manuale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "confermamanuale_no":
        context.user_data.clear()
        await query.edit_message_text("❌ Operazione annullata. Scrivi /start per riaprire il menu.")
        return ConversationHandler.END

    giornata = context.user_data.get('manuale_giornata')
    casa_full = context.user_data.get('manuale_casa_full')
    ospite_full = context.user_data.get('manuale_ospite_full')
    gol_casa = context.user_data.get('manuale_gol_casa')
    gol_ospite = context.user_data.get('manuale_gol_ospite')

    await query.edit_message_text("⏳ Applico il risultato e ricalcolo i punteggi...")
    try:
        report = await asyncio.to_thread(applica_risultato_manuale, giornata, casa_full, ospite_full, gol_casa, gol_ospite)
        await context.bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode="Markdown")
    except Exception as e:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Errore durante l'applicazione del risultato: {e}")

    context.user_data.clear()
    return ConversationHandler.END

async def annulla_azione_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await pulisci_dati(context)
    await query.edit_message_text("❌ Operazione annullata. Scrivi /start per riaprire il menu.")
    return ConversationHandler.END

async def annulla_tutto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await pulisci_dati(context)
    await update.message.reply_text("❌ Operazione annullata. Scrivi /start per riaprire il menu.")
    return ConversationHandler.END

async def pulisci_dati(context: ContextTypes.DEFAULT_TYPE):
    if 'foto_ricevute' in context.user_data:
        for foto in context.user_data['foto_ricevute']:
            if os.path.exists(foto): os.remove(foto)
        del context.user_data['foto_ricevute']

async def task_aggiornamento_automatico(context: ContextTypes.DEFAULT_TYPE):
    giornata = await asyncio.to_thread(ottieni_giornata_corrente)
    if giornata is None:
        # Meglio saltare il giro che ricalcolare la giornata sbagliata.
        logging.warning("task_aggiornamento_automatico: giornata corrente sconosciuta, giro saltato")
        return
    report = await asyncio.to_thread(esegui_calcolo_risultati, giornata)
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"⏰ **AUTO UPDATE (G.{giornata})**\n\n{report}", parse_mode="Markdown")

async def task_controlla_schedine_mancanti(context: ContextTypes.DEFAULT_TYPE):
    """Controlla chi non ha ancora caricato la schedina per la giornata corrente.
    Viene chiamata da un job schedulato 30 min prima della prima partita.
    La giornata da controllare arriva da context.job.data, calcolata da
    task_schedula_promemoria a partire dalla stessa partita usata per lo scheduling
    (evita disallineamenti con ottieni_giornata_corrente(), che può aggiornarsi
    con ritardo rispetto al calendario reale)."""
    try:
        giornata = context.job.data
        service = connetti_sheets()
        righe = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range="Giocate!A:B"
        ).execute(num_retries=3).get('values', [])
        
        giocatori_presenti = set()
        for riga in righe:
            if len(riga) >= 2 and riga_e_della_giornata(riga[0], giornata):
                giocatori_presenti.add(str(riga[1]).strip().lower())
        
        mancanti = [g.capitalize() for g in GIOCATORI if g.lower() not in giocatori_presenti]
        
        if mancanti:
            msg = f"⏰ **PROMEMORIA GIORNATA {giornata}**\n\n"
            msg += f"⚠️ Mancano **{len(mancanti)} schedine** a meno di 30 minuti dalla prima partita!\n\n"
            msg += "\n".join([f"❌ {nome}" for nome in mancanti])
            msg += "\n\nSollecitali subito!"
            await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"✅ **Giornata {giornata}**: tutte le schedine sono state caricate!",
                parse_mode="Markdown"
            )
    except Exception as e:
        logging.error(f"Errore controlla_schedine_mancanti: {e}")

async def task_schedula_promemoria(context: ContextTypes.DEFAULT_TYPE):
    """Job giornaliero: controlla se ci sono partite di Serie A OGGI e schedula
    il promemoria 30 min prima della prima di esse.

    NOTA: la ricerca partite avviene per DATA (dateFrom/dateTo=oggi), non per
    'giornata corrente' (ottieni_giornata_corrente()). Quel valore, riportato
    dall'API, può restare fermo sulla giornata precedente ancora per qualche ora
    dopo l'inizio del turno (es. il venerdì sera, prima che le altre partite del
    weekend abbiano un pronostico associato) — usarlo qui avrebbe fatto perdere
    del tutto la prima partita del turno, facendo scattare il promemoria un
    giorno dopo quello giusto. La giornata di riferimento viene invece letta
    direttamente dal campo 'matchday' della partita trovata."""
    try:
        tz = pytz.timezone('Europe/Rome')
        oggi_str = datetime.now(tz).date().strftime("%Y-%m-%d")

        url = f"https://api.football-data.org/v4/competitions/SA/matches?dateFrom={oggi_str}&dateTo={oggi_str}"
        matches = richiedi_con_retry(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
        if not matches:
            return  # Nessuna partita oggi, nessun promemoria

        # Trova la prima partita di oggi non ancora iniziata
        orari_oggi = []
        for m in matches:
            utc_str = m.get("utcDate", "")
            if utc_str and m["status"] in ["TIMED", "SCHEDULED"]:
                utc_dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
                ita_dt = utc_dt.astimezone(tz)
                orari_oggi.append((ita_dt, m.get("matchday")))

        if not orari_oggi:
            return

        prima_partita, giornata = min(orari_oggi, key=lambda x: x[0])
        orario_promemoria = prima_partita - timedelta(minutes=30)
        ora_corrente = datetime.now(tz)

        if orario_promemoria > ora_corrente:
            secondi_mancanti = (orario_promemoria - ora_corrente).total_seconds()
            context.job_queue.run_once(
                task_controlla_schedine_mancanti,
                when=secondi_mancanti,
                data=giornata,
                name=f"promemoria_g{giornata}"
            )
            logging.info(f"Promemoria schedine (Giornata {giornata}) schedulato alle {orario_promemoria.strftime('%H:%M')} (tra {int(secondi_mancanti/60)} min)")
    except Exception as e:
        logging.error(f"Errore task_schedula_promemoria: {e}")

async def task_controlla_anomalie_partite(context: ContextTypes.DEFAULT_TYPE):
    """Monitoraggio periodico della Giornata corrente: avvisa l'admin invece di
    lasciare che se ne accorga da solo controllando la dashboard. Due controlli:

    1) Partite con calcio d'inizio da oltre 3 ore ma stato ancora diverso da
       FINISHED secondo Football-Data — possibile problema dati lato API
       (visto il 30/08/2026 su Giornata 2).
    2) Righe di Giocate ancora IN CORSO la cui Partita non trova corrispondenza
       in nessuna partita ufficiale della giornata — probabile nome squadra
       scritto in modo insolito o ordine invertito: a differenza del caso (1),
       questa non si risolve da sola nemmeno quando l'API torna a funzionare,
       perché esegui_calcolo_risultati non ritenta con l'ordine invertito.
    """
    try:
        giornata = await asyncio.to_thread(ottieni_giornata_corrente)
        if giornata is None:
            return
        url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata}"
        matches = await asyncio.to_thread(
            lambda: richiedi_con_retry(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
        )
        if not matches:
            return

        tz = pytz.timezone('Europe/Rome')
        ora = datetime.now(tz)

        bloccate = []
        chiavi_bloccate = set()
        for m in matches:
            utc_str = m.get("utcDate", "")
            if not utc_str:
                continue
            utc_dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
            ita_dt = utc_dt.astimezone(tz)
            ore_passate = (ora - ita_dt).total_seconds() / 3600
            if ore_passate > 3 and m["status"] != "FINISHED":
                nome_match = f"{m['homeTeam']['name']} - {m['awayTeam']['name']}"
                bloccate.append(f"{nome_match} (iniziata {ore_passate:.0f}h fa, stato: {m['status']})")
                chiavi_bloccate.add(f"bloccata:{nome_match}")

        service = await asyncio.to_thread(connetti_sheets)
        righe = await asyncio.to_thread(
            lambda: service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range="Giocate!A:G"
            ).execute(num_retries=3).get('values', [])
        )
        non_riconosciute = set()
        for riga in righe:
            if len(riga) < 3 or not riga_e_della_giornata(riga[0], giornata):
                continue
            esito = str(riga[6]).strip() if len(riga) > 6 else ""
            if "CORSO" not in esito:
                continue
            partita = str(riga[2]).strip()
            if partita.count('-') != 1:
                non_riconosciute.add(partita)
                continue
            casa_sh, ospite_sh = [s.strip()[:5].lower() for s in partita.split('-')]
            match = next((m for m in matches if (casa_sh in str(m["homeTeam"]["name"]).lower() or casa_sh in str(m.get("homeTeam",{}).get("shortName","")).lower()) and (ospite_sh in str(m["awayTeam"]["name"]).lower() or ospite_sh in str(m.get("awayTeam",{}).get("shortName","")).lower())), None)
            if not match:
                non_riconosciute.add(partita)

        global ultime_anomalie_segnalate
        chiavi_attuali = chiavi_bloccate | {f"non_riconosciuta:{p}" for p in non_riconosciute}

        if chiavi_attuali == ultime_anomalie_segnalate:
            return  # stessa situazione dell'ultimo avviso: non ripetere lo stesso messaggio

        if not chiavi_attuali:
            # le anomalie precedenti si sono risolte da sole
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"✅ Giornata {giornata}: le anomalie segnalate in precedenza risultano risolte.",
                parse_mode="Markdown"
            )
            ultime_anomalie_segnalate = set()
            return

        msg = f"🔍 *Controllo automatico Giornata {giornata}*\n\n"
        if bloccate:
            msg += "⚠️ *Partite iniziate da tempo ma non ancora concluse secondo l'API:*\n"
            msg += "\n".join(f"- {b}" for b in bloccate)
            msg += "\n\nPotrebbe essere lo stesso problema del 30/08 — controlla prima di lanciare Aggiorna Risultati.\n\n"
        if non_riconosciute:
            msg += "⚠️ *Partite in bolletta non riconosciute tra quelle ufficiali della giornata:*\n"
            msg += "\n".join(f"- {p}" for p in non_riconosciute)
            msg += "\n\nProbabile nome squadra insolito o ordine invertito — non verranno segnate automaticamente finché non le correggi a mano."
        msg += "\n\n_(Non ripeterò questo stesso avviso finché la situazione non cambia.)_"

        await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
        ultime_anomalie_segnalate = chiavi_attuali
    except Exception as e:
        logging.error(f"Errore task_controlla_anomalie_partite: {e}")

async def task_backup_periodico(context: ContextTypes.DEFAULT_TYPE):
    """Backup settimanale: esporta Giocate/Classifica/Cassa in un file JSON e
    lo manda all'admin come documento Telegram.

    Perche' serve anche se Google Sheets ha gia' una cronologia versioni
    (File -> Cronologia delle versioni): quella protegge da modifiche errate
    ma resta dentro lo stesso account Google. Questo backup vive nella chat
    Telegram dell'admin, un posto completamente separato — se mai ci fossero
    problemi di accesso all'account Google, i dati restano comunque recuperabili
    da li'. Il file locale viene cancellato subito dopo l'invio: su Render il
    disco e' comunque effimero, Telegram e' la copia che conta.
    """
    percorso_file = None
    try:
        service = await asyncio.to_thread(connetti_sheets)
        risultato = await asyncio.to_thread(
            lambda: service.spreadsheets().values().batchGet(
                spreadsheetId=SPREADSHEET_ID,
                ranges=["Giocate!A:I", "Classifica!A:Z", "Cassa!A:D"]
            ).execute(num_retries=3)
        )
        value_ranges = risultato.get("valueRanges", [])
        backup = {
            "esportato_il": datetime.now(pytz.timezone('Europe/Rome')).strftime("%Y-%m-%d %H:%M:%S"),
            "giocate": value_ranges[0].get("values", []) if len(value_ranges) > 0 else [],
            "classifica": value_ranges[1].get("values", []) if len(value_ranges) > 1 else [],
            "cassa": value_ranges[2].get("values", []) if len(value_ranges) > 2 else [],
        }

        data_str = datetime.now(pytz.timezone('Europe/Rome')).strftime("%Y-%m-%d")
        percorso_file = f"backup_toto_amici_{data_str}.json"
        with open(percorso_file, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False, indent=2)

        n_giocate = len(backup["giocate"])
        with open(percorso_file, "rb") as f:
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=f,
                filename=percorso_file,
                caption=f"💾 Backup settimanale — {data_str}\n{n_giocate} righe in Giocate."
            )
    except Exception as e:
        logging.error(f"Errore task_backup_periodico: {e}")
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ Backup settimanale fallito: {e}")
        except Exception:
            pass
    finally:
        if percorso_file and os.path.exists(percorso_file):
            os.remove(percorso_file)

def costruisci_riepilogo_whatsapp(giornata, righe_classifica, righe_cassa, n_rinviate=0):
    """Testo del riepilogo di fine giornata, pronto da incollare su WhatsApp.

    Usa grassetto con un solo asterisco (*testo*) di proposito: e' la stessa
    sintassi che usa WhatsApp per il grassetto. Il messaggio viene inviato su
    Telegram SENZA parse_mode (vedi task_riepilogo_whatsapp), cosi' gli
    asterischi restano testo letterale nel messaggio invece di essere
    "consumati" dal rendering di Telegram — copiandolo e incollandolo su
    WhatsApp, la formattazione funziona li' invece che sparire.
    """
    if not righe_classifica or len(righe_classifica) < 2:
        return None
    header = righe_classifica[0]
    col_g = f"Giornata {giornata}"
    if col_g not in header:
        return None
    idx_g = header.index(col_g)

    giocatori = []
    for riga in righe_classifica[1:]:
        if not riga or not str(riga[0]).strip():
            continue
        nome = str(riga[0]).strip()
        punti_tot = int(estrai_numero(riga[1])) if len(riga) > 1 else 0
        punti_giornata = int(estrai_numero(riga[idx_g])) if len(riga) > idx_g else 0
        giocatori.append((nome, punti_tot, punti_giornata))
    if not giocatori:
        return None

    giocatori.sort(key=lambda x: -x[1])
    medaglie = ["🥇", "🥈", "🥉"]
    righe_testo = []
    for i, (nome, tot, pg) in enumerate(giocatori):
        pos = medaglie[i] if i < len(medaglie) else f"{i + 1}°"
        variazione = f" (+{pg})" if pg > 0 else ""
        righe_testo.append(f"{pos} {nome.capitalize()} - {tot} pt{variazione}")

    testo = f"📊 *Giornata {giornata} — Riepilogo finale*\n\n" + "\n".join(righe_testo)
    if n_rinviate:
        testo += f"\n\n⏸️ _{n_rinviate} event{'o' if n_rinviate == 1 else 'i'} in attesa di recupero: i punti verranno assegnati a partita giocata._"

    vincitori = [
        str(r[1]) for r in righe_cassa
        if len(r) > 1 and str(r[0]).strip() == col_g and "chiude la schedina" in str(r[1])
    ]
    if vincitori:
        nomi_vincitori = [v.split(" chiude")[0].capitalize() for v in vincitori]
        testo += "\n\n🏆 *Schedina chiusa:* " + ", ".join(nomi_vincitori) + " (+10 pt bonus)"

    if righe_cassa and len(righe_cassa[-1]) > 3 and righe_cassa[-1][3] != "Saldo Totale":
        testo += f"\n💰 *Fondo Cassa:* {righe_cassa[-1][3]}"

    testo += "\n\n⚽ Prossima giornata in arrivo!"
    return testo

async def task_riepilogo_whatsapp(context: ContextTypes.DEFAULT_TYPE, notifica_se_non_pronto=False):
    """Ogni mattina controlla se la giornata corrente e' completamente
    conclusa (nessuna riga ancora IN CORSO in Giocate) e, se non l'ha gia'
    fatto, manda all'admin il riepilogo pronto da incollare su WhatsApp.

    La "conclusione" si basa sui NOSTRI dati (Giocate), non su una nuova
    chiamata a Football-Data: una volta che una partita e' stata segnata
    correttamente resta protetta dall'anti-regressione (Sessione 6), quindi
    e' una base piu' affidabile di un controllo live che potrebbe trovare
    l'API di nuovo bloccata (vedi incidente 30/08/2026).

    notifica_se_non_pronto: se True (usato da /riepilogo), spiega all'admin
    perche' non ha mandato nulla invece di restare silenzioso.
    """
    global ultima_giornata_riepilogo_inviata
    try:
        giornata = await asyncio.to_thread(ottieni_giornata_corrente)
        if giornata is None:
            if notifica_se_non_pronto:
                await context.bot.send_message(chat_id=ADMIN_ID, text="⚠️ Non riesco a contattare Football-Data per sapere la giornata corrente. Riprova fra poco.")
            return

        service = await asyncio.to_thread(connetti_sheets)
        righe_giocate = await asyncio.to_thread(
            lambda: service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range="Giocate!A:G"
            ).execute(num_retries=3).get('values', [])
        )
        righe_giornata = [
            r for r in righe_giocate
            if len(r) >= 7 and riga_e_della_giornata(r[0], giornata)
        ]
        if not righe_giornata:
            if notifica_se_non_pronto:
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"ℹ️ Nessuna schedina ancora caricata per la Giornata {giornata}.")
            return
        if any("CORSO" in str(r[6]) for r in righe_giornata):
            if notifica_se_non_pronto:
                n_in_corso = sum(1 for r in righe_giornata if "CORSO" in str(r[6]))
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"⏳ Giornata {giornata} non ancora conclusa: {n_in_corso} eventi ancora IN CORSO.")
            return

        if str(giornata) == str(ultima_giornata_riepilogo_inviata):
            if notifica_se_non_pronto:
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"ℹ️ Il riepilogo della Giornata {giornata} è già stato mandato.")
            return

        righe_classifica = await asyncio.to_thread(
            lambda: service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range="Classifica!A:Z"
            ).execute(num_retries=3).get('values', [])
        )
        righe_cassa = await asyncio.to_thread(
            lambda: service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range="Cassa!A:D"
            ).execute(num_retries=3).get('values', [])
        )

        n_rinviate = sum(1 for r in righe_giornata if ESITO_RINVIATA in str(r[6]))
        testo = costruisci_riepilogo_whatsapp(giornata, righe_classifica, righe_cassa, n_rinviate)
        if not testo:
            return

        await context.bot.send_message(chat_id=ADMIN_ID, text=testo)  # niente parse_mode: vedi costruisci_riepilogo_whatsapp
        ultima_giornata_riepilogo_inviata = str(giornata)
    except Exception as e:
        logging.error(f"Errore task_riepilogo_whatsapp: {e}")

async def riepilogo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forza subito il controllo/invio del riepilogo, senza aspettare la mattina
    (utile per testare, o per rimandarlo se serve). Ignora la deduplica."""
    if update.effective_user.id != ADMIN_ID: return
    global ultima_giornata_riepilogo_inviata
    ultima_giornata_riepilogo_inviata = None
    await update.message.reply_text("⏳ Controllo se la giornata è conclusa...")
    await task_riepilogo_whatsapp(context, notifica_se_non_pronto=True)

async def post_init(application: Application):
    """Imposta i comandi rapidi ufficiali nel menu di Telegram (il tasto '/')"""
    await application.bot.set_my_commands([
        ("start", "Apri il menu principale"),
        ("status", "Giornata corrente e schedine mancanti"),
        ("backup", "Esporta subito un backup dei dati"),
        ("riepilogo", "Riepilogo giornata pronto per WhatsApp"),
        ("archiviastagione", "Chiudi la stagione e azzera i fogli"),
        ("setkey", "Cambia al volo la chiave API di Gemini")
    ])

def main():
    # Se le variabili d'ambiente non ci sono (es. testing locale), il bot si ferma qui per evitare errori.
    if not TOKEN:
        logging.error("ERRORE: Variabile TELEGRAM_TOKEN non trovata. Impossibile avviare il bot.")
        return

    # AVVIO DEL FINTO SITO WEB IN BACKGROUND PER RENDER
    threading.Thread(target=run_web_server, daemon=True).start()

    # AVVIO DEL BOT TELEGRAM
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    tz = pytz.timezone('Europe/Rome')
    # Orari scelti per dare più occasioni di "agganciare" un dato corretto prima che
    # Football-Data lo rielabori (visto il 30/08/2026): uno presto al mattino (prima di
    # eventuali rielaborazioni notturne), uno tardo dopo mezzanotte per le partite serali,
    # più i tre già esistenti nel corso della giornata/sera.
    for h, m in [(1,0), (8,0), (17,30), (20,30), (23,0)]:
        app.job_queue.run_daily(task_aggiornamento_automatico, time=dt_time(hour=h, minute=m, tzinfo=tz))

    # Job giornaliero: alle 10:00 controlla se ci sono partite oggi e schedula promemoria 30min prima
    app.job_queue.run_daily(task_schedula_promemoria, time=dt_time(hour=10, minute=0, tzinfo=tz))

    # Job ricorrente ogni 2 ore: controlla anomalie nei dati Football-Data della giornata corrente
    app.job_queue.run_repeating(task_controlla_anomalie_partite, interval=7200, first=600)

    # Backup settimanale (lunedì mattina, orario tranquillo) inviato come documento all'admin
    app.job_queue.run_daily(task_backup_periodico, time=dt_time(hour=9, minute=0, tzinfo=tz), days=(0,))

    # Riepilogo di fine giornata per WhatsApp: controllato ogni mattina, si invia da
    # solo (una volta sola) appena la giornata risulta completamente conclusa
    app.job_queue.run_daily(task_riepilogo_whatsapp, time=dt_time(hour=9, minute=15, tzinfo=tz))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(gestisci_menu, pattern="^menu_")],
            ATTESA_FOTO_MULTIPLE: [
                MessageHandler(filters.PHOTO, ricevi_foto_multipla),
                CallbackQueryHandler(fine_invio_foto_callback, pattern="^fine_invio_foto$"),
                CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$")
            ],
            SCELTA_GIORNATA: [
                CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$"),
                CallbackQueryHandler(scegli_giornata, pattern="^giornata_")
            ],
            SCELTA_GIOCATORE: [
                CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$"),
                CallbackQueryHandler(scegli_giocatore, pattern="^giocatore_")
            ],
            CONFERMA: [
                CallbackQueryHandler(esegui_conferma, pattern="^conferma_"),
                CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$")
            ],
            CONFERMA_LETTURA_IA: [
                CallbackQueryHandler(esegui_salvataggio_ia, pattern="^salva_ia_"),
                CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$")
            ],
            SCELTA_GIORNATA_UPDATE: [
                CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$"),
                CallbackQueryHandler(scegli_giornata_update, pattern="^update_")
            ],
            ATTESA_NUOVA_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, gestisci_testo_chiave),
                CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$")
            ],
            SCELTA_GIORNATA_MANUALE: [
                CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$"),
                CallbackQueryHandler(scegli_giornata_manuale, pattern="^manualeg_")
            ],
            SCELTA_PARTITA_MANUALE: [
                CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$"),
                CallbackQueryHandler(scegli_partita_manuale, pattern="^manualep_")
            ],
            ATTESA_RISULTATO_MANUALE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_risultato_manuale),
                CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$")
            ],
            CONFERMA_RISULTATO_MANUALE: [
                CallbackQueryHandler(esegui_conferma_risultato_manuale, pattern="^confermamanuale_")
            ]
        },
        fallbacks=[CommandHandler("cancel", annulla_tutto)]
    )

    app.add_handler(CommandHandler("setkey", set_api_key_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("riepilogo", riepilogo_command))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("archiviastagione", archivia_stagione_command)],
        states={CONFERMA_ARCHIVIA_STAGIONE: [CallbackQueryHandler(esegui_archivia_stagione, pattern="^archivia_")]},
        fallbacks=[CommandHandler("cancel", annulla_tutto)],
    ))
    app.add_handler(conv_handler)
    logging.info("🤖 Super-Bot Telegram avviato: in ascolto su Telegram e pronto ai ping di keep-alive.")
    app.run_polling()

if __name__ == '__main__':
    main()