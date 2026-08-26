import os
import json
import time
import requests
from PIL import Image
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = '1q0aaYXl7VYiUzEbttGaoQjNq7ta5wiHD4Qvg5Si7IvE'
SERVICE_ACCOUNT_FILE = 'credenziali.json'
FILE_LOG = 'giocate_completate.txt'
FOOTBALL_DATA_KEY = "ef8a4016b5ab4f90a486ea0fea46fd1f"
LIMITI_SCHEDINA = {"Combo": 1, "Fisse": 4, "Doppie Chance": 2, "Variabili": 3}

def leggi_chiave_api():
    try:
        with open('chiave_api.txt', 'r') as f: return f.read().strip()
    except FileNotFoundError: exit()

client = genai.Client(api_key=leggi_chiave_api())
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets'])
sheets_service = build('sheets', 'v4', credentials=creds)

CARTELLA_BASE = "schedine_whatsapp"
scelta = input("Quale giornata vuoi analizzare? (Inserisci solo il numero, es. 1): ")
GIORNATA = f"giornata_{scelta.strip()}"
percorso_giornata = os.path.join(CARTELLA_BASE, GIORNATA)

def raggruppa_foto_giocatori(percorso):
    giocatori = {}
    if not os.path.exists(percorso): return giocatori
    for file in os.listdir(percorso):
        if file.lower().endswith(('.png', '.jpg', '.jpeg')):
            nome = file.split('_')[0].lower().replace('.jpg', '').replace('.jpeg', '').replace('.png', '')
            if nome not in giocatori: giocatori[nome] = []
            giocatori[nome].append(os.path.join(percorso, file))
    return giocatori

def giocatore_gia_elaborato(giocatore):
    if not os.path.exists(FILE_LOG): return False
    with open(FILE_LOG, 'r') as f: return f"{GIORNATA}_{giocatore}" in f.read().splitlines()

def segna_come_elaborato(giocatore):
    with open(FILE_LOG, 'a') as f: f.write(f"{GIORNATA}_{giocatore}\n")

def analizza_schedine(lista_foto):
    immagini_ottimizzate = []
    for foto in lista_foto:
        img = Image.open(foto)
        if img.mode != 'RGB': img = img.convert('RGB')
        img.thumbnail((1000, 1000))
        immagini_ottimizzate.append(img)
    
    prompt = """Analizza schedina. 1. VINCITA POTENZIALE in EURO. 2. EVENTI in: "Combo", "Fisse", "Doppie Chance", "Variabili"."""
    response = client.models.generate_content(model='gemini-3.6-flash', contents=[prompt] + immagini_ottimizzate, config=types.GenerateContentConfig(response_mime_type="application/json"))
    return response.text

# NOVITÀ: Normalizzazione
def normalizza_nomi_partite(dati_json, giornata_num):
    try:
        url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata_num}"
        matches = requests.get(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY}).json().get("matches", [])
        if not matches: return dati_json
        
        dati = json.loads(dati_json)
        for cat in ["Combo", "Fisse", "Doppie Chance", "Variabili"]:
            for ev in dati.get("eventi", dati).get(cat, []):
                if "-" in ev.get("partita", ""):
                    c_sh, o_sh = [s.strip()[:5].lower() for s in ev["partita"].split('-')]
                    for m in matches:
                        ac, ao = str(m["homeTeam"]["name"]).lower(), str(m["awayTeam"]["name"]).lower()
                        sc, so = str(m["homeTeam"].get("shortName","")).lower(), str(m["awayTeam"].get("shortName","")).lower()
                        if (c_sh in ac or c_sh in sc) and (o_sh in ao or o_sh in so):
                            ev["partita"] = f"{m['homeTeam'].get('shortName', m['homeTeam']['name'])} - {m['awayTeam'].get('shortName', m['awayTeam']['name'])}"
                            break
        return json.dumps(dati)
    except: return dati_json

def scrivi_su_sheets_con_regole(nome_giocatore, json_data):
    try:
        dati = json.loads(json_data)
        v_raw = str(dati.get("vincita_potenziale", "0")).replace(',', '.')
        vincita = f"{float(v_raw):.2f}".replace('.', ',') if v_raw != "0" else "0,00"

        righe = []
        prima = True
        
        for cat in ["Combo", "Fisse", "Doppie Chance", "Variabili"]:
            for idx, ev in enumerate(dati.get("eventi", dati).get(cat, [])):
                pron = str(ev.get("pronostico", "")).upper().replace("1.5", "2.5").replace("3.5", "2.5")
                if idx >= LIMITI_SCHEDINA[cat]: pron += " (ANNULLATA ECCESSO)"
                q_raw = str(ev.get("quota", "")).replace('.', ',')
                
                riga = [GIORNATA.replace('_', ' ').title(), nome_giocatore.upper(), ev.get("partita", ""), cat, pron, q_raw]
                if prima: riga.extend(["", vincita]); prima = False
                righe.append(riga)

        if righe:
            sheets_service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range="Giocate!A:I", valueInputOption="USER_ENTERED", body={'values': righe}).execute()
            return True
    except: pass
    return False

def main():
    print(f"\n--- Avvio: {GIORNATA.upper()} ---")
    foto_per_giocatore = raggruppa_foto_giocatori(percorso_giornata)
    for giocatore, lista_foto in foto_per_giocatore.items():
        if giocatore_gia_elaborato(giocatore): continue
        for _ in range(3):
            try:
                risultato_json = analizza_schedine(lista_foto)
                # CHIAMATA AL NORMALIZZATORE
                risultato_json = normalizza_nomi_partite(risultato_json, scelta.strip())
                if scrivi_su_sheets_con_regole(giocatore, risultato_json): segna_come_elaborato(giocatore)
                break 
            except: time.sleep(10)
if __name__ == "__main__": main()