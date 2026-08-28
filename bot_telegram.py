import os
import json
import logging
import re
import requests
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

GIOCATORI = [
    "cecilia", "dario", "davide", "fazio", 
    "gaetano", "giacomo", "giovanni", "mario", 
    "michele", "mirko", "nico", "paolo", 
    "pulizzer", "silvio", "villari", "vincenzo"
]

LIMITI_SCHEDINA = {"Combo": 1, "Fisse": 4, "Doppie Chance": 2, "Variabili": 3}

# Stati Conversazione
MENU, ATTESA_FOTO_MULTIPLE, SCELTA_GIORNATA, SCELTA_GIOCATORE, CONFERMA, CONFERMA_LETTURA_IA, SCELTA_GIORNATA_UPDATE, ATTESA_NUOVA_KEY = range(8)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

if not TOKEN or not SPREADSHEET_ID or not FOOTBALL_DATA_KEY or ADMIN_ID == 0:
    logging.warning("⚠️ ATTENZIONE: Variabili d'ambiente mancanti. Il bot potrebbe non funzionare correttamente!")

last_ping_time = None

# ==========================================
# SERVER WEB PER MANTENERE IL BOT SVEGLIO (TRUCCO RENDER)
# ==========================================
app_web = Flask(__name__)

@app_web.route('/')
def home():
    global last_ping_time
    from datetime import datetime
    now = datetime.now()
    if last_ping_time is not None:
        delta = (now - last_ping_time).total_seconds()
        if delta > 1800:  # > 30 minuti
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                    json={
                        "chat_id": ADMIN_ID,
                        "text": f"⚠️ **ALLARME DOWNTIME**\nMi sono appena svegliato, ma non ricevevo ping da {int(delta/60)} minuti. \nControlla Render o cron-job.org!",
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
    try:
        with open('chiave_api.txt', 'r') as f: return f.read().strip()
    except: return ""

def get_gemini_client():
    chiave = leggi_chiave_api()
    return genai.Client(api_key=chiave) if chiave else None

def connetti_sheets():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return build('sheets', 'v4', credentials=creds)

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
        matches = requests.get(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
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
                        if (c_sh in ac or c_sh in sc) and (o_sh in ao or o_sh in so):
                            ev["partita"] = f"{m['homeTeam'].get('shortName', m['homeTeam']['name'])} - {m['awayTeam'].get('shortName', m['awayTeam']['name'])}"
                            break
        return json.dumps(dati)
    except: return dati_json

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
            pronostico = str(evento.get("pronostico", "")).upper()
            
            if "OVER_1.5" in pronostico: pronostico = pronostico.replace("1.5", "2.5")
            if "UNDER_3.5" in pronostico: pronostico = pronostico.replace("3.5", "2.5")
            
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
        ).execute()
        return True
    return False

# ==========================================
# CALCOLO RISULTATI E API
# ==========================================
def ottieni_giornata_corrente():
    try:
        res = requests.get("https://api.football-data.org/v4/competitions/SA", headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json()
        return res.get('currentSeason', {}).get('currentMatchday', 1)
    except: return 1

def estrai_numero(testo):
    try:
        match = re.search(r'\d+(?:\.\d+)?', str(testo).replace(',', '.'))
        return float(match.group()) if match else 0.0
    except: return 0.0

def controlla_esito(pronostico, gol_casa, gol_ospite):
    if "ANNULLATA" in pronostico: return "➖ ANNULLATA"
    tot, segno = gol_casa + gol_ospite, "1" if gol_casa > gol_ospite else ("2" if gol_ospite > gol_casa else "X")
    entrambe, vinta = "GOAL" if (gol_casa > 0 and gol_ospite > 0) else "NOGOAL", True
    for p in pronostico.split('+'):
        p = p.strip()
        if p in ["1", "X", "2"] and p != segno: vinta = False
        elif p == "1X" and segno not in ["1", "X"]: vinta = False
        elif p == "X2" and segno not in ["X", "2"]: vinta = False
        elif p == "12" and segno not in ["1", "2"]: vinta = False
        elif p == "GOAL" and entrambe != "GOAL": vinta = False
        elif p == "NOGOAL" and entrambe != "NOGOAL": vinta = False
        elif p == "PARI" and (tot % 2) != 0: vinta = False
        elif p == "DISPARI" and (tot % 2) == 0: vinta = False
        elif "UNDER" in p or "OVER" in p:
            try:
                if "UNDER" in p and tot > float(p.split('_')[1]): vinta = False
                if "OVER" in p and tot < float(p.split('_')[1]): vinta = False
            except: pass
    return "✅ VINTA" if vinta else "❌ PERSA"

def calcola_punteggio_partita(pronostico, quota):
    if "ANNULLATA" in pronostico: return 0
    punti = 6 if "+" in pronostico else (4 if pronostico in ["1","X","2"] else (1 if pronostico in ["1X","X2","12"] else 2))
    return punti * 2 if quota >= 3.50 else punti

def esegui_calcolo_risultati(giornata):
    service = connetti_sheets()
    url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata}"
    try: matches_api = requests.get(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
    except: return "Errore di connessione a Football-Data API."

    if not matches_api: return "Nessuna partita trovata per questa giornata."

    righe_giocate = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Giocate!A:I").execute().get('values', [])
    classifica, aggiornamenti_testo, richieste_stile = {}, [], []
    colore_verde, colore_rosso, colore_grigio = {"red":0.85,"green":0.95,"blue":0.85}, {"red":0.95,"green":0.85,"blue":0.85}, {"red":0.90,"green":0.90,"blue":0.90}
    sheet_id_giocate = next(s['properties']['sheetId'] for s in service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute().get('sheets', []) if s['properties']['title'].lower() == 'giocate')

    for idx, riga in enumerate(righe_giocate):
        if len(riga) < 6 or "giornata" not in str(riga[0]).lower() or str(giornata) not in str(riga[0]): continue
        gio, partita, pron, quota = str(riga[1]).strip(), str(riga[2]).strip(), str(riga[4]).strip().upper(), estrai_numero(riga[5])
        vincita = estrai_numero(riga[7]) if len(riga) > 7 else 0.0

        if gio not in classifica: classifica[gio] = {"punti": 0, "vinte": 0, "perse": 0, "in_corso": 0, "cassa": vincita}
        elif vincita > 0: classifica[gio]["cassa"] = vincita

        casa_sh, ospite_sh = [s.strip()[:5] for s in partita.lower().split('-')]
        match = next((m for m in matches_api if (casa_sh in str(m["homeTeam"]["name"]).lower() or casa_sh in str(m.get("homeTeam",{}).get("shortName","")).lower()) and (ospite_sh in str(m["awayTeam"]["name"]).lower() or ospite_sh in str(m.get("awayTeam",{}).get("shortName","")).lower())), None)
        
        punti_partita = 0
        if match:
            if match["status"] != "FINISHED":
                testo_esito, col = "⏳ IN CORSO", colore_grigio
                classifica[gio]["in_corso"] += 1
            else:
                testo_esito = controlla_esito(pron, match["score"]["fullTime"]["home"], match["score"]["fullTime"]["away"])
                if "VINTA" in testo_esito: col, punti_partita = colore_verde, calcola_punteggio_partita(pron, quota); classifica[gio]["punti"] += punti_partita; classifica[gio]["vinte"] += 1
                elif "ANNULLATA" in testo_esito: col = colore_grigio
                else: col = colore_rosso; classifica[gio]["perse"] += 1
            
            aggiornamenti_testo.extend([{'range': f"Giocate!G{idx+1}", 'values': [[testo_esito]]}, {'range': f"Giocate!I{idx+1}", 'values': [[punti_partita]]}])
            richieste_stile.append({"repeatCell": {"range": {"sheetId": sheet_id_giocate, "startRowIndex": idx, "endRowIndex": idx+1, "startColumnIndex": 6, "endColumnIndex": 7}, "cell": {"userEnteredFormat": {"backgroundColor": col}}, "fields": "userEnteredFormat.backgroundColor"}})

    if aggiornamenti_testo:
        service.spreadsheets().values().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={'valueInputOption': 'USER_ENTERED', 'data': aggiornamenti_testo}).execute()
        service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": richieste_stile}).execute()

    vincitori, report = [], f"📊 *REPORT GIORNATA {giornata}*\n\n"
    for gio, dati in classifica.items():
        if (dati["vinte"] + dati["perse"] + dati["in_corso"]) == 0: continue
        if dati["perse"] > 0: stato = "❌ Bruciata"
        elif dati["in_corso"] > 0: stato = f"⏳ In attesa ({dati['in_corso']})"
        else:
            stato, dati["punti"] = "🏆 CHIUSA! (+10 Pt)", dati["punti"] + 10
            v_euro = dati["cassa"] / 2.0
            if v_euro > 0: vincitori.append({"nome": gio, "importo": v_euro})
        report += f"👤 *{gio.upper()}* - {dati['punti']} Pt\n({dati['vinte']} V | {dati['perse']} P | {dati['in_corso']} C) -> {stato}\n\n"

    righe_class = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Classifica!A:Z").execute().get('values', [["Giocatore", "Punti Totali"]])
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
    service.spreadsheets().values().update(spreadsheetId=SPREADSHEET_ID, range="Classifica!A1", valueInputOption="USER_ENTERED", body={"values": righe_class}).execute()

    if vincitori:
        res_cassa = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Cassa!A:D").execute()
        righe_cassa = res_cassa.get('values', []) or [["Giornata", "Descrizione", "Entrate", "Saldo Totale"]]
        saldo = estrai_numero(righe_cassa[-1][3]) if len(righe_cassa[-1]) > 3 and righe_cassa[-1][3] != "Saldo Totale" else 0.0
        nuove = []
        for v in vincitori:
            descr = f"{v['nome'].upper()} chiude la schedina!"
            if not any(len(r) > 1 and r[0] == f"Giornata {giornata}" and r[1] == descr for r in righe_cassa):
                saldo += v["importo"]
                nuove.append([f"Giornata {giornata}", descr, f"{v['importo']:.2f} €".replace(".", ","), f"{saldo:.2f} €".replace(".", ",")])
                righe_cassa.append(nuove[-1])
        if nuove:
            service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range="Cassa!A:D", valueInputOption="USER_ENTERED", body={"values": nuove}).execute()
            report += "💰 *Vincite registrate in Cassa!*\n"
    return report

# ==========================================
# GESTIONE TELEGRAM E MENU CON PULSANTE KEY
# ==========================================
async def set_api_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ Uso corretto: `/setkey <tua_chiave_api>`", parse_mode="Markdown")
        return
    nuova_chiave = args[0].strip()
    try:
        with open('chiave_api.txt', 'w') as f: f.write(nuova_chiave)
        await update.message.reply_text("✅ **Chiave API Gemini aggiornata con successo!**", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")

async def gestisci_testo_chiave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    nuova_chiave = update.message.text.strip()
    try:
        with open('chiave_api.txt', 'w') as f: f.write(nuova_chiave)
        await update.message.reply_text("✅ **Chiave API Gemini aggiornata con successo!**\nScrivi /start per tornare al menu.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")
    return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    kb = [
        [InlineKeyboardButton("📥 Carica Schedina", callback_data="menu_carica")],
        [InlineKeyboardButton("⚽ Aggiorna Risultati & Punteggi", callback_data="menu_aggiorna")],
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
        risultato_json_raw = analizza_schedine_multiple(foto_lista)
        risultato_json = normalizza_nomi_partite(risultato_json_raw, giorn)
        
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
        successo = scrivi_su_sheets_con_regole(gio, giorn, risultato_json)
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
    report = esegui_calcolo_risultati(giornata)
    await context.bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode="Markdown")
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
    giornata = ottieni_giornata_corrente()
    report = esegui_calcolo_risultati(giornata)
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"⏰ **AUTO UPDATE (G.{giornata})**\n\n{report}", parse_mode="Markdown")

async def task_controlla_schedine_mancanti(context: ContextTypes.DEFAULT_TYPE):
    """Controlla chi non ha ancora caricato la schedina per la giornata corrente.
    Viene chiamata da un job schedulato 30 min prima della prima partita."""
    try:
        giornata = ottieni_giornata_corrente()
        service = connetti_sheets()
        righe = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range="Giocate!A:B"
        ).execute().get('values', [])
        
        giocatori_presenti = set()
        for riga in righe:
            if len(riga) >= 2 and str(giornata) in str(riga[0]):
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
    """Job giornaliero: controlla a che ora inizia la prima partita di oggi
    e schedula il promemoria 30 min prima."""
    try:
        giornata = ottieni_giornata_corrente()
        url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata}"
        matches = requests.get(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
        if not matches:
            return
        
        tz = pytz.timezone('Europe/Rome')
        oggi = datetime.now(tz).date()
        
        # Trova la prima partita di OGGI
        orari_oggi = []
        for m in matches:
            utc_str = m.get("utcDate", "")
            if utc_str:
                utc_dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
                ita_dt = utc_dt.astimezone(tz)
                if ita_dt.date() == oggi and m["status"] in ["TIMED", "SCHEDULED"]:
                    orari_oggi.append(ita_dt)
        
        if not orari_oggi:
            return  # Nessuna partita oggi, nessun promemoria
        
        prima_partita = min(orari_oggi)
        orario_promemoria = prima_partita - timedelta(minutes=30)
        ora_corrente = datetime.now(tz)
        
        if orario_promemoria > ora_corrente:
            secondi_mancanti = (orario_promemoria - ora_corrente).total_seconds()
            context.job_queue.run_once(
                task_controlla_schedine_mancanti,
                when=secondi_mancanti,
                name=f"promemoria_g{giornata}"
            )
            logging.info(f"Promemoria schedine schedulato alle {orario_promemoria.strftime('%H:%M')} (tra {int(secondi_mancanti/60)} min)")
    except Exception as e:
        logging.error(f"Errore task_schedula_promemoria: {e}")

async def post_init(application: Application):
    """Imposta i comandi rapidi ufficiali nel menu di Telegram (il tasto '/')"""
    await application.bot.set_my_commands([
        ("start", "Apri il menu principale"),
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
    for h, m in [(17,30), (20,30), (23,0)]:
        app.job_queue.run_daily(task_aggiornamento_automatico, time=dt_time(hour=h, minute=m, tzinfo=tz))

    # Job giornaliero: alle 10:00 controlla se ci sono partite oggi e schedula promemoria 30min prima
    app.job_queue.run_daily(task_schedula_promemoria, time=dt_time(hour=10, minute=0, tzinfo=tz))

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
            ]
        },
        fallbacks=[CommandHandler("cancel", annulla_tutto)]
    )

    app.add_handler(CommandHandler("setkey", set_api_key_command))
    app.add_handler(conv_handler)
    print("🤖 Super-Bot Telegram (con Web Service) avviato...")
    app.run_polling()

if __name__ == '__main__':
    main()