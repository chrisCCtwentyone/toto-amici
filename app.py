import streamlit as st
import pandas as pd
import requests
import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="Toto-Amici 2026",
    page_icon=":material/sports_soccer:",
    layout="wide"
)

# --- CSS MINIMAL ---
st.html("""
<style>
header {visibility: hidden !important;}
#MainMenu {visibility: hidden !important;}
a.header-anchor {display: none !important;}
h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {display: none !important;}
.block-container {padding-top: 1.5rem !important; padding-bottom: 2rem !important;}
</style>
""")

# --- COSTANTI ---
try:
    SPREADSHEET_ID = st.secrets["SPREADSHEET_ID"]
    FOOTBALL_DATA_KEY = st.secrets["FOOTBALL_DATA_KEY"]
except KeyError:
    st.error(":material/error: Chiavi segrete mancanti! Configurale su Streamlit Cloud nei Secrets.")
    st.stop()

OBIETTIVO_CASSA = 3200.0
EMOJI_POSIZIONE = {0: "🥇", 1: "🥈", 2: "🥉"}

# ==========================================
# CREDENZIALI E SERVICE (CACHED)
# ==========================================
def _get_credentials():
    """
    1. Locale / Render: legge credenziali.json
    2. Streamlit Cloud: fallback su st.secrets["gcp_service_account"]
    """
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    if os.path.exists('credenziali.json'):
        return Credentials.from_service_account_file('credenziali.json', scopes=SCOPES)
    return Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )

@st.cache_resource
def get_sheets_service():
    """Service Sheets cached come risorsa: costruito UNA SOLA VOLTA per tutta la sessione."""
    return build('sheets', 'v4', credentials=_get_credentials())

# ==========================================
# CARICAMENTO DATI — UNICA CHIAMATA BATCH
# ==========================================
@st.cache_data(ttl=60)
def carica_tutti_i_dati():
    """
    Carica Classifica, Cassa e Giocate in UNA sola chiamata batchGet.
    Prima era 3 chiamate separate + 3 build() → ora 1 chiamata, service riusato.
    """
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().batchGet(
            spreadsheetId=SPREADSHEET_ID,
            ranges=["Classifica!A:Z", "Cassa!A:D", "Giocate!A:I"]
        ).execute()

        dfs = []
        for vr in result.get("valueRanges", []):
            values = vr.get("values", [])
            if not values:
                dfs.append(pd.DataFrame())
                continue
            headers = values[0]
            data = values[1:]
            dati_allineati = [riga + [""] * (len(headers) - len(riga)) for riga in data]
            dfs.append(pd.DataFrame(dati_allineati, columns=headers))

        # Garanzia 3 DataFrame anche se un foglio è vuoto
        while len(dfs) < 3:
            dfs.append(pd.DataFrame())
        return dfs[0], dfs[1], dfs[2]

    except Exception as e:
        st.error(f"Errore di caricamento dati: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=60)
def scarica_risultati_api(giornata):
    """Risultati live Serie A dalla Football-Data API."""
    url = f"https://api.football-data.org/v4/competitions/SA/matches?matchday={giornata}"
    headers_req = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    partite_ufficiali = []
    risultati_mappati = {}
    try:
        res = requests.get(url, headers=headers_req, timeout=10)
        if res.status_code == 200:
            for m in res.json().get("matches", []):
                casa_full = m["homeTeam"]["name"]
                ospite_full = m["awayTeam"]["name"]
                nome_ufficiale = f"{casa_full} - {ospite_full}"
                partite_ufficiali.append((casa_full, ospite_full, nome_ufficiale))
                status = m["status"]
                if status in ["FINISHED", "IN_PLAY", "PAUSED"]:
                    h = m["score"]["fullTime"]["home"] or 0
                    a = m["score"]["fullTime"]["away"] or 0
                    score_str = f"{h} - {a}" if status == "FINISHED" else f"{h} - {a} (In Corso)"
                elif status in ["TIMED", "SCHEDULED"]:
                    score_str = "Da giocare"
                else:
                    score_str = "Rinviata/Altro"
                risultati_mappati[nome_ufficiale] = score_str
    except Exception:
        pass
    return partite_ufficiali, risultati_mappati

# ==========================================
# NORMALIZZAZIONE NOMI SQUADRE
# ==========================================
def normalizza_nome_squadra(squadra_raw, lista_ufficiali):
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

# ==========================================
# CARICAMENTO INIZIALE DATI
# ==========================================
df_classifica, df_cassa, df_giocate = carica_tutti_i_dati()

# ==========================================
# HEADER
# ==========================================
col_title, col_refresh = st.columns([5, 1])
with col_title:
    st.title(":material/sports_soccer: Toto-Amici 2026")
    st.caption("Risultati, classifiche, statistiche e montepremi in tempo reale · Serie A")
with col_refresh:
    st.write("")
    if st.button(":material/refresh: Aggiorna", key="btn_refresh"):
        st.cache_data.clear()
        st.rerun()

st.write("")

# ==========================================
# TABS
# ==========================================
tab_classifica, tab_live, tab_confronto, tab_stats, tab_regolamento = st.tabs([
    ":material/leaderboard: Classifica & Cassa",
    ":material/live_tv: Schedine Live",
    ":material/compare_arrows: Confronto Giocate",
    ":material/bar_chart: Statistiche",
    ":material/gavel: Regolamento"
])

# ==========================================
# TAB 1: CLASSIFICA E CASSA
# ==========================================
with tab_classifica:

    if not df_classifica.empty:
        df_classifica['Punti Totali'] = pd.to_numeric(
            df_classifica['Punti Totali'], errors='coerce'
        ).fillna(0).astype(int)
        df_classifica = df_classifica.sort_values(
            by='Punti Totali', ascending=False
        ).reset_index(drop=True)

        colonne_giornate = [c for c in df_classifica.columns if 'giornata' in str(c).lower()]

        # --- PODIO: top 3 ---
        n_top = min(3, len(df_classifica))
        if n_top > 0:
            st.subheader("Podio")
            podio_cols = st.columns(n_top, border=True)
            for i in range(n_top):
                row = df_classifica.iloc[i]
                giocatore = str(row['Giocatore'])
                punti = int(row['Punti Totali'])
                delta_str = None
                sparkline_data = None
                if colonne_giornate:
                    valori = []
                    for cg in colonne_giornate:
                        try:
                            v = int(str(row.get(cg, 0)).strip() or 0)
                            valori.append(v)
                        except:
                            valori.append(0)
                    if len(valori) >= 1 and valori[-1] > 0:
                        delta_str = f"+{valori[-1]} pt ultima giornata"
                    sparkline_data = valori if any(v > 0 for v in valori) else None

                with podio_cols[i]:
                    emoji = EMOJI_POSIZIONE.get(i, f"#{i+1}")
                    if sparkline_data:
                        st.metric(
                            label=f"{emoji} {giocatore.upper()}",
                            value=f"{punti} pt",
                            delta=delta_str,
                            chart_data=sparkline_data,
                            chart_type="bar"
                        )
                    else:
                        st.metric(
                            label=f"{emoji} {giocatore.upper()}",
                            value=f"{punti} pt",
                            delta=delta_str
                        )

        st.write("")

        # --- CLASSIFICA COMPLETA (full width, mobile-friendly) ---
        st.subheader("Classifica completa")
        df_display = df_classifica[['Giocatore', 'Punti Totali']].copy()
        df_display.index = df_display.index + 1
        st.dataframe(
            df_display,
            hide_index=False,
            width="stretch",
            column_config={
                "Giocatore": st.column_config.TextColumn("Giocatore"),
                "Punti Totali": st.column_config.NumberColumn("Punti", format="%d pt"),
            }
        )

        # --- STORICO GIORNATE ---
        with st.expander(":material/history: Storico punteggi per giornata"):
            df_classifica_pulita = df_classifica.replace("", pd.NA).dropna(axis=1, how='all').fillna("")
            st.dataframe(df_classifica_pulita, hide_index=True, width="stretch")

    else:
        st.info("Classifica non ancora disponibile.")

    st.write("")
    st.subheader(":material/savings: Fondo Cassa")

    if not df_cassa.empty:
        try:
            ultimo_saldo_str = str(df_cassa['Saldo Totale'].iloc[-1])
            saldo_pulito = ultimo_saldo_str.replace('€', '').replace('.', '').replace(',', '.').strip()
            saldo_num = float(saldo_pulito)
        except:
            ultimo_saldo_str = "0,00 €"
            saldo_num = 0.0

        progresso = min(saldo_num / OBIETTIVO_CASSA, 1.0)
        perc = progresso * 100

        col_c1, col_c2, col_c3 = st.columns(3, border=True)
        with col_c1:
            st.metric(label=":material/account_balance_wallet: Montepremi attuale", value=ultimo_saldo_str)
        with col_c2:
            st.metric(label=":material/flag: Obiettivo", value=f"{OBIETTIVO_CASSA:,.0f} €")
        with col_c3:
            st.metric(label=":material/percent: Completamento", value=f"{perc:.1f}%")

        st.progress(progresso)
        if progresso >= 1.0:
            st.success("OBIETTIVO RAGGIUNTO! I premi sono interamente coperti.", icon=":material/emoji_events:")

        with st.expander(":material/receipt_long: Movimenti di cassa"):
            st.dataframe(
                df_cassa,
                hide_index=True,
                width="stretch",
                column_config={"Descrizione": st.column_config.TextColumn("Descrizione", width="large")}
            )
    else:
        st.metric(label=":material/account_balance_wallet: Montepremi attuale", value="0,00 €")
        st.caption("Nessun movimento registrato.")

# ==========================================
# TAB 2: SCHEDINE LIVE
# ==========================================
with tab_live:
    st.subheader("Live score schedine")
    st.caption("Risultati in tempo reale via Football-Data.org")

    if not df_giocate.empty:
        giornate_disponibili = [
            g for g in df_giocate['Giornata'].dropna().unique() if str(g).strip() != ""
        ]
        giocatori_disponibili = sorted([
            g for g in df_giocate['Giocatore'].dropna().unique() if str(g).strip() != ""
        ])

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            giornata_selezionata = st.selectbox(
                "Giornata", giornate_disponibili,
                index=len(giornate_disponibili) - 1 if giornate_disponibili else 0
            )
        with col_f2:
            giocatore_selezionato = st.selectbox("Giocatore", giocatori_disponibili)

        giornata_num_api = str(giornata_selezionata).lower().replace("giornata", "").strip()
        partite_ufficiose, risultati_live = scarica_risultati_api(giornata_num_api)

        df_filtrato = df_giocate[
            (df_giocate['Giornata'] == giornata_selezionata) &
            (df_giocate['Giocatore'] == giocatore_selezionato)
        ]

        if not df_filtrato.empty:
            vincite_presenti = [
                v for v in df_filtrato['Vincita Potenziale'].tolist()
                if str(v).strip() not in ["", "0", "0.0"]
            ]
            vincita_mostrata = vincite_presenti[0] if vincite_presenti else "0.00"

            # Riepilogo esiti (senza "Annullate" — non usate nel torneo)
            n_vinte = sum(1 for _, r in df_filtrato.iterrows() if "VINTA" in str(r.get('Esito', '')))
            n_perse = sum(1 for _, r in df_filtrato.iterrows() if "PERSA" in str(r.get('Esito', '')))
            n_corso = sum(1 for _, r in df_filtrato.iterrows() if "CORSO" in str(r.get('Esito', '')))

            with st.container(border=True):
                col_v, col_p, col_c, col_eur = st.columns(4)
                with col_v:
                    st.metric(":material/check_circle: Vinte", n_vinte)
                with col_p:
                    st.metric(":material/cancel: Perse", n_perse)
                with col_c:
                    st.metric(":material/schedule: In corso", n_corso)
                with col_eur:
                    st.metric(":material/payments: Vincita pot.", f"{vincita_mostrata} €")

            st.write("")

            for _, row in df_filtrato.iterrows():
                esito = str(row.get('Esito', ''))
                partita_nome = str(row.get('Partita', ''))
                partita_normalizzata = normalizza_partita_completa(partita_nome, partite_ufficiose)
                risultato_match = risultati_live.get(partita_normalizzata, "")

                if "VINTA" in esito:
                    badge_color, badge_icon = "green", ":material/check_circle:"
                elif "PERSA" in esito:
                    badge_color, badge_icon = "red", ":material/cancel:"
                elif "CORSO" in esito:
                    badge_color, badge_icon = "orange", ":material/schedule:"
                elif "ANNULLATA" in esito:
                    badge_color, badge_icon = "gray", ":material/block:"
                else:
                    badge_color, badge_icon = "gray", ":material/help:"

                with st.container(border=True):
                    col_match, col_esito = st.columns([4, 1])
                    with col_match:
                        st.markdown(f"**:material/sports_soccer: {partita_normalizzata}**")
                        pronostico = row.get('Pronostico', '')
                        quota = row.get('Quota', '')
                        punti = row.get('Punti Partita', '0')
                        tipo = row.get('Tipologia', '')
                        st.caption(
                            f"{tipo} · Pronostico: **{pronostico}** · Quota: **@{quota}** · "
                            f"Punti: **+{punti} pt**"
                        )
                        if risultato_match:
                            st.badge(
                                f"Risultato: {risultato_match}",
                                icon=":material/scoreboard:",
                                color="blue"
                            )
                    with col_esito:
                        st.badge(esito, icon=badge_icon, color=badge_color)
        else:
            st.warning("Schedina non trovata per questo giocatore.", icon=":material/search_off:")
    else:
        st.info("Nessuna giocata registrata.", icon=":material/inbox:")

# ==========================================
# TAB 3: CONFRONTO GIOCATE
# ==========================================
with tab_confronto:
    st.subheader("Confronto giocate per partita")
    st.caption("Scopri cosa ha giocato ogni partecipante per i vari eventi della giornata.")

    if not df_giocate.empty:
        giornate_comp = [
            g for g in df_giocate['Giornata'].dropna().unique() if str(g).strip() != ""
        ]
        if giornate_comp:
            giornata_selezionata_comp = st.selectbox(
                "Giornata da analizzare",
                giornate_comp,
                index=len(giornate_comp) - 1
            )

            df_giornata = df_giocate[
                df_giocate['Giornata'] == giornata_selezionata_comp
            ].copy()

            # Filtra righe spurie: rimuovi header casuali e partite vuote
            df_giornata = df_giornata[
                df_giornata['Partita'].str.strip() != ""
            ]
            df_giornata = df_giornata[
                df_giornata['Giocatore'].str.strip().str.lower() != 'giocatore'
            ]

            if not df_giornata.empty:
                giornata_num_api = str(giornata_selezionata_comp).lower().replace("giornata", "").strip()
                partite_ufficiose, _ = scarica_risultati_api(giornata_num_api)

                df_giornata['Partita_Pulita'] = df_giornata['Partita'].apply(
                    lambda x: normalizza_partita_completa(str(x), partite_ufficiose)
                )

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
                ).fillna("—")

                st.dataframe(pivot, width="stretch", height=420)
            else:
                st.info("Nessuna giocata trovata per questa giornata.")
    else:
        st.info("Nessuna giocata registrata nel database.")

# ==========================================
# TAB 4: STATISTICHE
# ==========================================
with tab_stats:
    st.subheader("Hall of Fame & curiosità")
    st.caption("Analisi basata sulle partite già giocate (escluse le gare ancora in corso o non ancora disputate).")

    if not df_giocate.empty:
        df_stats = df_giocate[df_giocate['Giocatore'].str.strip() != ""].copy()

        def parse_quota(q):
            try:
                return float(str(q).replace(',', '.'))
            except:
                return 0.0

        df_stats['Quota Num'] = df_stats['Quota'].apply(parse_quota)

        # FIX BUG WIN RATE: considera SOLO le partite con esito definitivo (VINTA o PERSA)
        # Esclude: IN CORSO, vuoti, partite future già caricate in bolletta
        df_valutate = df_stats[
            df_stats['Esito'].str.contains("VINTA|PERSA", na=False, regex=True)
        ]

        stats_giocatori = []
        for player in df_stats['Giocatore'].unique():
            df_p_valutate = df_valutate[df_valutate['Giocatore'] == player]
            tot = len(df_p_valutate)
            vinte = len(df_p_valutate[df_p_valutate['Esito'].str.contains("VINTA", na=False)])
            # Quota media solo sulle partite valutate
            quota_media = df_p_valutate['Quota Num'].mean() if tot > 0 else 0.0
            stats_giocatori.append({
                'Giocatore': player,
                'Win_Rate': (vinte / tot * 100) if tot > 0 else 0,
                'Quota_Media': quota_media,
                'Vinte': vinte,
                'Totali': tot
            })

        # Filtra giocatori con almeno 1 partita valutata
        stats_giocatori = [s for s in stats_giocatori if s['Totali'] > 0]

        col_s1, col_s2 = st.columns(2)

        with col_s1:
            st.markdown("#### :material/person: I protagonisti")
            if stats_giocatori:
                df_pg = pd.DataFrame(stats_giocatori)
                cecchino = df_pg.loc[df_pg['Win_Rate'].idxmax()]
                folle = df_pg.loc[df_pg['Quota_Media'].idxmax()]
                conservatore = df_pg.loc[df_pg['Quota_Media'].idxmin()]

                with st.container(border=True):
                    st.markdown("**:material/my_location: Il Cecchino**")
                    st.metric(
                        label=cecchino['Giocatore'].upper(),
                        value=f"{cecchino['Win_Rate']:.1f}% win rate",
                        delta=f"{int(cecchino['Vinte'])}/{int(cecchino['Totali'])} pronostici presi"
                    )

                with st.container(border=True):
                    st.markdown("**:material/whatshot: Quello pazzo in culo**")
                    st.metric(
                        label=folle['Giocatore'].upper(),
                        value=f"Quota media {folle['Quota_Media']:.2f}",
                        delta="Gioca le quote più alte del gruppo"
                    )

                with st.container(border=True):
                    st.markdown("**:material/shield: Il Conservatore**")
                    st.metric(
                        label=conservatore['Giocatore'].upper(),
                        value=f"Quota media {conservatore['Quota_Media']:.2f}",
                        delta="Va sul sicuro"
                    )

        with col_s2:
            st.markdown("#### :material/sports_soccer: Le squadre di Serie A")
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
                    n_amuleto = pd.Series(squadre_vinte).value_counts().max()
                    st.markdown("**:material/auto_awesome: La squadra amuleto**")
                    st.metric(
                        label=amuleto.upper(),
                        value=f"{n_amuleto} vittorie portate",
                        delta="La più fortunata per il gruppo"
                    )
                else:
                    st.markdown("**:material/auto_awesome: La squadra amuleto:** —")

            with st.container(border=True):
                if squadre_perse:
                    maledetta = pd.Series(squadre_perse).value_counts().idxmax()
                    n_maledetta = pd.Series(squadre_perse).value_counts().max()
                    st.markdown("**:material/skull: La squadra maledetta**")
                    st.metric(
                        label=maledetta.upper(),
                        value=f"{n_maledetta} pronostici bruciati",
                        delta="La più scomoda da giocare"
                    )
                else:
                    st.markdown("**:material/skull: La squadra maledetta:** —")

        # --- TABELLA COMPLETA WIN RATE ---
        st.write("")
        with st.expander(":material/table_chart: Tabella completa statistiche giocatori"):
            if stats_giocatori:
                df_pg_full = pd.DataFrame(stats_giocatori).sort_values('Win_Rate', ascending=False)
                st.dataframe(
                    df_pg_full.rename(columns={
                        'Win_Rate': 'Win Rate %',
                        'Quota_Media': 'Quota Media',
                    }),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Giocatore": st.column_config.TextColumn("Giocatore"),
                        "Win Rate %": st.column_config.NumberColumn("Win Rate %", format="%.1f%%"),
                        "Quota Media": st.column_config.NumberColumn("Quota Media", format="%.2f"),
                        "Vinte": st.column_config.NumberColumn("Vinte"),
                        "Totali": st.column_config.NumberColumn("Totali (definitivi)"),
                    }
                )
    else:
        st.info("Nessuna giocata registrata.")

# ==========================================
# TAB 5: REGOLAMENTO
# ==========================================
with tab_regolamento:
    st.subheader("Regolamento ufficiale Toto-Amici")

    col_r1, col_r2 = st.columns(2)

    with col_r1:
        with st.container(border=True):
            st.markdown("#### :material/receipt: 1. La bolletta")
            st.markdown("""
- **Costo:** **5 €** a giornata
- **Composizione obbligatoria:**
  - **1 Combo** (1X2 + O/U 2.5, 1X2 + GG/NG)
  - **4 Fisse** (1, X, 2)
  - **2 Doppie Chance** (1X, X2, 12)
  - **3 Variabili** (Over/Under 2.5, Goal/NoGoal, Pari/Dispari)
            """)

        with st.container(border=True):
            st.markdown("#### :material/savings: 4. Cassa e montepremi")
            st.markdown("""
- **Quota di partecipazione:** **200 €** a persona, entro la 36ª giornata
- **Vincite:** 50% al giocatore, 50% al Fondo Cassa *(da versare subito dopo la vincita)*
            """)
            st.markdown("**Esempio ripartizione premi (15 giocatori · 3.000 €)**")
            df_premi = pd.DataFrame({
                "Posizione": ["🥇 1°", "🥈 2°", "🥉 3°", "4°", "5°"],
                "Premio": ["1.200 €", "800 €", "500 €", "300 €", "200 €"]
            })
            st.dataframe(df_premi, hide_index=True, width="stretch")

    with col_r2:
        with st.container(border=True):
            st.markdown("#### :material/star: 2. Sistema punteggi")
            df_punti = pd.DataFrame({
                "Tipo": ["Combo", "Fisse", "Doppie Chance", "Variabili (O/U, ecc.)", "Bonus chiusura"],
                "Punti base": ["6", "4", "1", "2", "+10"],
                "Con quota ≥ 3.50": ["12", "8", "2", "4", "—"]
            })
            st.dataframe(df_punti, hide_index=True, width="stretch")
            st.caption("🚀 Se la quota di un singolo evento è ≥ 3.50, i punti raddoppiano. Fa fede la quota in bolletta.")

        with st.container(border=True):
            st.markdown("#### :material/gavel: 3. Regole ed errori")
            st.markdown("""
- **Bolletta errata** (es. troppe fisse): le selezioni in eccesso vengono annullate (0 pt). Le corrette restano valide. La bolletta è valida economicamente.
- **Errore in buona fede:** Over 1.5 → vale solo se la partita finisce Over 2.5. Economicamente fa fede la bolletta reale.
- **Scadenza:** bolletta da pubblicare **5 minuti prima** dell'inizio della prima partita. In ritardo → 0 pt e bolletta nulla economicamente.
- **Partite rinviate:** per i punti si aspetta il recupero. Economicamente, se il sito chiude la giocata, la vincita si divide a metà.
            """)