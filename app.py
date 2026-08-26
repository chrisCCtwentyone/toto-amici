import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- CONFIGURAZIONE PAGINA STREAMLIT ---
st.set_page_config(page_title="Toto-Amici 2026", page_icon="⚽", layout="wide")

# --- INIEZIONE CSS PER NASCONDERE ELEMENTI DI STREAMLIT ---
st.markdown("""
    <style>
    /* Nasconde la barra in alto (tasto Fork, i tre puntini, ecc.) */
    header {visibility: hidden !important;}
    #MainMenu {visibility: hidden !important;}
    
    /* Nasconde la "catenina" (ancora del link) accanto ai titoli */
    a.header-anchor {display: none !important;}
    h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {display: none !important;}
    
    /* Riduce lo spazio vuoto in alto lasciato dalla barra nascosta */
    .block-container {padding-top: 1rem !important;}
    </style>
    """, unsafe_allow_html=True)

# L'ID del tuo foglio Google
SPREADSHEET_ID = '1q0aaYXl7VYiUzEbttGaoQjNq7ta5wiHD4Qvg5Si7IvE'

@st.cache_data(ttl=60)
def carica_dati_da_sheets(range_name):
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    try:
        # LETTURA SICURA DAL CLOUD
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], 
            scopes=SCOPES
        )
        service = build('sheets', 'v4', credentials=creds)
        
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        values = result.get('values', [])
        
        if not values:
            return pd.DataFrame()
            
        headers = values[0]
        data = values[1:]
        
        dati_allineati = [riga + [""] * (len(headers) - len(riga)) for riga in data]
        df = pd.DataFrame(dati_allineati, columns=headers)
        return df
    except Exception as e:
        st.error(f"Errore di caricamento dati: {e}")
        return pd.DataFrame()

# --- CARICAMENTO DATI ---
df_classifica = carica_dati_da_sheets("Classifica!A:Z")
df_cassa = carica_dati_da_sheets("Cassa!A:D")
df_giocate = carica_dati_da_sheets("Giocate!A:I")

# --- INTERFACCIA UTENTE ---
st.title("⚽ Toto-Amici")
st.markdown("Risultati, classifiche, statistiche e montepremi in tempo reale.")
st.write("")

# --- NAVIGAZIONE A SCHEDE (TABS) ---
tab_classifica, tab_live, tab_stats = st.tabs(["🏆 Classifica & Cassa", "🎯 Schedine Live", "📊 Statistiche & Curiosità"])

# ==========================================
# TAB 1: CLASSIFICA E CASSA
# ==========================================
with tab_classifica:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Leaderboard")
        if not df_classifica.empty:
            df_classifica['Punti Totali'] = pd.to_numeric(df_classifica['Punti Totali'], errors='coerce').fillna(0).astype(int)
            df_classifica = df_classifica.sort_values(by='Punti Totali', ascending=False)
            df_compatta = df_classifica[['Giocatore', 'Punti Totali']]
            
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
                ultimo_saldo_str = df_cassa['Saldo Totale'].iloc[-1]
                st.metric(label="Montepremi Attuale", value=ultimo_saldo_str)
            except Exception:
                st.metric(label="Montepremi Attuale", value="0,00 €")
                
            with st.expander("📜 Movimenti di cassa"):
                st.dataframe(
                    df_cassa, 
                    hide_index=True, 
                    width="stretch",
                    column_config={
                        "Descrizione": st.column_config.TextColumn("Descrizione", width="large")
                    }
                )
        else:
            st.metric(label="Montepremi Attuale", value="0,00 €")
            st.info("Nessun movimento.")

# ==========================================
# TAB 2: SCHEDINE LIVE
# ==========================================
with tab_live:
    st.subheader("Live Score Schedine")

    if not df_giocate.empty:
        giornate_disponibili = [g for g in df_giocate['Giornata'].dropna().unique() if str(g).strip() != ""]
        giocatori_disponibili = sorted([g for g in df_giocate['Giocatore'].dropna().unique() if str(g).strip() != ""])
        
        col_filter1, col_filter2 = st.columns(2)
        with col_filter1:
            giornata_selezionata = st.selectbox("📅 Giornata", giornate_disponibili, index=len(giornate_disponibili)-1 if giornate_disponibili else 0)
        with col_filter2:
            giocatore_selezionato = st.selectbox("👤 Giocatore", giocatori_disponibili)
        
        df_filtrato = df_giocate[(df_giocate['Giornata'] == giornata_selezionata) & (df_giocate['Giocatore'] == giocatore_selezionato)]
        
        if not df_filtrato.empty:
            vincite_presenti = [v for v in df_filtrato['Vincita Potenziale'].tolist() if str(v).strip() not in ["", "0", "0.0"]]
            vincita_mostrata = vincite_presenti[0] if vincite_presenti else "0.00"
            
            st.write("")
            st.markdown(f"""
            <div style="background-color: rgba(128, 128, 128, 0.15); border-left: 5px solid gray; padding: 10px; border-radius: 5px; margin-bottom: 20px;">
                💶 <b>Vincita Potenziale:</b> {vincita_mostrata} €
            </div>
            """, unsafe_allow_html=True)
            
            for index, row in df_filtrato.iterrows():
                partita = row.get('Partita', '')
                pronostico = row.get('Pronostico', '')
                quota = row.get('Quota', '')
                esito = str(row.get('Esito', ''))
                punti = row.get('Punti Partita', '0')
                
                if "VINTA" in esito:
                    esito_color = "#28a745"
                elif "PERSA" in esito:
                    esito_color = "#dc3545"
                else:
                    esito_color = "#6c757d"
                
                with st.container(border=True):
                    st.markdown(f"**⚽ {partita}**")
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 15px; margin-bottom: 5px;">
                        <div>Pronostico: <b>{pronostico}</b> <span style="font-size: 13px; color: gray;">(@{quota})</span></div>
                        <div style="color: {esito_color}; font-weight: bold;">{esito}</div>
                    </div>
                    <div style="display: flex; justify-content: flex-end; font-size: 14px;">
                        <span style="background-color: rgba(128,128,128,0.1); padding: 2px 8px; border-radius: 10px;">
                            <b>+{punti} Pt</b>
                        </span>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.warning("Schedina non trovata per questo giocatore.")
    else:
        st.info("Nessuna giocata registrata.")

# ==========================================
# TAB 3: STATISTICHE E HALL OF FAME
# ==========================================
with tab_stats:
    st.subheader("Hall of Fame & Curiosità")
    st.markdown("Analisi basata su tutte le schedine giocate fino ad oggi.")
    st.write("")

    if not df_giocate.empty:
        df_stats = df_giocate[df_giocate['Giocatore'].str.strip() != ""].copy()
        
        def parse_quota(q):
            try:
                return float(str(q).replace(',', '.'))
            except:
                return 0.0
        df_stats['Quota Num'] = df_stats['Quota'].apply(parse_quota)

        stats_giocatori = []
        for player in df_stats['Giocatore'].unique():
            df_p = df_stats[df_stats['Giocatore'] == player]
            tot_partite = len(df_p)
            vinte = len(df_p[df_p['Esito'].str.contains("VINTA", na=False)])
            win_rate = (vinte / tot_partite * 100) if tot_partite > 0 else 0
            quota_media = df_p['Quota Num'].mean()
            
            if tot_partite > 0:
                stats_giocatori.append({
                    'Giocatore': player, 
                    'Win_Rate': win_rate, 
                    'Quota_Media': quota_media,
                    'Vinte': vinte,
                    'Totali': tot_partite
                })

        squadre_vinte = []
        squadre_perse = []
        
        for index, row in df_stats.iterrows():
            esito = str(row['Esito'])
            partita = str(row['Partita'])
            if "-" in partita:
                squadre = [s.strip() for s in partita.split('-')]
                if "VINTA" in esito:
                    squadre_vinte.extend(squadre)
                elif "PERSA" in esito:
                    squadre_perse.extend(squadre)

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
                    # TWEAK RICHIESTO: Il nuovo titolo per lo scommettitore folle
                    st.markdown(f"**🤪 Quello pazzo in culo:** {folle['Giocatore'].upper()}")
                    st.caption(f"Gioca la quota media più alta del gruppo: {folle['Quota_Media']:.2f}")

                with st.container(border=True):
                    st.markdown(f"**🛡️ Il Conservatore:** {conservatore['Giocatore'].upper()}")
                    st.caption(f"Va sul sicuro. Quota media più bassa: {conservatore['Quota_Media']:.2f}")
            else:
                st.info("Non ci sono ancora dati sufficienti sui giocatori.")

        with col_s2:
            st.markdown("#### ⚽ Le Squadre di Serie A")
            
            with st.container(border=True):
                if squadre_perse:
                    maledetta = pd.Series(squadre_perse).value_counts().idxmax()
                    volte_persa = pd.Series(squadre_perse).value_counts().max()
                    st.markdown(f"**👻 La Squadra Maledetta:** {maledetta.upper()}")
                    st.caption(f"Vi ha fatto bruciare {volte_persa} pronostici in totale!")
                else:
                    st.markdown("**👻 La Squadra Maledetta:** -")
                    st.caption("Nessuna schedina persa finora... incredibile!")

            with st.container(border=True):
                if squadre_vinte:
                    amuleto = pd.Series(squadre_vinte).value_counts().idxmax()
                    volte_vinta = pd.Series(squadre_vinte).value_counts().max()
                    st.markdown(f"**🍀 La Squadra Amuleto:** {amuleto.upper()}")
                    st.caption(f"Vi ha regalato {volte_vinta} pronostici azzeccati!")
                else:
                    st.markdown("**🍀 La Squadra Amuleto:** -")
                    st.caption("Ancora nessun pronostico vinto.")
    else:
        st.info("Non ci sono giocate registrate per calcolare le statistiche.")