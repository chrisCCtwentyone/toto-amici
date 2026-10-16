#!/usr/bin/env python3
"""
Prova di QUALITA' della lettura delle schedine. Non scrive niente su Sheets.

PERCHE' ESISTE
--------------
La quota gratuita Gemini finisce presto (16/10/2026). Due rimedi possibili:
foto piu' piccole / media_resolution piu' bassa (meno token per foto) e il
piano B Cloudflare Workers AI. Nessuno dei due va acceso "a fede": questo script
rilegge le foto VERE di una giornata gia' caricata e le confronta con le righe
che stanno nel foglio Giocate (la verita'), dicendo quanti pronostici e quote
vengono letti esattamente.

DOVE PRENDE I DATI
------------------
- foto: schedine_whatsapp/giornata_N/<giocatore>_<k>.jpeg (piu' foto dello
  stesso giocatore = una sola schedina, lette insieme come fa il bot);
- verita': righe della giornata N del foglio Giocate (SOLA LETTURA);
- partite: Football-Data, UNA sola chiamata.
Serve il .env (come scripts/dry_run_non_regressione.py) + credenziali.json.
Per --lettore cloudflare servono anche CLOUDFLARE_AI_TOKEN e CLOUDFLARE_ACCOUNT_ID.

ESEMPI (ogni comando e' UNA configurazione, ognuno consuma quota!)
------------------------------------------------------------------
    # Gemini com'e' oggi (1000 px, media_resolution di default)
    python3 scripts/prova_qualita_lettura.py --lettore gemini --dimensione 1000 --media-resolution nessuna --n 5
    # Gemini ridotto
    python3 scripts/prova_qualita_lettura.py --lettore gemini --dimensione 700 --media-resolution low --n 5
    # Cloudflare (primo modello della catena)
    python3 scripts/prova_qualita_lettura.py --lettore cloudflare --n 5
"""
import argparse
import json
import os
import re
import sys
import time

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RADICE)


def carica_env():
    """Legge il .env come farebbe Render con le variabili d'ambiente."""
    percorso = os.path.join(RADICE, ".env")
    if not os.path.exists(percorso):
        return
    for riga in open(percorso):
        riga = riga.strip()
        if riga and "=" in riga and not riga.startswith("#"):
            chiave, valore = riga.split("=", 1)
            os.environ.setdefault(chiave, valore.strip().strip('"').strip("'"))


def leggi_argomenti(argv=None):
    p = argparse.ArgumentParser(
        description="Confronta la lettura IA delle foto vere con le righe di Giocate. Non scrive su Sheets.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog="ESEMPI" + __doc__.split("ESEMPI")[1])
    p.add_argument("--lettore", choices=("gemini", "cloudflare"), required=True)
    p.add_argument("--giornata", type=int, default=1, help="giornata di riferimento (default 1)")
    p.add_argument("--n", type=int, default=5, help="quante schedine (giocatori) leggere, default 5")
    p.add_argument("--giocatori", default="", help="elenco separato da virgole (es. cecilia,dario) invece dei primi N")
    p.add_argument("--dimensione", type=int, default=1000, help="lato massimo delle foto in px (default 1000)")
    p.add_argument("--media-resolution", default="nessuna", choices=("nessuna", "low", "medium", "high"),
                   help="solo Gemini: media_resolution (nessuna = non passata, come oggi)")
    p.add_argument("--modello", default="", help="gemini: restringe la catena a quel solo modello; cloudflare: id del modello @cf/...")
    p.add_argument("--pausa", type=float, default=5.0, help="secondi di pausa fra le chiamate (default 5)")
    p.add_argument("--cartella", default="", help="cartella foto (default schedine_whatsapp/giornata_N)")
    return p.parse_args(argv)


def raggruppa_foto(cartella):
    """{giocatore: [percorsi ordinati]} dal nome file 'cecilia_1.jpeg'."""
    gruppi = {}
    for nome in sorted(os.listdir(cartella)):
        m = re.match(r"^(.+?)_(\d+)\.(?:jpe?g|png)$", nome, re.IGNORECASE)
        if m:
            gruppi.setdefault(m.group(1).lower(), []).append(os.path.join(cartella, nome))
    return gruppi


def tolleranza_uguali(a, b, tol=0.01):
    return abs(a - b) <= tol


def confronta(letti, verita, partite, abbina, normalizza, numero):
    """Confronta gli eventi letti con quelli veri. Entrambi: liste di dict
    {partita, pronostico, quota}. Restituisce un dict di conteggi.

    L'abbinamento e' per partita UNICA (statistiche.abbina_partita sulle partite
    ufficiali della giornata); fra piu' eventi della stessa partita si preferisce
    quello con lo stesso pronostico. Veri senza lettura = mancanti; letti senza
    corrispondente = inventati."""
    def chiave(e):
        m = abbina(e.get("partita", ""), partite)
        return m["id"] if m else "?" + re.sub(r"\W", "", str(e.get("partita", "")).lower())

    liberi = [(chiave(e), e) for e in letti]
    esatti = quote_esatte = categorie_esatte = mancanti = 0
    for v in verita:
        k = chiave(v)
        candidati = [i for i, (kk, _) in enumerate(liberi) if kk == k]
        if not candidati:
            mancanti += 1
            continue
        pv = normalizza(v["pronostico"])
        scelto = next((i for i in candidati if normalizza(liberi[i][1].get("pronostico", "")) == pv), candidati[0])
        letto = liberi.pop(scelto)[1]
        if normalizza(letto.get("pronostico", "")) == pv:
            esatti += 1
        if tolleranza_uguali(numero(letto.get("quota", "")), numero(v["quota"])):
            quote_esatte += 1
        # Categoria (Tipologia) cosi' come la dava il lettore, prima della riclassifica del bot.
        if str(letto.get("categoria", "")).strip().lower() == str(v.get("categoria", "")).strip().lower():
            categorie_esatte += 1
    return {"veri": len(verita), "letti": len(letti), "esatti": esatti,
            "quote_esatte": quote_esatte, "categorie_esatte": categorie_esatte, "mancanti": mancanti, "inventati": len(liberi)}


def righe_vere(griglia, giornata, giocatore, riga_e_della_giornata):
    """Eventi veri di un giocatore + vincita potenziale, da Giocate!A:I."""
    eventi, vincita = [], None
    for r in griglia:
        if len(r) < 6 or not riga_e_della_giornata(r[0], giornata) or str(r[1]).strip().upper() != giocatore.upper():
            continue
        eventi.append({"partita": r[2], "categoria": r[3],
                       "pronostico": re.sub(r"\s*\(ANNULLATA ECCESSO\)", "", str(r[4])).strip(), "quota": r[5]})
        if vincita is None and len(r) > 7 and str(r[7]).strip():
            vincita = r[7]
    return eventi, vincita


def tabella(titolo, risultati, errori, tempi, token):
    veri = sum(r["veri"] for r in risultati)
    pc = lambda x: f"{100 * x / veri:.0f}%" if veri else "n/d"
    es, qe = sum(r["esatti"] for r in risultati), sum(r["quote_esatte"] for r in risultati)
    print("\n" + "=" * 70)
    print(f"  {titolo}")
    print("=" * 70)
    print(f"  schedine lette:         {len(risultati)}   (errori: {errori})")
    print(f"  eventi veri / letti:    {veri} / {sum(r['letti'] for r in risultati)}")
    print(f"  pronostici esatti:      {es}/{veri}  = {pc(es)}")
    print(f"  quote esatte:           {qe}/{veri}  = {pc(qe)}")
    ce = sum(r["categorie_esatte"] for r in risultati)
    print(f"  categorie esatte:       {ce}/{veri}  = {pc(ce)}  (come le dava il lettore; il bot poi le riclassifica)")
    print(f"  eventi mancanti:        {sum(r['mancanti'] for r in risultati)}")
    print(f"  eventi inventati:       {sum(r['inventati'] for r in risultati)}")
    print(f"  vincita potenziale ok:  {sum(1 for r in risultati if r.get('vincita_ok'))}/{len(risultati)}")
    print(f"  tempo medio:            {sum(tempi) / len(tempi):.1f}s" if tempi else "  tempo medio:            n/d")
    tk = [t for t in token if t]
    if tk:
        print(f"  token in ingresso medi: {sum(tk) / len(tk):.0f}")
    print("=" * 70 + "\n")


def main(argv=None):
    a = leggi_argomenti(argv)
    carica_env()
    cartella = a.cartella or os.path.join(RADICE, "schedine_whatsapp", f"giornata_{a.giornata}")
    if not os.path.isdir(cartella):
        sys.exit(f"ERRORE: cartella foto non trovata: {cartella}")
    gruppi = raggruppa_foto(cartella)
    scelti = [g.strip().lower() for g in a.giocatori.split(",") if g.strip()] or list(gruppi)[:a.n]
    scelti = [g for g in scelti if g in gruppi]
    if not scelti:
        sys.exit("ERRORE: nessuna foto trovata per i giocatori richiesti.")

    import bot_telegram as bt
    from google.genai import types
    from statistiche import abbina_partita, estrai_numero

    if a.lettore == "cloudflare" and not (os.environ.get("CLOUDFLARE_AI_TOKEN") and os.environ.get("CLOUDFLARE_ACCOUNT_ID")):
        sys.exit("ERRORE: per --lettore cloudflare servono CLOUDFLARE_AI_TOKEN e CLOUDFLARE_ACCOUNT_ID (nel .env o nell'ambiente).")
    if a.lettore == "gemini" and not bt.leggi_chiave_api():
        sys.exit("ERRORE: chiave Gemini non configurata.")

    mr = None
    if a.lettore == "gemini":
        mr = (types.MediaResolution.MEDIA_RESOLUTION_UNSPECIFIED if a.media_resolution == "nessuna"
              else bt.media_resolution_da_nome(a.media_resolution))
    dim = (a.dimensione, a.dimensione)
    titolo = (f"{a.lettore}  dimensione={a.dimensione}px  " +
              (f"media_resolution={a.media_resolution}  modello={a.modello or 'catena'}" if a.lettore == "gemini"
               else f"modello={a.modello or bt.MODELLI_CLOUDFLARE_AI[0][0]}"))

    print(f"\nConfigurazione: {titolo}")
    print(f"Schedine da leggere: {len(scelti)} ({', '.join(scelti)}), {sum(len(gruppi[g]) for g in scelti)} foto")
    extra = " (di piu' se la catena Gemini ritenta o cambia modello)" if a.lettore == "gemini" else ""
    print(f"Chiamate che faro': {len(scelti)} al lettore ({a.lettore}){extra}, "
          f"1 a Football-Data, 1 lettura (sola lettura) di Google Sheets. Pausa {a.pausa:.0f}s fra le chiamate.\n")

    griglia = bt.connetti_sheets().spreadsheets().values().get(
        spreadsheetId=bt.SPREADSHEET_ID, range="Giocate!A:I").execute(num_retries=3).get("values", [])
    partite = bt.richiedi_con_retry(
        f"https://api.football-data.org/v4/competitions/SA/matches?matchday={a.giornata}",
        headers={"X-Auth-Token": bt.FOOTBALL_DATA_KEY}).json().get("matches", [])

    risultati, tempi, token, errori = [], [], [], 0
    for i, g in enumerate(scelti):
        if i:
            time.sleep(a.pausa)
        veri, vincita_vera = righe_vere(griglia, a.giornata, g, bt.riga_e_della_giornata)
        if not veri:
            print(f"- {g}: nessuna riga in Giocate per la giornata {a.giornata}, salto")
            continue
        inizio = time.time()
        try:
            imgs = bt.prepara_foto(gruppi[g], dim)
            if a.lettore == "gemini":
                testo = bt.leggi_con_gemini(bt.get_gemini_client(), imgs, media_resolution=mr,
                                            modelli=(a.modello,) if a.modello else None)
                modello_usato = bt.ultima_lettura_ia["modello"]
                token.append(bt.ultima_lettura_ia.get("token_ingresso"))
            else:
                modello = a.modello or bt.MODELLI_CLOUDFLARE_AI[0][0]
                formato = dict(bt.MODELLI_CLOUDFLARE_AI).get(modello, "response_format")
                testo, modello_usato = bt.leggi_con_cloudflare(bt.PROMPT_LETTURA_SCHEDINA, imgs, modelli=((modello, formato),))
            dati = json.loads(testo)
            ev = bt.estrai_eventi_per_categoria(dati)
            letti = [dict(e, categoria=c) for c in bt.CATEGORIE_SCHEDINA for e in ev[c]]
        except Exception as e:
            errori += 1
            print(f"- {g}: ERRORE {type(e).__name__}: {str(e)[:200]}")
            continue
        secondi = time.time() - inizio
        tempi.append(secondi)
        r = confronta(letti, veri, partite, abbina_partita, bt.normalizza_pronostico, estrai_numero)
        r["vincita_ok"] = vincita_vera is not None and tolleranza_uguali(
            estrai_numero(dati.get("vincita_potenziale", "0")), estrai_numero(vincita_vera))
        risultati.append(r)
        print(f"- {g}: {r['esatti']}/{r['veri']} pronostici, {r['quote_esatte']}/{r['veri']} quote, {r['categorie_esatte']}/{r['veri']} categorie, "
              f"mancanti {r['mancanti']}, inventati {r['inventati']}, vincita {'ok' if r['vincita_ok'] else 'DIVERSA'}, "
              f"{secondi:.1f}s [{modello_usato}]")

    tabella(titolo, risultati, errori, tempi, token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
