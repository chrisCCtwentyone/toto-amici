import streamlit as st
import pandas as pd
import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- CONFIGURAZIONE PAGINA STREAMLIT ---
st.set_page_config(page_title="Toto-Amici 2026", page_icon="⚽", layout="wide")

st.markdown("""
    <style>
    header {visibility: hidden !important;}
    #MainMenu {visibility: hidden !important;}
    a.header-anchor {display: none !important;}
    h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {display: none !important;}
    .block-container {padding-top: 1rem !important;}
    </style>
    """, unsafe_allow_html=True)

SPREADSHEET_ID = '1q0aaYXl7VYiUzEbttGaoQjNq7ta5wiHD4Qvg5Si7IvE'
OBIETTIVO_CASSA = 3200.0 
FOOTBALL_DATA_KEY = "ef8a4016b5ab4f90a486ea0fea46fd1f"

@st.cache_data(ttl=60)
def carica_dati_da_sheets(range_name):
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        service = build('sheets', 'v4', credentials=creds)
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        values = result.get('values', [])
        if not values: return pd.DataFrame()
        headers = values[0]
        data = values[1:]
        dati_allineati = [riga + [""] * (len(headers) - len(riga)) for riga in data]
        return pd.DataFrame(dati_allineati, columns=headers)
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=60)
def scarica_risultati_api(giornata):
    """Scarica API e restituisce sia il punteggio live che il NOME UFFICIALE della partita"""
    url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    risultati_mappati = {}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            for m in res.json().get("matches", []):
                casa = str(m["homeTeam"]["name"]).lower()
                ospite = str(m["awayTeam"]["name"]).lower()
                short_casa = str(m["homeTeam"].get("shortName", casa)).lower()
                short_ospite = str(m["awayTeam"].get("shortName", ospite)).lower()
                
                nome_ufficiale = f"{m['homeTeam'].get('shortName', m['homeTeam']['name'])} - {m['awayTeam'].get('shortName', m['awayTeam']['name'])}"
                
                status = m["status"]
                if status in ["FINISHED", "IN_PLAY", "PAUSED"]:
                    h_score = m["score"]["fullTime"]["home"] if m["score"]["fullTime"]["home"] is not None else 0
                    a_score = m["score"]["fullTime"]["away"] if m["score"]["fullTime"]["away"] is not None else 0
                    score_str = f"{h_score} - {a_score}" if status == "FINISHED" else f"{h_score} - {a_score} (In Corso)"
                elif status in ["TIMED", "SCHEDULED"]: score_str = "Da giocare"
                else: score_str = "Rinviata/Altro"
                    
                key1 = f"{casa[:5]}-{ospite[:5]}"
                key2 = f"{short_casa[:5]}-{short_ospite[:5]}"
                info = {"score": score_str, "nome": nome_ufficiale}
                risultati_mappati[key1] = info
                risultati_mappati[key2] = info
    except: pass
    return risultati_mappati

df_classifica = carica_dati_da_sheets("Classifica!A:Z")
df_cassa = carica_dati_da_sheets("Cassa!A:D")
df_giocate = carica_dati_da_sheets("Giocate!A:I")

st.title("⚽ Toto-Amici")
st.markdown("Risultati, classifiche, statistiche e montepremi in tempo reale.")
st.write("")

tab_classifica, tab_live, tab_confronto, tab_stats, tab_regolamento = st.tabs([
    "🏆 Classifica & Cassa", "🎯 Schedine Live", "🔍 Confronto Giocate", "📊 Statistiche", "📜 Regolamento"
])

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
                st.dataframe(df_classifica.replace("", pd.NA).dropna(axis=1, how='all').fillna(""), hide_index=True, width="stretch")

    with col2:
        st.subheader("Fondo Cassa")
        if not df_cassa.empty:
            try:
                ultimo_saldo_str = str(df_cassa['Saldo Totale'].iloc[-1])
                saldo_num = float(ultimo_saldo_str.replace('€', '').replace('.', '').replace(',', '.').strip())
            except:
                ultimo_saldo_str, saldo_num = "0,00 €", 0.0
            st.metric(label="Montepremi Attuale", value=ultimo_saldo_str)
            progresso = min(saldo_num / OBIETTIVO_CASSA, 1.0)
            st.markdown(f"**Obiettivo Premi:** {saldo_num:,.2f} € / {OBIETTIVO_CASSA:,.2f} €")
            st.progress(progresso)
            with st.expander("📜 Movimenti di cassa"):
                st.dataframe(df_cassa, hide_index=True, width="stretch")

with tab_live:
    st.subheader("Live Score Schedine")
    if not df_giocate.empty:
        giornate_disponibili = [g for g in df_giocate['Giornata'].dropna().unique() if str(g).strip() != ""]
        giocatori_disponibili = sorted([g for g in df_giocate['Giocatore'].dropna().unique() if str(g).strip() != ""])
        col_f1, col_f2 = st.columns(2)
        with col_f1: giornata_selezionata = st.selectbox("📅 Giornata", giornate_disponibili, index=len(giornate_disponibili)-1 if giornate_disponibili else 0)
        with col_f2: giocatore_selezionato = st.selectbox("👤 Giocatore", giocatori_disponibili)
        
        giornata_num_api = str(giornata_selezionata).lower().replace("giornata", "").strip()
        risultati_live = scarica_risultati_api(giornata_num_api)
        
        df_filtrato = df_giocate[(df_giocate['Giornata'] == giornata_selezionata) & (df_giocate['Giocatore'] == giocatore_selezionato)]
        if not df_filtrato.empty:
            vincite_presenti = [v for v in df_filtrato['Vincita Potenziale'].tolist() if str(v).strip() not in ["", "0", "0.0"]]
            st.markdown(f"""
            <div style="background-color: rgba(128, 128, 128, 0.15); border-left: 5px solid gray; padding: 10px; border-radius: 5px; margin-bottom: 20px; margin-top: 10px;">
                💶 <b>Vincita Potenziale:</b> {vincite_presenti[0] if vincite_presenti else '0.00'} €
            </div>
            """, unsafe_allow_html=True)
            
            for index, row in df_filtrato.iterrows():
                esito = str(row.get('Esito', ''))
                partita_nome = str(row.get('Partita', ''))
                
                parts = [s.strip()[:5].lower() for s in partita_nome.split('-')]
                risultato_match, nome_ufficiale_match = "", partita_nome
                if len(parts) == 2:
                    info = risultati_live.get(f"{parts[0]}-{parts[1]}", {})
                    risultato_match = info.get("score", "")
                    nome_ufficiale_match = info.get("nome", partita_nome)

                esito_color = "#28a745" if "VINTA" in esito else ("#dc3545" if "PERSA" in esito else "#6c757d")
                badge = f'<span style="background-color: #f0f2f6; padding: 2px 8px; border-radius: 5px; color: #31333F; font-size: 14px;"><b>Risultato: {risultato_match}</b></span>' if risultato_match else ""
                
                with st.container(border=True):
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-size: 16px;"><b>⚽ {nome_ufficiale_match}</b></span>
                        {badge}
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 15px; margin-bottom: 5px;">
                        <div>Pronostico: <b>{row.get('Pronostico', '')}</b> <span style="font-size: 13px; color: gray;">(@{row.get('Quota', '')})</span></div>
                        <div style="color: {esito_color}; font-weight: bold;">{esito}</div>
                    </div>
                    """, unsafe_allow_html=True)
        else: st.warning("Schedina non trovata.")

with tab_confronto:
    st.subheader("🔍 Confronto Giocate per Partita")
    st.markdown("Scopri cosa ha giocato ogni partecipante (le partite sono state normalizzate e unificate in automatico).")
    if not df_giocate.empty:
        giornate_comp = [g for g in df_giocate['Giornata'].dropna().unique() if str(g).strip() != ""]
        if giornate_comp:
            giornata_selezionata_comp = st.selectbox("📅 Scegli la Giornata da analizzare", giornate_comp, index=len(giornate_comp)-1)
            df_giornata = df_giocate[df_giocate['Giornata'] == giornata_selezionata_comp].copy()
            
            if not df_giornata.empty:
                giornata_num_api = str(giornata_selezionata_comp).lower().replace("giornata", "").strip()
                risultati_live = scarica_risultati_api(giornata_num_api)
                
                # LA CURA: NORMALIZZA I NOMI PER LA PIVOT
                def normalizza_partita_per_pivot(nome_originale):
                    try:
                        parts = [s.strip()[:5].lower() for s in str(nome_originale).split('-')]
                        if len(parts) == 2:
                            return risultati_live.get(f"{parts[0]}-{parts[1]}", {}).get("nome", str(nome_originale).title())
                    except: pass
                    return str(nome_originale).title()

                df_giornata['Partita_Ufficiale'] = df_giornata['Partita'].apply(normalizza_partita_per_pivot)
                df_giornata['Giocata'] = df_giornata.apply(lambda row: f"{str(row.get('Pronostico',''))} (@{str(row.get('Quota',''))})", axis=1)
                
                pivot = df_giornata.pivot_table(index='Partita_Ufficiale', columns='Giocatore', values='Giocata', aggfunc=lambda x: ' | '.join(x)).fillna("-")
                st.dataframe(pivot, use_container_width=True, height=500)

with tab_stats:
    st.subheader("Hall of Fame & Curiosità")
    if not df_giocate.empty:
        df_stats = df_giocate[df_giocate['Giocatore'].str.strip() != ""].copy()
        df_stats['Quota Num'] = df_stats['Quota'].apply(lambda q: float(str(q).replace(',', '.')) if str(q).replace(',', '.').replace('.','').isdigit() else 0.0)
        
        stats = []
        for player in df_stats['Giocatore'].unique():
            df_p = df_stats[df_stats['Giocatore'] == player]
            vinte = len(df_p[df_p['Esito'].str.contains("VINTA", na=False)])
            stats.append({'Giocatore': player, 'Win_Rate': (vinte/len(df_p)*100) if len(df_p)>0 else 0, 'Quota_Media': df_p['Quota Num'].mean(), 'Vinte': vinte, 'Totali': len(df_p)})

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            if stats:
                df_pg = pd.DataFrame(stats)
                st.markdown("#### 👤 I Protagonisti")
                st.markdown(f"**🎯 Il Cecchino:** {df_pg.loc[df_pg['Win_Rate'].idxmax()]['Giocatore'].upper()}")
                st.markdown(f"**💀 Il Pazzo:** {df_pg.loc[df_pg['Quota_Media'].idxmax()]['Giocatore'].upper()}")
                st.markdown(f"**🛡️ Il Conservatore:** {df_pg.loc[df_pg['Quota_Media'].idxmin()]['Giocatore'].upper()}")

        with col_s2:
            st.markdown("#### ⚽ Le Squadre di Serie A")
            s_perse = [s.strip() for r in df_stats[df_stats['Esito'].str.contains("PERSA", na=False)]['Partita'] for s in str(r).split('-')]
            s_vinte = [s.strip() for r in df_stats[df_stats['Esito'].str.contains("VINTA", na=False)]['Partita'] for s in str(r).split('-')]
            st.markdown(f"**🍀 La Squadra Amuleto:** {pd.Series(s_vinte).value_counts().idxmax().upper() if s_vinte else '-'}")
            st.markdown(f"**👻 La Squadra Maledetta:** {pd.Series(s_perse).value_counts().idxmax().upper() if s_perse else '-'}")

with tab_regolamento:
    st.subheader("📜 Regolamento Ufficiale Toto-amici")
    st.markdown("*(Regolamento inalterato)*")