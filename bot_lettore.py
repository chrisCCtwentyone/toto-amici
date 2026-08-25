import os
import json
import time
from PIL import Image
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- SETUP CREDENZIALI ---
SPREADSHEET_ID = '1q0aaYXl7VYiUzEbttGaoQjNq7ta5wiHD4Qvg5Si7IvE'
SERVICE_ACCOUNT_FILE = 'credenziali.json'
FILE_LOG = 'giocate_completate.txt'

def leggi_chiave_api():
    try:
        with open('chiave_api.txt', 'r') as f:
            chiave = f.read().strip()
            if not chiave:
                print("ERRORE: Il file 'chiave_api.txt' è vuoto.")
                exit()
            return chiave
    except FileNotFoundError:
        print("ERRORE: Non trovo il file 'chiave_api.txt'.")
        exit()

client = genai.Client(api_key=leggi_chiave_api())

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
sheets_service = build('sheets', 'v4', credentials=creds)

CARTELLA_BASE = "schedine_whatsapp"

scelta = input("Quale giornata vuoi analizzare? (Inserisci solo il numero, es. 1): ")
GIORNATA = f"giornata_{scelta.strip()}"
percorso_giornata = os.path.join(CARTELLA_BASE, GIORNATA)

def raggruppa_foto_giocatori(percorso):
    giocatori = {}
    if not os.path.exists(percorso):
        print(f"Errore: La cartella {percorso} non esiste.")
        return giocatori
    for file in os.listdir(percorso):
        if file.lower().endswith(('.png', '.jpg', '.jpeg')):
            nome = file.split('_')[0].lower().replace('.jpg', '').replace('.jpeg', '').replace('.png', '')
            if nome not in giocatori:
                giocatori[nome] = []
            giocatori[nome].append(os.path.join(percorso, file))
    return giocatori

def giocatore_gia_elaborato(giocatore):
    if not os.path.exists(FILE_LOG):
        return False
    with open(FILE_LOG, 'r') as f:
        elaborati = f.read().splitlines()
    return f"{GIORNATA}_{giocatore}" in elaborati

def segna_come_elaborato(giocatore):
    with open(FILE_LOG, 'a') as f:
        f.write(f"{GIORNATA}_{giocatore}\n")

def analizza_schedine(lista_foto):
    print("   -> [DEBUG] Preparo e comprimo le foto...")
    immagini_ottimizzate = []
    for foto in lista_foto:
        img = Image.open(foto)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.thumbnail((1000, 1000))
        immagini_ottimizzate.append(img)
    
    print("   -> [DEBUG] Invio a Gemini (modello: gemini-3.6-flash)...")
    
    prompt = """
    Analizza queste schedine di calcio ed estrai due cose fondamentali:
    1. Una chiave globale "vincita_potenziale" contenente SOLO LA CIFRA NUMERICA (in euro) scritta in fondo alla schedina. Se leggi "Vincita: 142,50 €", devi scrivere SOLO "142.50". Niente testo. Se non c'è, scrivi "0".
    2. La lista degli eventi, classificata in: "Combo", "Fisse", "Doppie Chance", "Variabili".
    
    Per ogni evento fornisci le chiavi: "partita", "pronostico", "quota".
    
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
        contents=[prompt] + immagini_ottimizzate,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    
    print("   -> [DEBUG] Dati estratti con successo!")
    return response.text

def scrivi_su_sheets(nome_giocatore, json_data):
    print("   -> [DEBUG] Scrittura su Google Sheets in corso...")
    try:
        dati = json.loads(json_data)
        vincita = dati.get("vincita_potenziale", "0")
        eventi = dati.get("eventi", dati) 
        
        righe_da_inserire = []
        prima_riga = True
        
        for categoria in ["Combo", "Fisse", "Doppie Chance", "Variabili"]:
            for evento in eventi.get(categoria, []):
                riga = [
                    GIORNATA.replace('_', ' ').title(), 
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
            print(f"--> SUCCESSO! Inserite {len(righe_da_inserire)} righe per {nome_giocatore.upper()} (Vincita: {vincita})!")
            return True
    except Exception as e:
        print(f"Errore durante la scrittura: {e}")
    return False

def main():
    print(f"\n--- Avvio Lettura Toto-Amici: {GIORNATA.upper()} ---")
    foto_per_giocatore = raggruppa_foto_giocatori(percorso_giornata)
    if not foto_per_giocatore: return

    for giocatore, lista_foto in foto_per_giocatore.items():
        if giocatore_gia_elaborato(giocatore):
            print(f"[SKIP] {giocatore.upper()} è già stato elaborato. Salto!")
            continue

        print(f"\nAnalizzo le giocate di: {giocatore.upper()}...")
        for tentativo in range(3):
            try:
                risultato_json = analizza_schedine(lista_foto)
                successo = scrivi_su_sheets(giocatore, risultato_json)
                if successo: segna_come_elaborato(giocatore)
                break 
            except Exception as e:
                print(f"   -> [ERRORE]: {e}. Ritento tra 10 sec...")
                time.sleep(10)
        time.sleep(3)

if __name__ == "__main__":
    main()