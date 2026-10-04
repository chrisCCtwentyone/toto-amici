# Guida per chi costruisce una scheda

Sito nuovo di Toto-Amici: **Vite + React + TypeScript + Tailwind v4 + motion**, servito da **un solo Cloudflare Worker** con static assets. La base (shell, tema, dati, componenti, Worker) è pronta: a te resta **una scheda**, cioè **un file** in `src/schede/`.

Contratto dati: [`../restyling/snapshot-schema.md`](../restyling/snapshot-schema.md) (`versione_schema: 1`). Decisioni e contesto: [`../RESTYLING.md`](../RESTYLING.md). Stile: direzione 5 «Diretta» di `../restyling/proposte-stili.html`.

## Comandi

Da dentro `frontend/`:

| Comando | Cosa fa |
|---|---|
| `npm run dev` | Sito su http://localhost:5173 con **dati veri locali** (nessun Cloudflare). |
| `npm run build` | Typecheck + build in `dist/`. |
| `npm run typecheck` | Solo typecheck (sito + Worker). |
| `npm test` | Test unitari (vitest). `npm run test:watch` per il ciclo veloce. |
| `npm run cf:dev` | Build + Worker vero in locale (`wrangler dev`, KV locale vuoto; serve `.dev.vars`, vedi sotto). |
| `npx playwright-cli ...` | Verifiche nel browser (config in `.playwright/cli.config.json`, usa chromium). |

**Prima volta:** serve `restyling/snapshot-locale.json` (dati veri, **gitignored**). Se manca: dalla radice del repo `python3 scripts/genera_snapshot_locale.py` (legge Sheets in sola lettura, una chiamata a Football-Data). Non va committato.

**Football-Data:** il limite (10 richieste/minuto) è condiviso col bot in produzione. In `npm run dev` `/api/live` è **finto** (dev/mock-api.ts), non chiama nessuno. Non lanciare cicli di richieste vere.

### Prove utili in sviluppo

| Indirizzo | Effetto |
|---|---|
| `/?vetrina` | Vetrina di tutti i componenti condivisi con dati veri (copia l'uso da `src/vetrina/Vetrina.tsx`). |
| `/?devEta=300` | Il segnale risulta vecchio di 300 minuti: compare l'avviso «dati vecchi». |
| `/?devSegnale=assente` | `/api/segnale` risponde 404. |
| `/?devSnapshot=errore` | `/api/snapshot` risponde 500: pagina d'errore. |
| `/#coppa` | Apre direttamente una scheda (`classifica`, `live`, `confronto`, `statistiche`, `coppa`, `regolamento`). |

Per provare il tema: bottone in alto a destra, oppure `document.documentElement.dataset.tema = "chiaro" | "scuro"` dalla console.

## Come è organizzato

```
frontend/
  worker/index.ts, live.ts     Worker: /api/snapshot, /api/segnale, /api/live
  wrangler.jsonc               un Worker + static assets + KV "SNAPSHOT"
  dev/mock-api.ts              API finte per npm run dev (solo sviluppo)
  src/
    schede/                    UNA SCHEDA = UN FILE (+ registro.ts)  <-- il tuo lavoro
    componenti/                componenti condivisi (index.ts li esporta tutti)
    shell/                     intestazione, barra schede, banner, ticker, pie' di pagina
    lib/                       formattatori, dati, live, esiti, tema (condivisi)
    tipi/snapshot.ts           tipi TypeScript dello schema
    index.css                  design token del tema Diretta (chiaro + scuro)
    vetrina/                   solo sviluppo
```

La shell monta la tua scheda **solo a dati pronti**: dentro la scheda lo snapshot esiste sempre. Il caricamento, gli errori, l'avviso «dati vecchi», la barra delle schede e la transizione fra schede li gestisce la shell: non rifarli.

### Il tuo file

`src/schede/<Nome>.tsx` ha un `export default function Nome()` senza props. **Sostituisci il contenuto, tieni il nome del file e `export default`** (il registro lo importa a richiesta). Puoi creare sottocartelle/componenti privati accanto, ad esempio `src/schede/classifica/Podio.tsx`.

| File | Cosa mostra | Sezioni dello schema da cui legge |
|---|---|---|
| `ClassificaCassa.tsx` | podio, classifica con tendenza, ritirati, storico per giornata; Fondo Cassa, barra, grafico versamenti, movimenti | §5 `classifica`, §6 `cassa`; il titolo/stagione è già in shell |
| `SchedineLive.tsx` | selettori giornata e giocatore; riepilogo esiti, vincita potenziale; carte per partita con pronostico, quota, esito, punti; **risultato in diretta** | §7 `giornata_corrente`, `giocatori`, `schedine`, `partite`; live dal Worker (`useLive`); `regole.soglia_quota_doppia` per l'asterisco |
| `ConfrontoGiocate.tsx` | griglia partite × giocatori, colori per esito, riga «Vincita potenziale», colonna «Scelta del gruppo» | §7 `partite` (righe, già in ordine) × `schedine[].righe` (celle), `partite[].scelta_gruppo`, `regole.soglia_quota_doppia` |
| `Statistiche.tsx` | timer ultima schedina vinta, protagonisti, giornata da incorniciare, Semper Fidelis, squadre amuleto/maledetta, per un soffio, tabella completa (+ ritirati) | §8 `statistiche` (titoli e descrizioni delle card sono testo del sito, §17.24) |
| `Coppa.tsx` | tabellone a 16 su 4 turni, provvisorio/definitivo, campione, avviso «16 partecipanti» | §9 `coppa` (+ testi statici «Come funziona») |
| `Regolamento.tsx` | bolletta, punteggi, regole, Cassa e premi | §10 `regole` (numeri) + testi statici del sito; gli importi dei premi: `obiettivo_cassa × percentuale / 100` |

Mappa completa scheda → sezioni: §11 dello schema.

## Come leggere i dati

```tsx
import { useSnapshot } from "../lib/DatiContext";
const s = useSnapshot();            // Snapshot tipato, sempre presente
s.classifica.giocatori              // già ordinati, con `posizione` esplicita
```

- **Tipi:** `src/tipi/snapshot.ts` (`Snapshot`, `Schedina`, `Esito`...). Se lo schema cambia, si cambia lì.
- **Filtrare per giornata/giocatore:** `s.schedine.find(x => x.giornata === g && x.giocatore === nome)`, **confronto per uguaglianza di interi, mai per sottostringa**.
- **Partita di una riga:** `mappaPartite(s).get(riga.partita_id)` (`lib/selettori.ts`). Le partite con `ufficiale: false` hanno id negativo e non hanno risultato live.
- **Selettore di giornata:** `giornateDisponibili(s)` (`lib/selettori.ts`); default `s.giornata_corrente`.
- **Risultati in diretta** (solo Schedine Live, eventualmente Confronto): `const live = useLive(giornata)`, poi `live.partite.get(partita.id)` → `{stato, gol_casa, gol_ospite, minuto?, inizio_il}`. Se `live.nonDisponibile` mostra «risultati non disponibili» e **continua con lo snapshot**. Esito a video: `esitoVisualizzato(riga.esito, livePartita)` e `riepilogoVisualizzato(...)` (`lib/esiti.ts`): «da giocare» diventa «in corso» a partita iniziata, gli esiti finali non si toccano mai.
- **Non chiamare `fetch` dalle schede** (tranne `useLive`): snapshot e segnale li carica e aggiorna il provider (ogni 5 minuti e al ritorno sulla pagina).
- **Array garantiti nell'ordine** (§1): il sito non riordina. Se una lista ti sembra nell'ordine sbagliato è un bug dello snapshot, non da correggere nel React.
- **`null` ≠ 0.** Una quota `null` si mostra «—» (`formattaQuota`), un `punti_per_giornata` `null` è una cella vuota.

## Componenti condivisi (`src/componenti`, tutti da `../componenti`)

| Componente | A cosa serve |
|---|---|
| `BarraObliqua` | riga di classifica «Diretta» (casella posizione, barra proporzionale, nome, valore). Avvolgila in `<ol className="m-0 list-none p-0">`; lunghezza con `frazioneBarra()` (`lib/barre`) |
| `NumeroAnimato` | numero che sale fino al valore; `formato={formattaEuro}` ecc. |
| `Card` | superficie base con titolo (`titolo` + `evidenza` ciano), `bandiera` colorata, `azione` a destra |
| `TitoloSezione` | titolo condensato fuori da una Card |
| `PillolaEsito` | etichetta di un esito (`vinta`, `persa`, `in_corso`...): colore + glifo + testo |
| `PallinoLive` | pallino lampeggiante, o bollino rosa «LIVE» con `etichetta` |
| `Ticker` | striscia rosa scorrevole (decorativa, `aria-hidden`) |
| `SelettoreGiornata` | `‹ menu ›`, target touch 44px |
| `SelettoreGiocatore` | pillole come radiogroup, scorrono in orizzontale su telefono |
| `Pulsante` | `primario` / `secondario`, min 44px |
| `Scheletro`, `StatoVuoto` | caricamento locale e «niente da mostrare» (sempre con una spiegazione) |

Guarda `/?vetrina` per vederli con dati veri. Se ti serve un componente che userebbero anche le altre schede, **non copiarlo**: aggiungilo in `src/componenti/` ed esportalo da `index.ts`.

## Formattatori (`lib/format.ts`) — l'unico posto dove un numero diventa testo

`formattaIntero`, `formattaDecimale(n, dec)`, `formattaEuro`, `formattaEuroIntero`, `formattaQuota`, `formattaPercentuale` (0-100), `formattaFrazione` (0-1), `formattaConSegno`, `formattaOrdinale`, `etichettaGiornata`, `formattaOra`, `formattaData`, `formattaGiornoEsteso`, `testoAggiornamento`, `formattaDurata`. Tutti `it-IT` con migliaia sempre raggruppate (`1.200`, non `1200`), orari in **Europe/Rome**.

## Stile: token, non colori

I colori sono **token** in `src/index.css` (chiaro e scuro con `light-dark()`), esposti come utility Tailwind:

- superfici: `bg-bg`, `bg-superficie`, `bg-superficie-2`, `border-linea`
- testo: `text-ink`, `text-ink-2` (secondario), `text-accento-testo` (ciano leggibile in entrambi i temi), `text-marchio-testo`
- marchio: `bg-accento` + `text-su-accento`, `bg-live` + `text-su-live`, `bg-oro` + `text-su-oro`, `bg-marchio`
- significato: `text-vinta`, `text-persa`, `text-in-corso`, `text-sale`, `text-scende`, `bg-avviso-fondo`
- font: `font-display` (Saira Extra Condensed: titoli e cifre), `font-testo` (Saira, è il default)
- forma: `.obliquo` (parallelogramma) con il testo in un figlio `.contro-obliquo`; `rounded-diretta`; ombra `shadow-card`

Regole:

- **Niente colori letterali** (`#fff`, `text-white`, `bg-[#...]`, `text-blue-500`): usa i token. Se ne serve uno nuovo, si aggiunge **in `index.css` in entrambi i temi**.
- **Mobile first** (375px), poi desktop (`sm:`, `md:`). Niente scroll orizzontale della pagina; target touch ≥ 44px.
- **Movimento:** `motion` (`import { motion } from "motion/react"`), durate brevi, curva `EASE_USCITA` (`lib/movimento`). `MotionConfig reducedMotion="user"` è già in `App`; per CSS puro usa `motion-reduce:`. Mai mettere su **uno stesso elemento** una classe che usa `transform` (es. `.obliquo`) e una prop `x`/`scale` di motion: motion sovrascrive il transform. Metti l'animazione su un elemento esterno.
- **Accessibilità:** il significato non sta mai nel solo colore (le pillole hanno glifo + testo), `focus-visible` è già globale, usa elementi semantici (`<ol>`, `<table>` con `<th scope>`, `<button>`).
- Testi in **italiano**.

## Cosa NON fare

- **Non calcolare** nulla di dominio: niente somme di punti, classifiche, spareggi, percentuali, "chi ha vinto", scelta del gruppo, raggruppamenti per squadra. Se un numero manca nello snapshot, si chiede al lato Python (`statistiche.py`), non si ricostruisce nel React. Sono ammessi solo filtri (giornata, giocatore), ordinamenti di presentazione espliciti e scale grafiche.
- **Non filtrare per sottostringa** (la causa del bug che riscrisse 13 giornate): interi e uguaglianza.
- **Niente `float(x.replace(",", "."))` in versione JS**: i numeri nello snapshot sono già numeri.
- **Niente colori o font letterali**, niente `fetch` diretto, niente `localStorage` per dati.
- **Non toccare** `src/shell/`, `src/lib/DatiContext.tsx`, `index.css`, `worker/` senza concordarlo: sono condivisi. Se serve una modifica, falla piccola e segnalala.
- **Non committare** `restyling/snapshot-locale.json` né `.dev.vars` (sono già ignorati).

## Worker (riferimento)

| Endpoint | Cosa fa |
|---|---|
| `GET /api/snapshot`, `/api/segnale` | restituisce così com'è (senza `JSON.parse`) la chiave KV `snapshot` / `segnale`; cache 60 s; 404 se non pubblicato |
| `GET /api/live?giornata=N` | `{giornata, partite: [{id, stato, gol_casa, gol_ospite, inizio_il, minuto?}], errore?}`; N in 1-38 (400 altrimenti); cache condivisa 120 s; se Football-Data non risponde: **200** con `partite: []` e `errore`, mai 500 |

La chiave Football-Data è il secret `FOOTBALL_DATA_KEY` (`wrangler secret put`), in locale in `.dev.vars` (gitignored). **Non si fa deploy da qui**: lo decide l'utente.
