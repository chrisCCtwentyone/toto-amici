#!/usr/bin/env python3
"""Sola lettura: scarica Giocate, Classifica e Cassa da Sheets (scope readonly) e
tutte le partite di Serie A da Football-Data (UNA chiamata) in un JSON per
scripts/verifica_punteggi_indipendente.py. Uso: python3 scripts/scarica_dati_verifica.py dati.json"""
import os, sys, json
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, R); os.chdir(R)
from scripts.dry_run_non_regressione import carica_env
carica_env()
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests
cred=service_account.Credentials.from_service_account_file('credenziali.json',scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
svc=build('sheets','v4',credentials=cred)
SID=os.environ['SPREADSHEET_ID']
out={}
for nome,rng in [('giocate','Giocate!A:I'),('classifica','Classifica'),('cassa','Cassa!A:D')]:
    out[nome]=svc.spreadsheets().values().get(spreadsheetId=SID,range=rng).execute(num_retries=3).get('values',[])
r=requests.get('https://api.football-data.org/v4/competitions/SA/matches',headers={'X-Auth-Token':os.environ['FOOTBALL_DATA_KEY']},timeout=30)
r.raise_for_status(); out['matches']=r.json()['matches']
json.dump(out,open(sys.argv[1],'w'))
print(len(out['giocate']),'righe giocate,',len(out['matches']),'partite')
