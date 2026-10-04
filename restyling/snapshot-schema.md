# Snapshot JSON — schema del contratto bot ⇄ sito

> Schema **approvato il 04/10/2026** (Fase 0 di [RESTYLING.md](../RESTYLING.md)), `versione_schema: 1`. Le domande aperte della prima stesura sono state chiuse una per una: l'esito è in §17.
> Contratto fra il **bot** (Python: genera lo snapshot e lo salva su Cloudflare KV) e il **nuovo sito** (Vite + React: lo legge, filtra e mostra). Il sito non calcola niente di dominio.
> I riferimenti `app.py:N` e `statistiche.py:N` indicano dove oggi nasce ogni dato (numeri di riga al 04/10/2026, branch `rilascio-3.0`).

## Indice

1. [Regole di formato](#1-regole-di-formato)
2. [I documenti su KV e la struttura generale](#2-i-documenti-su-kv-e-la-struttura-generale)
3. [Radice dello snapshot](#3-radice-dello-snapshot)
4. [`segnale` — segnale di vita](#4-segnale--segnale-di-vita-documento-separato)
5. [`classifica`](#5-classifica)
6. [`cassa`](#6-cassa)
7. [`partite` e `schedine` — Schedine Live e Confronto Giocate](#7-partite-e-schedine--schedine-live-e-confronto-giocate)
8. [`statistiche`](#8-statistiche)
9. [`coppa`](#9-coppa)
10. [`regole` — Regolamento](#10-regole--regolamento)
11. [Mappa scheda → sezioni (copertura)](#11-mappa-scheda--sezioni-copertura)
12. [Enum stabili](#12-enum-stabili)
13. [Differenze attese rispetto al sito di oggi](#13-differenze-attese-rispetto-al-sito-di-oggi)
14. [Dimensione a fine stagione (misurata)](#14-dimensione-a-fine-stagione-misurata)
15. [Funzioni da aggiungere a `statistiche.py`](#15-funzioni-da-aggiungere-a-statistichepy)
16. [Errori, lavoro inutile e punti fragili trovati in `app.py`](#16-errori-lavoro-inutile-e-punti-fragili-trovati-in-apppy)
17. [Decisioni di dettaglio (ex domande aperte)](#17-decisioni-di-dettaglio-ex-domande-aperte)

---

## 1. Regole di formato

| Regola | Perché |
|---|---|
| **`versione_schema`** intera in testa a ogni documento. Si incrementa solo per modifiche **non retrocompatibili** (campo tolto, tipo o significato cambiato); aggiungere un campo opzionale non la cambia. | Bot e sito si deployano in momenti diversi: il sito deve poter riconoscere uno snapshot che non sa leggere e mostrare «aggiornamento in corso» invece di rompersi (stesso problema dell'`ImportError` del 16-18/09 su Streamlit Cloud). |
| **Timestamp ISO 8601 in UTC con la `Z`** (`"2026-10-04T15:30:12Z"`), mai ora locale. Il sito converte in `Europe/Rome`. | Sul server l'ora locale è UTC e con l'ora legale la stessa ora italiana cade a ore UTC diverse; un solo formato senza ambiguità. È anche il formato che Football-Data già usa (`leggi_orario_utc`, `statistiche.py:114`). |
| **Numeri come numeri JSON** (`1674.56`, mai `"1.674,56"`). Importi in euro come `number` con punto decimale. Nessuna unità dentro il valore (niente `"90 pt"`, `"855,70 €"`). | Il punto delle migliaia ha già causato due bug (CLAUDE.md). Il bot converte **una volta**, con `estrai_numero()`; il sito formatta con `Intl.NumberFormat('it-IT')`. |
| **Giornata come intero** (`12`), mai `"Giornata 12"`. | Il confronto per sottostringa ha riscritto 13 giornate (Sessione 13). Con un intero il bug non è nemmeno esprimibile. `"Giornata 12"` è un'etichetta e la compone il sito. |
| **Esiti come enum minuscolo senza emoji** (§12): `vinta`, `persa`, `in_corso`, `annullata`, `rinviata`, `da_verificare`, `da_giocare`. | Nel foglio l'esito è un testo con emoji (`"✅ VINTA"`) che l'app interpreta con `"VINTA" in esito`. Un enum chiuso si può controllare nei test e il sito fa uno `switch`, non un confronto fra stringhe. |
| **Niente stringhe di presentazione** dove il sito può comporle: niente `"🥇 1°"`, `"90 pt"`, `"🟢 ▲2"`, `"1 · 5 su 7"`, `"+14 pt ultima giornata"`. **Sì ai testi di dominio** (titoli e descrizioni delle card, nomi di squadra e di partita, codici di pronostico come `OVER_2.5`). | Emoji, ordinali, unità e frecce sono aspetto grafico e cambieranno con lo stile «Diretta». I testi di dominio restano accanto alla logica che li produce. |
| **Chiavi in italiano `snake_case`**, coerenti col codice (`punti_totali`, `vincita_potenziale`, `ultima_giornata_giocata`). Valori di enum in minuscolo `snake_case`. | Stesso vocabolario di `statistiche.py` e del bot: chi legge lo snapshot trova gli stessi nomi nel codice. |
| **Valori assenti: `null`, mai stringa vuota né `0` finto.** Una chiave non `nullable` è sempre presente. | `0` e «non so» sono cose diverse (una cella vuota in Classifica ≠ 0 punti, `statistiche.py:292`). |
| **Niente dati sensibili**: mai ID Telegram, nomi utente Telegram, chiavi API, `SPREADSHEET_ID`, indirizzi dei fogli. **Niente di più di quanto il sito mostra già** (vincolo 5 di RESTYLING.md). | Lo snapshot è pubblico. Per questo la diagnostica interna (righe scartate, incoerenze) **non** sta nello snapshot: va nel log del bot e negli avvisi agli admin. |
| **Nomi dei giocatori in MAIUSCOLO**, come nel foglio (`"PAOLO"`), senza il suffisso `(RITIRATO)`. La chiave di un giocatore è il suo nome. | È ciò che Giocate e Classifica contengono già (`nome_giocatore.strip().upper()`). I ritirati hanno una lista a parte, quindi il nome non collide mai con quello di un attivo. |
| **Ordine degli array garantito** (e scritto sotto): il sito non riordina. | L'ordinamento (spareggi, orario d'inizio) è logica di dominio e sta in Python. |

---

## 2. I documenti su KV e la struttura generale

Due chiavi su Cloudflare KV, entrambe `versione_schema: 1`:

| Chiave KV | Contenuto | Quando si scrive | Dimensione |
|---|---|---|---|
| `snapshot` | tutto il contenuto (questo documento, §3, §5-§10) | dopo ogni scrittura del bot su Sheets e, ogni 15 minuti, **solo se è cambiato qualcosa** | ~810 KB grezzo, ~54 KB gzip a fine stagione (§14) |
| `segnale` | il segnale di vita (§4) | **a ogni controllo**, anche quando lo snapshot è identico | < 400 byte |

Perché due chiavi: la decisione 2 di RESTYLING.md vuole che il controllo ogni 15 minuti ripubblichi solo se qualcosa è cambiato **e** lasci comunque un segnale di vita. Con un solo documento il segnale costringerebbe a riscrivere ~810 KB a ogni controllo (circa 74 scritture/giorno fuori dalla pausa notturna, comunque sotto il tetto di 1.000: decisione §17.1). Con due chiavi il sito legge il piccolo `segnale` spesso e riscarica lo `snapshot` solo quando cambia l'`impronta`.

Il Worker deve **servire il corpo dello snapshot senza fare `JSON.parse`** (`env.KV.get(chiave, "stream")` → `Response`): il parse di 810 KB misurato in Node su Mac è ~3 ms, e sul piano free i ms di CPU sono 10 in tutto (misura indicativa: non è stata fatta dentro un Worker).

```
snapshot
├── versione_schema, generato_il, stagione, giornata_corrente, giocatori   (§3)
├── classifica      Classifica & Cassa   (§5)
├── cassa           Classifica & Cassa   (§6)
├── partite         Schedine Live + Confronto Giocate  (§7)
├── schedine        Schedine Live + Confronto Giocate  (§7)
├── statistiche     Statistiche          (§8)
├── coppa           Coppa                (§9)
└── regole          Regolamento (+ Coppa, Cassa)  (§10)
```

---

## 3. Radice dello snapshot

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `versione_schema` | int | obbl. | Versione del contratto (oggi `1`). | nuovo |
| `generato_il` | string ISO 8601 UTC | obbl. | Istante in cui il bot ha **costruito** questo contenuto (cambia solo quando cambia il contenuto). Non è il segnale di vita: quello è in `segnale.ultimo_controllo_il`. | `_data_load_time`, `app.py:382` (oggi è l'ora di caricamento della pagina, non l'età dei dati) |
| `stagione` | string `"AAAA-AA"` | obbl. | Etichetta della stagione in corso, es. `"2026-27"`. Il titolo del sito la legge da qui (oggi «Toto-Amici 2026», scritto a mano in `app.py:389`). | `etichetta_stagione()`, `bot_telegram.py:1005`, alimentata da `startDate` della stagione di Football-Data |
| `giornata_corrente` | int | null | **null** se non c'è nessuna giocata | La giornata più alta presente in Giocate: è quella selezionata di default nelle schede Live e Confronto. | `index=len(giornate_disponibili)-1`, `app.py:644` e `:783` (oggi è l'ultima **per ordine di comparsa nel foglio**, non la più alta) |
| `giocatori` | array&lt;string&gt; | obbl. (può essere `[]`) | Nomi di chi ha almeno una riga in Giocate, **in ordine alfabetico**. Sono i «pills» della scheda Live. | `giocatori_disponibili`, `app.py:638-640` |

```json
{
  "versione_schema": 1,
  "generato_il": "2026-10-04T15:30:12Z",
  "stagione": "2026-27",
  "giornata_corrente": 5,
  "giocatori": ["DARIO", "MARIO", "PAOLO", "SIRACUSA"]
}
```
*(le sezioni `classifica`, `cassa`, `partite`, `schedine`, `statistiche`, `coppa`, `regole` sono omesse: seguono nei paragrafi successivi)*

---

## 4. `segnale` — segnale di vita (documento separato)

Documento a parte (chiave KV `segnale`), scritto a ogni controllo del bot.

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `versione_schema` | int | obbl. | Come in §3. | nuovo |
| `ultimo_controllo_il` | string ISO 8601 UTC | obbl. | Ultimo istante in cui il bot ha **verificato** i fogli e confermato che lo snapshot è allineato (anche se non lo ha riscritto). Il sito lo mostra come «Aggiornato alle HH:MM del gg/mm» e avvisa se è troppo vecchio. | nuovo (decisione 3) |
| `generato_il` | string ISO 8601 UTC | obbl. | Uguale a `snapshot.generato_il` dello snapshot attualmente pubblicato. | nuovo |
| `impronta` | string (hex) | obbl. | Hash SHA-256 del contenuto dello snapshot **escluso** `generato_il`. Il sito riscarica `snapshot` solo se è diversa da quella che ha già. Serve anche al bot per decidere se ripubblicare. | nuovo (`impronta_snapshot`, §15) |
| `soglia_allarme_minuti` | int | obbl. | Oltre questi minuti senza controllo il sito mostra l'avviso «dati vecchi». Oggi `120` (decisione 3). | nuovo |
| `pausa_notturna` | object | obbl. | Fascia in cui il bot dorme di proposito e il sito **non** avvisa. | `PAUSA_NOTTURNA_INIZIO/FINE`, `bot_telegram.py:53-54` |
| `pausa_notturna.inizio` | string `"HH:MM"` | obbl. | `"02:00"` | idem |
| `pausa_notturna.fine` | string `"HH:MM"` | obbl. | `"07:30"` | idem |
| `pausa_notturna.fuso` | string | obbl. | `"Europe/Rome"`. Gli orari della pausa sono ora italiana (con l'ora legale `02:00` cade a ore UTC diverse). | `in_pausa_notturna`, `bot_telegram.py:57` |

Perché `pausa_notturna` sta nei dati e non nel React: la fascia è una decisione del bot (Sessione 26); se cambia, deve cambiare in un posto solo. **Regola del sito** (decisione §17.2): `minuti_senza_segnale = (adesso − ultimo_controllo_il) − (minuti di quell'intervallo che cadono dentro la pausa, in ora italiana)`; se supera `soglia_allarme_minuti` mostra l'avviso. Esempio: ultimo controllo 01:55, adesso 07:31 → intervallo 336 min, di cui 330 dentro la pausa (02:00-07:30): restano 6 minuti, nessun allarme. Senza la sottrazione, alle 07:31 scatterebbe un falso allarme ogni mattina.

```json
{
  "versione_schema": 1,
  "ultimo_controllo_il": "2026-10-04T15:45:03Z",
  "generato_il": "2026-10-04T15:30:12Z",
  "impronta": "9f2c1ab07d3e4c55b1c0a8e2f61d7a93c4e5b6d70812ab34cd56ef7890123456",
  "soglia_allarme_minuti": 120,
  "pausa_notturna": { "inizio": "02:00", "fine": "07:30", "fuso": "Europe/Rome" }
}
```

---

## 5. `classifica`

Scheda **Classifica & Cassa**, parte alta: podio, classifica completa con tendenza, storico per giornata.

### 5.1 Oggetto `classifica`

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `ultima_giornata_giocata` | int | null | **null** se nessuno ha ancora punti | Ultima giornata con almeno un punteggio diverso da 0 fra i giocatori attivi. È la giornata a cui si riferiscono `variazione_posizione` e `punti_ultima_giornata`. | `ultima_giocata`, `app.py:486-492` |
| `giocatori` | array&lt;riga&gt; | obbl. | Giocatori **attivi**, già in ordine di classifica. Le prime tre righe sono il **podio**; un pari merito si riconosce dalla `posizione` uguale. | `df_classifica` ordinato e senza ritirati, `app.py:433-441` |
| `ritirati` | array&lt;ritirato&gt; | obbl. (può essere `[]`) | Giocatori ritirati (nel foglio `NOME (RITIRATO)`), in ordine di punti decrescenti e, a parità di punti, **alfabetico per nome**. Il sito li mette in fondo alla classifica con la dicitura «Ritirato». | `df_ritirati`, `app.py:440`, `:531-543` |

### 5.2 `riga` di `giocatori`

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `posizione` | int | obbl. | Posizione **esplicita** con ranking sportivo (decisione §17.15): a parità di `punti_totali` **e** di pronostici vinti la **stessa** posizione, e la successiva salta (4°, 4°, 6°). Ordine delle righe: `punti_totali` decrescente, poi pronostici vinti decrescente, poi nome alfabetico (solo per fissare l'ordine delle righe: a quel punto la posizione è già uguale). I pronostici vinti del sostituto includono quelli del ritirato (§17.17). | `app.py:433-435`; `classifica_per_coppa` ripete lo stesso criterio, `statistiche.py:288` (oggi: posizioni consecutive per ordine del foglio, differenza A10) |
| `nome` | string | obbl. | Nome in maiuscolo. | `Giocatore` |
| `punti_totali` | int | obbl. | Colonna «Punti Totali» del foglio (la somma la scrive il bot). | `app.py:421-423` |
| `variazione_posizione` | int | null | **null** se non c'è una giornata precedente con cui confrontare | Posizioni guadagnate (`posizione` prima − `posizione` ora, con lo stesso ranking sportivo) rispetto alla classifica prima di `ultima_giornata_giocata`: **positivo = salito**, `0` = invariata, negativo = sceso. La classifica precedente usa lo **stesso spareggio**, con i pronostici vinti **fino alla giornata precedente** (§17.16). Il sito compone «🟢 ▲2», «⚪ –», «🔴 ▼1». Differenza attesa P9a, §13. | `tendenza_per_giocatore`, `app.py:485-510` |
| `punti_ultima_giornata` | int | null | **null** se `ultima_giornata_giocata` è null | Punti fatti in `ultima_giornata_giocata` (0 se la cella è vuota). Il sito li usa per «+14 pt ultima giornata» sul podio. | `delta_str`, `app.py:464-465` — **oggi non funziona**, vedi §16 D1 |
| `punti_per_giornata` | array&lt;int \| null&gt; | obbl. | Un elemento per giornata: **indice 0 = Giornata 1**. `null` = cella vuota (quel giocatore non ha una schedina valutata in quella giornata), **diverso da `0`**. Lunghezza = ultima giornata con almeno una cella non vuota fra tutti i giocatori (attivi e ritirati); le colonne future del foglio non ci sono. Una colonna `null` per tutti si nasconde. | «Storico punteggi per giornata», `app.py:546-554`; `punti_per_giornata()`, `statistiche.py:292` |

### 5.3 `ritirato`

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `nome` | string | obbl. | Senza suffisso: `"PULIZZER"`. | `nome_senza_ritiro`, `statistiche.py:39` |
| `punti_totali` | int | obbl. | Punti congelati nella riga `(RITIRATO)`. | `app.py:538-539` |
| `punti_per_giornata` | array&lt;int \| null&gt; | obbl. | Come sopra, stessa lunghezza dell'array degli attivi. | `app.py:548-551` |

```json
{
  "ultima_giornata_giocata": 4,
  "giocatori": [
    { "posizione": 1, "nome": "PAOLO", "punti_totali": 61, "variazione_posizione": 2,
      "punti_ultima_giornata": 18, "punti_per_giornata": [14, 12, 17, 18] },
    { "posizione": 2, "nome": "DARIO", "punti_totali": 57, "variazione_posizione": 2,
      "punti_ultima_giornata": 15, "punti_per_giornata": [20, 9, 13, 15] },
    { "posizione": 3, "nome": "MARIO", "punti_totali": 54, "variazione_posizione": -1,
      "punti_ultima_giornata": 10, "punti_per_giornata": [15, 17, 12, 10] },
    { "posizione": 3, "nome": "SIRACUSA", "punti_totali": 54, "variazione_posizione": -2,
      "punti_ultima_giornata": 0, "punti_per_giornata": [30, 20, 4, 0] }
  ],
  "ritirati": [
    { "nome": "PULIZZER", "punti_totali": 90, "punti_per_giornata": [30, 20, 25, 15] }
  ]
}
```
*(esempio a 4 giocatori; MARIO e SIRACUSA sono pari a 54 e a pari pronostici vinti: stessa posizione 3, il successivo sarebbe il 5°; l'ordine delle due righe è alfabetico. A fine stagione `giocatori` ha 16 righe e `punti_per_giornata` 38 elementi.)*

---

## 6. `cassa`

Scheda **Classifica & Cassa**, parte bassa: Fondo Cassa, barra di avanzamento, grafico dei versamenti, tabella dei movimenti.

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `saldo` | number | obbl. | Montepremi attuale in euro. **Somma di tutte le `Entrate`** (come `saldo_cassa()` del bot), non l'ultima cella «Saldo Totale». `0` se non ci sono movimenti. (Differenza attesa A2, §13: oggi si legge l'ultima cella; verificata sul foglio vero, oggi coincide: 1 riga, 430,00 €.) | `ultimo_saldo_str`, `app.py:564-569`; `saldo_cassa`, `bot_telegram.py:1168` |
| `obiettivo` | number | obbl. | Obiettivo Cassa in euro (`3200`). | `OBIETTIVO_CASSA`, `app.py:165` |
| `completamento` | number | obbl. | `saldo / obiettivo`, **limitato a 1** (0…1). Il sito lo mostra in % e come barra. | `progresso`, `app.py:571-572` |
| `obiettivo_raggiunto` | bool | obbl. | `saldo >= obiettivo` (messaggio «OBIETTIVO RAGGIUNTO!»). | `app.py:584-585` |
| `movimenti` | array&lt;movimento&gt; | obbl. (può essere `[]`) | Righe del foglio Cassa **nell'ordine del foglio**. | `df_cassa_view`, `app.py:619-622` |
| `versamenti_per_giornata` | array&lt;{giornata, versato}&gt; | obbl. | Un elemento per ogni giornata presente in Cassa **o** in Giocate (anche a zero), **ordinato per giornata crescente**. È il grafico a barre. | `versamenti_map`, `giornate_cassa`, `app.py:595-617` |

`movimento`:

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `giornata` | int | null | **null** se l'etichetta del foglio non è «Giornata N». Oggi tutte le righe di Cassa sono «Giornata N» (verificato sui dati veri): le eventuali future righe diverse restano fuori dal grafico ma nella tabella (§17.10) | Giornata del movimento. | colonna `Giornata` |
| `descrizione` | string | obbl. | Testo del movimento, es. `"PAOLO chiude la schedina!"`. Testo di dominio, mostrato così. | colonna `Descrizione` |
| `entrata` | number | null | **null** se la cella è vuota | Importo versato in euro. | colonna `Entrate` |
| `saldo` | number | null | **null** se la cella è vuota | «Saldo Totale» scritto nel foglio **a quella riga**, mostrato nella tabella dei movimenti. Può non coincidere col `saldo` complessivo se qualcuno ha corretto il foglio a mano. | colonna `Saldo Totale` |

`versamenti_per_giornata[]`: `{ "giornata": int, "versato": number }` — `versato` è la somma delle `entrata` con quella `giornata`.

```json
{
  "saldo": 845.2,
  "obiettivo": 3200.0,
  "completamento": 0.264125,
  "obiettivo_raggiunto": false,
  "movimenti": [
    { "giornata": 1, "descrizione": "PAOLO chiude la schedina!", "entrata": 417.35, "saldo": 417.35 },
    { "giornata": 3, "descrizione": "DARIO chiude la schedina!", "entrata": 305.0, "saldo": 722.35 },
    { "giornata": 3, "descrizione": "MARIO chiude la schedina!", "entrata": 122.85, "saldo": 845.2 }
  ],
  "versamenti_per_giornata": [
    { "giornata": 1, "versato": 417.35 },
    { "giornata": 2, "versato": 0.0 },
    { "giornata": 3, "versato": 427.85 },
    { "giornata": 4, "versato": 0.0 }
  ]
}
```

---

## 7. `partite` e `schedine` — Schedine Live e Confronto Giocate

Le righe di Giocate sono **pulite** (decisione 1 di RESTYLING.md) e organizzate in due liste:

- `partite`: ogni partita **una volta sola**, con l'`id` di Football-Data, il nome ufficiale, l'orario e la «scelta del gruppo». Serve al Worker (abbinamento per **id**, decisione 4 di RESTYLING.md) e al Confronto.
- `schedine`: una per coppia (giornata, giocatore), con la vincita potenziale e le sue righe, che puntano a una partita con `partita_id`.

Perché annidare le righe nella schedina invece di una lista piatta: la vincita potenziale è un dato **della schedina**, nel foglio sta solo sulla prima riga (`riga.extend(["", vincita])`, `bot_telegram.py:955-958`) e l'app la cerca come «primo valore non vuoto» (`app.py:662-666`, `:846-854`); filtrare per giornata e giocatore diventa un `find`; e la misura (§14) dà ~11% di grezzo in meno, a parità di gzip (decisione §17.4).

### 7.1 `partite[]`

**Ordine garantito**: per giornata crescente e, dentro la giornata, per calcio d'inizio (`ordina_partite_per_orario`, `statistiche.py:360`): prima le partite con orario, poi quelle senza, in ordine alfabetico. Il sito non riordina: è lo stesso ordine delle righe del Confronto e delle carte della scheda Live (oggi i due ordinamenti sono diversi, §16 D6). Contiene solo le partite che compaiono in almeno una riga di Giocate.

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `id` | int | obbl. | **`id` della partita su Football-Data** (`match.id`): stabile fra snapshot diversi. Il Worker abbina i risultati live **per id**, non per nome (decisione §17.5); le righe delle schedine lo usano come `partita_id`. Se `ufficiale` è `false` non esiste un id reale: si assegna un intero **negativo** progressivo (`-1`, `-2`…) valido solo dentro questo snapshot, che il Worker ignora. | nuovo |
| `giornata` | int | obbl. | Giornata di campionato (`matchday` di Football-Data se `ufficiale`, altrimenti quella del foglio). | colonna `Giornata` |
| `nome` | string | obbl. | Se `ufficiale` è `true`: nome ufficiale Football-Data nel formato **`"<casa> - <ospite>"`** con i nomi completi (`"FC Internazionale Milano - ACF Fiorentina"`), come `f"{casa_full} - {ospite_full}"` (`app.py:275`). È solo testo da mostrare: l'abbinamento del Worker è per `id`. Se `false`: il testo scritto nel foglio, senza `title()`. | `normalizza_partita_completa`, `app.py:360-371` (spostata in Python, decisione 1 di RESTYLING.md) |
| `ufficiale` | bool | obbl. | `true` se la riga del foglio è stata abbinata a una partita reale **di quella giornata** (§7.3). `false` = nessuna partita trovata: il sito la mostra senza risultato e non la manda al Worker. | nuovo: oggi il fallimento è silenzioso (`squadra_raw.title()`, `app.py:358`) |
| `inizio_il` | string ISO 8601 UTC | null | **null** se non noto | Calcio d'inizio **al momento della generazione** (`utcDate` di Football-Data). Serve a ordinare e come ripiego se il Worker non risponde; la fonte viva dell'orario è il Worker (decisione 4 di Fase 0 e Fase 3). Decisione §17.6. | `data` / `utc`, `app.py:279-304` |
| `scelta_gruppo` | object | obbl. | Pronostico più giocato su questa partita (colonna «Scelta del gruppo» del Confronto). Vedi sotto. | `scelta_del_gruppo`, `statistiche.py:194`; `app.py:869-875` |

`scelta_gruppo`:

| Campo | Tipo | Obbl. / null | Significato |
|---|---|---|---|
| `tipo` | enum | obbl. | `maggioranza` (almeno un pronostico scelto da ≥ 2 giocatori, oppure un solo giocatore), `tutti_diversi` (nessun pronostico scelto da almeno due giocatori, con più di un giocatore), `nessuna` (nessun pronostico valido). Il sito compone «Tutti diversi» / «—». |
| `pronostici` | array&lt;string&gt; | obbl. | I pronostici a pari voti più alto, **in ordine alfabetico** (es. `["1", "X"]` per «1 / X»). `[]` se `tipo` ≠ `maggioranza`. Conta solo il pronostico **identico**: `1+OVER_2.5` non vale come `1`; ogni giocatore conta una volta per pronostico. **Le selezioni annullate («… (ANNULLATA ECCESSO)», esito `annullata`) non contano come voto** (decisione §17.18, differenza attesa A11). |
| `voti` | int | obbl. | Quanti giocatori hanno scelto quel pronostico (`1` se `tutti_diversi`, `0` se `nessuna`). |
| `su` | int | obbl. | Quanti giocatori hanno un voto valido (non annullato) su questa partita. Il sito compone «5 su 7». |

```json
[
  { "id": 535201, "giornata": 5, "nome": "FC Internazionale Milano - ACF Fiorentina", "ufficiale": true,
    "inizio_il": "2026-09-20T16:00:00Z",
    "scelta_gruppo": { "tipo": "maggioranza", "pronostici": ["1"], "voti": 5, "su": 7 } },
  { "id": 535202, "giornata": 5, "nome": "AS Roma - SS Lazio", "ufficiale": true,
    "inizio_il": "2026-09-20T18:45:00Z",
    "scelta_gruppo": { "tipo": "tutti_diversi", "pronostici": [], "voti": 1, "su": 7 } },
  { "id": -1, "giornata": 5, "nome": "Pisa - Cremo", "ufficiale": false,
    "inizio_il": null,
    "scelta_gruppo": { "tipo": "maggioranza", "pronostici": ["1", "X"], "voti": 3, "su": 6 } }
]
```

### 7.2 `schedine[]`

**Ordine garantito**: per `giornata` crescente, poi `giocatore` alfabetico. Dentro `righe`: lo stesso ordine di `partite` (calcio d'inizio), a parità l'ordine del foglio (Combo, Fisse, Doppie Chance, Variabili).

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `giornata` | int | obbl. | Giornata. | `Giornata`, `app.py:656-659` |
| `giocatore` | string | obbl. | Nome in maiuscolo. | `Giocatore` |
| `vincita_potenziale` | number | obbl. | Vincita potenziale in euro; `0` se nel foglio non c'è un valore valido. Primo valore non vuoto e maggiore di zero fra le righe della schedina. | `vincita_mostrata`, `app.py:661-666`; `vincita_map`, `app.py:846-854` |
| `riepilogo` | object | obbl. | Conteggio delle righe per esito **così come salvato nel foglio** (decisione 9: la scheda Live conta anche rinviate, da verificare, annullate). Chiavi: `vinte`, `perse`, `in_corso`, `rinviate`, `da_verificare`, `annullate`, `da_giocare` (tutti int ≥ 0; la somma è `righe.length`). Il passaggio `da_giocare` → `in_corso` quando il live dice che la partita è iniziata lo fa il sito (decisione 8) e ricalcola lui il riepilogo a video. | `n_vinte/n_perse/n_corso`, `app.py:669-671` |
| `righe` | array&lt;riga&gt; | obbl. | Le selezioni della schedina (di norma 10: 1 Combo, 4 Fisse, 2 Doppie Chance, 3 Variabili). | `df_filtrato`, `app.py:706-762` |

`riga`:

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `partita_id` | int | obbl. | `id` in `partite` (id Football-Data, negativo se `ufficiale: false`): da lì si leggono `nome`, `inizio_il`, `ufficiale`. | `Partita_Pulita`, `app.py:802-804` |
| `tipologia` | enum | null | `combo` \| `fisse` \| `doppie_chance` \| `variabili`; **null** se il foglio contiene altro. Il sito compone «Doppie Chance». | colonna `Tipologia`, `app.py:740` |
| `pronostico` | string | obbl. | Pronostico normalizzato **così com'è nel foglio**: `"1"`, `"1X"`, `"1+OVER_2.5"`, `"GOAL"`, `"OVER_2.5 (ANNULLATA ECCESSO)"`. Contiene underscore per costruzione: nel sito non è Markdown, quindi niente problema di escape. | colonna `Pronostico` |
| `quota` | number | null | **null** se vuota o non leggibile (mai `0`). Con `estrai_numero`. Il sito mostra `@2.35` e l'asterisco se `quota >= regole.soglia_quota_doppia`. | `Quota`, `app.py:810-815` |
| `esito` | enum | obbl. | Vedi §12. Cella vuota → `da_giocare`. | `Esito`, `app.py:714-727` |
| `punti` | int | obbl. | «Punti Partita» scritti dal bot (`0` se vuoto). Il sito mostra «+N pt». | `Punti Partita`, `app.py:739` |

Come il sito costruisce le due schede **senza calcolare**:

- **Schedine Live**: sceglie giornata e giocatore, `schedine.find(...)`, e per ogni `riga` cerca la partita con `id == riga.partita_id`. Il punteggio e lo stato del live vengono dal Worker, abbinati con `partite[...].id` (id Football-Data; le partite con `ufficiale: false` non vanno al Worker). Regola già presente oggi (`app.py:742-751`): se l'esito è finale (`vinta`, `persa`, `annullata`) non si mostra «Da giocare» dal live.
- **Confronto Giocate**: sceglie la giornata, prende le `partite` di quella giornata (già in ordine) come righe e le `schedine` di quella giornata come colonne; la cella è l'insieme delle `righe` con quel `partita_id` (può essercene più di una: si uniscono con « | ») colorata per `esito` (`vinta` verde, `persa` rosso, gli altri nessun colore, come oggi `app.py:880-886`). La riga «Vincita potenziale» è `schedina.vincita_potenziale`; l'ultima colonna è `partita.scelta_gruppo`.

```json
{
  "giornata": 5,
  "giocatore": "PAOLO",
  "vincita_potenziale": 855.7,
  "riepilogo": { "vinte": 2, "perse": 0, "in_corso": 1, "rinviate": 0,
                 "da_verificare": 0, "annullate": 0, "da_giocare": 0 },
  "righe": [
    { "partita_id": 535201, "tipologia": "combo", "pronostico": "1+OVER_2.5", "quota": 3.85,
      "esito": "vinta", "punti": 12 },
    { "partita_id": 535202, "tipologia": "fisse", "pronostico": "X", "quota": 3.2,
      "esito": "vinta", "punti": 4 },
    { "partita_id": -1, "tipologia": "variabili", "pronostico": "GOAL", "quota": 1.7,
      "esito": "in_corso", "punti": 0 }
  ]
}
```
*(esempio abbreviato a 3 righe; il `riepilogo` conta le righe mostrate)*

### 7.3 Abbinamento delle righe del foglio alle partite

Dato verificato sui dati veri: nelle Giornate 1-2 il foglio Giocate ha nomi partita **disordinati** (29 scritture diverse per 10 partite in G1: maiuscole diverse, suffissi come «Sassuolo Calcio», «Como 1907», «Venezia FC»); dalla G3 coincidono con lo `shortName` di Football-Data. Regola (decisione 4 di RESTYLING.md, §17.5):

1. Il bot fa **una sola** chiamata `GET /v4/competitions/SA/matches` (senza `matchday`: 380 partite, ~353 KB, `id`, `matchday`, `utcDate`, `status`, `shortName`/`name`, `score.fullTime` sempre presenti; `season.currentMatchday` esiste, §17.3) per **pubblicazione**, non una per giornata.
2. Per ogni riga di Giocate considera **solo le 10 partite di quella giornata** (`matchday` = giornata della riga).
3. Divide il testo del foglio in due squadre, le normalizza (minuscole, spazi, senza suffissi societari: «FC», «AC», «Calcio», «1907»…) e le confronta, per **uguaglianza** delle forme normalizzate (non per sottostringa), con quelle delle due squadre di ciascuna partita (sia `shortName` sia `name`); prova anche le squadre invertite, come già fa `esegui_calcolo_risultati` (`bot_telegram.py:1321-1330`). Se **una sola** partita corrisponde, la riga prende il suo `id` Football-Data.
4. Se nessuna partita corrisponde (o ne corrispondono due), il bot **non indovina**: la riga è pubblicata come `ufficiale: false` (id negativo, nome come scritto nel foglio) e il bot **avvisa gli admin** con `avvisa_admin()` (giornata, giocatore, testo), senza ripetere lo stesso avviso a ogni controllo (stato nel foglio `Stato`).

Conseguenza: la normalizzazione per sottostringa contro le 20 squadre (§16 D11) non serve più. Se la chiamata a Football-Data fallisce (dopo `richiedi_con_retry`), il bot **non pubblica** e tiene lo snapshot precedente (stessa regola del §17.13): meglio dati vecchi che tutte le righe «non ufficiali».

---

## 8. `statistiche`

Scheda **Statistiche**. Tutti i calcoli sono in Python; i titoli e le descrizioni delle card **non** sono nello snapshot: sono testo statico nel React (decisione §17.24). Nello snapshot restano le chiavi fisse di `premi` e i numeri.

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `ultima_schedina_vinta` | object | null | **null** se nessuna schedina è mai stata chiusa. Vedi §8.1. | `app.py:1022-1060` |
| `premi` | object | obbl. | Le card «I protagonisti» e «Le squadre di Serie A». Vedi §8.2. | `app.py:1116-1259` |
| `per_un_soffio` | array&lt;soffio&gt; | obbl. (può essere `[]`) | Schedine perse per un solo evento. Vedi §8.3. | `app.py:1261-1283` |
| `giocatori` | array&lt;stat&gt; | obbl. | Tabella completa: un elemento per giocatore con almeno una partita valutata, **ordinato per `win_rate` decrescente** (sul valore esatto `vinte / totali`), a parità `totali` decrescente e poi nome. | `app.py:1287-1300` |
| `ritirati` | array&lt;stat&gt; | obbl. (può essere `[]`) | Statistiche congelate dei ritirati (dalle schedine del sostituto fino all'ultima giornata con punti nella riga congelata). Fuori dai premi. Ordine: punti decrescenti della riga congelata, poi **nome alfabetico**. | `stats_ritirati`, `app.py:1099-1109` |

`stat` (riga della tabella completa):

| Campo | Tipo | Obbl. | Significato |
|---|---|---|---|
| `nome` | string | obbl. | Giocatore (ritirati senza suffisso). |
| `win_rate` | number | obbl. | `vinte / totali * 100`, 0-100, già **arrotondato a 1 decimale** dal Python come lo mostra oggi il sito (decisione §17.27: sito vecchio e nuovo coincidono). |
| `quota_media` | number \| null | obbl. | Media delle quote **numeriche** delle sole righe valutate, già **arrotondata a 2 decimali** dal Python (§17.27). **`null` = nessuna quota leggibile** fra le righe valutate: il giocatore **non concorre** per «Il Folle» e «Il Conservatore» (mai uno 0 finto, A4); il sito mostra «—» nella tabella. |
| `vinte` | int | obbl. | Righe `vinta`. |
| `totali` | int | obbl. | Righe `vinta` o `persa` (le `in_corso`, `rinviate`, `da_verificare`, `annullata`, `da_giocare` non contano). |

### 8.1 `ultima_schedina_vinta`

Il timer «Tempo passato dall'ultima schedina vinta». L'istante di partenza lo calcola il Python (decisione 5); il conteggio che scorre lo fa il sito.

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `giornata` | int | obbl. | Ultima giornata con almeno una schedina chiusa, ricavata dalle righe «chiude la schedina» di Cassa (il verdetto già verificato dal bot). | `schedine_chiuse_ultima_giornata`, `statistiche.py:90` |
| `vincitori` | array&lt;string&gt; | obbl. | Chi ha chiuso in quella giornata (senza doppioni). | idem |
| `inizio_il` | string ISO 8601 UTC | null | Fine stimata dell'**ultima** partita fra le schedine dei vincitori (inizio + 2 h). **null** se anche una sola partita non ha un orario noto o non è stata abbinata: meglio nessun timer che uno partito dal momento sbagliato. Il sito mostra «chiusa il gg/mm verso le HH:MM» da qui. | `momento_fine_schedina`, `statistiche.py:122`; `app.py:1032-1053` |

### 8.2 `premi`

Un oggetto con chiavi fisse. Ogni chiave vale **`null`** se non c'è un dato da mostrare (il sito mostra «—» o nasconde la card, come oggi), altrimenti un **array non vuoto di vincitori**: a pari merito ci sono **tutti** i pari merito (decisione §17.14, differenza attesa A9), in ordine alfabetico per `giocatore` (o per `squadra`; a parità, per giornata). **Nessun minimo di pronostici**: con una sola partita valutata chi l'ha presa è «Il Cecchino» al 100%, e a inizio stagione i pari merito possono essere molti (anche tutti i giocatori): lo gestisce il React. I confronti si fanno sui valori **esatti**, prima dell'arrotondamento.

Titoli e descrizioni delle card stanno nel React (§17.24): qui solo i dati.

| Chiave | Elemento dell'array | Regola | Origine oggi |
|---|---|---|---|
| `cecchino` | `{giocatore, win_rate, vinte, totali}` | `win_rate` più alto. Il sito compone «5/7 pronostici presi». | `app.py:1120`, `:1125-1131` |
| `benedizione` | come `cecchino` | `win_rate` più basso. | `app.py:1121`, `:1133-1140` |
| `folle` | `{giocatore, quota_media}` | Quota media più alta. | `app.py:1122`, `:1142-1148` |
| `conservatore` | `{giocatore, quota_media}` | Quota media più bassa. | `app.py:1123`, `:1150-1156` |
| `giornata_da_incorniciare` | `{giocatore, giornata, punti}` | Punteggio più alto in una singola giornata. Solo giocatori attivi; **null** se nessuno ha mai fatto più di 0. | `app.py:1158-1178` |
| `semper_fidelis` | `{giocatore, squadra, volte}` | `volte` = **giornate distinte** (§17.19) in cui il giocatore ha almeno un pronostico sulla stessa squadra (nome ufficiale), contando **solo partite giocate** (esito finale: `vinta` o `persa`) e pronostici **non annullati**. **null** se il massimo è < 2. | `app.py:1180-1221` |
| `squadra_amuleto` | `{squadra, vittorie_portate}` | Squadra (nome ufficiale) con più pronostici `vinta` **su di lei** (§17.20). | `app.py:1234-1245` |
| `squadra_maledetta` | `{squadra, pronostici_bruciati}` | Squadra con più pronostici `persa` su di lei. | `app.py:1247-1259` |

**Squadra scelta da un pronostico** (per Semper Fidelis, amuleto e maledetta, decisione §17.20): `1` e `1X` → squadra di casa; `2` e `X2` → ospite; nelle combo (`1+OVER_2.5`) vale il primo segno prima del `+`. Tutto il resto (`X`, `12`, `OVER_…`, `UNDER_…`, `GOAL`/`NOGOAL`, `PARI`, `DISPARI`) **non conta per nessuna squadra**. Le righe `ufficiale: false` non hanno una squadra ufficiale e non contano.

Le prime quattro e `giornata_da_incorniciare` sono `null` se non c'è nessun giocatore con partite valutate (oggi la sezione resta vuota, `app.py:1118`).

### 8.3 `soffio` (Per un soffio)

| Campo | Tipo | Obbl. / null | Significato |
|---|---|---|---|
| `giocatore` | string | obbl. | Nome in maiuscolo. |
| `giornata` | int | obbl. | Giornata. |
| `partita` | string | obbl. | L'evento sbagliato (nome ufficiale se abbinata, altrimenti come nel foglio). |
| `pronostico` | string | obbl. | Pronostico sbagliato. |
| `quota` | number | null | Quota dell'evento sbagliato. |

Ordine: giornata più recente per prima, poi nome (`statistiche.py:191`). Una schedina conta solo se **esattamente una** riga è `persa` e tutte le altre `vinta` o `annullata` (con almeno una `vinta`): una schedina ancora aperta non compare (`statistiche.py:152`).

```json
{
  "ultima_schedina_vinta": { "giornata": 3, "vincitori": ["DARIO", "MARIO"], "inizio_il": "2026-09-14T20:55:00Z" },
  "premi": {
    "cecchino": [ { "giocatore": "PAOLO", "win_rate": 58.3, "vinte": 28, "totali": 48 } ],
    "benedizione": [ { "giocatore": "VILLARI", "win_rate": 33.3, "vinte": 16, "totali": 48 },
                     { "giocatore": "ZETA", "win_rate": 33.3, "vinte": 16, "totali": 48 } ],
    "folle": [ { "giocatore": "MIRKO", "quota_media": 2.92 } ],
    "conservatore": [ { "giocatore": "FAZIO", "quota_media": 1.98 } ],
    "giornata_da_incorniciare": [ { "giocatore": "DARIO", "giornata": 3, "punti": 41 } ],
    "semper_fidelis": [ { "giocatore": "PAOLO", "squadra": "SSC Napoli", "volte": 4 } ],
    "squadra_amuleto": [ { "squadra": "Juventus FC", "vittorie_portate": 31 } ],
    "squadra_maledetta": [ { "squadra": "US Lecce", "pronostici_bruciati": 27 } ]
  },
  "per_un_soffio": [
    { "giocatore": "MARIO", "giornata": 4, "partita": "Torino FC - Genoa CFC",
      "pronostico": "OVER_2.5", "quota": 1.85 }
  ],
  "giocatori": [
    { "nome": "PAOLO", "win_rate": 58.3, "quota_media": 2.41, "vinte": 28, "totali": 48 },
    { "nome": "VILLARI", "win_rate": 33.3, "quota_media": 2.1, "vinte": 16, "totali": 48 }
  ],
  "ritirati": [
    { "nome": "PULIZZER", "win_rate": 44.4, "quota_media": 2.5, "vinte": 16, "totali": 36 }
  ]
}
```

---

## 9. `coppa`

Scheda **Coppa**: tabellone a 16 su 4 turni (ottavi alla 35ª, quarti 36ª, semifinali 37ª, finale 38ª).

| Campo | Tipo | Obbl. / null | Significato | Origine oggi |
|---|---|---|---|---|
| `definitiva` | bool | obbl. | `true` quando la Giornata 34 è **conclusa** (`34 in giornate_concluse`): la classifica che alimenta il tabellone non può più cambiare. Decide se il tabellone è «definitivo» o «provvisorio» e quale riquadro informativo mostrare (decisione §17.21, differenza attesa A14). | `coppa_iniziata`, `app.py:1316-1318` (oggi: basta una riga di giornata ≥ 35 in Giocate) |
| `partecipanti` | int | obbl. | Giocatori attivi usati per il tabellone (ritirati esclusi). Il tabellone è fatto per 16. | `len(partecipanti_coppa)`, `app.py:1319`, `:1420` |
| `tabellone_disponibile` | bool | obbl. | `false` se `partecipanti` ≠ 16: i turni sono scheletri vuoti e il sito mostra l'avviso «il tabellone è pensato per 16 partecipanti, ora ce ne sono N». | `if ottavi`, `app.py:1321-1327`, `:1418-1423`; `tabellone_ottavi`, `statistiche.py:228` |
| `prima_giornata` | int | obbl. | `35`. | `PRIMA_GIORNATA_COPPA`, `statistiche.py:251` |
| `ultima_giornata_tabellone` | int | obbl. | `34`: fino a qui il tabellone segue la classifica, poi è fisso. | `ULTIMA_GIORNATA_TABELLONE`, `statistiche.py:252` |
| `turni` | array&lt;turno&gt; | obbl. | Sempre 4 elementi, in ordine. | `turni_coppa`, `statistiche.py:324` |
| `campione` | voce | null | **null** finché la finale non ha un vincitore. | `app.py:1361-1366` |

`turno`: `{ "turno": enum, "giornata": int, "sfide": array<sfida> }` con `turno` ∈ `ottavi` \| `quarti` \| `semifinali` \| `finale` (il sito mette le maiuscole: `TURNI_COPPA`, `statistiche.py:250`) e `sfide` di 8, 4, 2, 1 elementi **nell'ordine del tabellone** (le sfide 1-2 degli ottavi vanno nel primo quarto, 3-4 nel secondo…: «Vincente ottavo N» lo compone il sito dall'indice).

`sfida`:

| Campo | Tipo | Obbl. / null | Significato |
|---|---|---|---|
| `giocatori` | array di 2 (`voce` \| null) | obbl. | **null** se il giocatore non è ancora noto (turno precedente non concluso o `tabellone_disponibile` false). |
| `punti` | array di 2 (int \| null) | obbl. | Punti nella giornata del turno; **null** se ancora senza punti o giocatore ignoto. |
| `vincente` | int (0 \| 1) | null | Indice in `giocatori`. **null** finché la giornata non è conclusa. A parità di punti passa chi era più in alto nella classifica del tabellone. |

`voce`: `{ "posizione": int, "nome": string }` — la posizione è quella della classifica del tabellone (non una stringa «3°»). A pari punti e pari pronostici vinti il tabellone ordina i giocatori in **ordine alfabetico** (deterministico: non dipende dall'ordine del foglio).

```json
{
  "definitiva": false,
  "partecipanti": 16,
  "tabellone_disponibile": true,
  "prima_giornata": 35,
  "ultima_giornata_tabellone": 34,
  "turni": [
    { "turno": "ottavi", "giornata": 35, "sfide": [
        { "giocatori": [ { "posizione": 1, "nome": "PAOLO" }, { "posizione": 16, "nome": "VILLARI" } ],
          "punti": [null, null], "vincente": null }
    ] },
    { "turno": "quarti", "giornata": 36, "sfide": [
        { "giocatori": [null, null], "punti": [null, null], "vincente": null }
    ] },
    { "turno": "semifinali", "giornata": 37, "sfide": [
        { "giocatori": [null, null], "punti": [null, null], "vincente": null }
    ] },
    { "turno": "finale", "giornata": 38, "sfide": [
        { "giocatori": [null, null], "punti": [null, null], "vincente": null }
    ] }
  ],
  "campione": null
}
```
*(esempio abbreviato: `sfide` ha 1 elemento invece di 8, 4, 2, 1)*

---

## 10. `regole` — Regolamento

Il **testo** del regolamento (frasi, titoli dei riquadri) resta nel sito: è copia statica. Nello snapshot stanno i **numeri**, perché esistono già nel codice del bot (`LIMITI_SCHEDINA`, `bot_telegram.py:324`; `calcola_punteggio_partita`, `:1267`; `OBIETTIVO_CASSA`, `app.py:165`) e scriverli anche a mano nel React vorrebbe dire tre copie da tenere allineate. Nello snapshot da una costante `REGOLE` in `statistiche.py` (decisione §17.25).

| Campo | Tipo | Valore | Origine oggi |
|---|---|---|---|
| `costo_giornata` | number | `5` (€ a giornata) | `app.py:1467` |
| `quota_partecipazione` | number | `200` (€ a persona) | `app.py:1498` |
| `scadenza_quota_giornata` | int | `36` («entro la 36ª giornata») | `app.py:1498` |
| `quota_cassa_su_vincita` | number | `0.5` (50% al Fondo Cassa, 50% al giocatore) | `app.py:1499` |
| `minuti_pubblicazione_prima_partita` | int | `5` | `app.py:1491` |
| `soglia_quota_doppia` | number | `3.5` (quota ≥ soglia → punti raddoppiati) | `app.py:1480`, `:930`; `bot_telegram.py:1267` |
| `bonus_chiusura` | int | `10` | `app.py:1478` |
| `giocatori` | int | `16` (differenza attesa P9d: l'esempio di oggi dice 15 giocatori) | `app.py:1501`, `:1430` |
| `obiettivo_cassa` | number | `3200` (differenza attesa P9d: oggi l'esempio dice 3.000) | `app.py:165`, `:1501` |
| `composizione` | object | `{combo: 1, doppie_chance: 2, variabili: 3, fisse: 4}` | `app.py:1468-1473`; `LIMITI_SCHEDINA` |
| `punti` | object | per tipologia `{base, quota_alta}`: combo 6/12, doppie_chance 1/2, variabili 2/4, fisse 4/8 | `app.py:1477-1481` |
| `ripartizione_premi` | array&lt;{posizione, percentuale}&gt; | 1→40, 2→27, 3→17, 4→10, 5→6 (somma 100). Gli importi li calcola il sito: `obiettivo_cassa × percentuale / 100` (1.280, 864, 544, 320, 192 €). Differenza attesa P9d. | `app.py:1502-1506` (oggi importi fissi su 3.000 €) |

```json
{
  "costo_giornata": 5,
  "quota_partecipazione": 200,
  "scadenza_quota_giornata": 36,
  "quota_cassa_su_vincita": 0.5,
  "minuti_pubblicazione_prima_partita": 5,
  "soglia_quota_doppia": 3.5,
  "bonus_chiusura": 10,
  "giocatori": 16,
  "obiettivo_cassa": 3200,
  "composizione": { "combo": 1, "doppie_chance": 2, "variabili": 3, "fisse": 4 },
  "punti": {
    "combo": { "base": 6, "quota_alta": 12 },
    "doppie_chance": { "base": 1, "quota_alta": 2 },
    "variabili": { "base": 2, "quota_alta": 4 },
    "fisse": { "base": 4, "quota_alta": 8 }
  },
  "ripartizione_premi": [
    { "posizione": 1, "percentuale": 40 }, { "posizione": 2, "percentuale": 27 },
    { "posizione": 3, "percentuale": 17 }, { "posizione": 4, "percentuale": 10 },
    { "posizione": 5, "percentuale": 6 }
  ]
}
```

---

## 11. Mappa scheda → sezioni (copertura)

| Scheda di `app.py` | Cosa mostra | Dove sta nello snapshot |
|---|---|---|
| **Intestazione** (`app.py:387-399`) | titolo con la stagione, «Agg. HH:MM», pulsante Aggiorna, «Versione · novità» | `stagione`; `segnale.ultimo_controllo_il`; Aggiorna = rilettura del sito (nessun dato); novità: §17.26 (file nel repo del sito) |
| **Classifica & Cassa** (`:418`) | podio con delta | `classifica.giocatori[0..2]` + `punti_ultima_giornata` |
| | classifica completa, tendenza, ritirati in fondo | `classifica.giocatori[].posizione/punti_totali/variazione_posizione`, `classifica.ritirati` |
| | storico punteggi per giornata | `classifica.*.punti_per_giornata` |
| | Fondo Cassa: montepremi, obiettivo, % completamento, barra, messaggio obiettivo | `cassa.saldo/obiettivo/completamento/obiettivo_raggiunto` |
| | grafico versamenti per giornata, tabella movimenti | `cassa.versamenti_per_giornata`, `cassa.movimenti` |
| **Schedine Live** (`:630`) | selettori giornata e giocatore | `giornata_corrente`, `giocatori`, `schedine[].giornata/giocatore` |
| | riepilogo esiti + vincita potenziale | `schedine[].riepilogo`, `.vincita_potenziale` |
| | carte per partita: nome, orario, tipologia, pronostico, quota, esito, punti | `schedine[].righe[]` + `partite[]` |
| | risultato in diretta, avviso API non raggiungibile | **Worker** (Fase 3), non lo snapshot |
| **Confronto Giocate** (`:771`) | selettore giornata, griglia partite × giocatori, colori per esito, asterisco quota ≥ 3.50 | `partite[]` (righe, in ordine d'orario) × `schedine[].righe[]` (celle) + `regole.soglia_quota_doppia` |
| | riga «Vincita potenziale» | `schedine[].vincita_potenziale` |
| | colonna «Scelta del gruppo» | `partite[].scelta_gruppo` |
| **Statistiche** (`:939`) | timer ultima schedina vinta | `statistiche.ultima_schedina_vinta` |
| | protagonisti, giornata da incorniciare, Semper Fidelis | `statistiche.premi.*` |
| | squadre amuleto / maledetta | `statistiche.premi.squadra_*` |
| | Per un soffio | `statistiche.per_un_soffio` |
| | tabella completa (+ ritirati) | `statistiche.giocatori`, `.ritirati` |
| **Coppa** (`:1307`) | tabellone provvisorio/definitivo, punti, vincenti, campione, avviso 16 partecipanti | `coppa.*` |
| | «Come funziona» / «Gli accoppiamenti» (testi con i numeri delle giornate) | testi nel sito + `coppa.prima_giornata`, `.ultima_giornata_tabellone` |
| **Regolamento** (`:1458`) | bolletta, punteggi, regole, Cassa e premi | testi nel sito + `regole.*` |
| **Piede di pagina** | firma | statico |

---

## 12. Enum stabili

**`esito`** (riga di una schedina), da testo del foglio (confronto per **sottostringa nello stesso ordine di `app.py:714-727`**, che resta l'unico posto in cui si interpreta il testo):

| Valore | Testo del foglio | Significato |
|---|---|---|
| `vinta` | `✅ VINTA` | Pronostico preso. |
| `persa` | `❌ PERSA` | Pronostico sbagliato. |
| `in_corso` | `⏳ IN CORSO` | Partita iniziata/non finita, esito scritto dal bot. |
| `rinviata` | `⏸️ RINVIATA` | Partita rinviata/sospesa: i punti aspettano il recupero. |
| `da_verificare` | `⚠️ DA VERIFICARE` | Pronostico non interpretabile dal bot; **non** conta né vinto né perso. |
| `annullata` | `➖ ANNULLATA` | Selezione annullata (es. eccesso): 0 punti. |
| `da_giocare` | *(cella vuota)* | Il bot non ha ancora calcolato la riga (decisione 8). Diventa «In corso» a video quando il live dice che la partita è iniziata. |

Un testo non riconosciuto diventa `da_verificare` (mai `vinta`: «mai far vincere per default»; §17.11).

**`tipologia`**: `combo`, `fisse`, `doppie_chance`, `variabili`.
**`scelta_gruppo.tipo`**: `maggioranza`, `tutti_diversi`, `nessuna`.
**`coppa.turni[].turno`**: `ottavi`, `quarti`, `semifinali`, `finale`.

---

## 13. Differenze attese rispetto al sito di oggi

Da segnare come **attese** nel confronto sui dati veri (Fase 1, «si gira su dati veri prima di dichiarare fatto»).

Già decise (punto 9 di RESTYLING.md):

| # | Differenza |
|---|---|
| P9a | Frecce di tendenza: stesso spareggio per la posizione attuale e per quella precedente. |
| P9b | Squadra amuleto/maledetta contata per squadra **ufficiale**, non per nome scritto nel foglio. |
| P9c | La scheda Live conta anche rinviate, da verificare e annullate. |
| P9d | Regolamento: 16 giocatori, obiettivo 3.200 €, ripartizione 40/27/17/10/6 in percentuale. |

**Nuove, emerse scrivendo lo schema — approvate il 04/10/2026** come correzioni di errori (punto 10 di RESTYLING.md). A1-A8 dallo schema; A9-A14 dalle decisioni di dominio sulle card, sulla classifica e sulla Coppa; A15 dal confronto sui dati veri:

| # | Differenza | Dettaglio |
|---|---|---|
| A1 | Il delta sul podio funziona | Oggi `+N pt ultima giornata` non compare mai (§16 D1); con lo snapshot compare quando l'ultima giornata giocata ha dato punti. |
| A2 | Montepremi = somma delle Entrate | Oggi è l'ultima cella «Saldo Totale». Identico finché nessuno ritocca il foglio a mano (§16 D3, §17.9: verificato sul foglio vero). |
| A3 | Montepremi mai «0,00 €» in silenzio | Oggi un saldo illeggibile diventa `0,00 €` senza avviso (`app.py:567-569`). Nello snapshot: il bot **non pubblica** e avvisa l'admin. |
| A4 | Quota media senza le quote illeggibili | Oggi una quota vuota/illeggibile vale `0.0` e **abbassa la media** (`app.py:1064-1070`). |
| A5 | Un solo ordine delle partite | Scheda Live e Confronto usano lo stesso ordine d'orario (oggi sono due algoritmi diversi, §16 D6). |
| A6 | Abbinamento su nomi ufficiali, per giornata | Oggi la normalizzazione fuzzy contro 20 squadre può confondere nomi che si contengono (§16 D11); ora l'abbinamento è per uguaglianza fra le 10 partite della giornata (§7.3). |
| A7 | Ordini deterministici a parità | Oggi `sort_values` e `idxmax` a parità dipendono dall'ordine del foglio e da un ordinamento non stabile (§16 D13). |
| A8 | Spareggio con nomi in maiuscole/minuscole diversi | Oggi se «Paolo» in Classifica e «PAOLO» in Giocate non coincidono per un carattere, i pronostici vinti valgono 0 e lo spareggio salta in silenzio (`app.py:429-432`). |
| A9 | Card a pari merito: si mostrano **tutti** | Cecchino, benedizione, folle, conservatore, giornata da incorniciare, Semper Fidelis, amuleto, maledetta: oggi vince il primo per ordine del foglio. Nessun minimo di pronostici (decisione 14). |
| A10 | Classifica: stessa posizione a pari merito | Oggi posizioni consecutive per ordine del foglio; ora, a parità di punti **e** di pronostici vinti, stessa posizione (4°, 4°, 6°) (decisione 15). |
| A11 | Selezioni annullate non votano | «(ANNULLATA ECCESSO)» non conta più come voto nella Scelta del gruppo (decisione 18). |
| A12 | Semper Fidelis per giornate distinte | Oggi conta righe, anche non giocate o annullate; ora giornate distinte, solo partite giocate e pronostici non annullati (decisione 19). |
| A13 | Amuleto/maledetta: solo la squadra scelta | Oggi contano entrambe le squadre della riga, anche con Over o Pari; ora solo la squadra del pronostico (1/1X → casa, 2/X2 → ospite) (decisione 20). |
| A14 | Coppa «definitiva» a Giornata 34 conclusa | Oggi scatta alla prima riga di giornata ≥ 35 in Giocate (decisione 21). |
| A15 | «Per un soffio» mostra il nome ufficiale della partita | Oggi mostra il testo scritto nel foglio («Fiorentina - Torino»); ora il nome ufficiale abbinato da Football-Data («ACF Fiorentina - Torino FC», §8.3). Lo snapshot **già** usava il nome ufficiale; il confronto sui dati veri lo ha segnalato come differenza non codificata (prima etichettata §8.3). |

**Celle non numeriche in Classifica** (decisione 04/10/2026, non è una differenza ma una regola dello snapshot): una cella di `Punti Totali` o di `Giornata N` scritta ma non numerica (es. `-`, `12,5`) **vale 0**, esattamente come nel bot (`esegui_calcolo_risultati` somma solo le celle `isdigit()`), così sito e bot mostrano gli stessi totali. Lo snapshot **non** si blocca: il bot manda un avviso agli admin che nomina giocatore e colonna da correggere. Una cella vuota vale 0 (o `null` in `punti_per_giornata`) senza avviso. Il giocatore **duplicato** in Classifica resta un errore bloccante (non si indovina quale riga vale). Sostituisce la regola «cella non numerica → `ValueError`» di N9 (§15).

**Bug della tipologia (sito vecchio, corretto anche lì)**: la scheda Schedine Live di `app.py` leggeva la colonna `Tipologia`, ma l'intestazione vera del foglio è `Tipologia Giocata`, quindi la tipologia non compariva mai sulle carte. Corretto il 04/10/2026 anche in `app.py` (legge `Tipologia Giocata`, ripiego su `Tipologia`): non è una differenza attesa, sito vecchio e snapshot ora mostrano la stessa tipologia. Lo snapshot l'aveva già giusta (`righe[].tipologia`).

Confermati **senza** differenza rispetto a oggi: spareggio precedente con i pronostici vinti fino alla giornata precedente (16), il sostituto SIRACUSA eredita i pronostici vinti del ritirato PULIZZER (17), esito non riconosciuto → `da_verificare` (11), partite vuote tenute come `ufficiale: false` (12; 0 righe sui dati veri).

---

## 14. Dimensione a fine stagione (misurata)

**Prova reale**: `scratchpad/misura_snapshot2.py` genera uno snapshot **sintetico** secondo questo schema (rimisurato dopo le decisioni del 04/10/2026) — 38 giornate, 16 giocatori attivi più 1 ritirato, **6.080 righe** di Giocate in 608 schedine, 380 partite con `id` a 6 cifre come quelli di Football-Data, 28 movimenti di Cassa, `premi` come liste di vincitori (con un pari merito), tutte le sezioni di statistiche e Coppa — e lo misura. Dati inventati ma con la stessa forma: quote casuali a due decimali (quasi incomprimibili, come nel foglio vero), nomi di squadra ufficiali, 10 righe a schedina.

Percorso: `/private/tmp/claude-501/-Users-silviochristianbenanti-Desktop-Toto-Amici-Progetto/e3be7374-8571-4323-b430-dab0fd6d0f37/scratchpad/misura_snapshot2.py` (output: `snapshot_sintetico.json`).

| Variante | JSON compatto | JSON indentato | gzip -9 | brotli -11 |
|---|---|---|---|---|
| **Schema approvato** (righe annidate nelle schedine) | **809,3 KB** | 1.491,0 KB | **53,6 KB** | **44,3 KB** |
| Alternativa scartata: righe piatte (una per riga di Giocate, con `giornata` e `giocatore` ripetuti) | 903,9 KB | 1.411,0 KB | 54,2 KB | 45,9 KB |

Per sezione (compatto → gzip):

| Sezione | Compatto | gzip -9 |
|---|---|---|
| `schedine` | 720,8 KB | 43,3 KB |
| `partite` | 73,3 KB | 5,9 KB |
| `statistiche` | 4,8 KB | 1,1 KB |
| `classifica` | 3,8 KB | 1,1 KB |
| `cassa` | 3,7 KB | 0,8 KB |
| `coppa` | 1,9 KB | 0,4 KB |
| `regole` | 0,6 KB | 0,3 KB |

Letture:

- **Rispetto alla bozza** (788,9 KB / 53,7 KB gzip / 44,3 KB brotli): +20 KB di grezzo e **nessuna differenza dopo la compressione**. L'aumento è quasi tutto l'`id` di Football-Data (6 cifre invece di 1-3) ripetuto in ogni `partita_id` delle 6.080 righe; si comprime bene perché ogni id ricorre ~16 volte. Le liste di vincitori nei `premi` valgono qualche decina di byte, e togliere titolo e descrizione delle card ne fa risparmiare circa 0,4 KB; la posizione esplicita c'era già.
- **~54 KB gzip** (~44 KB brotli): sopra la stima «~40 KB compressi» di RESTYLING.md (+35% in gzip, +10% in brotli), ma nessun problema: il limite di un valore KV è 25 MiB e il browser scarica il file compresso (Cloudflare serve brotli/gzip da sé). Il 98% del peso sono le 6.080 righe, cioè esattamente i dati che i filtri per giornata/giocatore richiedono.
- Lo snapshot **cresce linearmente** con le giornate: a metà stagione è la metà.
- **Parse**: `JSON.parse` dello snapshot da 810 KB ≈ 3 ms in Node su Mac. Il Worker non deve farlo (§2); il browser sì, una volta.
- Se in futuro servisse dimezzare: sono le chiavi ripetute nelle righe (`partita_id`, `tipologia`, `pronostico`, `quota`, `esito`, `punti`, ×6.080). Righe come array posizionali taglierebbero il grezzo di circa un terzo, ma rendono il contratto illeggibile: non conviene finché non serve.
- `segnale` < 400 byte.

---

## 15. Funzioni da aggiungere a `statistiche.py`

Tutte **pure** (niente rete, niente Sheets, niente `pandas`): `requirements-bot.txt` non ha `pandas` e il bot importa già `statistiche` (`bot_telegram.py:15`). Operano su liste e dizionari; chi legge i fogli e chiama Football-Data è il bot, che passa i dati già letti. Ogni funzione ha un test.

Numerazione: **S** = spostata dal bot (nessuna logica nuova), **N** = nuova.

| # | Nome e firma | Cosa sostituisce in `app.py` | Cosa evita |
|---|---|---|---|
| **S1** | `estrai_numero(testo) -> float` — spostata da `bot_telegram.py:1190`; il bot la importa da `statistiche` (cambiano solo gli import del bot, §17.7). | `_parse_euro` (`:589`), `parse_quota` (`:1064`), il `float(quota.replace(',', '.'))` di `formatta_giocata` (`:811`), il `replace('.', '')` di `vincita_map` (`:852`), il parse del saldo (`:565`) | **Quattro parser diversi dello stesso formato**, uno dei quali (`:811`) è esattamente la forma che CLAUDE.md vieta. Un parser solo, già testato. |
| **S2** | `etichetta_stagione(data_inizio) -> str \| None` — spostata da `bot_telegram.py:1005`; il bot la importa da `statistiche` (§17.7). | titolo scritto a mano «2026» (`:389`) | Serve a `partite_della_stagione` per `stagione` senza una chiamata in più; va in `statistiche.py` perché l'import inverso (`statistiche` → `bot_telegram`) sarebbe circolare. |
| N1 | `esito_da_testo(testo) -> str` — testo del foglio → enum §12. | i `"VINTA" in esito` sparsi: `:669-671`, `:714-727`, `:745`, `:817-821`, `:1074-1076`, `:1229-1232`; e quelli in `statistiche.py` (`:173-181`, `:273`, `:319`) | Interpretare il testo dell'esito in **un solo punto**, con un `da_verificare` sicuro per i testi sconosciuti. Le altre funzioni leggono l'enum, non sottostringhe. |
| N2 | `tipologia_da_testo(testo) -> str \| None` | `tipo`, `:740` | Stesso motivo: `"Doppie Chance"` → `doppie_chance`; sconosciuta → `None` invece di mostrare testo grezzo. |
| N3 | `pulisci_giocate(valori) -> (righe, scartate)` — da `valori` (lista di liste di `Giocate!A:I` con intestazione) a righe `{giornata:int, giocatore, partita_testo, tipologia, pronostico, quota:float\|None, esito, vincita:float, punti:int}`; `scartate` = righe ignorate con il motivo (riga di intestazione ripetuta, senza giocatore, giornata non valida). | filtro righe spurie del solo Confronto (`:790-796`), `df_stats` (`:1062`), `dropna()` dei selettori (`:635-640`, `:776-778`) | Oggi la stessa pulizia è fatta **in tre posti, con tre criteri diversi**: in Live le righe spurie si vedrebbero, nelle statistiche si contano. `scartate` va al log del bot (non allo snapshot). Converte numeri e giornata **una volta**, con `numero_giornata`: chiude `str(giornata).lower().replace("giornata","")` (`:651`, `:799`) e il confronto esatto `df['Giornata'] == "Giornata 12"` (`:656`). |
| N4 | `movimenti_cassa(valori) -> list[dict]` — da `Cassa!A:D` a `{giornata:int\|None, descrizione, entrata:float\|None, saldo:float\|None}`. | `df_cassa`, `:562-622` | Righe di Cassa lette come numeri veri; `giornata` intera. |
| N5 | `partite_della_stagione(matches) -> dict` — dalla **risposta di una sola chiamata** Football-Data (`/competitions/SA/matches` senza `matchday`: 380 partite, verificato, §17.3) a `{"stagione": "2026-27", "per_giornata": {giornata: [{id, nome, casa, ospite, inizio: datetime \| None}]}}`. `nome` = `f"{casa} - {ospite}"` con i nomi completi; `casa` e `ospite` portano sia `name` sia `shortName` per l'abbinamento. `id` = `match.id`. | `scarica_risultati_api` (`:262`), `orari_partite_giornata` (`:312`), `scarica_squadre_serie_a` (`:327`) | **Fino a 38+ chiamate API per giornata diventano una per pubblicazione**: oggi ogni scheda chiama `scarica_risultati_api` per la giornata scelta (`:652`, `:800`, `:1032`) e il rate limit è 10/minuto. È anche lo spirito della regola «una sola chiamata per stagione». |
| N6 | `abbina_partita(nome_sheet, partite_giornata) -> dict \| None` — abbina il testo scritto nel foglio a **una** delle 10 partite della **stessa giornata** (§7.3): normalizza le due squadre (minuscole, senza suffissi societari) e le confronta **per uguaglianza** con `shortName` e `name` di casa e ospite, provando anche le squadre invertite (come `esegui_calcolo_risultati`, `bot_telegram.py:1321-1330`). Restituisce `None` se nessuna partita corrisponde o se ne corrispondono due: il bot non indovina. | `normalizza_nome_squadra` (`:348`), `normalizza_partita_completa` (`:360`), l'abbinamento fuzzy di `:1185-1197` | (1) Oggi un abbinamento fallito **restituisce comunque una stringa** (`squadra_raw.title()`, `:358`) e il sito ci cerca sopra un risultato che non esiste, senza avvisi: ora `None` → `ufficiale: false` + avviso agli admin. (2) Oggi si accetta anche un accoppiamento «Lazio - Roma» che **non esiste** fra le partite del giorno (casa e ospite abbinati separatamente, `:369-370`). (3) La sottostringa `squadra in uff` (`:354`) fa sì che «milan» sia contenuto in «fc internazionale milano»: **non serve più**, perché si confronta solo fra le 10 partite della giornata e per uguaglianza (D11). (4) Sito e bot abbinavano con due algoritmi diversi (`[:5]` nel bot, `normalizza_*` nel sito). **Test con le scritture reali** di G1-G2 (29 varianti per 10 partite, tipo «Sassuolo Calcio», «Como 1907», «Venezia FC»). |
| N7 | `scelta_del_gruppo_dati(pronostici_per_giocatore) -> dict` — `{tipo, pronostici, voti, su}`; riceve **solo i voti non annullati** (§17.18); `scelta_del_gruppo` (`:194`) resta come funzione di sola formattazione sul risultato (i suoi 5 test non cambiano). | `:869-875` | Il testo «1 · 5 su 7» non è presentazione da mettere nel JSON; i dati sì. Elimina anche il filtro `df_giornata[... == partita].groupby(...)` rifatto **per ogni partita** (`:870-874`). |
| N8 | `costruisci_partite_e_schedine(righe, per_giornata) -> (partite, schedine)` — raggruppa le righe pulite, abbina le partite (N6; `id` = id Football-Data, negativo per le non ufficiali), ordina (`ordina_partite_per_orario`, `:360`), calcola `riepilogo`, `vincita_potenziale` e `scelta_gruppo`. | `:656-762` (Live), `:786-877` (Confronto: pivot, vincite, scelta) | Il **pivot di pandas con sentinelle `\|\|\|VINTA`/`\|\|\|PERSA`** nel testo della cella (`:817-889`): un trucco per far passare il colore attraverso `pivot_table`, che si romperebbe con qualsiasi testo contenente `\|\|\|`. Ora l'esito è un campo. Elimina anche il doppio `normalizza_partita_completa` per riga (`:693` e `:709`) e i due ordinamenti diversi (§16 D6). |
| N9 | `classifica_ordinata(righe_classifica, righe_pulite) -> dict` — sezione `classifica` (§5): `Punti Totali` come intero, ordine per punti poi pronostici vinti poi nome, **`posizione` esplicita con ranking sportivo** (stessa posizione a pari punti e pronostici vinti, §17.15), ritirati separati, `punti_per_giornata` con `None` per le celle vuote. Nome del giocatore confrontato **senza distinguere maiuscole**; i pronostici vinti del sostituto includono quelli del ritirato (§17.17). | `:421-441`, `:516-554` | `pd.to_numeric(errors='coerce').fillna(0)` (`:421`): una cella non numerica diventava **0 punti** senza traccia; ora vale 0 **come nel bot** ma con un **avviso** agli admin che nomina giocatore e colonna (decisione 04/10/2026, §13); il giocatore duplicato resta `ValueError`. Vittorie cercate per nome esatto (`:429-432`): con una maiuscola diversa lo spareggio salta in silenzio. |
| N10 | `variazioni_posizione(righe_classifica, righe_pulite) -> (ultima_giornata, {nome: {variazione, punti_ultima}})` — **stesso** criterio di spareggio e **stesso ranking sportivo** per la classifica prima e dopo; i pronostici vinti per quella precedente sono contati **fino alla giornata precedente** (§17.16). | `:478-510` e il delta del podio `:454-466` | (1) Oggi la classifica precedente non ha spareggio e ordina con un sort non stabile (`:499`), la attuale sì (`:433`): frecce spurie fra pari punti (decisione 9). (2) Il delta del podio legge **`valori[-1]`, cioè l'ultima colonna del foglio = Giornata 38** (`:464-465`) — vuota fino a fine stagione, quindi «+N pt ultima giornata» non compare mai. (3) `sparkline_data` (`:466`) è calcolato e **mai usato**. (4) `_numero_giornata_col` restituisce `0` su errore (`:479-483`) e le colonne si scelgono con `'giornata' in c.lower()` (`:443`): ora `numero_giornata`. |
| N11 | `riepilogo_cassa(movimenti, obiettivo) -> dict` — `saldo` (somma delle entrate), `obiettivo`, `completamento`, `obiettivo_raggiunto`, `movimenti`. | `:562-585` | Il saldo letto dall'**ultima riga** (`:564`) può divergere dal vero dopo una correzione a mano: il bot ricalcola dalla somma (`saldo_cassa`, `:1168`) proprio per questo. `except:` nudo che mette `0,00 €` (`:567-569`): un errore di lettura mostra «Montepremi 0 €» a tutti senza avvisi. |
| N12 | `versamenti_per_giornata(movimenti, giornate_giocate) -> list` | `:589-617` | Il grafico usa le **etichette testuali** come chiave, unisce Cassa e Giocate come insiemi di stringhe (`:605-608`: «Giornata 5» e « Giornata 5» sarebbero due barre) e manda le etichette non numeriche a `0` (`:599-603`). Con interi: un'unica barra per giornata. |
| N13 | `statistiche_per_giocatore(righe_pulite) -> list[dict]` — tabella `giocatori` (§8): `win_rate` (1 decimale) e `quota_media` (2 decimali) **già arrotondati** (§17.27), `vinte`, `totali`, con **un solo giro** sulle righe; poi `righe_del_ritirato` (già esistente, `:64`) per `ritirati`. Restituisce anche i valori esatti per i confronti dei premi. | `:1062-1112`, `:1287-1300` | Quota non leggibile = `0.0` che entra nella media (`:1064-1070`, `:1082`). `statistiche_giocatore` rifiltra l'intero DataFrame **per ogni giocatore** (`:1091-1094`). Per ogni ritirato `df_valutate.reset_index().to_dict('records')` copia **tutta la tabella** (`:1101-1103`). Ordine finale con `sort_values` non stabile (`:1289`). |
| N14 | `premi_giocatori(stats) -> dict` — `cecchino`, `benedizione`, `folle`, `conservatore` come **liste di tutti i pari merito** in ordine alfabetico, **senza minimo** di pronostici (§17.14); niente titoli né descrizioni (stanno nel React). | `:1116-1156` | `idxmax`/`idxmin` restituiscono il **primo** a parità e l'ordine dipende da come i giocatori compaiono in Giocate (`:1120-1123`): non deterministico dopo una correzione a mano. Differenza attesa A9. |
| N15 | `giornata_da_incorniciare(righe_classifica_attivi) -> list \| None` — lista dei pari merito sul punteggio più alto. | `:1158-1178` | Doppio ciclo con `try/except` nudo su `int(str(...).strip() or 0)` (`:1164-1167`) e colonne scelte per sottostringa (`:1160`): ora `punti_per_giornata` già interi. |
| N16 | `semper_fidelis(righe_pulite, partite) -> list \| None` — per (giocatore, squadra ufficiale) conta le **giornate distinte** in cui c'è almeno un pronostico su quella squadra (via N23), **solo partite giocate** (esito `vinta`/`persa`) e pronostici non annullati; lista dei pari merito, `None` se il massimo è < 2 (§17.19). | `:1180-1221` | `iterrows` su ~6.000 righe (`:1187`) con normalizzazione fuzzy contro 20 squadre per **due volte a riga** (`:1195-1196`); ora squadre ufficiali già nella partita (N6). La funzione dipende da `scarica_squadre_serie_a()` (`:1185`) e **non produce niente** se la chiamata fallisce: ora nessuna chiamata. Conta righe invece di giornate (D9): differenza attesa A12. |
| N17 | `squadre_amuleto_maledetta(righe_pulite, partite) -> dict` — conta **per squadra ufficiale** le righe `vinta` / `persa` **solo sulla squadra scelta** dal pronostico (N23); liste di pari merito (§17.20). Le righe `ufficiale: false` non contano. | `:1223-1259` | Si contano i testi grezzi del foglio (`:1230-1232`): «Inter» e «Inter Milan» sarebbero due squadre diverse (decisione 9, P9b); e oggi si contano entrambe le squadre di ogni riga, anche con Over o Pari (differenza attesa A13). Rifà `pd.Series(...).value_counts()` due volte a testa (`:1236-1237`, `:1249-1250`). |
| N18 | `ultima_schedina_vinta(movimenti, righe_pulite, partite) -> dict \| None` — compone `schedine_chiuse_ultima_giornata` (`:90`) e `momento_fine_schedina` (`:122`); `inizio_il` = massimo dei momenti dei vincitori, `None` se uno solo è ignoto. | `:1022-1060` | Una chiamata API in più solo per il timer (`orari_partite_giornata`, `:1032`). Il blocco da 60 righe di HTML+JS del timer (`:955-1020`) esce dal Python: lo rifà il React. `scomponi_durata` (`:138`) resta solo come specifica nei test. |
| N19 | `coppa_snapshot(righe_classifica, righe_pulite) -> dict` — sezione `coppa` (§9), componendo `classifica_per_coppa`, `tabellone_ottavi`, `punti_per_giornata`, `giornate_concluse`, `turni_coppa` esistenti; `definitiva` = `34 in giornate_concluse` (§17.21); costruisce i turni «vuoti» se i partecipanti non sono 16. | `:1314-1327`, `:1361-1366` | La conversione `to_dict("records")` dei due DataFrame a ogni rerun (`:1314-1315`); il turno scheletro costruito con `[{...}] * (8 >> i)` (stesso dict ripetuto, `:1325`). |
| N20 | `REGOLE` (costante, non funzione) — dizionario di §10 (16 giocatori, obiettivo 3.200 €, ripartizione 40/27/17/10/6; §17.25); più un test che la confronta con `LIMITI_SCHEDINA` e `calcola_punteggio_partita` del bot. | tabelle e testi del Regolamento (`:1465-1506`) | Tre copie dei numeri (bot, `app.py`, React) che si possono scollare; il test le tiene allineate. |
| N21 | `costruisci_snapshot(valori_classifica, valori_cassa, valori_giocate, matches, adesso) -> (snapshot, avvisi)` — orchestra tutto; `avvisi` = lista di testi per il log e per gli admin (righe non abbinate a una partita, righe scartate, cassa incoerente, classifica con totale ≠ somma delle giornate). Solleva se `Classifica`, `Giocate` o la risposta di Football-Data sono vuote o illeggibili: il bot non pubblica, tiene lo snapshot precedente e avvisa gli admin con `avvisa_admin()` (§17.13). | `carica_tutti_i_dati` (`:228-259`) | `carica_tutti_i_dati` **cattura ogni eccezione e restituisce DataFrame vuoti** (`:257-259`): con `st.cache_data` (ttl 180 s) il fallimento resta in cache e tutti vedono «Classifica non ancora disponibile» per 3 minuti. Qui un risultato vuoto o un errore **non produce uno snapshot**: resta il precedente. |
| N22 | `costruisci_segnale(snapshot, adesso) -> dict` e `impronta_snapshot(snapshot) -> str` — SHA-256 del JSON canonico (chiavi ordinate, separatori compatti) **senza** `generato_il`. | — (nuovo) | L'impronta permette di ripubblicare «solo se cambiato» senza confrontare 800 KB e al sito di riscaricare solo quando serve. |
| N23 | `squadra_scelta(pronostico, partita) -> str \| None` — squadra ufficiale scelta da un pronostico: `1`/`1X` → casa, `2`/`X2` → ospite, primo segno prima del `+` nelle combo; `None` per tutto il resto (`X`, `12`, Over/Under, Gol/NoGol, Pari/Dispari). Usata da N16 e N17. | i due cicli di `:1180-1259` | La stessa regola di scelta della squadra scritta due volte, con criteri diversi (Semper Fidelis solo `1`/`1X`/`2`/`X2`, amuleto su entrambe le squadre). |

**Funzioni esistenti da adattare** (restano, con i test aggiornati):

- `schedine_perse_per_un_soffio` (`statistiche.py:152`): oggi restituisce `quota` come **stringa** e `partita` come testo grezzo; deve restituire la quota come numero e la partita ufficiale (o essere alimentata con righe pulite).
- `scelta_del_gruppo` (`statistiche.py:194`): diventa il formattatore di `scelta_del_gruppo_dati`.

**Conteggio**: 23 funzioni nuove (N1-N23, di cui N20 è una costante), 2 spostate dal bot (S1-S2), 2 esistenti da adattare.

---

## 16. Errori, lavoro inutile e punti fragili trovati in `app.py`

Tutti quelli che hanno una correzione nello snapshot sono già collegati alla funzione che li evita (§15). Qui l'elenco completo, con i riferimenti.

### Errori logici

| # | Dove | Problema |
|---|---|---|
| D1 | `app.py:464-465` | Il delta del podio `+N pt ultima giornata` usa `valori[-1]`, l'**ultima colonna** del foglio. La Sessione 28 ha verificato che l'intestazione ha già «Giornata 1…38» fino alla colonna AN, quindi `valori[-1]` è la Giornata 38: sempre vuota fino a fine stagione. Il delta non compare mai. (N10) |
| D2 | `app.py:499` vs `:433` | Frecce di tendenza: la classifica precedente è ordinata solo per punti con un sort non stabile; l'attuale per punti **e** pronostici vinti. Due giocatori a pari punti possono mostrare una freccia che non corrisponde a nessun cambio reale. Già decisione 9. (N10) |
| D3 | `app.py:564-569` | Saldo = ultima cella «Saldo Totale», ma il bot lo ricalcola dalla somma delle Entrate perché il foglio può essere corretto a mano (`saldo_cassa`, `bot_telegram.py:1168`). Inoltre `except:` nudo → `0,00 €`: un errore di lettura è indistinguibile da una cassa vuota. (N11) |
| D4 | `app.py:1064-1070`, `:1082` | `parse_quota` restituisce `0.0` quando la quota non è leggibile: quel `0.0` entra nella media e abbassa la `quota_media` del giocatore (e quindi «Il Conservatore»). Una quota mancante deve restare fuori dalla media. (N13) |
| D5 | `app.py:1230-1232` | Amuleto/maledetta contano le **stringhe del foglio**: «Inter», «Inter Milan», «inter» sono tre squadre. Già decisione 9. (N17) |
| D6 | `app.py:686-704` vs `:835-842` | Due ordinamenti delle partite per la stessa giornata: la scheda Live riconverte l'orario già formattato `"dd/mm HH:MM"` con `strptime` (senza anno, quindi 29/02 fallisce → `datetime.max`; i pari orario restano nell'ordine del foglio), il Confronto usa `ordina_partite_per_orario` (datetime con fuso, pari orario alfabetici). Le due schede possono mostrare le stesse partite in ordine diverso. (N8) |
| D7 | `app.py:662-664` vs `:846-851` | La stessa cella «Vincita Potenziale» è letta in due modi: Live scarta `"", "0", "0.0"` e mostra il testo grezzo + « €» (quindi `"0,00"` passa e si vede `0,00 €`); il Confronto fa `replace('.', '').replace(',', '.')`. (S1, N8) |
| D8 | `app.py:1316-1318` | «Tabellone definitivo» scatta appena in Giocate compare **una riga** di giornata ≥ 35, ma la classifica del tabellone si congela quando la 34ª è conclusa. Se la bolletta della 35ª viene caricata mentre la 34ª è ancora in corso, il sito dice «definitivo» su una classifica che può ancora cambiare. Corretto nello snapshot: `definitiva` scatta a Giornata 34 conclusa (A14, §17.21). |
| D9 | `app.py:1180-1221` | Semper Fidelis conta **righe**, non giornate («giornata dopo giornata» suggerirebbe giornate distinte): un giocatore con `1` e `1X` sulla stessa partita vale 2. Conta anche righe non ancora giocate o annullate. Corretto nello snapshot: giornate distinte, solo partite giocate e non annullate (A12, §17.19). |

### Fragile (funziona per ora)

| # | Dove | Problema |
|---|---|---|
| D10 | `app.py:429-432` | `vittorie_per_giocatore.get(g, 0)` cerca il nome **esatto**: basta una differenza di maiuscole fra Classifica e Giocate e lo spareggio smette di funzionare, senza errori. (N9) |
| D11 | `app.py:348-358`, `:1185-1197` | Normalizzazione per sottostringa: `squadra_clean in uff_clean` fa trovare «milan» dentro «fc internazionale milano». Con le 10 squadre di casa di una giornata non ci si cade; con le 20 squadre di `scarica_squadre_serie_a()` il risultato dipende dall'ordine della lista. Con l'abbinamento per giornata e per uguaglianza (§7.3) il problema non esiste più. (N6, N16) |
| D12 | `app.py:421-423` | `pd.to_numeric(errors='coerce').fillna(0)`: una cella di punti non numerica diventa 0 punti senza traccia. (N9) |
| D13 | `app.py:1120-1123`, `:1236`, `:1249`, `:1289` | `idxmax`, `idxmin`, `value_counts().idxmax()` e `sort_values` risolvono i pari merito con l'**ordine di comparsa nel foglio** (e un quicksort non stabile): una riga spostata a mano cambia chi è «Il Cecchino». (N13, N14, N17) |
| D14 | `app.py:817-889` | Il colore delle celle del Confronto viaggia come testo nascosto `\|\|\|VINTA`/`\|\|\|PERSA` dentro la cella e viene tolto dopo. (N8) |
| D15 | `app.py:605-608`, `:599-603` | Le giornate della Cassa sono stringhe: due scritture della stessa giornata danno due barre; un'etichetta non numerica diventa «Giornata 0». (N12) |
| D16 | `app.py:651`, `:799`, `:656` | `str(g).lower().replace("giornata","")` e `df['Giornata'] == giornata_selezionata`: confronti di testo dove serve un numero. (N3) |
| D17 | `app.py:228-259` | `carica_tutti_i_dati` inghiotte ogni eccezione, restituisce tre DataFrame vuoti e `st.cache_data` li tiene in cache 180 s: un blip di Sheets mostra «Classifica non ancora disponibile» a tutti per 3 minuti. (N21) |

### Lavoro inutile

| # | Dove | Problema |
|---|---|---|
| D18 | `app.py:466` | `sparkline_data` è calcolato per ognuno dei tre del podio e **mai usato**. |
| D19 | `app.py:693` e `:709` | `normalizza_partita_completa` due volte per ogni riga della schedina (una per l'ordine, una per il nome). |
| D20 | `app.py:870-874` | Per ogni partita della giornata: nuovo filtro del DataFrame + `groupby` per la scelta del gruppo. |
| D21 | `app.py:1091-1094`, `:1101-1103` | Un filtro del DataFrame per giocatore; una copia completa della tabella (`reset_index().to_dict('records')`) per ogni ritirato. |
| D22 | `app.py:1187`, `:1228` | Due `iterrows` sull'intera Giocate (~6.000 righe) per Semper Fidelis e squadre, in più il giro della Classifica per il record. |
| D23 | `app.py:800`, `:652`, `:1032` | La stessa chiamata Football-Data per giornata fatta da tre schede (cache 3 minuti): il bot ne fa una per tutta la stagione. (N5) |

---

## 17. Decisioni di dettaglio (ex domande aperte)

Le 31 domande della bozza sono state chiuse il 04/10/2026. Il numero è lo stesso della bozza, così i rimandi `§17.N` nel resto del documento restano validi. **Verificato** = controllato sui dati veri (foglio Google Sheets, API Football-Data).

### Architettura e pubblicazione

1. **Segnale di vita in un documento KV separato (`segnale`)**: confermato (§2). Il controllo ogni 15 minuti non riscrive ~810 KB.
2. **«Aggiornato alle» usa `ultimo_controllo_il`**; il sito sottrae dal buco i minuti caduti nella pausa 02:00-07:30 e avvisa oltre 120 minuti: confermato (§4).
3. **Football-Data: una sola chiamata per pubblicazione. Verificato**: `GET /v4/competitions/SA/matches` senza `matchday` restituisce 380 partite (38 giornate × 10), con `id`, `matchday`, `utcDate`, `status`, `shortName`/`name`, `score.fullTime` sempre presenti; ~353 KB. `season.currentMatchday` esiste. Il bot **non** fa una chiamata per giornata (§7.3, N5).
4. **Righe annidate nelle schedine**: confermato (§7, §14).
5. **`id` delle partite = id di Football-Data.** Il Worker abbina i risultati live **per id**, non per nome: sostituisce il «nome ufficiale esatto» della decisione 4 di RESTYLING.md (aggiornata). Per le righe non abbinate, id negativo valido solo nello snapshot (§7.1).
6. **`inizio_il` nello snapshot** come ripiego e per ordinare: confermato.
7. **`estrai_numero` ed `etichetta_stagione` si spostano in `statistiche.py`** e il bot le importa: approvato (S1-S2). Cambiano solo gli import del bot, non la logica.
8. **Due «dialetti» in `statistiche.py`** (funzioni vecchie su dizionari con le colonne del foglio, funzioni nuove su righe pulite `snake_case`): accettato per ora; si adattano solo `schedine_perse_per_un_soffio` e `scelta_del_gruppo` (§15).

### Cassa e dati

9. **Saldo = somma delle Entrate**, come fa il bot (`saldo_cassa`). **Verificato** sul foglio vero: oggi coincide con l'ultima cella (1 riga, 430,00 €).
10. **Righe di Cassa non «Giornata N»**: **verificato**, oggi non ce ne sono. Le eventuali future restano fuori dal grafico ma nella tabella (`giornata: null`, §6).
11. **Esito non riconosciuto → `da_verificare`**: confermato (regola del progetto: mai far vincere per default).
12. **Righe di Giocate con partita vuota**: **verificato**, 0 righe sui dati veri. Si tiene il comportamento della bozza (`ufficiale: false` con `nome: ""`).
13. **Dati illeggibili → il bot non pubblica**, tiene lo snapshot precedente e avvisa gli admin con `avvisa_admin()`: confermato (N9, N21). Vale anche se la chiamata a Football-Data fallisce (§7.3).

### Regole di dominio

14. **Card a pari merito: si mostrano tutti** i pari merito (le chiavi di `premi` sono liste di vincitori, §8.2). **Nessun minimo** di pronostici. Differenza attesa A9. Riguarda Cecchino, Benedizione, Pazzo, Conservatore, Giornata da incorniciare, Semper Fidelis, Amuleto, Maledetta.
15. **Classifica: stessa posizione** a parità di punti **e** di pronostici vinti (ranking sportivo: 4°, 4°, 6°); lo schema ha la `posizione` esplicita per riga (§5.2). Differenza attesa A10.
16. **Spareggio della classifica precedente** con i pronostici vinti **fino alla giornata precedente**: confermato (§5.2, N10).
17. **Il sostituto (SIRACUSA) eredita i pronostici vinti del ritirato (PULIZZER)** per lo spareggio, coerente con i punti ereditati nella Sessione 20: confermato, è il comportamento di oggi.
18. **Le selezioni «(ANNULLATA ECCESSO)» non contano come voto** nella Scelta del gruppo (correzione di un errore). Differenza attesa A11.
19. **Semper Fidelis conta giornate distinte**, solo partite giocate (esito finale) e pronostici non annullati. Differenza attesa A12.
20. **Amuleto/maledetta: solo la squadra scelta** dal pronostico (1/1X → casa, 2/X2 → ospite; primo segno prima del `+` nelle combo); Over/Under/Gol/NoGol/Pari/Dispari/X non contano per nessuna squadra (§8.2). Differenza attesa A13.
21. **Coppa «definitiva» quando la Giornata 34 è conclusa** (`34 in giornate_concluse`): il campo si chiama `definitiva` (§9). Differenza attesa A14.
22. **Timer dell'ultima schedina vinta**: una schedina chiusa con vincita potenziale 0 non produce la riga «chiude la schedina» in Cassa e non fa ripartire il timer. Replicato il comportamento di oggi: confermato.
23. **Giornata di riferimento per tendenza e delta del podio** = ultima con almeno un punto diverso da 0. Replicato il comportamento di oggi: confermato.

### Testi e contenuto

24. **Titoli e descrizioni delle card NON nello snapshot**: stanno nel React come testo statico. Nello snapshot restano le chiavi fisse di `premi` (§8.2).
25. **Numeri del Regolamento nello snapshot** da una costante `REGOLE` in `statistiche.py` (§10, N20): 16 giocatori, obiettivo 3.200 €, ripartizione 40/27/17/10/6.
26. **Versione e novità** in un file del repo del sito, non nello snapshot: confermato. `VERSIONE_APP`/`NOVITA` di `app.py` diventano inutili con lo spegnimento di Streamlit.
27. **`win_rate` e `quota_media` consegnati già arrotondati** dal Python come li mostra oggi il sito (win rate 1 decimale, quota 2 decimali), così sito vecchio e nuovo coincidono (§8). Risolve la differenza di arrotondamento Python/JavaScript sui valori a metà.
28. **Nome del giocatore = chiave**, in maiuscolo: confermato. Se un giorno servisse distinguere due omonimi, servirà un `id`.
29. **Cosa NON c'è nello snapshot, di proposito** (oggi il sito non lo mostra, vincolo 5): i pronostici vinti per lo spareggio, le righe scartate e le incoerenze (log del bot e `avvisa_admin()`), la sparkline del podio (D18). Un campo opzionale si aggiunge senza cambiare `versione_schema`: confermato.
30. **`giocatori` (elenco dei «pills»)** = chi ha righe in Giocate, quindi SIRACUSA sì e PULIZZER no (come oggi): confermato.
31. **`giornata_corrente`** = giornata più alta in Giocate: confermato.
