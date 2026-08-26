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

TOKEN = "8996951565:AAGbxyDm4ZuA_Wntv1Vv_IoxQPS-Hvf7euw"
ADMIN_ID = 173820382
SPREADSHEET_ID = '1q0aaYXl7VYiUzEbttGaoQjNq7ta5wiHD4Qvg5Si7IvE'
SERVICE_ACCOUNT_FILE = 'credenziali.json'
FOOTBALL_DATA_KEY = "ef8a4016b5ab4f90a486ea0fea46fd1f"

GIOCATORI = [
    "cecilia", "dario", "davide", "fazio", "gaetano", "giacomo", "giovanni", "mario", 
    "michele", "mirko", "nico", "paolo", "pulizzer", "silvio", "villari", "vincenzo"
]
LIMITI_SCHEDINA = {"Combo": 1, "Fisse": 4, "Doppie Chance": 2, "Variabili": 3}
MENU, RICEVI_FOTO, SCELTA_GIORNATA, SCELTA_GIOCATORE, CONFERMA, SCELTA_GIORNATA_UPDATE = range(6)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def leggi_chiave_api():
    try:
        with open('chiave_api.txt', 'r') as f: return f.read().strip()
    except: return ""

client = genai.Client(api_key=leggi_chiave_api()) if leggi_chiave_api() else None

def connetti_sheets():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return build('sheets', 'v4', credentials=creds)

def analizza_schedina_con_gemini(percorso_foto):
    img = Image.open(percorso_foto)
    if img.mode != 'RGB': img = img.convert('RGB')
    img.thumbnail((1000, 1000))
    prompt = """Analizza questa schedina sportiva. 1. VINCITA POTENZIALE in EURO. 2. EVENTI: "Combo", "Fisse", "Doppie Chance", "Variabili" (partita, pronostico, quota)."""
    response = client.models.generate_content(model='gemini-3.6-flash', contents=[prompt, img], config=types.GenerateContentConfig(response_mime_type="application/json"))
    return response.text

# NOVITÀ: Normalizzazione rigorosa dei nomi partita prima di salvare
def normalizza_nomi_partite(dati_json, giornata_num):
    try:
        url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata_num}"
        matches = requests.get(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
        if not matches: return dati_json
        
        dati = json.loads(dati_json)
        eventi = dati.get("eventi", dati)
        
        for cat in ["Combo", "Fisse", "Doppie Chance", "Variabili"]:
            for ev in eventi.get(cat, []):
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
    
    vincita = f"{float(str(dati.get('vincita_potenziale', '0')).replace(',', '.')):.2f}".replace('.', ',') if str(dati.get('vincita_potenziale', '0')) != "0" else "0,00"
    righe = []
    prima = True
    
    for cat in ["Combo", "Fisse", "Doppie Chance", "Variabili"]:
        for idx, ev in enumerate(dati.get("eventi", dati).get(cat, [])):
            pron = str(ev.get("pronostico", "")).upper().replace("1.5", "2.5").replace("3.5", "2.5")
            if idx >= LIMITI_SCHEDINA[cat]: pron += " (ANNULLATA ECCESSO)"
            q_raw = str(ev.get("quota", "")).replace('.', ',')
            
            riga = [f"Giornata {giornata_num}", nome_giocatore.upper(), ev.get("partita", ""), cat, pron, q_raw]
            if prima: riga.extend(["", vincita]); prima = False
            righe.append(riga)

    if righe:
        sheets_service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range="Giocate!A:I", valueInputOption="USER_ENTERED", body={'values': righe}).execute()
        return True
    return False

# ----- Funzioni Calcolo e Bot Telegram (Rimaste inalterate) -----
def ottieni_giornata_corrente():
    try: return requests.get("https://api.football-data.org/v4/competitions/SA", headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get('currentSeason', {}).get('currentMatchday', 1)
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

def calcola_punteggio_partita(pron, quota):
    if "ANNULLATA" in pron: return 0
    pti = 6 if "+" in pron else (4 if pron in ["1","X","2"] else (1 if pron in ["1X","X2","12"] else 2))
    return pti * 2 if quota >= 3.50 else pti

def esegui_calcolo_risultati(giornata):
    service = connetti_sheets()
    matches_api = requests.get(f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata}", headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
    if not matches_api: return "Nessuna partita trovata."

    righe_giocate = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Giocate!A:I").execute().get('values', [])
    classifica, agg_testo, req_stile = {}, [], []
    c_verde, c_rosso, c_grigio = {"red":0.85,"green":0.95,"blue":0.85}, {"red":0.95,"green":0.85,"blue":0.85}, {"red":0.90,"green":0.90,"blue":0.90}
    s_id = next(s['properties']['sheetId'] for s in service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute().get('sheets', []) if s['properties']['title'].lower() == 'giocate')

    for idx, riga in enumerate(righe_giocate):
        if len(riga) < 6 or "giornata" not in str(riga[0]).lower() or str(giornata) not in str(riga[0]): continue
        gio, partita, pron, quota = str(riga[1]).strip(), str(riga[2]).strip(), str(riga[4]).strip().upper(), estrai_numero(riga[5])
        vincita = estrai_numero(riga[7]) if len(riga) > 7 else 0.0

        if gio not in classifica: classifica[gio] = {"punti": 0, "vinte": 0, "perse": 0, "in_corso": 0, "cassa": vincita}
        elif vincita > 0: classifica[gio]["cassa"] = vincita

        c_sh, o_sh = [s.strip()[:5] for s in partita.lower().split('-')]
        match = next((m for m in matches_api if (c_sh in str(m["homeTeam"]["name"]).lower() or c_sh in str(m.get("homeTeam",{}).get("shortName","")).lower()) and (o_sh in str(m["awayTeam"]["name"]).lower() or o_sh in str(m.get("awayTeam",{}).get("shortName","")).lower())), None)
        
        pti_match = 0
        if match:
            if match["status"] != "FINISHED":
                esito, col = "⏳ IN CORSO", c_grigio
                classifica[gio]["in_corso"] += 1
            else:
                esito = controlla_esito(pron, match["score"]["fullTime"]["home"], match["score"]["fullTime"]["away"])
                if "VINTA" in esito: col, pti_match = c_verde, calcola_punteggio_partita(pron, quota); classifica[gio]["punti"] += pti_match; classifica[gio]["vinte"] += 1
                elif "ANNULLATA" in esito: col = c_grigio
                else: col = c_rosso; classifica[gio]["perse"] += 1
            agg_testo.extend([{'range': f"Giocate!G{idx+1}", 'values': [[esito]]}, {'range': f"Giocate!I{idx+1}", 'values': [[pti_match]]}])
            req_stile.append({"repeatCell": {"range": {"sheetId": s_id, "startRowIndex": idx, "endRowIndex": idx+1, "startColumnIndex": 6, "endColumnIndex": 7}, "cell": {"userEnteredFormat": {"backgroundColor": col}}, "fields": "userEnteredFormat.backgroundColor"}})

    if agg_testo:
        service.spreadsheets().values().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={'valueInputOption': 'USER_ENTERED', 'data': agg_testo}).execute()
        service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": req_stile}).execute()

    vincitori, report = [], f"📊 *REPORT GIORNATA {giornata}*\n\n"
    for gio, dati in classifica.items():
        if sum([dati["vinte"], dati["perse"], dati["in_corso"]]) == 0: continue
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
            report += "💰 *Vincite in Cassa!*\n"
    return report

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    kb = [[InlineKeyboardButton("📥 Carica", callback_data="menu_carica")], [InlineKeyboardButton("⚽ Aggiorna", callback_data="menu_aggiorna")]]
    await update.message.reply_text("👋 *Menu Toto-Amici*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return MENU

async def gestisci_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "menu_carica":
        await query.edit_message_text("📸 Mandami la foto.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")]]))
        return RICEVI_FOTO
    elif query.data == "menu_aggiorna":
        kb = [[InlineKeyboardButton(str(i), callback_data=f"update_{i}") for i in range(r, r+5)] for r in range(1, 39, 5)]
        kb[-1] = [InlineKeyboardButton(str(i), callback_data=f"update_{i}") for i in range(36, 39)]
        kb.append([InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")])
        await query.edit_message_text("📅 Quale **Giornata** aggiornare?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return SCELTA_GIORNATA_UPDATE

async def ricevi_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    if not os.path.exists("temp_telegram"): os.makedirs("temp_telegram")
    context.user_data['percorso_foto'] = "temp_telegram/schedina_tmp.jpg"
    await photo_file.download_to_drive(context.user_data['percorso_foto'])
    kb = [[InlineKeyboardButton(str(i), callback_data=f"giornata_{i}") for i in range(r, r+5)] for r in range(1, 39, 5)]
    kb[-1] = [InlineKeyboardButton(str(i), callback_data=f"giornata_{i}") for i in range(36, 39)]
    kb.append([InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")])
    await update.message.reply_text("📅 A quale **Giornata** si riferisce?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return SCELTA_GIORNATA

async def scegli_giornata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    context.user_data['giornata'] = query.data.split('_')[1]
    kb = [[InlineKeyboardButton(GIOCATORI[i].capitalize(), callback_data=f"giocatore_{GIOCATORI[i]}") for i in range(r, r+4)] for r in range(0, len(GIOCATORI), 4)]
    kb.append([InlineKeyboardButton("❌ Annulla", callback_data="annulla_azione")])
    await query.edit_message_text(text=f"✅ Giornata {context.user_data['giornata']}\n👤 Di chi è?", reply_markup=InlineKeyboardMarkup(kb))
    return SCELTA_GIOCATORE

async def scegli_giocatore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    context.user_data['giocatore'] = query.data.split('_')[1]
    kb = [[InlineKeyboardButton("✅ Conferma", callback_data="conferma_si")], [InlineKeyboardButton("❌ Annulla", callback_data="conferma_no")]]
    await query.edit_message_text(text=f"⚠️ Vuoi elaborare:\n👤 **{context.user_data['giocatore'].capitalize()}** - 📅 **Giornata {context.user_data['giornata']}**?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    return CONFERMA

async def esegui_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "conferma_no":
        await pulisci_dati(context); await query.edit_message_text("❌ Annullato.")
        return ConversationHandler.END

    gio, giorn, foto = context.user_data['giocatore'], context.user_data['giornata'], context.user_data['percorso_foto']
    await query.edit_message_text(f"⏳ Analisi in corso per {gio.capitalize()} (Giornata {giorn})...")
    
    try:
        risultato_json = analizza_schedina_con_gemini(foto)
        # CHIAMATA AL NORMALIZZATORE
        risultato_json = normalizza_nomi_partite(risultato_json, giorn)
        msg = f"✅ Schedina caricata!" if scrivi_su_sheets_con_regole(gio, giorn, risultato_json) else "⚠️ Errore scrittura."
        await query.message.reply_text(msg)
    except Exception as e: await query.message.reply_text(f"❌ Errore: {e}")
        
    await pulisci_dati(context)
    return ConversationHandler.END

async def scegli_giornata_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    giornata = query.data.split('_')[1]
    await query.edit_message_text(f"⏳ Aggiornamento in corso Giornata {giornata}...")
    await context.bot.send_message(chat_id=ADMIN_ID, text=esegui_calcolo_risultati(giornata), parse_mode="Markdown")
    return ConversationHandler.END

async def annulla_azione_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await pulisci_dati(context); await update.callback_query.edit_message_text("❌ Annullato. Scrivi /start")
    return ConversationHandler.END

async def annulla_tutto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await pulisci_dati(context); await update.message.reply_text("❌ Annullato.")
    return ConversationHandler.END

async def pulisci_dati(context: ContextTypes.DEFAULT_TYPE):
    if 'percorso_foto' in context.user_data and os.path.exists(context.user_data['percorso_foto']):
        os.remove(context.user_data['percorso_foto']); del context.user_data['percorso_foto']

async def task_aggiornamento_automatico(context: ContextTypes.DEFAULT_TYPE):
    giorn = ottieni_giornata_corrente()
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"⏰ **AUTO UPDATE (G.{giorn})**\n\n{esegui_calcolo_risultati(giorn)}", parse_mode="Markdown")

def main():
    app = Application.builder().token(TOKEN).build()
    tz = pytz.timezone('Europe/Rome')
    for h, m in [(17,30), (20,30), (23,0)]: app.job_queue.run_daily(task_aggiornamento_automatico, time=dt_time(hour=h, minute=m, tzinfo=tz))
    
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(gestisci_menu, pattern="^menu_")],
            RICEVI_FOTO: [MessageHandler(filters.PHOTO, ricevi_foto), CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$")],
            SCELTA_GIORNATA: [CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$"), CallbackQueryHandler(scegli_giornata, pattern="^giornata_")],
            SCELTA_GIOCATORE: [CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$"), CallbackQueryHandler(scegli_giocatore, pattern="^giocatore_")],
            CONFERMA: [CallbackQueryHandler(esegui_conferma, pattern="^conferma_")],
            SCELTA_GIORNATA_UPDATE: [CallbackQueryHandler(annulla_azione_callback, pattern="^annulla_azione$"), CallbackQueryHandler(scegli_giornata_update, pattern="^update_")]
        },
        fallbacks=[CommandHandler("cancel", annulla_tutto)]
    ))
    print("🤖 Super-Bot avviato...")
    app.run_polling()

if __name__ == '__main__': main()