import requests
import json

url = "https://v3.football.api-sports.io/fixtures"
headers = {"x-apisports-key": "987e3070a8fd4bd45c9e3961e6f54b62"}
querystring = {"league": 135, "season": 2026}

print("Richiedo i dati a API-Football...")
risposta = requests.get(url, headers=headers, params=querystring)
print(json.dumps(risposta.json(), indent=4))