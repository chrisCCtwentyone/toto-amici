import os
import json
import logging
from PIL import Image
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# --- CONFIGURAZIONI BASE ---
TOKEN = "8996951565:AAGbxyDm4ZuA_Wntv1Vv_IoxQPS-Hvf7euw"
ADMIN_ID = 173820382  # Il tuo ID di sicurezza

SPREADSHEET_ID = '1q0aaYXl7VYiUzEbttGaoQjNq7ta5wiHD4Qvg5Si7IvE'
SERVICE_ACCOUNT_FILE = 'credenziali.json'

GIOCATORI = [
    "cecilia", "dario", "davide", "fazio", 
    "gaetano", "giacomo", "giovanni", "mario", 
    "michele", "mirko", "nico", "paolo", 
    "pulizzer", "silvio", "villari", "vincenzo"
]

# Stati del flusso di caricamento
SCELTA_GIORNATA, SCELTA_GIOCATORE, CONFERMA = range(3)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- INIZIALIZZAZIONE GEMINI E SHEETS ---
def leggi_chiave_api():
    try:
        with open('chiave_api.txt', 'r') as f:
            chiave = f.read().strip()
            return chiave
    except FileNotFoundError:
        return ""

api_key = leggi_chiave_api()
client = genai.Client(api_key=api_key) if api_key else None

def analizza_schedina_con_gemini(percorso_foto):
    if not client:
        raise Exception("Chiave API di Gemini non trovata in chiave_api.txt")
    
    img = Image.open(percorso_foto)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    img.thumbnail((1000, 1000))
    
    prompt = """
    Sei un assistente esperto nell'analisi di schedine di scommesse sportive. Analizza questa immagine con estrema attenzione.

    1. **VINCITA POTENZIALE ("vincita_potenziale"):**
       - Cerca la dicitura relativa alla vincita totale stimata, vincita massima, o potenziale rimborso in fondo alla schedina.
       - ATTENZIONE A NON CONFONDERE IL MOLTIPLICATORE TOTALE CON GLI EURO: La vincita in euro si calcola quasi sempre moltiplicando la quota totale complessiva per l'importo giocato (che per regolamento è finto a 5€ se non diversamente specificato). 
       - Restituisci SOLO IL VALORE NUMERICO FINALE IN EURO (es. se la vincita è 72,50 €, scrivi "72.50"). Niente simboli di valuta o testo.

    2. **EVENTI DELLA SCHEDINA:**
       Estrai la lista degli eventi dividendola tassativamente in queste 4 categorie: "Combo", "Fisse", "Doppie Chance", "Variabili".
       Per ogni evento fornisci le chiavi esatte: "partita", "pronostico", "quota".
    
    REGOLA FONDAMENTALE PER I PRONOSTICI (NORMALIZZAZIONE):
    1. Esito Finale (Fisse): 1, X, 2
    2. Doppia Chance: 1X, X2, 12
    3. Gol / No Gol (Variabili): GOAL, NOGOAL
    4. Under / Over (Variabili): UNDER_2.5, OVER_2.5, ecc.
    5. Combo: Unisci le giocate con il simbolo "+". Es: 1+OVER_2.5, 1X+GOAL.
    6. Pari / Dispari (Variabili): scrivi ESATTAMENTE "PARI" oppure "DISPARI".
    """
    
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=[prompt, img],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return response.text

def scrivi_su_sheets(nome_giocatore, giornata_num, json_data):
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    sheets_service = build('sheets', 'v4', credentials=creds)
    
    nome_giornata_formattato = f"Giornata {giornata_num}"
    
    dati = json.loads(json_data)
    vincita = dati.get("vincita_potenziale", "0")
    eventi = dati.get("eventi", dati) 
    
    righe_da_inserire = []
    prima_riga = True
    
    for categoria in ["Combo", "Fisse", "Doppie Chance", "Variabili"]:
        for evento in eventi.get(categoria, []):
            riga = [
                nome_giornata_formattato, 
                nome_giocatore.upper(), 
                evento.get("partita", ""), 
                categoria, 
                evento.get("pronostico", ""), 
                str(evento.get("quota", ""))
            ]
            
            if prima_riga:
                riga.append("")
                riga.append(str(vincita))
                prima_riga = False
                
            righe_da_inserire.append(riga)

    if righe_da_inserire:
        body = {'values': righe_da_inserire}
        sheets_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, 
            range="Giocate!A:H",
            valueInputOption="USER_ENTERED", 
            body=body
        ).execute()
        return True
    return False

# --- GESTIONE BOT TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("👋 Ciao Admin! Mandami la foto di una bolletta per caricarla direttamente su Google Sheets.")

async def ricevi_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
        
    photo_file = await update.message.photo[-1].get_file()
    if not os.path.exists("temp_telegram"):
        os.makedirs("temp_telegram")
        
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
            
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📸 Foto ricevuta!\n\n📅 A quale **Giornata** di Serie A si riferisce?", reply_markup=reply_markup, parse_mode='Markdown')
    return SCELTA_GIORNATA

async def scegli_giornata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    giornata = query.data.split('_')[1]
    context.user_data['giornata'] = giornata

    keyboard = []
    riga = []
    for nome in GIOCATORI:
        riga.append(InlineKeyboardButton(nome.capitalize(), callback_data=f"giocatore_{nome}"))
        if len(riga) == 4:
            keyboard.append(riga)
            riga = []
    if riga:
        keyboard.append(riga)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=f"✅ Giornata: {giornata}\n\n👤 Di chi è questa schedina?", reply_markup=reply_markup)
    return SCELTA_GIOCATORE

async def scegli_giocatore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    giocatore = query.data.split('_')[1]
    context.user_data['giocatore'] = giocatore
    giornata = context.user_data['giornata']

    keyboard = [
        [InlineKeyboardButton("✅ Conferma e Analizza", callback_data="conferma_si")],
        [InlineKeyboardButton("❌ Annulla e Riavvia", callback_data="conferma_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    testo_conferma = f"⚠️ **CONTROLLO DATI** ⚠️\n\nVuoi elaborare questa foto come:\n👤 Giocatore: **{giocatore.capitalize()}**\n📅 Giornata: **{giornata}**?"
    await query.edit_message_text(text=testo_conferma, reply_markup=reply_markup, parse_mode='Markdown')
    return CONFERMA

async def esegui_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    scelta = query.data
    giocatore = context.user_data['giocatore']
    giornata = context.user_data['giornata']
    percorso_foto = context.user_data['percorso_foto']

    if scelta == "conferma_no":
        await query.edit_message_text(text="❌ Operazione annullata. Mandami una nuova foto quando vuoi.")
        if os.path.exists(percorso_foto):
            os.remove(percorso_foto)
        return ConversationHandler.END

    if scelta == "conferma_si":
        await query.edit_message_text(text=f"⏳ Analisi in corso per {giocatore.capitalize()} (Giornata {giornata})...\n\n*(Gemini sta leggendo la bolletta...)*")
        
        try:
            risultato_json = analizza_schedina_con_gemini(percorso_foto)
            successo = scrivi_su_sheets(giocatore, giornata, risultato_json)
            
            if successo:
                await query.message.reply_text(f"✅ **Fatto!** Schedina di {giocatore.capitalize()} caricata con successo su Google Sheets per la Giornata {giornata}!", parse_mode='Markdown')
            else:
                await query.message.reply_text("⚠️ Analisi completata, ma c'è stato un problema nella scrittura su Google Sheets.")
                
        except Exception as e:
            await query.message.reply_text(f"❌ Errore durante l'elaborazione: {e}")
            
        if os.path.exists(percorso_foto):
            os.remove(percorso_foto)
            
        return ConversationHandler.END

async def annulla_tutto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operazione annullata.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).job_queue(None).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO, ricevi_foto)],
        states={
            SCELTA_GIORNATA: [CallbackQueryHandler(scegli_giornata, pattern="^giornata_")],
            SCELTA_GIOCATORE: [CallbackQueryHandler(scegli_giocatore, pattern="^giocatore_")],
            CONFERMA: [CallbackQueryHandler(esegui_conferma, pattern="^conferma_")]
        },
        fallbacks=[CommandHandler("cancel", annulla_tutto)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    print("🤖 Bot Telegram Completo avviato! In attesa di foto...")
    app.run_polling()

if __name__ == '__main__':
    main()