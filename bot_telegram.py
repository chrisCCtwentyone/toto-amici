import os
import json
import logging
import re
import requests
from datetime import time as dt_time
import pytz
from PIL import Image
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# ==========================================
# 1. CONFIGURAZIONI GLOBALI E CHIAVI
# ==========================================
TOKEN = "8996951565:AAGbxyDm4ZuA_Wntv1Vv_IoxQPS-Hvf7euw"
ADMIN_ID = 173820382

SPREADSHEET_ID = '1q0aaYXl7VYiUzEbttGaoQjNq7ta5wiHD4Qvg5Si7IvE'
SERVICE_ACCOUNT_FILE = 'credenziali.json'
FOOTBALL_DATA_KEY = "ef8a4016b5ab4f90a486ea0fea46fd1f"

GIOCATORI = [
    "cecilia", "dario", "davide", "fazio", 
    "gaetano", "giacomo", "giovanni", "mario", 
    "michele", "mirko", "nico", "paolo", 
    "pulizzer", "silvio", "villari", "vincenzo"
]

LIMITI_SCHEDINA = {"Combo": 1, "Fisse": 4, "Doppie Chance": 2, "Variabili": 3}

# Stati Conversazione Telegram
MENU, RICEVI_FOTO, SCELTA_GIORNATA, SCELTA_GIOCATORE, CONFERMA, SCELTA_GIORNATA_UPDATE = range(6)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def leggi_chiave_api():
    try:
        with open('chiave_api.txt', 'r') as f:
            return f.read().strip()
    except: return ""

client = genai.Client(api_key=leggi_chiave_api()) if leggi_chiave_api() else None

def connetti_sheets():
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

# ==========================================
# 2. MOTORE AI E INSERIMENTO SCHEDINE
# ==========================================
def analizza_schedina_con_gemini(percorso_foto):
    img = Image.open(percorso_foto)
    if img.mode != 'RGB': img = img.convert('RGB')
    img.thumbnail((1000, 1000))
    
    prompt = """
    Analizza questa schedina sportiva.
    1. VINCITA POTENZIALE: Restituisci SOLO IL VALORE NUMERICO IN EURO (es. "72.50").
    2. EVENTI: Dividi in "Combo", "Fisse", "Doppie Chance", "Variabili" con chiavi: "partita", "pronostico", "quota".
    Regole normalizzazione: Esito (1,X,2), Doppia (1X,X2,12), Variabili (GOAL, NOGOAL, UNDER_2.5, OVER_2.5, PARI, DISPARI).
    """
    response = client.models.generate_content(
        model='gemini-3.6-flash', contents=[prompt, img],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return response.text

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
# 3. MOTORE AGGIORNAMENTO RISULTATI
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
    
    tot = gol_casa + gol_ospite
    segno = "1" if gol_casa > gol_ospite else ("2" if gol_ospite > gol_casa else "X")
    entrambe = "GOAL" if (gol_casa > 0 and gol_ospite > 0) else "NOGOAL"
    
    vinta = True
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
                val = float(p.split('_')[1])
                if "UNDER" in p and tot > val: vinta = False
                if "OVER" in p and tot < val: vinta = False
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
    classifica = {}
    aggiornamenti_testo, richieste_stile = [], []
    colore_verde, colore_rosso, colore_grigio = {"red":0.85,"green":0.95,"blue":0.85}, {"red":0.95,"green":0.85,"blue":0.85}, {"red":0.90,"green":0.90,"blue":0.90}
    sheet_id_giocate = next(s['properties']['sheetId'] for s in service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute().get('sheets', []) if s['properties']['title'].lower() == 'giocate')

    for idx, riga in enumerate(righe_giocate):
        if len(riga) < 6 or "giornata" not in str(riga[0]).lower() or str(riga[1]).lower() == "giocatore": continue
        if str(giornata) not in str(riga[0]): continue
        
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
                if "VINTA" in testo_esito:
                    col, punti_partita = colore_verde, calcola_punteggio_partita(pron, quota)
                    classifica[gio]["punti"] += punti_partita
                    classifica[gio]["vinte"] += 1
                elif "ANNULLATA" in testo_esito:
                    col = colore_grigio
                else:
                    col = colore_rosso
                    classifica[gio]["perse"] += 1
            
            aggiornamenti_testo.extend([{'range': f"Giocate!G{idx+1}", 'values': [[testo_esito]]}, {'range': f"Giocate!I{idx+1}", 'values': [[punti_partita]]}])
            richieste_stile.append({"repeatCell": {"range": {"sheetId": sheet_id_giocate, "startRowIndex": idx, "endRowIndex": idx+1, "startColumnIndex": 6, "endColumnIndex": 7}, "cell": {"userEnteredFormat": {"backgroundColor": col}}, "fields": "userEnteredFormat.backgroundColor"}})

    if aggiornamenti_testo:
        service.spreadsheets().values().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={'valueInputOption': 'USER_ENTERED', 'data': aggiornamenti_testo}).execute()
        service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": richieste_stile}).execute()

    vincitori = []
    report = f"📊 *REPORT GIORNATA {giornata}*\n\n"
    
    for gio, dati in classifica.items():
        if (dati["vinte"] + dati["perse"] + dati["in_corso"]) == 0: continue
        
        if dati["perse"] > 0:
            stato = "❌ Bruciata"
        elif dati["in_corso"] > 0:
            stato = f"⏳ In attesa ({dati['in_corso']})"
        else:
            stato = "🏆 CHIUSA! (+10 Pt)"
            dati["punti"] += 10
            vincita_euro = dati["cassa"] / 2.0
            if vincita_euro > 0:
                vincitori.append({"nome": gio, "importo": vincita_euro})
                
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
        tot = sum([int(str(x)) for x in righe_class[mappa[gio.lower()]][2:] if str(x).isdigit()])
        righe_class[mappa[gio.lower()]][1] = tot
    service.spreadsheets().values().update(spreadsheetId=SPREADSHEET_ID, range="Classifica!A1", valueInputOption="USER_ENTERED", body={"values": righe_class}).execute()

    if vincitori:
        res_cassa = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Cassa!A:D").execute()
        righe_cassa = res_cassa.get('values', [])
        
        if not righe_cassa:
            righe_cassa = [["Giornata", "Descrizione", "Entrate", "Saldo Totale"]]
            saldo_attuale = 0.0
        else:
            saldo_attuale = estrai_numero(righe_cassa[-1][3]) if len(righe_cassa[-1]) > 3 else 0.0

        nuove_righe_cassa = []
        for v in vincitori:
            descrizione = f"{v['nome'].upper()} chiude la schedina!"
            gia_registrato = any(len(r) > 1 and r[0] == f"Giornata {giornata}" and r[1] == descrizione for r in righe_cassa)
                    
            if not gia_registrato:
                saldo_attuale += v["importo"]
                nuova_riga = [
                    f"Giornata {giornata}",
                    descrizione,
                    f"{v['importo']:.2f} €".replace(".", ","),
                    f"{saldo_attuale:.2f} €".replace(".", ",")
                ]
                nuove_righe_cassa.append(nuova_riga)
                righe_cassa.append(nuova_riga)

        if nuove_righe_cassa:
            service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID, range="Cassa!A:D",
                valueInputOption="USER_ENTERED", body={"values": nuove_righe_cassa}
            ).execute()
            report += "💰 *Vincite registrate in Cassa!*\n"

    return report

# ==========================================
# 4. GESTIONE TELEGRAM E MENU
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    keyboard = [
        [InlineKeyboardButton("📥 Carica Schedina", callback_data="menu_carica")],
        [InlineKeyboardButton("⚽ Aggiorna Risultati & Punteggi", callback_data="menu_aggiorna")]
    ]
    await update.message.reply_text("👋 *Menu Principale Toto-Amici*\nCosa vuoi fare?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return MENU

async def gestisci_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "menu_carica":
        keyboard = [[InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")]]
        await query.edit_message_text("📸 Perfetto! Mandami la foto della bolletta.", reply_markup=InlineKeyboardMarkup(keyboard))
        return RICEVI_FOTO
    elif query.data == "menu_aggiorna":
        keyboard = []
        riga = []
        for i in range(1, 39):
            riga.append(InlineKeyboardButton(str(i), callback_data=f"update_{i}"))
            if len(riga) == 5 or i == 38:
                keyboard.append(riga)
                riga = []
        keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")])
        await query.edit_message_text("📅 Quale **Giornata** vuoi aggiornare e calcolare?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return SCELTA_GIORNATA_UPDATE

async def ricevi_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    photo_file = await update.message.photo[-1].get_file()
    if not os.path.exists("temp_telegram"): os.makedirs("temp_telegram")
    percorso_foto = f"temp_telegram/schedina_tmp.jpg"
    await photo_file.download_to_drive(percorso_foto)
    context.user_data['percorso_foto'] = percorso_foto

    keyboard = []
    riga = []
    for i in range(1, 39):
        riga.append(InlineKeyboardButton(str(i), callback_data=f"giornata_{i}"))
        if len(riga) == 5 or i == 38:
            keyboard.append(riga)
            riga = []
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")])
    await update.message.reply_text("📅 A quale **Giornata** si riferisce la bolletta caricata?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return SCELTA_GIORNATA

async def scegli_giornata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['giornata'] = query.data.split('_')[1]
    
    keyboard = []
    riga = []
    for nome in GIOCATORI:
        riga.append(InlineKeyboardButton(nome.capitalize(), callback_data=f"giocatore_{nome}"))
        if len(riga) == 4:
            keyboard.append(riga)
            riga = []
    if riga: keyboard.append(riga)
    keyboard.append([InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")])
    
    await query.edit_message_text(text=f"✅ Giornata: {context.user_data['giornata']}\n\n👤 Di chi è?", reply_markup=InlineKeyboardMarkup(keyboard))
    return SCELTA_GIOCATORE

async def scegli_giocatore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['giocatore'] = query.data.split('_')[1]
    
    keyboard = [[InlineKeyboardButton("✅ Conferma", callback_data="conferma_si")], [InlineKeyboardButton("❌ Annulla", callback_data="conferma_no")]]
    await query.edit_message_text(text=f"⚠️ Vuoi elaborare:\n👤 **{context.user_data['giocatore'].capitalize()}** - 📅 **Giornata {context.user_data['giornata']}**?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return CONFERMA

async def esegui_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "conferma_no":
        await pulisci_dati(context)
        await query.edit_message_text("❌ Operazione annullata. Scrivi /start per riaprire il menu.")
        return ConversationHandler.END

    gio, giorn, foto = context.user_data['giocatore'], context.user_data['giornata'], context.user_data['percorso_foto']
    await query.edit_message_text(f"⏳ Analisi in corso per {gio.capitalize()} (Giornata {giorn})...")
    
    try:
        risultato_json = analizza_schedina_con_gemini(foto)
        successo = scrivi_su_sheets_con_regole(gio, giorn, risultato_json)
        msg = f"✅ Schedina caricata con successo!" if successo else "⚠️ Errore nella scrittura su Sheets."
        await query.message.reply_text(msg)
    except Exception as e:
        await query.message.reply_text(f"❌ Errore: {e}")
        
    await pulisci_dati(context)
    return ConversationHandler.END

async def scegli_giornata_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    giornata = query.data.split('_')[1]
    
    await query.edit_message_text(f"⏳ Avvio aggiornamento manuale per la **Giornata {giornata}**...\nSto contattando l'API Football e aggiornando Google Sheets.", parse_mode="Markdown")
    
    report = esegui_calcolo_risultati(giornata)
    await context.bot.send_message(chat_id=ADMIN_ID, text=report, parse_mode="Markdown")
    return ConversationHandler.END

async def annulla_azione_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await pulisci_dati(context)
    await query.edit_message_text("❌ Operazione annullata. Scrivi /start per riaprire il menu.")
    return ConversationHandler.END

async def annulla_tutto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await pulisci_dati(context)
    await update.message.reply_text("❌ Operazione annullata. Scrivi /start per riaprire il menu.")
    return ConversationHandler.END

async def pulisci_dati(context: ContextTypes.DEFAULT_TYPE):
    if 'percorso_foto' in context.user_data:
        foto = context.user_data['percorso_foto']
        if os.path.exists(foto):
            os.remove(foto)
        del context.user_data['percorso_foto']

# --- AGGIORNAMENTO AUTOMATICO (CRON) ---
async def task_aggiornamento_automatico(context: ContextTypes.DEFAULT_TYPE):
    giornata = ottieni_giornata_corrente()
    report = esegui_calcolo_risultati(giornata)
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"⏰ **AGGIORNAMENTO AUTOMATICO (Giornata {giornata})**\n\n{report}", parse_mode="Markdown")

def main():
    app = Application.builder().token(TOKEN).build()
    
    tz = pytz.timezone('Europe/Rome')
    app.job_queue.run_daily(task_aggiornamento_automatico, time=dt_time(hour=17, minute=30, tzinfo=tz))
    app.job_queue.run_daily(task_aggiornamento_automatico, time=dt_time(hour=20, minute=30, tzinfo=tz))
    app.job_queue.run_daily(task_aggiornamento_automatico, time=dt_time(hour=23, minute=0, tzinfo=tz))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(gestisci_menu, pattern="^menu_")],
            RICEVI_FOTO: [
                MessageHandler(filters.PHOTO, ricevi_foto),
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
                CallbackQueryHandler(esegui_conferma, pattern="^conferma_")
            ],
            SCELTA_GIORNATA_UPDATE: [
                CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$"),
                CallbackQueryHandler(scegli_giornata_update, pattern="^update_")
            ]
        },
        fallbacks=[CommandHandler("cancel", annulla_tutto)]
    )

    app.add_handler(conv_handler)
    print("🤖 Super-Bot Telegram avviato! In attesa di comandi...")
    app.run_polling()

if __name__ == '__main__':
    main()