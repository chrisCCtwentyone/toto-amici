import streamlit as st
import pandas as pd
import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- CONFIGURAZIONE PAGINA STREAMLIT ---
st.set_page_config(page_title="Toto-Amici 2026", page_icon="⚽", layout="wide")

# --- INIEZIONE CSS PER NASCONDERE ELEMENTI DI STREAMLIT ---
st.markdown("""
    <style>
    header {visibility: hidden !important;}
    #MainMenu {visibility: hidden !important;}
    a.header-anchor {display: none !important;}
    h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {display: none !important;}
    .block-container {padding-top: 1rem !important;}
    </style>
    """, unsafe_allow_html=True)

# --- COSTANTI E CHIAVI (BLINDATE) ---
try:
    SPREADSHEET_ID = st.secrets["SPREADSHEET_ID"]
    FOOTBALL_DATA_KEY = st.secrets["FOOTBALL_DATA_KEY"]
except KeyError:
    st.error("⚠️ Chiavi segrete mancanti! Configurale su Streamlit Cloud nei Secrets.")
    st.stop()

OBIETTIVO_CASSA = 3200.0 # Il vostro traguardo per coprire i premi

# --- FUNZIONI DI CARICAMENTO DATI ---
@st.cache_data(ttl=60)
def carica_dati_da_sheets(range_name):
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], 
            scopes=SCOPES
        )
        service = build('sheets', 'v4', credentials=creds)
        
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        values = result.get('values', [])
        
        if not values: return pd.DataFrame()
            
        headers = values[0]
        data = values[1:]
        
        dati_allineati = [riga + [""] * (len(headers) - len(riga)) for riga in data]
        return pd.DataFrame(dati_allineati, columns=headers)
    except Exception as e:
        st.error(f"Errore di caricamento dati: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def scarica_risultati_api(giornata):
    """Chiama le API per ottenere i risultati in tempo reale e i nomi ufficiali della giornata."""
    url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    partite_ufficiali = []
    risultati_mappati = {}
    
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            matches = res.json().get("matches", [])
            for m in matches:
                casa_full = m["homeTeam"]["name"]
                ospite_full = m["awayTeam"]["name"]
                nome_ufficiale = f"{casa_full} - {ospite_full}"
                partite_ufficiali.append((casa_full, ospite_full, nome_ufficiale))
                
                status = m["status"]
                if status in ["FINISHED", "IN_PLAY", "PAUSED"]:
                    h_score = m["score"]["fullTime"]["home"] if m["score"]["fullTime"]["home"] is not None else 0
                    a_score = m["score"]["fullTime"]["away"] if m["score"]["fullTime"]["away"] is not None else 0
                    score_str = f"{h_score} - {a_score}" if status == "FINISHED" else f"{h_score} - {a_score} (In Corso)"
                elif status in ["TIMED", "SCHEDULED"]:
                    score_str = "Da giocare"
                else:
                    score_str = "Rinviata/Altro"
                    
                risultati_mappati[nome_ufficiale] = score_str
    except:
        pass
        
    return partite_ufficiali, risultati_mappati

def normalizza_nome_squadra(squadra_raw, lista_ufficiali):
    """Trova la squadra ufficiale corrispondente ignorando acronimi superflui come FC, Calcio, AC, ecc."""
    squadra_clean = squadra_raw.lower()
    for uff in lista_ufficiali:
        uff_clean = uff.lower()
        parole_uff = set(uff_clean.split()) - {"fc", "calcio", "ac", "as", "ss", "cd", "bologna", "inter", "milan"}
        parole_raw = set(squadra_clean.split()) - {"fc", "calcio", "ac", "as", "ss", "cd"}
        
        if uff_clean in squadra_clean or squadra_clean in uff_clean:
            return uff
        if parole_uff & parole_raw:
            return uff
    return squadra_raw.title()

def normalizza_partita_completa(partita_sheet, partite_ufficiali):
    """Prende la stringa dello Sheet e la mappa esattamente sulla partita ufficiale della Serie A."""
    if "-" not in partita_sheet:
        return partita_sheet
    
    parti = partita_sheet.split("-")
    if len(parti) != 2:
        return partita_sheet
        
    casa_raw, ospite_raw = parti[0].strip(), parti[1].strip()
    
    case_ufficiali = [p[0] for p in partite_ufficiali]
    ospiti_ufficiali = [p[1] for p in partite_ufficiali]
    
    casa_norm = normalizza_nome_squadra(casa_raw, case_ufficiali)
    ospite_norm = normalizza_nome_squadra(ospite_raw, ospiti_ufficiali)
    
    return f"{casa_norm} - {ospite_norm}"

# --- CARICAMENTO DATI FOGLI ---
df_classifica = carica_dati_da_sheets("Classifica!A:Z")
df_cassa = carica_dati_da_sheets("Cassa!A:D")
df_giocate = carica_dati_da_sheets("Giocate!A:I")

# --- INTERFACCIA UTENTE ---
st.title("⚽ Toto-Amici")
st.markdown("Risultati, classifiche, statistiche e montepremi in tempo reale.")
st.write("")

# --- NAVIGAZIONE A SCHEDE (TABS) ---
tab_classifica, tab_live, tab_confronto, tab_stats, tab_regolamento = st.tabs([
    "🏆 Classifica & Cassa", 
    "🎯 Schedine Live", 
    "🔍 Confronto Giocate",
    "📊 Statistiche",
    "📜 Regolamento"
])

# ==========================================
# TAB 1: CLASSIFICA E CASSA
# ==========================================
with tab_classifica:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Leaderboard")
        if not df_classifica.empty:
            df_classifica['Punti Totali'] = pd.to_numeric(df_classifica['Punti Totali'], errors='coerce').fillna(0).astype(int)
            df_classifica = df_classifica.sort_values(by='Punti Totali', ascending=False).reset_index(drop=True)
            df_compatta = df_classifica[['Giocatore', 'Punti Totali']].copy()
            
            if len(df_compatta) > 0: df_compatta.loc[0, 'Giocatore'] = "🥇 " + str(df_compatta.loc[0, 'Giocatore'])
            if len(df_compatta) > 1: df_compatta.loc[1, 'Giocatore'] = "🥈 " + str(df_compatta.loc[1, 'Giocatore'])
            if len(df_compatta) > 2: df_compatta.loc[2, 'Giocatore'] = "🥉 " + str(df_compatta.loc[2, 'Giocatore'])
            
            st.dataframe(df_compatta, hide_index=True, width="stretch")
            
            st.markdown("##### 📈 Grafico Punteggi")
            st.bar_chart(df_compatta.set_index('Giocatore'), height=250)
            
            with st.expander("🔍 Storico giornate (Dettaglio)"):
                df_classifica_pulita = df_classifica.replace("", pd.NA).dropna(axis=1, how='all').fillna("")
                st.dataframe(df_classifica_pulita, hide_index=True, width="stretch")
        else:
            st.info("Classifica non disponibile.")

    with col2:
        st.subheader("Fondo Cassa")
        if not df_cassa.empty:
            try:
                ultimo_saldo_str = str(df_cassa['Saldo Totale'].iloc[-1])
                saldo_pulito = ultimo_saldo_str.replace('€', '').replace('.', '').replace(',', '.').strip()
                saldo_num = float(saldo_pulito)
            except:
                ultimo_saldo_str = "0,00 €"
                saldo_num = 0.0

            st.metric(label="Montepremi Attuale", value=ultimo_saldo_str)
            
            progresso = min(saldo_num / OBIETTIVO_CASSA, 1.0)
            st.markdown(f"**Obiettivo Premi:** {saldo_num:,.2f} € / {OBIETTIVO_CASSA:,.2f} €")
            st.progress(progresso)
            if progresso >= 1.0:
                st.success("🎉 OBIETTIVO RAGGIUNTO! Premi interamente coperti dalla cassa!")
                
            with st.expander("📜 Movimenti di cassa"):
                st.dataframe(
                    df_cassa, 
                    hide_index=True, 
                    width="stretch",
                    column_config={"Descrizione": st.column_config.TextColumn("Descrizione", width="large")}
                )
        else:
            st.metric(label="Montepremi Attuale", value="0,00 €")
            st.info("Nessun movimento.")

# ==========================================
# TAB 2: SCHEDINE LIVE (CON RISULTATI REALI)
# ==========================================
with tab_live:
    st.subheader("Live Score Schedine")
    if not df_giocate.empty:
        giornate_disponibili = [g for g in df_giocate['Giornata'].dropna().unique() if str(g).strip() != ""]
        giocatori_disponibili = sorted([g for g in df_giocate['Giocatore'].dropna().unique() if str(g).strip() != ""])
        
        col_f1, col_f2 = st.columns(2)
        with col_f1: giornata_selezionata = st.selectbox("📅 Giornata", giornate_disponibili, index=len(giornate_disponibili)-1 if giornate_disponibili else 0)
        with col_f2: giocatore_selezionato = st.selectbox("👤 Giocatore", giocatori_disponibili)
        
        giornata_num_api = str(giornata_selezionata).lower().replace("giornata", "").strip()
        partite_ufficiose, risultati_live = scarica_risultati_api(giornata_num_api)
        
        df_filtrato = df_giocate[(df_giocate['Giornata'] == giornata_selezionata) & (df_giocate['Giocatore'] == giocatore_selezionato)]
        
        if not df_filtrato.empty:
            vincite_presenti = [v for v in df_filtrato['Vincita Potenziale'].tolist() if str(v).strip() not in ["", "0", "0.0"]]
            vincita_mostrata = vincite_presenti[0] if vincite_presenti else "0.00"
            
            st.markdown(f"""
            <div style="background-color: rgba(128, 128, 128, 0.15); border-left: 5px solid gray; padding: 10px; border-radius: 5px; margin-bottom: 20px; margin-top: 10px;">
                💶 <b>Vincita Potenziale:</b> {vincita_mostrata} €
            </div>
            """, unsafe_allow_html=True)
            
            for index, row in df_filtrato.iterrows():
                esito = str(row.get('Esito', ''))
                partita_nome = str(row.get('Partita', ''))
                
                partita_normalizzata = normalizza_partita_completa(partita_nome, partite_ufficiose)
                risultato_match = risultati_live.get(partita_normalizzata, "")

                if "VINTA" in esito: esito_color = "#28a745"
                elif "PERSA" in esito: esito_color = "#dc3545"
                else: esito_color = "#6c757d"
                
                badge_risultato = f'<span style="background-color: #f0f2f6; padding: 2px 8px; border-radius: 5px; color: #31333F; font-size: 14px;"><b>Risultato: {risultato_match}</b></span>' if risultato_match else ""
                
                with st.container(border=True):
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-size: 16px;"><b>⚽ {partita_normalizzata}</b></span>
                        {badge_risultato}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 15px; margin-bottom: 5px;">
                        <div>Pronostico: <b>{row.get('Pronostico', '')}</b> <span style="font-size: 13px; color: gray;">(@{row.get('Quota', '')})</span></div>
                        <div style="color: {esito_color}; font-weight: bold;">{esito}</div>
                    </div>
                    <div style="display: flex; justify-content: flex-end; font-size: 14px;">
                        <span style="background-color: rgba(128,128,128,0.1); padding: 2px 8px; border-radius: 10px;">
                            <b>+{row.get('Punti Partita', '0')} Pt</b>
                        </span>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.warning("Schedina non trovata per questo giocatore.")
    else:
        st.info("Nessuna giocata registrata.")

# ==========================================
# TAB 3: CONFRONTO GIOCATE (UNIFICATO)
# ==========================================
with tab_confronto:
    st.subheader("🔍 Confronto Giocate per Partita")
    st.markdown("Scopri cosa ha giocato ogni partecipante per i vari eventi della giornata.")
    
    if not df_giocate.empty:
        giornate_comp = [g for g in df_giocate['Giornata'].dropna().unique() if str(g).strip() != ""]
        if giornate_comp:
            giornata_selezionata_comp = st.selectbox("📅 Scegli la Giornata da analizzare", giornate_comp, index=len(giornate_comp)-1)
            
            df_giornata = df_giocate[df_giocate['Giornata'] == giornata_selezionata_comp].copy()
            
            if not df_giornata.empty:
                giornata_num_api = str(giornata_selezionata_comp).lower().replace("giornata", "").strip()
                partite_ufficiose, _ = scarica_risultati_api(giornata_num_api)
                
                df_giornata['Partita_Pulita'] = df_giornata['Partita'].apply(lambda x: normalizza_partita_completa(str(x), partite_ufficiose))
                
                def formatta_giocata(row):
                    pronostico = str(row.get('Pronostico', ''))
                    quota = str(row.get('Quota', ''))
                    return f"{pronostico} (@{quota})"
                
                df_giornata['Giocata'] = df_giornata.apply(formatta_giocata, axis=1)
                
                pivot = df_giornata.pivot_table(
                    index='Partita_Pulita', 
                    columns='Giocatore', 
                    values='Giocata', 
                    aggfunc=lambda x: ' | '.join(x)
                ).fillna("-")
                
                st.dataframe(pivot, use_container_width=True, height=500)
            else:
                st.info("Nessuna giocata trovata per questa giornata.")
    else:
        st.info("Nessuna giocata registrata nel database.")

# ==========================================
# TAB 4: STATISTICHE E HALL OF FAME
# ==========================================
with tab_stats:
    st.subheader("Hall of Fame & Curiosità")
    st.markdown("Analisi basata su tutte le schedine giocate fino ad oggi.")
    st.write("")

    if not df_giocate.empty:
        df_stats = df_giocate[df_giocate['Giocatore'].str.strip() != ""].copy()
        
        def parse_quota(q):
            try: return float(str(q).replace(',', '.'))
            except: return 0.0
        df_stats['Quota Num'] = df_stats['Quota'].apply(parse_quota)

        stats_giocatori = []
        for player in df_stats['Giocatore'].unique():
            df_p = df_stats[df_stats['Giocatore'] == player]
            tot = len(df_p)
            vinte = len(df_p[df_p['Esito'].str.contains("VINTA", na=False)])
            stats_giocatori.append({
                'Giocatore': player, 
                'Win_Rate': (vinte / tot * 100) if tot > 0 else 0, 
                'Quota_Media': df_p['Quota Num'].mean(),
                'Vinte': vinte, 'Totali': tot
            })

        col_s1, col_s2 = st.columns(2)
        
        with col_s1:
            st.markdown("#### 👤 I Protagonisti")
            if stats_giocatori:
                df_pg = pd.DataFrame(stats_giocatori)
                cecchino = df_pg.loc[df_pg['Win_Rate'].idxmax()]
                folle = df_pg.loc[df_pg['Quota_Media'].idxmax()]
                conservatore = df_pg.loc[df_pg['Quota_Media'].idxmin()]
                
                with st.container(border=True):
                    st.markdown(f"**🎯 Il Cecchino:** {cecchino['Giocatore'].upper()}")
                    st.caption(f"{cecchino['Win_Rate']:.1f}% di pronostici presi ({cecchino['Vinte']}/{cecchino['Totali']})")
                
                with st.container(border=True):
                    st.markdown(f"**💀 Quello pazzo in culo:** {folle['Giocatore'].upper()}")
                    st.caption(f"Gioca la quota media più alta del gruppo: {folle['Quota_Media']:.2f}")

                with st.container(border=True):
                    st.markdown(f"**🛡️ Il Conservatore:** {conservatore['Giocatore'].upper()}")
                    st.caption(f"Va sul sicuro. Quota media più bassa: {conservatore['Quota_Media']:.2f}")

        with col_s2:
            st.markdown("#### ⚽ Le Squadre di Serie A")
            squadre_perse = []
            squadre_vinte = []
            
            for _, row in df_stats.iterrows():
                if "PERSA" in str(row['Esito']) and "-" in str(row['Partita']):
                    squadre_perse.extend([s.strip() for s in str(row['Partita']).split('-')])
                if "VINTA" in str(row['Esito']) and "-" in str(row['Partita']):
                    squadre_vinte.extend([s.strip() for s in str(row['Partita']).split('-')])
            
            with st.container(border=True):
                if squadre_vinte:
                    amuleto = pd.Series(squadre_vinte).value_counts().idxmax()
                    st.markdown(f"**🍀 La Squadra Amuleto:** {amuleto.upper()}")
                    st.caption(f"Vi ha fatto vincere {pd.Series(squadre_vinte).value_counts().max()} pronostici in totale!")
                else:
                    st.markdown("**🍀 La Squadra Amuleto:** -")

            with st.container(border=True):
                if squadre_perse:
                    maledetta = pd.Series(squadre_perse).value_counts().idxmax()
                    st.markdown(f"**👻 La Squadra Maledetta:** {maledetta.upper()}")
                    st.caption(f"Vi ha fatto bruciare {pd.Series(squadre_perse).value_counts().max()} pronostici in totale!")
                else:
                    st.markdown("**👻 La Squadra Maledetta:** -")

# ==========================================
# TAB 5: REGOLAMENTO
# ==========================================
with tab_regolamento:
    st.subheader("📜 Regolamento Ufficiale Toto-amici")
    
    st.markdown("""
    ### ⚽ 1. La Bolletta
    *   **Costo:** Ogni giornata va giocata una bolletta da **5 €**.
    *   **Composizione Obbligatoria:** 
        *   **1 Combo** (1X2 + O/U 2.5, 1X2 + GG/NG)
        *   **4 Fisse**
        *   **2 Doppie Chance**
        *   **3 Variabili (Over 2.5 / Under 2.5 / Pari / Dispari / Goal / NoGoal)**
    
    ### 🎯 2. Sistema Punteggi
    *   **Combo:** 6 punti
    *   **Fisse:** 4 punti
    *   **Doppie Chance:** 1 punto
    *   **Mercati Base (O/U, ecc.):** 2 punti
    *   **🚀 Moltiplicatore Quota Alta:** Se la quota giocata di un singolo evento è **≥ 3.50**, i punti di quell'evento si **raddoppiano** (es. Combo = 12 pt, Fissa = 8 pt, ecc.). *Fa fede SOLTANTO la quota pubblicata nella bolletta.*
    *   **🔥 Bonus Vincita:** Se un giocatore chiude (vince) la bolletta, ottiene **10 punti BONUS**.
    
    ### ⚖️ 3. Regole, Errori e Penalità
    *   **Bolletta Errata (Es. troppe fisse):** Tutte le selezioni in eccesso/errate (nell'esempio, le fisse) verranno ritenute **annullate** ai fini del gioco (0 points). Le selezioni corrette restano valide. La bolletta resta valida ai fini economici.
    *   **Errore in buona fede:** Se si gioca per errore palese un OVER 1.5 al posto di un 2.5, ai fini del punteggio sarà valida *solo se* la partita finisce OVER 2.5. Ai fini del fondo-cassa fa fede la bolletta reale con l'1.5. (Stessa regola per Under 3.5).
    *   **⏳ Scadenza Pubblicazione:** La bolletta va pubblicata **5 minuti prima** dell'inizio della prima partita. Se pubblicata in ritardo: **0 PUNTI** per la giornata e la bolletta diventa **nulla ai fini economici** (in caso di vincita, la quota è tutta del giocatore che l'ha giocata).
    *   **Partite Rinviate:** Per i punti si aspetta il recupero della partita. Ai fini economici, se il sito di scommesse ritiene la giocata chiusa/pagata, i soldi si dividono sempre a metà.
    
    ### 💰 4. Cassa e Montepremi
    *   **Quota di Partecipazione:** **200 € a persona**, da versare entro la 36ª giornata per far quadrare i conti col fondo cassa.
    *   **Ripartizione Vincite:** In caso di bolletta vincente, la vincita si divide a metà: **50% a chi l'ha giocata**, **50% nel Fondo Cassa**. *(La metà del fondo-cassa va data subito dopo la vincita).*
    
    ---
    
    **🏆 Esempio Ripartizione Premi (su 15 giocatori e 3.000€ Montepremi)**
    *   **1° Classificato:** 1.200 €
    *   **2° Classificato:** 800 €
    *   **3° Classificato:** 500 €
    *   **4° Classificato:** 300 €
    *   **5° Classificato:** 200 €
    
    *(Se dalle bollette chiuse a fine anno risultano a fondo cassa 3.000 euro, ogni giocatore prenderà i suoi 200 euro).*
    """)