import os
import sys
import gc
import ctypes
import json
import logging
import random
import re
import time
import resource
import asyncio
import requests
from api_utils import richiedi_con_retry
from statistiche import e_ritirato, nome_senza_ritiro
from datetime import time as dt_time, datetime, timedelta
import pytz
import threading
from flask import Flask
from PIL import Image
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeChat
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# ==========================================
# VARIABILI D'AMBIENTE (SICUREZZA CLOUD)
# ==========================================
TOKEN = os.environ.get("TELEGRAM_TOKEN")
# ADMIN_ID resta l'OWNER: l'unico che puo' cambiare la chiave API e archiviare
# la stagione (le due operazioni che non sono "gestione quotidiana"). Gli altri
# admin si aggiungono con ADMIN_IDS, e hanno tutto il resto. Vedi e_admin/e_owner.
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
FOOTBALL_DATA_KEY = os.environ.get("FOOTBALL_DATA_KEY")
SERVICE_ACCOUNT_FILE = 'credenziali.json'

# Fogli di lavoro della stagione IN CORSO. Le stagioni passate restano nello
# stesso spreadsheet con il suffisso dell'annata (es. "Giocate 2026-27"),
# create da /archiviastagione. Vedi PROJECT_LOG.md, Sessione 13.
FOGLI_STAGIONE = ("Giocate", "Classifica", "Cassa")


def leggi_admin_ids(owner_id, grezzo):
    """Lista degli ID autorizzati: l'owner piu' quelli elencati in ADMIN_IDS.

    L'owner e' sempre il primo, e la lista non ha duplicati: l'ordine conta,
    perche' e' l'ordine in cui partono le notifiche broadcast.

    Un valore non numerico viene ignorato con un warning invece di far
    esplodere l'avvio: una virgola di troppo incollata nel pannello Render
    non deve impedire al bot di partire — resterebbe giu' fino al prossimo
    intervento manuale, che e' molto peggio di un admin in meno per un giro.
    """
    ids = []
    if owner_id:
        ids.append(owner_id)
    for pezzo in re.split(r"[,;\s]+", str(grezzo or "")):
        if not pezzo:
            continue
        try:
            valore = int(pezzo)
        except ValueError:
            logging.warning("ADMIN_IDS: ignoro il valore non numerico %r", pezzo)
            continue
        if valore and valore not in ids:
            ids.append(valore)
    return ids


OWNER_ID = ADMIN_ID
ADMIN_IDS = leggi_admin_ids(OWNER_ID, os.environ.get("ADMIN_IDS", ""))


def e_admin(user_id):
    """True se l'utente puo' usare il bot. Con ADMIN_ID non configurato la
    lista e' vuota e qui non passa nessuno: meglio un bot muto che un bot
    aperto a chiunque."""
    return user_id in ADMIN_IDS


def e_owner(user_id):
    """True solo per ADMIN_ID. Serve alle due operazioni riservate:
    /setkey (tocca una credenziale) e /archiviastagione (svuota i fogli)."""
    return bool(OWNER_ID) and user_id == OWNER_ID


def nome_attore(update):
    """Nome leggibile di chi ha lanciato l'azione, per la riga di tracciabilita'
    mandata agli altri admin. Con piu' di una persona al comando, «e' stato
    ricalcolato» non basta piu': serve sapere da chi."""
    utente = getattr(update, "effective_user", None)
    if utente is None:
        return "Admin"
    nome = (getattr(utente, "full_name", None) or getattr(utente, "first_name", None) or "").strip()
    return nome or f"Admin {utente.id}"


def destinatari_notifica(destinatari=None, escludi=None):
    """Chi deve ricevere un messaggio. None = tutti gli admin.

    `escludi` serve alle righe di tracciabilita': chi ha appena fatto
    l'operazione ha gia' l'esito completo nella sua chat, ricevere anche
    l'avviso «X ha fatto Y» sarebbe solo rumore.
    """
    lista = list(ADMIN_IDS) if destinatari is None else (
        [destinatari] if isinstance(destinatari, int) else list(destinatari)
    )
    if escludi is not None:
        lista = [i for i in lista if i != escludi]
    return lista


async def avvisa_admin(context, testo, destinatari=None, escludi=None, parse_mode="Markdown", **kwargs):
    """Manda un messaggio agli admin e restituisce quanti l'hanno ricevuto.

    Due garanzie, entrambe nate da incidenti gia' visti:

    1. Un invio fallito non ferma gli altri. Basta che UN admin abbia bloccato
       il bot (Telegram risponde 403) perche' un `send_message` in cima al giro
       faccia saltare la notifica anche a chi l'avrebbe ricevuta: l'avviso di
       anomalia che nessuno legge e' peggio di nessun avviso.
    2. Se Telegram rifiuta la formattazione, il testo parte lo stesso senza
       parse_mode. Il Markdown legacy si rompe su un underscore dispari — i
       pronostici normalizzati ne sono pieni per costruzione (`OVER_2.5`) — e
       un errore di formattazione non deve far buttare via il contenuto
       (Sessione 15).
    """
    # parse_mode=None non viene passato affatto, invece che passato a None:
    # e' la stessa cosa per Telegram, ma lascia la chiamata identica a un
    # send_message normale.
    extra = dict(kwargs)
    if parse_mode:
        extra["parse_mode"] = parse_mode

    inviati = 0
    for chat_id in destinatari_notifica(destinatari, escludi):
        try:
            await context.bot.send_message(chat_id=chat_id, text=testo, **extra)
            inviati += 1
            continue
        except Exception as e:
            errore = e
        if parse_mode:
            try:
                await context.bot.send_message(chat_id=chat_id, text=testo, **kwargs)
                inviati += 1
                logging.warning("Notifica a %s inviata senza formattazione: %s", chat_id, errore)
                continue
            except Exception as e:
                errore = e
        logging.error("Notifica all'admin %s non riuscita: %s", chat_id, errore)
    return inviati


async def traccia_azione(update, context, testo):
    """Avvisa gli ALTRI admin di un'azione che tocca punteggi, Cassa o dati.

    Non e' un registro a prova di contestazione: e' la convenzione minima che
    serve a due persone per non pestarsi i piedi — vedere passare «Silvio ha
    inserito Inter-Roma 2-1» evita di rifare la stessa correzione due volte, o
    di cercare per mezz'ora chi ha cambiato un punteggio. Resta nella chat, dove
    gli admin guardano gia'; niente colonne nuove su Sheets, che vorrebbe dire
    toccare la scrittura per indice di riga (il bug delle 13 giornate).
    """
    try:
        logging.info("AZIONE ADMIN — %s (id %s): %s",
                     nome_attore(update), getattr(getattr(update, "effective_user", None), "id", "?"), testo)
        attore_id = getattr(getattr(update, "effective_user", None), "id", None)
        if len(destinatari_notifica(escludi=attore_id)) == 0:
            return 0
        return await avvisa_admin(
            context,
            f"👤 *{escape_markdown(nome_attore(update))}* {testo}",
            escludi=attore_id,
        )
    except Exception as e:
        # Non solleva mai: viene chiamata subito dopo operazioni che hanno GIA'
        # scritto su Sheets, e un problema nell'avvisare gli altri non deve far
        # credere a chi ha agito che il lavoro sia fallito.
        logging.error("Tracciabilita' non riuscita (l'operazione era andata a buon fine): %s", e)
        return 0

# ==========================================
# LAVORO IN PARALLELO FRA PIU' ADMIN
# ==========================================
# Il controllo anti-doppione vero sta in scrivi_su_sheets_con_regole (rilegge
# il foglio e rifiuta una schedina gia' presente). Qui ci sono i due pezzi che
# quel controllo da solo non puo' coprire:
#
#   1. la finestra fra la sua lettura e la sua scrittura (~1s), in cui due
#      salvataggi simultanei trovano entrambi il posto libero -> lock_salvataggio_schedina;
#   2. il caso in cui nessuno dei due ha ancora salvato perche' stanno
#      entrambi caricando le foto -> LAVORAZIONI_IN_CORSO.

_lock_salvataggio = None


def lock_salvataggio_schedina():
    """Serializza «rileggi il foglio, controlla, scrivi» fra tutti gli admin.

    Senza, con due "Salva" premuti nello stesso secondo entrambi i controlli
    rileggono Giocate prima che l'altro abbia scritto, entrambi trovano il
    posto libero, e la schedina finisce nel foglio due volte — che e'
    esattamente il caso che il controllo doveva impedire (i punti verrebbero
    contati due volte, misurato: 50 diventano 90).

    Il bot e' un processo solo su Render, quindi basta serializzare qui: un
    lock distribuito sarebbe sproporzionato. Non protegge da una modifica
    fatta a mano sul foglio nello stesso istante, ma quello non e' il caso
    che stiamo coprendo.

    Creato alla prima chiamata, cioe' dentro un event loop gia' avviato.
    """
    global _lock_salvataggio
    if _lock_salvataggio is None:
        _lock_salvataggio = asyncio.Lock()
    return _lock_salvataggio


# (giornata, giocatore) -> (admin_id, nome, momento_di_inizio)
LAVORAZIONI_IN_CORSO = {}
SCADENZA_LAVORAZIONE_S = 900  # 15 minuti


def chiave_lavorazione(giornata, giocatore):
    return (str(giornata).strip(), str(giocatore).strip().lower())


def segna_lavorazione(giornata, giocatore, admin_id, nome, adesso=None):
    """Registra che un admin ha iniziato a caricare questa schedina."""
    adesso = time.time() if adesso is None else adesso
    # Le lavorazioni scadute si buttano qui: un flusso abbandonato a meta'
    # (app chiusa, foto mai confermate) non deve restare nel registro per
    # sempre ne' tenere occupata una schedina.
    for chiave, (_, _, inizio) in list(LAVORAZIONI_IN_CORSO.items()):
        if adesso - inizio > SCADENZA_LAVORAZIONE_S:
            del LAVORAZIONI_IN_CORSO[chiave]
    LAVORAZIONI_IN_CORSO[chiave_lavorazione(giornata, giocatore)] = (admin_id, nome, adesso)


def lavorazione_altrui(giornata, giocatore, admin_id, adesso=None):
    """Chi ALTRI sta gia' caricando questa schedina: (nome, secondi) oppure None.

    E' un avviso, non un lucchetto: l'altro admin potrebbe abbandonare a meta',
    e bloccare la schedina per un lavoro che non arrivera' mai sarebbe peggio
    del problema. Chi legge l'avviso decide.
    """
    adesso = time.time() if adesso is None else adesso
    voce = LAVORAZIONI_IN_CORSO.get(chiave_lavorazione(giornata, giocatore))
    if voce is None:
        return None
    chi, nome, inizio = voce
    if chi == admin_id or adesso - inizio > SCADENZA_LAVORAZIONE_S:
        return None
    return nome, int(adesso - inizio)


def libera_lavorazione(giornata, giocatore, admin_id):
    """Toglie la lavorazione, ma solo se e' la propria: annullare il proprio
    caricamento non deve sbloccare quello di un altro."""
    chiave = chiave_lavorazione(giornata, giocatore)
    voce = LAVORAZIONI_IN_CORSO.get(chiave)
    if voce is not None and voce[0] == admin_id:
        del LAVORAZIONI_IN_CORSO[chiave]


def da_quanto(secondi):
    """«da meno di un minuto» invece di «da 0 min»."""
    return "da meno di un minuto" if secondi < 60 else f"da {secondi // 60} min"


GIOCATORI = [
    "cecilia", "dario", "davide", "fazio", 
    "gaetano", "giacomo", "giovanni", "mario", 
    "michele", "mirko", "nico", "paolo", 
    "silvio", "siracusa", "villari", "vincenzo"
]

LIMITI_SCHEDINA = {"Combo": 1, "Fisse": 4, "Doppie Chance": 2, "Variabili": 3}

# Stati Conversazione
(MENU, ATTESA_FOTO_MULTIPLE, SCELTA_GIORNATA, SCELTA_GIOCATORE, CONFERMA, CONFERMA_LETTURA_IA,
 SCELTA_GIORNATA_UPDATE, ATTESA_NUOVA_KEY, SCELTA_GIORNATA_MANUALE, SCELTA_PARTITA_MANUALE,
 ATTESA_RISULTATO_MANUALE, CONFERMA_RISULTATO_MANUALE, CONFERMA_ARCHIVIA_STAGIONE) = range(13)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
# httpx registra OGNI chiamata a Telegram: con il polling sono circa 8.600 righe
# al giorno, tutte uguali, dentro cui va poi cercato l'errore vero. Restano i
# suoi WARNING e ERROR, che sono gli unici utili.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Foto delle schedine scaricate da Telegram, cancellate a fine caricamento.
CARTELLA_FOTO = "temp_telegram"


def pulisci_foto_residue(cartella=CARTELLA_FOTO):
    """Cancella le foto rimaste da un caricamento interrotto e ne restituisce il numero.

    Le foto si cancellano a fine flusso (conferma o annullamento): se l'admin ne
    manda qualcuna e poi abbandona, restano li'. Il disco di Render e' effimero,
    quindi un riavvio le porterebbe via comunque: questa e' la stessa pulizia
    fatta in modo esplicito, utile anche in locale.
    """
    if not os.path.isdir(cartella):
        return 0
    cancellate = 0
    for nome in os.listdir(cartella):
        percorso = os.path.join(cartella, nome)
        if os.path.isfile(percorso):
            try:
                os.remove(percorso)
                cancellate += 1
            except OSError:
                logging.warning("Non sono riuscito a cancellare la foto residua %s", percorso)
    return cancellate

if not TOKEN or not SPREADSHEET_ID or not FOOTBALL_DATA_KEY or ADMIN_ID == 0:
    logging.warning("⚠️ ATTENZIONE: Variabili d'ambiente mancanti. Il bot potrebbe non funzionare correttamente!")

last_ping_time = None
ultime_anomalie_segnalate = set()  # chiavi stabili delle anomalie dell'ultimo avviso inviato (per non ripetere lo stesso avviso ad ogni controllo)
ultimo_report_inviato = None  # (giornata, testo) dell'ultimo AUTO UPDATE: se non cambia nulla non lo si ripete
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
            # Girano nel thread di Flask, senza il `context` di python-telegram-bot:
            # qui l'invio e' una POST diretta. Un fallimento su un admin non deve
            # impedire l'allarme agli altri, quindi il try sta DENTRO il ciclo.
            testo_allarme = (
                f"⚠️ **ALLARME KEEP-ALIVE**\nSono passati {int(delta/60)} minuti dall'ultimo ping "
                f"(Render spegne il servizio dopo 15).\nControlla che il job su cron-job.org sia attivo e riuscito."
            )
            for admin_id in ADMIN_IDS:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                        json={
                            "chat_id": admin_id,
                            "text": testo_allarme,
                            "parse_mode": "Markdown"
                        }
                    )
                except Exception as e:
                    logging.error(f"Errore invio alert Telegram a {admin_id}: {e}")
    last_ping_time = now
    return "✅ Il Bot Toto-Amici è online e sta funzionando perfettamente 24/7!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port, threaded=True)

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

CATEGORIE_SCHEDINA = ("Combo", "Fisse", "Doppie Chance", "Variabili")

# Schema imposto all'API: la forma del JSON non deve dipendere dal modello che
# risponde. Il 02/09/2026 lo stesso gemini-3.5-flash ha restituito le categorie
# dentro "eventi" in una richiesta e al primo livello in quella dopo; un modello
# di riserva ha risposto con una forma che il codice non riconosceva, e il bot
# ha mostrato "0 eventi" su una schedina piena, senza alcun errore (Sessione 15).
_SCHEMA_EVENTO = {
    "type": "object",
    "properties": {
        "partita": {"type": "string"},
        "pronostico": {"type": "string"},
        "quota": {"type": "string"},
    },
    "required": ["partita", "pronostico", "quota"],
}
SCHEMA_SCHEDINA = {
    "type": "object",
    "properties": {
        "vincita_potenziale": {"type": "string"},
        "eventi": {
            "type": "object",
            "properties": {c: {"type": "array", "items": _SCHEMA_EVENTO} for c in CATEGORIE_SCHEDINA},
            "required": list(CATEGORIE_SCHEDINA),
        },
    },
    "required": ["vincita_potenziale", "eventi"],
}


def _chiave_categoria(testo):
    """'Doppia Chance', 'doppie_chance', 'DOPPIE CHANCE' -> 'doppiechance'."""
    return re.sub(r"[^a-z]", "", str(testo).lower())


_ALIAS_CATEGORIE = {_chiave_categoria(c): c for c in CATEGORIE_SCHEDINA}
_ALIAS_CATEGORIE.update({
    "doppiachance": "Doppie Chance",
    "doppiechances": "Doppie Chance",
    "doppie": "Doppie Chance",
    "combinate": "Combo",
    "combo": "Combo",
    "fissa": "Fisse",
    "variabile": "Variabili",
})


def estrai_eventi_per_categoria(dati):
    """Riporta il JSON dell'IA alla forma attesa dal resto del codice, comunque
    sia arrivato: {"Combo": [...], "Fisse": [...], ...}.

    Difesa in profondita' accanto a SCHEMA_SCHEDINA: lo schema impedisce il
    problema a monte, questa funzione lo sopravvive se un modello lo ignora.
    Prima il codice faceva `dati.get("eventi", dati).get(categoria, [])`, cioe'
    pretendeva le chiavi ESATTE: bastava "Doppia Chance" al posto di "Doppie
    Chance" per far leggere 0 eventi senza sollevare nessun errore — che e' il
    modo peggiore di fallire, perche' sembra una schedina vuota invece di un
    bug (Sessione 15).

    Forme gestite:
    - {"eventi": {"Combo": [...]}}          (quella dichiarata nello schema)
    - {"Combo": [...], "Fisse": [...]}      (categorie al primo livello)
    - chiavi con maiuscole/spazi/underscore diversi
    - {"eventi": [{"categoria": "Combo", ...}]}  (lista piatta)
    """
    risultato = {c: [] for c in CATEGORIE_SCHEDINA}
    if not isinstance(dati, dict):
        return risultato

    contenitore = dati.get("eventi", dati)

    if isinstance(contenitore, list):
        for evento in contenitore:
            if not isinstance(evento, dict):
                continue
            etichetta = evento.get("categoria") or evento.get("tipo") or ""
            canonica = _ALIAS_CATEGORIE.get(_chiave_categoria(etichetta))
            if canonica:
                risultato[canonica].append(evento)
        return risultato

    if not isinstance(contenitore, dict):
        return risultato

    for chiave, valore in contenitore.items():
        canonica = _ALIAS_CATEGORIE.get(_chiave_categoria(chiave))
        if canonica and isinstance(valore, list):
            risultato[canonica].extend(v for v in valore if isinstance(v, dict))
    return risultato


def escape_markdown(testo):
    """Neutralizza i caratteri che Telegram interpreta come formattazione.

    Serve per QUALSIASI testo che non abbiamo scritto noi (output dell'IA, nomi
    partita, pronostici) prima di infilarlo in un messaggio con
    parse_mode="Markdown". I pronostici normalizzati contengono underscore per
    costruzione — `OVER_2.5`, `UNDER_2.5`, `1+OVER_2.5` (vedi il prompt di
    analizza_schedine_multiple) — e in Markdown legacy l'underscore apre il
    corsivo: con un numero dispari di underscore nel messaggio, Telegram
    risponde "Can't parse entities: can't find end of the entity" e RIFIUTA
    l'intero messaggio. E' successo il 02/09/2026 caricando una schedina della
    Giornata 3: la lettura IA era perfetta, ma il riepilogo non partiva e il
    lavoro veniva buttato via (Sessione 15).
    """
    if testo is None:
        return ""
    testo = str(testo)
    for carattere in ("_", "*", "`", "["):
        testo = testo.replace(carattere, "\\" + carattere)
    return testo


ERRORI_GEMINI_TRANSITORI = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "INTERNAL", "504", "DEADLINE", "TIMED OUT", "TIMEOUT")
ERRORI_MODELLO_NON_DISPONIBILE = ("404", "NOT_FOUND", "NOT FOUND")
# Un 503 arriva in una frazione di secondo: riprovare lo stesso modello costa
# nulla. Un timeout invece ha gia' bruciato 60 secondi, e riprovare lo stesso
# modello congestionato quasi certamente ne brucia altri 60 mentre l'admin
# aspetta. In quel caso conviene cambiare modello subito.
ERRORI_SENZA_SECONDO_TENTATIVO = ("504", "DEADLINE", "TIMED OUT", "TIMEOUT")

# Catena di modelli, provati in quest'ordine. NON e' ridondanza per eccesso di
# zelo: misurazioni del 02/09/2026 sullo stesso identico carico (immagine +
# risposta JSON) con la chiave del progetto:
#   gemini-3.8-flash    -> 503 UNAVAILABLE (il piu' recente, sempre saturo)
#   gemini-3.6-flash    -> 96s su un prompt banale, oppure 503  <- era il primario
#   gemini-3.7-flash    -> 38s
#   gemini-3.5-flash    -> 18s sulla schedina completa, 10/10 pronostici corretti
#   gemini-flash-latest ->  2s in un test, 503 dieci minuti dopo
# La congestione SI SPOSTA da un modello all'altro nel giro di minuti: nessun
# singolo modello e' affidabile da solo, per questo serve una catena e non
# semplicemente un modello diverso (Sessione 15).
MODELLI_GEMINI = ("gemini-3.5-flash", "gemini-flash-latest", "gemini-3.7-flash", "gemini-3.6-flash")

# Il minimo accettato dall'API e' 10s. Senza un tetto, un modello congestionato
# tiene occupato il bot per oltre un minuto e mezzo (96s misurati) mentre
# l'admin aspetta davanti a "L'IA sta analizzando le foto...".
TIMEOUT_GEMINI_MS = 60000

# Risoluzione a cui vengono ridotte le foto delle schedine prima di mandarle
# all'IA. Oltre questa soglia non si guadagna in accuratezza di lettura, ma si
# paga molta memoria (vedi il commento in analizza_schedine_multiple).
DIMENSIONE_MAX_FOTO = (1000, 1000)


def memoria_picco_mb():
    """Massima memoria mai occupata dal processo da quando e' partito, in MB.

    E' il numero che conta per capire perche' Render ha ucciso il bot: e' il
    picco a sfondare il limite, non la media. Ma NON scende mai, quindi da solo
    non dice come stiamo adesso — per quello c'e' memoria_mb().

    Usa `resource`, che e' nella libreria standard: nessuna dipendenza in piu'
    da installare su Render. ru_maxrss e' in byte su macOS e in kilobyte su
    Linux (dove gira il bot), da cui la distinzione.
    """
    try:
        grezzo = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return grezzo / (1024 * 1024) if sys.platform == "darwin" else grezzo / 1024
    except Exception:
        return 0.0


def memoria_mb():
    """Memoria occupata dal processo IN QUESTO MOMENTO (RSS), in MB.

    Serve a smettere di indovinare: il 01/09/2026 Render ha ucciso il bot per
    superamento del limite di memoria e la diagnosi si e' basata su una
    coincidenza di orari, non su un numero.

    Su Linux (dove gira il bot) il valore attuale si legge da /proc/self/status.
    Altrove — cioe' in locale su macOS durante i test — quel file non esiste e
    si ripiega sul picco, che e' comunque meglio di niente: l'importante e' che
    la funzione non sollevi mai, perche' viene chiamata dentro i log e da
    /diagnostica.
    """
    try:
        with open("/proc/self/status") as f:
            for riga in f:
                if riga.startswith("VmRSS:"):
                    return int(riga.split()[1]) / 1024  # il valore e' in kB
    except Exception:
        pass
    return memoria_picco_mb()


def libera_memoria_al_sistema_operativo():
    """Chiede esplicitamente all'allocatore di restituire all'OS la memoria
    liberata, invece di lasciare che il processo se la tenga "in cassa".

    Perche' serve: quando un oggetto Python viene liberato, l'interprete NON
    restituisce sempre quella memoria al sistema operativo — su Linux (dove
    gira il bot) la tiene riservata nell'arena di glibc per riusarla nelle
    allocazioni successive. Con thread diversi (ogni chiamata passa da
    asyncio.to_thread) glibc puo' arrivare a creare un'arena per thread: una
    volta che un thread ha allocato memoria per un'operazione pesante, quella
    memoria puo' restare "intrappolata" nella sua arena anche dopo che
    l'oggetto Python e' stato liberato, senza che sia un vero leak — e senza
    che gc.collect() da solo la riporti indietro, perche' gc.collect() ripulisce
    i cicli di riferimento, non tocca l'allocatore sottostante.

    Misurato con /diagnostica il 04/09/2026: 489 MB su 512 subito dopo il
    caricamento di una schedina (Sessione 17) — troppo alto per essere
    spiegato dalle sole foto, che Telegram comprime gia' a ~1280px prima di
    consegnarle al bot (il caso da 46,7 MB per foto misurato in Sessione 16
    era un file non compresso, un percorso che questo bot non riceve mai:
    l'unico handler registrato e' filters.PHOTO, non filters.Document).

    malloc_trim(0) e' la chiamata di glibc che chiede all'OS di riprendersi
    la memoria libera in cima alle arene. Esiste solo su Linux: su macOS (dove
    girano i test) fallisce silenziosamente, e va bene cosi'.
    """
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


# Ultimo modello che ha risposto e quanto ci ha messo: serve a dire all'admin
# "l'IA ha faticato" nel riepilogo, invece di lasciarlo solo nei log di Render.
ultima_lettura_ia = {"modello": None, "secondi": 0.0, "di_riserva": False}


class GeminiSovraccarico(Exception):
    """Tutti i modelli della catena sono congestionati: e' un problema di Google,
    non del bot, e si risolve solo aspettando. Distinta dalle altre eccezioni per
    poter mostrare all'admin un messaggio utile invece del JSON grezzo del 503."""


def chiama_gemini_con_fallback(chiamata, modelli=MODELLI_GEMINI, tentativi_per_modello=2, backoff_base=2.0):
    """Esegue `chiamata(modello)` scorrendo la catena finche' uno risponde.

    Perche' non basta richiedi_con_retry() di api_utils: quello avvolge
    requests.get(), mentre Gemini passa dall'SDK google-genai — client HTTP
    diverso, stessa identica situazione di googleapiclient per Sheets (vedi
    la regola su num_retries=3 in CLAUDE.md).

    Tre comportamenti distinti, perche' non tutti gli errori vanno trattati
    allo stesso modo:
    - transitorio (503/429/500/timeout): riprova sullo stesso modello, poi
      passa al successivo. Riprovare *lo stesso* modello saturo non basta:
      la prima versione di questo retry (3 tentativi in 6 secondi) non ha
      risolto niente, perche' la saturazione dura minuti, non secondi.
    - modello non disponibile (404): passa subito al successivo senza
      riprovare. I modelli vengono ritirati (gemini-2.5-flash e' gia'
      "no longer available"): la catena non deve morire per questo.
    - qualsiasi altro errore (chiave non valida, prompt rifiutato): rilanciato
      subito, perche' riprovare non lo risolve e farebbe solo aspettare.
    """
    ultimo_errore = None
    inizio = time.time()
    for modello in modelli:
        for tentativo in range(1, tentativi_per_modello + 1):
            try:
                risposta = chiamata(modello)
                di_riserva = modello != modelli[0]
                ultima_lettura_ia.update(modello=modello, secondi=time.time() - inizio, di_riserva=di_riserva)
                if di_riserva:
                    logging.warning(f"Gemini: risposta ottenuta dal modello di riserva '{modello}'")
                return risposta
            except Exception as e:
                ultimo_errore = e
                testo_errore = str(e).upper()
                if any(codice in testo_errore for codice in ERRORI_MODELLO_NON_DISPONIBILE):
                    logging.warning(f"Gemini: modello '{modello}' non disponibile, passo al successivo")
                    break
                if not any(codice in testo_errore for codice in ERRORI_GEMINI_TRANSITORI):
                    raise
                logging.warning(f"Gemini: '{modello}' non disponibile (tentativo {tentativo}/{tentativi_per_modello}): {str(e)[:120]}")
                if any(codice in testo_errore for codice in ERRORI_SENZA_SECONDO_TENTATIVO):
                    logging.warning(f"Gemini: '{modello}' ha superato il tempo massimo, passo al successivo senza riprovarlo")
                    break
                if tentativo < tentativi_per_modello:
                    time.sleep(backoff_base ** tentativo)
    raise GeminiSovraccarico(
        f"Tutti i modelli Gemini provati sono sovraccarichi ({', '.join(modelli)}). "
        f"Ultimo errore: {ultimo_errore}"
    )


def analizza_schedine_multiple(lista_percorsi_foto):
    client = get_gemini_client()
    if not client: raise Exception("Chiave API Gemini non configurata o vuota!")

    immagini_ottimizzate = []
    for percorso in lista_percorsi_foto:
        with Image.open(percorso) as originale:
            # draft() dice al decoder JPEG di produrre GIA' l'immagine ridotta,
            # invece di decodificarla a piena risoluzione per poi rimpicciolirla.
            # Misurato il 04/09/2026: una foto 4032x3024 (inviata come "file"
            # invece che come "foto" compressa da Telegram) costa 46,7 MB di
            # picco senza draft() e ~0 MB con draft(). Con tre foto sono oltre
            # 140 MB su un piano Render da 512 — molto piu' di tutti i dati
            # della stagione messi insieme, che pesano 1,6 MB (Sessione 16).
            originale.draft('RGB', DIMENSIONE_MAX_FOTO)
            img = originale.convert('RGB')
        img.thumbnail(DIMENSIONE_MAX_FOTO)
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
    logging.info(f"Analisi schedina: {len(immagini_ottimizzate)} foto pronte, memoria {memoria_mb():.0f} MB (picco {memoria_picco_mb():.0f})")
    response = chiama_gemini_con_fallback(lambda modello: client.models.generate_content(
        model=modello,
        contents=[prompt] + immagini_ottimizzate,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SCHEMA_SCHEDINA,
            http_options=types.HttpOptions(timeout=TIMEOUT_GEMINI_MS),
        )
    ))
    # Le immagini decodificate non servono piu': e' il punto giusto per
    # restituire la memoria all'OS invece di lasciarla intrappolata nell'arena
    # del thread che ha appena fatto il lavoro pesante (vedi il commento di
    # libera_memoria_al_sistema_operativo). Il log prima/dopo rende l'effetto
    # verificabile in produzione, non solo teorico.
    del immagini_ottimizzate
    prima = memoria_mb()
    libera_memoria_al_sistema_operativo()
    logging.info(f"Analisi schedina completata: memoria {prima:.0f} MB -> {memoria_mb():.0f} MB dopo il rilascio")
    return response.text

def normalizza_nomi_partite(dati_json, giornata_num):
    try:
        url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata_num}"
        matches = richiedi_con_retry(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
        if not matches: return dati_json
        
        dati = json.loads(dati_json)
        # Gli eventi restituiti sono gli stessi oggetti contenuti in `dati`:
        # modificarli qui aggiorna il JSON che viene poi riserializzato.
        eventi_per_categoria = estrai_eventi_per_categoria(dati)
        for cat in CATEGORIE_SCHEDINA:
            for ev in eventi_per_categoria.get(cat, []):
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

class SchedinaGiaPresente(Exception):
    """Quel giocatore ha gia' righe in Giocate per quella giornata.

    Senza questo controllo il secondo caricamento si limitava ad accodare le
    righe: nessun errore, nessun avviso, e la giornata veniva contata due volte.
    Misurato su dati finti: una schedina da 50 punti ne faceva 90 (Sessione 23).
    """

    def __init__(self, giocatore, giornata, righe):
        self.giocatore = giocatore
        self.giornata = giornata
        self.righe = righe
        super().__init__(
            f"{giocatore} ha gia' {len(righe)} righe per la Giornata {giornata} "
            f"(righe {righe[0]}-{righe[-1]} del foglio)"
        )


def righe_schedina_esistente(righe_giocate, giocatore, giornata):
    """Numeri di riga del foglio (1 = intestazione) gia' occupati da quel
    giocatore in quella giornata.

    Il confronto sulla giornata passa da riga_e_della_giornata: mai per
    sottostringa, altrimenti la Giornata 1 troverebbe anche la 12 (Sessione 13).
    """
    nome = str(giocatore).strip().upper()
    return [
        numero for numero, riga in enumerate(righe_giocate, start=1)
        if len(riga) > 1
        and riga_e_della_giornata(riga[0], giornata)
        and str(riga[1]).strip().upper() == nome
    ]


def scrivi_su_sheets_con_regole(nome_giocatore, giornata_num, json_data):
    sheets_service = connetti_sheets()
    dati = json.loads(json_data)

    # Controllo PRIMA di scrivere qualunque cosa: una schedina gia' caricata non
    # va sovrascritta di nascosto ne' raddoppiata. Si legge solo A:B, le due
    # colonne che servono (giornata e giocatore).
    esistenti = righe_schedina_esistente(
        sheets_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range="Giocate!A:B"
        ).execute(num_retries=3).get('values', []),
        nome_giocatore, giornata_num,
    )
    if esistenti:
        raise SchedinaGiaPresente(str(nome_giocatore).strip().upper(), giornata_num, esistenti)
    
    vincita_raw = str(dati.get("vincita_potenziale", "0")).replace(',', '.')
    try:
        vincita = f"{float(vincita_raw):.2f}".replace('.', ',')
    except: vincita = "0,00"

    eventi = estrai_eventi_per_categoria(dati)
    righe_da_inserire = []
    prima_riga = True
    
    for categoria in ["Combo", "Fisse", "Doppie Chance", "Variabili"]:
        eventi_cat = eventi.get(categoria, [])
        for idx, evento in enumerate(eventi_cat):
            pronostico = normalizza_pronostico(evento.get("pronostico", ""))
            
            if idx >= LIMITI_SCHEDINA[categoria]:
                pronostico += " (ANNULLATA ECCESSO)"
                
            quota_raw = str(evento.get("quota", "")).replace('.', ',')
            
            riga = [f"Giornata {giornata_num}", nome_giocatore.strip().upper(), evento.get("partita", ""), categoria, pronostico, quota_raw]
            
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

_id_foglio_giocate_cache = None


def id_foglio_giocate(service):
    """Identificativo interno del foglio Giocate, letto una volta per processo.

    Serve solo a colorare le celle. Non cambia mai per un foglio dato, mentre
    prima veniva richiesto a Google a ogni calcolo risultati (5-6 volte al
    giorno) insieme all'anagrafica completa del file.
    """
    global _id_foglio_giocate_cache
    if _id_foglio_giocate_cache is None:
        fogli = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute(num_retries=3).get('sheets', [])
        _id_foglio_giocate_cache = next(
            f['properties']['sheetId'] for f in fogli if f['properties']['title'].lower() == 'giocate'
        )
    return _id_foglio_giocate_cache


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
    logging.info(f"Calcolo G.{giornata}: lette {len(righe_giocate)} righe da Giocate, memoria {memoria_mb():.0f} MB (picco {memoria_picco_mb():.0f})")
    classifica, aggiornamenti_testo, richieste_stile = {}, [], []
    da_verificare_dettaglio = []
    colore_verde, colore_rosso, colore_grigio = {"red":0.85,"green":0.95,"blue":0.85}, {"red":0.95,"green":0.85,"blue":0.85}, {"red":0.90,"green":0.90,"blue":0.90}
    colore_giallo = {"red":1.0,"green":0.95,"blue":0.70}
    sheet_id_giocate = id_foglio_giocate(service)

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
    del righe_giocate, righe_class
    # Il log prima/dopo serve QUI piu' che nell'analisi schedina: questa
    # funzione gira piu' volte al giorno (job schedulati + comando manuale),
    # mentre una schedina si carica una volta a giornata. Cercando "dopo il
    # rilascio" nei log di Render il 09/09/2026 non c'era nemmeno una riga,
    # proprio perche' l'unico punto strumentato era quello sbagliato.
    prima = memoria_mb()
    libera_memoria_al_sistema_operativo()
    logging.info(f"Calcolo G.{giornata} completato: memoria {prima:.0f} MB -> {memoria_mb():.0f} MB dopo il rilascio")
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
# Soglia della prova di /diagnostica. NON e' il minimo consentito dall'API (10s):
# con 10s la diagnostica bocciava TUTTI i modelli mentre in realta' tre su
# quattro rispondevano in 2,6s / 8,7s / 15,6s. Una diagnostica che grida al
# lupo e' peggio di nessuna diagnostica, quindi la soglia sta sopra la peggiore
# latenza osservata per una risposta valida (Sessione 16).
TIMEOUT_PROVA_MODELLO_MS = 30000


def _prova_un_modello(modello):
    """Interroga un modello con una richiesta minima. Restituisce (nome, secondi, problema)."""
    client = get_gemini_client()
    if not client:
        return (modello, 0.0, "nessuna chiave configurata")
    inizio = time.time()
    try:
        client.models.generate_content(
            model=modello, contents=["Rispondi solo: OK"],
            config=types.GenerateContentConfig(
                http_options=types.HttpOptions(timeout=TIMEOUT_PROVA_MODELLO_MS)),
        )
        return (modello, time.time() - inizio, None)
    except Exception as e:
        testo = str(e)
        if "503" in testo or "UNAVAILABLE" in testo.upper():
            motivo = "sovraccarico"
        elif "404" in testo or "NOT_FOUND" in testo.upper():
            motivo = "non piu' disponibile"
        elif "DEADLINE" in testo.upper() or "timed out" in testo.lower():
            motivo = f"oltre {TIMEOUT_PROVA_MODELLO_MS // 1000}s"
        else:
            motivo = testo[:40]
        return (modello, time.time() - inizio, motivo)


async def _prova_modelli_gemini():
    """Prova tutti i modelli IN PARALLELO.

    In sequenza il comando avrebbe richiesto fino a due minuti (4 modelli per
    30s di timeout); in parallelo il caso peggiore resta 30s.
    """
    return await asyncio.gather(*(asyncio.to_thread(_prova_un_modello, m) for m in MODELLI_GEMINI))


async def diagnostica_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Controllo completo di tutti i pezzi da cui dipende il bot, in un colpo solo.

    Nasce dalle Sessioni 14-15: per scoprire che un modello Gemini metteva 96
    secondi a rispondere e' servito scrivere script sul computer dell'admin con
    la chiave API. Questo comando da' la stessa risposta da Telegram in pochi
    secondi, ed e' la prima mossa da fare quando qualcosa non va.
    """
    if not e_admin(update.effective_user.id): return
    messaggio = await update.message.reply_text("🔍 Controllo in corso... (i modelli IA richiedono qualche secondo)")

    righe = [f"🩺 *DIAGNOSTICA* — {datetime.now(pytz.timezone('Europe/Rome')).strftime('%d/%m %H:%M')}\n"]

    # --- Memoria ---
    # Il piano gratuito di Render da' 512 MB: superarli significa processo ucciso.
    # Il picco conta quanto l'attuale, perche' e' il picco che fa scattare il kill.
    usata, picco = memoria_mb(), memoria_picco_mb()
    percentuale = picco / 512 * 100
    icona = "✅" if percentuale < 60 else ("⚠️" if percentuale < 85 else "🔴")
    righe.append(f"{icona} *Memoria*: {usata:.0f} MB ora, picco {picco:.0f} MB su 512 ({percentuale:.0f}%)")

    # --- Accessi ---
    if len(ADMIN_IDS) == 1:
        righe.append("✅ *Admin*: 1 (solo l'amministratore principale)")
    else:
        righe.append(f"✅ *Admin*: {len(ADMIN_IDS)} autorizzati ({len(ADMIN_IDS) - 1} oltre al principale)")

    # --- Keep-alive ---
    if last_ping_time is None:
        righe.append("⚠️ *Keep-alive*: nessun ping ricevuto dall'avvio")
    else:
        da_quanto = (datetime.now() - last_ping_time).total_seconds()
        icona = "✅" if da_quanto < 600 else "🔴"
        righe.append(f"{icona} *Keep-alive*: ultimo ping {int(da_quanto/60)} min fa (Render spegne a 15)")

    # --- Google Sheets ---
    inizio = time.time()
    try:
        service = await asyncio.to_thread(connetti_sheets)
        valori = await asyncio.to_thread(
            lambda: service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range="Giocate!A:A"
            ).execute(num_retries=3).get('values', [])
        )
        righe.append(f"✅ *Google Sheets*: {len(valori)} righe in Giocate, risposta in {time.time()-inizio:.1f}s")
    except Exception as e:
        righe.append(f"🔴 *Google Sheets*: {escape_markdown(str(e)[:60])}")

    # --- Football-Data ---
    inizio = time.time()
    giornata = await asyncio.to_thread(ottieni_giornata_corrente)
    if giornata is None:
        righe.append("🔴 *Football-Data*: non raggiungibile")
    else:
        righe.append(f"✅ *Football-Data*: giornata corrente {giornata}, risposta in {time.time()-inizio:.1f}s")

    # --- Gemini ---
    righe.append("\n*Modelli IA* (in ordine di utilizzo):")
    esiti = await _prova_modelli_gemini()
    for modello, durata, problema in esiti:
        if problema is None:
            # Sotto i 10s e' pronto; tra 10 e 30 funziona ma si sente l'attesa.
            icona = "✅" if durata < 10 else "⚠️"
            righe.append(f"{icona} `{modello}` — {durata:.1f}s")
        else:
            righe.append(f"🔴 `{modello}` — {escape_markdown(problema)}")

    funzionanti = [e for e in esiti if e[2] is None]
    if not funzionanti:
        # "Fallirebbe" sarebbe troppo netto: il caricamento vero concede 60s,
        # il doppio della soglia usata qui, quindi potrebbe ancora farcela.
        righe.append("\n🔴 _Nessun modello ha risposto entro "
                     f"{TIMEOUT_PROVA_MODELLO_MS // 1000}s: il caricamento di una schedina "
                     "sarebbe molto lento o fallirebbe. Riprova tra qualche minuto._")
    elif len(funzionanti) < len(esiti):
        righe.append(f"\n✅ _{len(funzionanti)} modelli su {len(esiti)} disponibili: "
                     "il caricamento schedine funziona._")

    await messaggio.edit_text("\n".join(righe), parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riepilogo rapido: giornata corrente e chi non ha ancora caricato la schedina."""
    if not e_admin(update.effective_user.id): return
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
    if not e_admin(update.effective_user.id): return
    await update.message.reply_text("⏳ Preparo il backup...")
    await task_backup_periodico(context, destinatari=update.effective_user.id)

async def archivia_stagione_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia l'archiviazione della stagione. Operazione che SVUOTA i fogli di
    lavoro, quindi: backup automatico prima, poi conferma con codice.

    Un bottone "Sì" e' un solo tap distratto di distanza dallo svuotamento dei
    fogli di lavoro — troppo poco per l'unica operazione del progetto che
    cancella dati, specialmente ora che l'accesso admin potrebbe non restare
    per sempre a una sola persona (Sessione 17). La conferma richiede di
    DIGITARE un codice a 6 cifre generato li' per li' e mostrato solo in
    questo messaggio: non e' un tentativo di sicurezza crittografica (chi
    arriva fin qui e' gia' un admin autorizzato), e' un freno contro il tap
    a vuoto — costringe a fermarsi e leggere, non solo a toccare uno schermo."""
    if not e_owner(update.effective_user.id):
        if e_admin(update.effective_user.id):
            await update.message.reply_text(
                "🔒 Questo comando è riservato all'amministratore principale."
            )
        return

    etichetta = await asyncio.to_thread(stagione_corrente)
    if not etichetta:
        await update.message.reply_text("⚠️ Non riesco a determinare la stagione corrente (API non raggiungibile). Riprova più tardi.")
        return

    codice = f"{random.randint(0, 999999):06d}"
    context.user_data['stagione_da_archiviare'] = etichetta
    context.user_data['codice_conferma_archiviazione'] = codice
    await update.message.reply_text("💾 Prima di tutto ti mando un backup di sicurezza...")
    await task_backup_periodico(context, destinatari=update.effective_user.id)

    kb = [[InlineKeyboardButton("❌ Annulla", callback_data="archivia_no")]]
    await update.message.reply_text(
        f"⚠️ *Archiviazione stagione {etichetta}*\n\n"
        f"Farò una copia di Giocate, Classifica e Cassa nei fogli «... {etichetta}», "
        f"poi *svuoterò i fogli di lavoro* per la nuova stagione.\n\n"
        f"I dati storici restano consultabili nello spreadsheet, e hai appena ricevuto il backup qui sopra.\n\n"
        f"Per confermare, scrivi questo codice: `{codice}`",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )
    return CONFERMA_ARCHIVIA_STAGIONE

async def annulla_archiviazione(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    context.user_data.pop('stagione_da_archiviare', None)
    context.user_data.pop('codice_conferma_archiviazione', None)
    await query.edit_message_text("❌ Archiviazione annullata. Nessun dato è stato toccato.")
    return ConversationHandler.END

async def verifica_codice_archiviazione(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confronta il testo digitato con il codice mostrato. Un codice sbagliato
    non fa uscire dalla conversazione: si puo' ritentare o usare /cancel,
    esattamente come capiterebbe rileggendo il messaggio con piu' calma."""
    codice_atteso = context.user_data.get('codice_conferma_archiviazione')
    digitato = (update.message.text or "").strip()

    if digitato != codice_atteso:
        await update.message.reply_text(
            "❌ Codice non corretto. Ricontrolla il messaggio qui sopra e ridigitalo, "
            "oppure /cancel per annullare."
        )
        return CONFERMA_ARCHIVIA_STAGIONE

    etichetta = context.user_data.get('stagione_da_archiviare')
    await update.message.reply_text(f"⏳ Codice corretto. Archivio la stagione {etichetta}...")
    archiviata = False
    try:
        esito = await asyncio.to_thread(archivia_stagione, etichetta)
        archiviata = True
        await avvisa_admin(context, esito, destinatari=update.effective_user.id)
    except Exception as e:
        await avvisa_admin(context, f"❌ Archiviazione fallita: {e}",
                           destinatari=update.effective_user.id, parse_mode=None)
    if archiviata:
        # Fuori dal try: l'archiviazione svuota i fogli di lavoro, ed e' l'unica
        # operazione dopo la quale un altro admin, trovando la Classifica vuota,
        # penserebbe a un guasto. Ma un problema nell'avvisarlo non deve far
        # dichiarare fallita un'archiviazione riuscita.
        await traccia_azione(update, context,
                             f"ha archiviato la stagione {escape_markdown(str(etichetta))} e azzerato i fogli di lavoro.")
    context.user_data.pop('stagione_da_archiviare', None)
    context.user_data.pop('codice_conferma_archiviazione', None)
    return ConversationHandler.END

AVVISO_CHIAVE_SALVATA = (
    "✅ **Chiave API Gemini salvata.**\n\n"
    "⚠️ Su Render questo file può essere azzerato al prossimo riavvio: se vuoi che "
    "la chiave resti per sempre, impostala anche come variabile d'ambiente "
    "`GEMINI_API_KEY` nel pannello Render (ha la precedenza su questo file)."
)

async def set_api_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not e_owner(update.effective_user.id):
        if e_admin(update.effective_user.id):
            await update.message.reply_text(
                "🔒 Questo comando è riservato all'amministratore principale."
            )
        return
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
    if not e_owner(update.effective_user.id): return ConversationHandler.END
    nuova_chiave = update.message.text.strip()
    try:
        with open('chiave_api.txt', 'w') as f: f.write(nuova_chiave)
        await update.message.reply_text(AVVISO_CHIAVE_SALVATA + "\n\nScrivi /start per tornare al menu.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}\n\nSe il filesystem è in sola lettura, aggiorna la variabile d'ambiente `GEMINI_API_KEY` su Render.", parse_mode="Markdown")
    return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not e_admin(update.effective_user.id): return
    kb = [
        [InlineKeyboardButton("📥 Carica Schedina", callback_data="menu_carica")],
        [InlineKeyboardButton("⚽ Aggiorna Risultati & Punteggi", callback_data="menu_aggiorna")],
        [InlineKeyboardButton("✍️ Inserisci Risultato Manuale", callback_data="menu_manuale")],
    ]
    # La chiave API e' una credenziale: il bottone lo vede solo l'owner. Meglio
    # non mostrarlo affatto che mostrarlo e poi rifiutare — un bottone che non
    # funziona sembra un guasto.
    if e_owner(update.effective_user.id):
        kb.append([InlineKeyboardButton("⚙️ Cambia Chiave API", callback_data="menu_cambia_key")])
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
        if not e_owner(update.effective_user.id):
            await query.edit_message_text("🔒 La chiave API la cambia solo l'amministratore principale.")
            return ConversationHandler.END
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
    if not e_admin(update.effective_user.id): return
    photo_file = await update.message.photo[-1].get_file()
    if not os.path.exists(CARTELLA_FOTO): os.makedirs(CARTELLA_FOTO)
    
    percorso_foto = f"{CARTELLA_FOTO}/schedina_{len(context.user_data.get('foto_ricevute', [])) + 1}.jpg"
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
    
    # Se l'altro admin sta gia' caricando questa stessa schedina, va detto ORA:
    # e' il momento in cui fermarsi costa zero. Al salvataggio sarebbe troppo
    # tardi — uno dei due avrebbe gia' aspettato la lettura IA per niente.
    altro = lavorazione_altrui(context.user_data['giornata'], context.user_data['giocatore'],
                               update.effective_user.id)
    avviso = ""
    if altro:
        nome_altro, secondi = altro
        avviso = (f"\n\n🔸 *{escape_markdown(nome_altro)}* sta già caricando questa stessa schedina "
                  f"({da_quanto(secondi)}). Sentitevi prima di procedere: se la salva lui, "
                  f"il tuo salvataggio verrà rifiutato.")

    kb = [[InlineKeyboardButton("✅ Conferma", callback_data="conferma_si")], [InlineKeyboardButton("❌ Annulla", callback_data="conferma_no")]]
    await query.edit_message_text(text=f"⚠️ Vuoi elaborare:\n👤 **{context.user_data['giocatore'].capitalize()}** - 📅 **Giornata {context.user_data['giornata']}** ({len(context.user_data.get('foto_ricevute', []))} foto)?{avviso}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return CONFERMA

async def schedina_gia_nel_foglio(giocatore, giornata):
    """Righe gia' presenti in Giocate per quel giocatore in quella giornata.

    E' la stessa lettura che fa scrivi_su_sheets_con_regole prima di scrivere,
    ma anticipata: scoprire il doppione DOPO la lettura IA significa aver
    buttato via una chiamata a Gemini e una ventina di secondi di attesa.
    Il controllo che conta resta quello al salvataggio — questo serve solo a
    non far lavorare a vuoto.
    """
    service = await asyncio.to_thread(connetti_sheets)
    righe = await asyncio.to_thread(
        lambda: service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range="Giocate!A:B"
        ).execute(num_retries=3).get('values', [])
    )
    return righe_schedina_esistente(righe, giocatore, giornata)


async def esegui_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "conferma_no":
        await pulisci_dati(context)
        await query.edit_message_text("❌ Operazione annullata. Scrivi /start per riaprire il menu.")
        return ConversationHandler.END

    gio, giorn, foto_lista = context.user_data['giocatore'], context.user_data['giornata'], context.user_data.get('foto_ricevute', [])

    # Il doppione si scopre prima di chiamare l'IA, non dopo.
    try:
        esistenti = await schedina_gia_nel_foglio(gio, giorn)
    except Exception as e:
        # Se il foglio non risponde NON si blocca il caricamento: il controllo
        # che conta e' quello dentro scrivi_su_sheets_con_regole, che rifiuta
        # comunque. Qui un errore di lettura deve al massimo far perdere il
        # vantaggio dell'anticipo, non impedire di lavorare.
        logging.warning("Controllo anticipato doppioni non riuscito (si procede): %s", e)
        esistenti = []
    if esistenti:
        await query.edit_message_text(
            f"⚠️ *Schedina già presente*\n\n"
            f"{escape_markdown(gio.upper())} ha già *{len(esistenti)} righe* per la "
            f"*Giornata {escape_markdown(str(giorn))}* (righe {esistenti[0]}-{esistenti[-1]} del foglio Giocate).\n\n"
            f"Non ho letto le foto e non ho salvato niente. Se questa è la versione giusta, "
            f"cancella prima quelle righe dal foglio e ricarica.",
            parse_mode="Markdown"
        )
        await pulisci_dati(context)
        return ConversationHandler.END

    segna_lavorazione(giorn, gio, update.effective_user.id, nome_attore(update))
    context.user_data['lavorazione_admin_id'] = update.effective_user.id

    await query.edit_message_text(f"⏳ L'IA Gemini sta analizzando le foto ({len(foto_lista)}) di {gio.capitalize()}...")
    
    try:
        risultato_json_raw = await asyncio.to_thread(analizza_schedine_multiple, foto_lista)
        risultato_json = await asyncio.to_thread(normalizza_nomi_partite, risultato_json_raw, giorn)
        
        # Salva in sessione per dopo
        context.user_data['risultato_json'] = risultato_json
        
        # Genera riepilogo per admin
        dati = json.loads(risultato_json)
        vincita = dati.get("vincita_potenziale", "0")
        eventi = estrai_eventi_per_categoria(dati)

        # Zero eventi NON e' un risultato da mostrare come se fosse una lettura
        # riuscita: e' un fallimento. Il 02/09/2026 il bot ha presentato una
        # schedina piena come "0/1, 0/4, 0/2, 0/3" con il tasto "Conferma e
        # Salva" attivo — un clic distratto avrebbe scritto una schedina vuota
        # in Giocate. Meglio fermarsi e loggare il JSON grezzo per la diagnosi.
        if not any(eventi.get(c) for c in CATEGORIE_SCHEDINA):
            logging.error(f"Lettura IA senza eventi. JSON grezzo ricevuto: {risultato_json[:1500]}")
            await query.edit_message_text(
                "❌ *Lettura non riuscita: nessun evento riconosciuto.*\n\n"
                "Le foto sono arrivate e l'IA ha risposto, ma non ho trovato nessun pronostico. "
                "Di solito succede se la schermata è tagliata, molto sfocata o mostra solo il riepilogo finale.\n\n"
                "Riprova con /start allegando la schermata che elenca gli eventi. "
                "Ho salvato la risposta grezza nei log per capire cosa è andato storto.",
                parse_mode="Markdown"
            )
            await pulisci_dati(context)
            return ConversationHandler.END


        msg_riepilogo = f"🤖 **Lettura IA Completata!**\n\n"
        msg_riepilogo += f"💰 **Vincita Potenziale:** {escape_markdown(vincita)} €\n"
        
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
                    # escape_markdown su tutti e tre: arrivano dall'IA, non da noi.
                    msg_riepilogo += f"- {escape_markdown(ev.get('partita', '???'))} -> {escape_markdown(ev.get('pronostico', ''))} (@{escape_markdown(ev.get('quota', ''))})\n"
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

        # Se l'IA ha faticato l'admin deve saperlo qui, non nei log di Render:
        # e' il primo segnale che i modelli stanno peggiorando, e spiega anche
        # perche' la lettura ha richiesto piu' tempo del solito (Sessione 16).
        if ultima_lettura_ia["di_riserva"]:
            msg_riepilogo += (f"\n🐢 _Letta dal modello di riserva "
                              f"{escape_markdown(ultima_lettura_ia['modello'])} "
                              f"in {ultima_lettura_ia['secondi']:.0f}s — i modelli principali erano occupati._\n")
        elif ultima_lettura_ia["secondi"] > 30:
            msg_riepilogo += f"\n🐢 _Lettura lenta ({ultima_lettura_ia['secondi']:.0f}s): i server IA sono carichi._\n"

        kb = [
            [InlineKeyboardButton("✅ Conferma e Salva su Sheets", callback_data="salva_ia_si")],
            [InlineKeyboardButton("❌ Annulla (Lettura Errata)", callback_data="salva_ia_no")]
        ]
        # Un problema di FORMATTAZIONE non deve mai buttare via una lettura IA
        # riuscita: se Telegram rifiuta il Markdown, si rimanda lo stesso
        # riepilogo in testo semplice e l'admin puo' comunque confermare, invece
        # di dover ricaricare le foto da capo (Sessione 15).
        try:
            await query.edit_message_text(msg_riepilogo, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        except Exception as errore_formattazione:
            logging.warning(f"Riepilogo rifiutato da Telegram in Markdown, rimando in testo semplice: {errore_formattazione}")
            testo_semplice = msg_riepilogo.replace("**", "").replace("\\", "")
            await query.edit_message_text(testo_semplice, reply_markup=InlineKeyboardMarkup(kb))
        return CONFERMA_LETTURA_IA

    except GeminiSovraccarico:
        # Non e' un guasto del bot: sono i server di Google congestionati.
        # L'admin deve sapere che basta riprovare, non che c'e' da riparare qualcosa.
        logging.warning("Lettura schedina non riuscita: tutti i modelli Gemini sovraccarichi")
        await query.edit_message_text(
            "⏳ *Gemini è sovraccarico in questo momento.*\n\n"
            "Ho provato tutti i modelli disponibili, sono tutti congestionati lato Google — "
            "non è un problema del bot né delle tue foto.\n\n"
            "Riprova tra qualche minuto con /start: di solito rientra da solo.",
            parse_mode="Markdown"
        )
        await pulisci_dati(context)
        return ConversationHandler.END

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
        # Il lock copre rilettura + controllo + scrittura: e' l'unico modo per
        # cui due "Salva" simultanei non trovino entrambi il posto libero.
        async with lock_salvataggio_schedina():
            successo = await asyncio.to_thread(scrivi_su_sheets_con_regole, gio, giorn, risultato_json)
        msg = f"✅ Schedina salvata definitivamente nel Database!" if successo else "⚠️ Errore durante la scrittura su Sheets."
        await query.edit_message_text(msg)
    except SchedinaGiaPresente as gia:
        # Niente e' stato scritto: meglio fermarsi e far decidere a un umano che
        # accodare una seconda copia (i punti verrebbero contati due volte).
        await query.edit_message_text(
            f"⚠️ *Schedina già presente*\n\n"
            f"{escape_markdown(gia.giocatore)} ha già *{len(gia.righe)} righe* per la "
            f"*Giornata {escape_markdown(str(gia.giornata))}* (righe {gia.righe[0]}-{gia.righe[-1]} del foglio Giocate).\n\n"
            f"*Non ho salvato niente.* Se questa è la versione giusta, cancella prima "
            f"quelle righe dal foglio e ricarica la foto.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Errore durante la scrittura: {e}")
        
    await pulisci_dati(context)
    return ConversationHandler.END

async def scegli_giornata_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    giornata = query.data.split('_')[1]
    await query.edit_message_text(f"⏳ Aggiornamento manuale Giornata {giornata}...")
    report = await asyncio.to_thread(esegui_calcolo_risultati, giornata)
    await avvisa_admin(context, report, destinatari=update.effective_user.id)
    await traccia_azione(update, context, f"ha ricalcolato i punteggi della Giornata {escape_markdown(str(giornata))}.")
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
            chat_id=update.effective_chat.id,
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
        chat_id=update.effective_chat.id,
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
    if not e_admin(update.effective_user.id): return
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
    applicato = False
    try:
        report = await asyncio.to_thread(applica_risultato_manuale, giornata, casa_full, ospite_full, gol_casa, gol_ospite)
        applicato = True
        await avvisa_admin(context, report, destinatari=update.effective_user.id)
    except Exception as e:
        await avvisa_admin(context, f"❌ Errore durante l'applicazione del risultato: {e}",
                           destinatari=update.effective_user.id, parse_mode=None)
    if applicato:
        # Fuori dal try: una correzione a mano tocca punteggi e Cassa, e l'altro
        # admin deve saperlo — ma il risultato e' gia' scritto su Sheets, quindi
        # un errore qui non puo' essere riportato come "risultato non applicato".
        await traccia_azione(
            update, context,
            f"ha inserito a mano {escape_markdown(f'{casa_full} {gol_casa}-{gol_ospite} {ospite_full}')} "
            f"(Giornata {escape_markdown(str(giornata))})."
        )

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
    # Caricamento finito o abbandonato: la schedina torna libera per l'altro
    # admin subito, senza aspettare la scadenza dei 15 minuti.
    if 'lavorazione_admin_id' in context.user_data:
        libera_lavorazione(context.user_data.get('giornata'), context.user_data.get('giocatore'),
                           context.user_data.pop('lavorazione_admin_id'))
    # /cancel come fallback generico deve poter interrompere anche
    # l'archiviazione a meta': altrimenti il codice resterebbe appeso in
    # user_data pronto per essere confermato per sbaglio in una sessione dopo.
    context.user_data.pop('stagione_da_archiviare', None)
    context.user_data.pop('codice_conferma_archiviazione', None)

async def task_aggiornamento_automatico(context: ContextTypes.DEFAULT_TYPE):
    """Ricalcola la giornata corrente e avvisa l'admin SOLO se e' cambiato qualcosa.

    Il ricalcolo viene fatto comunque (e' quello che aggiorna Sheets): a essere
    condizionato e' l'invio del messaggio. Prima arrivava ogni sera comunque,
    anche a giornata conclusa e immutata da giorni: un messaggio che si ripete
    identico smette di essere letto, e quando poi cambia davvero qualcosa non lo
    noti piu'. Stessa logica gia' usata da task_controlla_anomalie_partite
    (Sessione 16).
    """
    global ultimo_report_inviato
    giornata = await asyncio.to_thread(ottieni_giornata_corrente)
    if giornata is None:
        # Meglio saltare il giro che ricalcolare la giornata sbagliata.
        logging.warning("task_aggiornamento_automatico: giornata corrente sconosciuta, giro saltato")
        return
    report = await asyncio.to_thread(esegui_calcolo_risultati, giornata)

    impronta = (giornata, report)
    if impronta == ultimo_report_inviato:
        logging.info(f"Auto update G.{giornata}: nessuna novita' rispetto all'ultimo invio, non lo ripeto")
        return
    ultimo_report_inviato = impronta

    await avvisa_admin(context, f"⏰ **AUTO UPDATE (G.{giornata})**\n\n{report}")

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
            await avvisa_admin(context, msg)
        else:
            await avvisa_admin(context, f"✅ **Giornata {giornata}**: tutte le schedine sono state caricate!")
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
            await avvisa_admin(context, f"✅ Giornata {giornata}: le anomalie segnalate in precedenza risultano risolte.")
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

        await avvisa_admin(context, msg)
        ultime_anomalie_segnalate = chiavi_attuali
    except Exception as e:
        logging.error(f"Errore task_controlla_anomalie_partite: {e}")

async def task_backup_periodico(context: ContextTypes.DEFAULT_TYPE, destinatari=None):
    """Backup settimanale: esporta Giocate/Classifica/Cassa in un file JSON e
    lo manda agli admin come documento Telegram.

    destinatari: None (job schedulato) = tutti gli admin; un ID = solo a lui.
    Lo passa /backup e lo passa /archiviastagione, dove il backup e' la rete di
    sicurezza di CHI sta archiviando: deve arrivargli subito, non riempire la
    chat degli altri di file che non hanno chiesto.

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
        inviati, ultimo_errore = 0, None
        for chat_id in destinatari_notifica(destinatari):
            # Il file va riaperto per ogni invio: Telegram consuma lo stream, e
            # riusare lo stesso handle manderebbe un allegato vuoto dal secondo
            # admin in poi. Un invio fallito non deve fermare gli altri.
            try:
                with open(percorso_file, "rb") as f:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=percorso_file,
                        caption=f"💾 Backup — {data_str}\n{n_giocate} righe in Giocate."
                    )
                inviati += 1
            except Exception as e:
                ultimo_errore = e
                logging.error(f"Invio backup a {chat_id} non riuscito: {e}")
        if inviati == 0 and ultimo_errore is not None:
            # Il backup e' stato costruito ma non e' arrivato a NESSUNO: va detto.
            # Un allegato puo' fallire (dimensione, formato) dove un testo passa,
            # quindi vale la pena provare comunque con un messaggio.
            await avvisa_admin(context, f"⚠️ Backup fallito: {ultimo_errore}", destinatari=destinatari)
    except Exception as e:
        logging.error(f"Errore task_backup_periodico: {e}")
        await avvisa_admin(context, f"⚠️ Backup fallito: {e}", destinatari=destinatari)
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
    ritirati = []
    for riga in righe_classifica[1:]:
        if not riga or not str(riga[0]).strip():
            continue
        nome = str(riga[0]).strip()
        punti_tot = int(estrai_numero(riga[1])) if len(riga) > 1 else 0
        if e_ritirato(nome):
            ritirati.append((nome_senza_ritiro(nome), punti_tot))
            continue
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

    if ritirati:
        righe_testo.append("———")
        righe_testo += [f"🚪 {nome.capitalize()} (ritirato) - {tot} pt" for nome, tot in ritirati]

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

async def task_riepilogo_whatsapp(context: ContextTypes.DEFAULT_TYPE, notifica_se_non_pronto=False, destinatari=None):
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
    destinatari: None (job schedulato) = tutti gli admin; un ID = solo a lui.
    Le spiegazioni del "perche' non l'ho mandato" vanno sempre e solo a chi ha
    chiesto: sono la risposta a un comando, non una notizia per tutti.
    """
    global ultima_giornata_riepilogo_inviata
    try:
        giornata = await asyncio.to_thread(ottieni_giornata_corrente)
        if giornata is None:
            if notifica_se_non_pronto:
                await avvisa_admin(context, "⚠️ Non riesco a contattare Football-Data per sapere la giornata corrente. Riprova fra poco.", destinatari=destinatari, parse_mode=None)
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
                await avvisa_admin(context, f"ℹ️ Nessuna schedina ancora caricata per la Giornata {giornata}.", destinatari=destinatari, parse_mode=None)
            return
        if any("CORSO" in str(r[6]) for r in righe_giornata):
            if notifica_se_non_pronto:
                n_in_corso = sum(1 for r in righe_giornata if "CORSO" in str(r[6]))
                await avvisa_admin(context, f"⏳ Giornata {giornata} non ancora conclusa: {n_in_corso} eventi ancora IN CORSO.", destinatari=destinatari, parse_mode=None)
            return

        if str(giornata) == str(ultima_giornata_riepilogo_inviata):
            if notifica_se_non_pronto:
                await avvisa_admin(context, f"ℹ️ Il riepilogo della Giornata {giornata} è già stato mandato.", destinatari=destinatari, parse_mode=None)
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

        # Il riepilogo va a TUTTI gli admin anche quando lo forza uno solo: e' il
        # testo da incollare su WhatsApp, e chiunque dei due puo' essere quello che
        # in quel momento ha il telefono in mano.
        await avvisa_admin(context, testo, parse_mode=None)  # niente parse_mode: vedi costruisci_riepilogo_whatsapp
        ultima_giornata_riepilogo_inviata = str(giornata)
    except Exception as e:
        logging.error(f"Errore task_riepilogo_whatsapp: {e}")

async def riepilogo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forza subito il controllo/invio del riepilogo, senza aspettare la mattina
    (utile per testare, o per rimandarlo se serve). Ignora la deduplica."""
    if not e_admin(update.effective_user.id): return
    global ultima_giornata_riepilogo_inviata
    ultima_giornata_riepilogo_inviata = None
    await update.message.reply_text("⏳ Controllo se la giornata è conclusa...")
    await task_riepilogo_whatsapp(context, notifica_se_non_pronto=True, destinatari=update.effective_user.id)

async def task_autoping(context: ContextTypes.DEFAULT_TYPE):
    """Il bot chiama il proprio indirizzo pubblico per generare traffico in entrata.

    Perche' serve: Render spegne un servizio gratuito dopo 15 minuti senza
    richieste HTTP in ENTRATA, e finora l'unica cosa che le generava era un
    servizio esterno (cron-job.org). Il 01/09/2026 quel servizio ha iniziato a
    fallire ogni esecuzione ("output troppo grande": trovando il servizio gia'
    giu' riceveva la pagina d'errore di Render, molto piu' grande dei 69 byte
    che restituiamo noi) e il bot e' rimasto spento finche' non e' stato
    riavviato a mano.

    Questo job non sostituisce il pinger esterno - se il processo e' morto non
    puo' certo risvegliarsi da solo - ma toglie il punto singolo di rottura
    finche' il bot e' vivo: basta che UNA delle due fonti funzioni.

    RENDER_EXTERNAL_URL viene impostata automaticamente da Render.
    """
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        return  # in locale non serve
    try:
        # richiedi_con_retry riprova da solo: un blip di rete non deve valere
        # come ping perso, perche' ogni ping perso avvicina lo spegnimento.
        await asyncio.to_thread(lambda: richiedi_con_retry(url, timeout=20))
        logging.info("Auto-ping keep-alive eseguito")
    except Exception as e:
        logging.warning(f"Auto-ping fallito: {e}")

COMANDI_ADMIN = [
    ("start", "Apri il menu principale"),
    ("status", "Giornata corrente e schedine mancanti"),
    ("diagnostica", "Controlla memoria, Sheets, API e modelli IA"),
    ("backup", "Esporta subito un backup dei dati"),
    ("riepilogo", "Riepilogo giornata pronto per WhatsApp"),
]

# Riservati all'owner: toccano una credenziale e cancellano dati.
COMANDI_OWNER = COMANDI_ADMIN + [
    ("archiviastagione", "Chiudi la stagione e azzera i fogli"),
    ("setkey", "Cambia al volo la chiave API di Gemini"),
]


async def post_init(application: Application):
    """Imposta i comandi rapidi ufficiali nel menu di Telegram (il tasto '/').

    Lista diversa per owner e admin: proporre nel menu un comando che poi
    risponde «riservato» e' un invito a premerlo. Il controllo vero resta
    comunque nei singoli handler — questo e' solo cosa Telegram mostra.
    """
    await application.bot.set_my_commands(COMANDI_ADMIN)
    for admin_id in ADMIN_IDS:
        comandi = COMANDI_OWNER if e_owner(admin_id) else COMANDI_ADMIN
        try:
            await application.bot.set_my_commands(comandi, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            # Un admin che non ha mai scritto al bot non ha ancora una chat:
            # Telegram rifiuta lo scope. Non e' un motivo per non avviare il bot.
            logging.warning("Non ho potuto impostare i comandi per l'admin %s: %s", admin_id, e)

def main():
    # Se le variabili d'ambiente non ci sono (es. testing locale), il bot si ferma qui per evitare errori.
    if not TOKEN:
        logging.error("ERRORE: Variabile TELEGRAM_TOKEN non trovata. Impossibile avviare il bot.")
        return

    logging.info("Admin autorizzati: %d (owner: %s)", len(ADMIN_IDS), OWNER_ID)

    residue = pulisci_foto_residue()
    if residue:
        logging.info("Pulite %d foto rimaste da un caricamento interrotto", residue)

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

    # Controllo anomalie ogni 4 ore (era 2): e' un avviso preventivo, non serve
    # al minuto, ed era il piu' frequente dei lavori che rileggono tutto Giocate
    # — 12 volte al giorno contro le 2 del calcolo risultati (Sessione 16).
    app.job_queue.run_repeating(task_controlla_anomalie_partite, interval=14400, first=600)

    # Auto-ping ogni 5 minuti. Non e' eccesso di zelo: Render spegne dopo 15 minuti
    # senza traffico, quindi a 10 minuti di intervallo UN SOLO ping perso creerebbe
    # un buco di 20 minuti e ucciderebbe il servizio. A 5 ne sopravvive due di fila.
    app.job_queue.run_repeating(task_autoping, interval=300, first=60)

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
    app.add_handler(CommandHandler("diagnostica", diagnostica_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("riepilogo", riepilogo_command))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("archiviastagione", archivia_stagione_command)],
        states={CONFERMA_ARCHIVIA_STAGIONE: [
            CallbackQueryHandler(annulla_archiviazione, pattern="^archivia_no$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, verifica_codice_archiviazione),
        ]},
        fallbacks=[CommandHandler("cancel", annulla_tutto)],
    ))
    app.add_handler(conv_handler)
    logging.info("🤖 Super-Bot Telegram avviato: in ascolto su Telegram e pronto ai ping di keep-alive.")
    # timeout=30: il polling lungo tiene aperta la richiesta fino a 30s invece
    # dei 10 di default. Le risposte restano immediate (Telegram risponde appena
    # arriva un messaggio), ma le richieste passano da ~8.600 a ~2.900 al giorno.
    app.run_polling(timeout=30)

if __name__ == '__main__':
    main()