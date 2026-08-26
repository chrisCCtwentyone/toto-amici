import os
import re
import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- SETUP CREDENZIALI E API ---
SPREADSHEET_ID = '1q0aaYXl7VYiUzEbttGaoQjNq7ta5wiHD4Qvg5Si7IvE'
SERVICE_ACCOUNT_FILE = 'credenziali.json'
FOOTBALL_DATA_KEY = "ef8a4016b5ab4f90a486ea0fea46fd1f"

def connetti_sheets():
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

def scarica_giornata_footballdata(giornata):
    url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    try:
        risposta = requests.get(url, headers=headers)
        if risposta.status_code == 200:
            return risposta.json()
        return None
    except Exception as e:
        print(f"Errore di connessione API: {e}")
        return None

def controlla_esito(pronostico, gol_casa, gol_ospite):
    # Controllo se la partita è stata annullata dal bot per eccesso limiti
    if "ANNULLATA" in pronostico: return "➖ ANNULLATA"

    tot_gol = gol_casa + gol_ospite
    segno = "1" if gol_casa > gol_ospite else ("2" if gol_ospite > gol_casa else "X")
    entrambe_segnano = "GOAL" if (gol_casa > 0 and gol_ospite > 0) else "NOGOAL"
    
    vinta = True
    parti = pronostico.split('+') 
    
    for p in parti:
        p = p.strip()
        if p in ["1", "X", "2"] and p != segno: vinta = False
        elif p == "1X" and segno not in ["1", "X"]: vinta = False
        elif p == "X2" and segno not in ["X", "2"]: vinta = False
        elif p == "12" and segno not in ["1", "2"]: vinta = False
        elif p == "GOAL" and entrambe_segnano != "GOAL": vinta = False
        elif p == "NOGOAL" and entrambe_segnano != "NOGOAL": vinta = False
        elif p == "PARI" and (tot_gol % 2) != 0: vinta = False
        elif p == "DISPARI" and (tot_gol % 2) == 0: vinta = False
        elif "UNDER" in p or "OVER" in p:
            try:
                valore = float(p.split('_')[1])
                if "UNDER" in p and tot_gol > valore: vinta = False
                if "OVER" in p and tot_gol < valore: vinta = False
            except:
                pass
            
    return "✅ VINTA" if vinta else "❌ PERSA"

def calcola_punteggio_partita(pronostico, quota):
    if "ANNULLATA" in pronostico: return 0

    punti = 0
    if "+" in pronostico: punti = 6
    elif pronostico in ["1", "X", "2"]: punti = 4
    elif pronostico in ["1X", "X2", "12"]: punti = 1
    else: punti = 2
        
    if quota >= 3.50:
        punti = punti * 2
        
    return punti

def estrai_numero(testo):
    try:
        if not testo: return 0.0
        testo = str(testo).replace(',', '.')
        match = re.search(r'\d+(?:\.\d+)?', testo)
        if match:
            return float(match.group())
        return 0.0
    except:
        return 0.0

def main():
    print("--- ⚽ CALCOLO ESITI, CLASSIFICA E CASSA TOTO-AMICI ⚽ ---")
    giornata_input = input("Inserisci il numero della giornata da controllare (es. 1): ").strip()
    
    dati_api = scarica_giornata_footballdata(giornata_input)
    if not dati_api or "matches" not in dati_api:
        print("Errore download API.")
        return
    matches_api = dati_api["matches"]
    
    service = connetti_sheets()
    
    # 1. LETTURA GIOCATE
    result_giocate = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Giocate!A:I").execute()
    righe_giocate = result_giocate.get('values', [])
    
    classifica = {}
    aggiornamenti_testo = []
    richieste_stile = []
    colore_verde = {"red": 0.85, "green": 0.95, "blue": 0.85}
    colore_rosso = {"red": 0.95, "green": 0.85, "blue": 0.85}
    colore_grigio = {"red": 0.90, "green": 0.90, "blue": 0.90}

    sheet_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheet_id_giocate = next(s['properties']['sheetId'] for s in sheet_metadata.get('sheets', []) if s['properties']['title'].lower() == 'giocate')

    print("\n-> Analisi delle giocate e assegnazione Punti Partita...")
    for index, riga in enumerate(righe_giocate):
        numero_riga = index + 1
        if len(riga) < 6 or str(riga[1]).strip().lower() == "giocatore": continue
        if f"giornata {giornata_input}" not in str(riga[0]).lower(): continue
            
        giocatore = str(riga[1]).strip()
        partita_sheet = str(riga[2]).strip()
        pronostico = str(riga[4]).strip().upper()
        quota = estrai_numero(riga[5])
        vincita_letta = estrai_numero(riga[7]) if len(riga) > 7 else 0.0

        if giocatore not in classifica:
            classifica[giocatore] = {"punti_giornata": 0, "vinte": 0, "perse": 0, "in_corso": 0, "vincita_potenziale": 0.0}
        
        if vincita_letta > 0:
            classifica[giocatore]["vincita_potenziale"] = vincita_letta

        casa_sheet, ospite_sheet = [s.strip()[:5] for s in partita_sheet.lower().split('-')]
        
        match_trovato = next((m for m in matches_api if 
            (casa_sheet in str(m["homeTeam"]["name"]).lower() or casa_sheet in str(m["homeTeam"].get("shortName", "")).lower()) and 
            (ospite_sheet in str(m["awayTeam"]["name"]).lower() or ospite_sheet in str(m["awayTeam"].get("shortName", "")).lower())), None)
        
        punti_partita_singola = 0

        if match_trovato:
            status = match_trovato["status"] 
            if status != "FINISHED":
                testo_esito, colore_scelto = "⏳ IN CORSO", colore_grigio
                classifica[giocatore]["in_corso"] += 1
            else:
                gol_casa, gol_ospite = match_trovato["score"]["fullTime"]["home"], match_trovato["score"]["fullTime"]["away"]
                testo_esito = controlla_esito(pronostico, gol_casa, gol_ospite)
                if "VINTA" in testo_esito:
                    colore_scelto = colore_verde
                    punti_partita_singola = calcola_punteggio_partita(pronostico, quota)
                    classifica[giocatore]["punti_giornata"] += punti_partita_singola
                    classifica[giocatore]["vinte"] += 1
                elif "ANNULLATA" in testo_esito:
                    colore_scelto = colore_grigio
                else:
                    colore_scelto = colore_rosso
                    classifica[giocatore]["perse"] += 1
            
            aggiornamenti_testo.append({'range': f"Giocate!G{numero_riga}", 'values': [[testo_esito]]})
            aggiornamenti_testo.append({'range': f"Giocate!I{numero_riga}", 'values': [[punti_partita_singola]]})
            
            richieste_stile.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id_giocate, "startRowIndex": numero_riga-1, "endRowIndex": numero_riga, "startColumnIndex": 6, "endColumnIndex": 7},
                    "cell": {"userEnteredFormat": {"backgroundColor": colore_scelto}},
                    "fields": "userEnteredFormat.backgroundColor"
                }
            })

    if aggiornamenti_testo:
        service.spreadsheets().values().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={'valueInputOption': 'USER_ENTERED', 'data': aggiornamenti_testo}).execute()
        service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": richieste_stile}).execute()

    # --- VERIFICA VINCITORI E REPORT WHATSAPP ---
    print("\n=======================================")
    print(f"📱 REPORT WHATSAPP - GIORNATA {giornata_input}")
    print("=======================================\n")
    
    totale_fondo_cassa = 0.0
    vincitori = []

    for gio, dati in classifica.items():
        if (dati["vinte"] + dati["perse"] + dati["in_corso"]) == 0: continue
        
        bonus_completamento = ""
        vincita_euro = 0.0
        
        if dati["perse"] > 0:
            stato_schedina = "❌ Schedina Bruciata"
        elif dati["in_corso"] > 0:
            stato_schedina = f"⏳ In attesa di {dati['in_corso']} partite"
        elif dati["perse"] == 0 and dati["in_corso"] == 0 and dati["vinte"] > 0: 
            stato_schedina = "🏆 SCHEDINA CHIUSA! 🏆"
            dati["punti_giornata"] += 10
            bonus_completamento = " (+10 Punti Bonus!)"
            vincita_euro = dati["vincita_potenziale"] / 2.0
            
            if vincita_euro > 0:
                totale_fondo_cassa += vincita_euro
                vincitori.append({"nome": gio, "importo": vincita_euro})

        print(f"👤 *{gio.upper()}*")
        print(f"📊 Punti Giornata: {dati['punti_giornata']}{bonus_completamento}")
        print(f"📝 Esito: {dati['vinte']} Vinte | {dati['perse']} Perse | {dati['in_corso']} In Corso")
        print(f"🎯 Status: {stato_schedina}")
        if vincita_euro > 0:
            print(f"💶 Vincita incassata: +{vincita_euro:.2f} €")
            print(f"🏦 Al Fondo Cassa: +{vincita_euro:.2f} €")
        print("-" * 30)

    # --- 2. AGGIORNAMENTO CLASSIFICA ---
    print("\n-> Aggiornamento foglio Classifica...")
    res_class = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Classifica!A:Z").execute()
    righe_class = res_class.get('values', [])
    
    if not righe_class: righe_class = [["Giocatore", "Punti Totali"]]
    
    headers_class = righe_class[0]
    colonna_giornata = f"Giornata {giornata_input}"
    if colonna_giornata not in headers_class:
        headers_class.append(colonna_giornata)
    idx_giornata = headers_class.index(colonna_giornata)
    
    for r in righe_class:
        while len(r) < len(headers_class): r.append("")
        
    mappa_giocatori = {str(r[0]).strip().lower(): i for i, r in enumerate(righe_class) if i > 0}
    
    for gio, dati in classifica.items():
        gio_low = gio.lower()
        if gio_low not in mappa_giocatori:
            righe_class.append([gio.upper(), 0] + [""] * (len(headers_class) - 2))
            mappa_giocatori[gio_low] = len(righe_class) - 1
            
        riga_idx = mappa_giocatori[gio_low]
        righe_class[riga_idx][idx_giornata] = dati['punti_giornata']
        
        totale = 0
        for i in range(2, len(headers_class)):
            val = str(righe_class[riga_idx][i]).strip()
            if val.isdigit(): totale += int(val)
        righe_class[riga_idx][1] = totale

    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range="Classifica!A1",
        valueInputOption="USER_ENTERED", body={"values": righe_class}
    ).execute()
    print("✨ Classifica aggiornata!")

    # --- 3. AGGIORNAMENTO CASSA ---
    if vincitori:
        print("-> Aggiornamento foglio Cassa (Montepremi)...")
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
            
            gia_registrato = False
            for r in righe_cassa:
                if len(r) > 1 and r[0] == f"Giornata {giornata_input}" and r[1] == descrizione:
                    gia_registrato = True
                    break
                    
            if not gia_registrato:
                saldo_attuale += v["importo"]
                nuova_riga = [
                    f"Giornata {giornata_input}",
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
            print("✨ Cassa aggiornata!")
        else:
            print("✨ I vincitori erano già stati registrati in Cassa in precedenza.")

if __name__ == "__main__":
    main()