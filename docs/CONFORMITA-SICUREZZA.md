# Conformità e sicurezza — Toto-Amici (sito 3.0)
Data: 31/10/2026 · Sito verificato: https://toto-amici.totoamici.workers.dev · Versione del codice: 864b11f (branch `rilascio-3.0`, **non ancora online**; online c'è la versione precedente, fino a dd39a16)
Dati: reali (nomi dei giocatori del torneo, pronostici, importi della cassa)

> Questo rapporto non è una consulenza legale. Dove serve un giudizio giuridico è scritto cosa si è osservato e cosa far confermare a un consulente.

## Cosa è cambiato rispetto al 24-25/10/2026
- **Modifiche al sito dal rapporto precedente** (`git diff ff029e6..864b11f -- frontend/`, 18 file, di cui 4 di test; commit 0c2531a, 6b78422, ee63daa, 5efe435, 864b11f):
  - **Ricarica automatica dopo un deploy** (`frontend/src/lib/ricaricaDopoDeploy.ts`, attivata in `frontend/src/main.tsx:8`) e **riquadro «Il sito è stato aggiornato: ricarica la pagina»** (`frontend/src/shell/ErroreScheda.tsx`, usato in `frontend/src/shell/Schede.tsx:58`). Già descritte il 24-25/10; ora sono **committate e online** (il testo `toto-ricarica-dopo-deploy` e il riquadro sono nel file `assets/index-CMNnkpr2.js` servito oggi dal sito).
  - **Storico punteggi ordinabile** in Classifica (`StoricoGiornate.tsx`, nuova funzione `ordinaStorico` in `frontend/src/schede/classifica-cassa-regolamento/storico.ts`): toccando l'intestazione G1, G2… o «Tot.» si riordinano le righe. Solo riordino nel browser dei numeri già presenti. **Online.**
  - **Grafici dell'andamento** in Statistiche (`AndamentoGrafici.tsx`, `GraficoLinee.tsx`, `andamento.ts` in `frontend/src/schede/statistiche-coppa/`): due grafici a linee disegnati a mano in SVG (nessuna libreria nuova), con la possibilità di mettere in risalto fino a 4 giocatori; la scelta resta sul dispositivo in `localStorage` con la chiave `andamento-giocatori`. **Online.** Una precisazione rispetto a quanto annotato il 25/10: la chiave **non** si scrive solo quando il visitatore sceglie, ma appena apre la scheda Statistiche (problema 4).
  - **Confronto Giocate, riga «Punti fatti»** (864b11f, `frontend/src/schede/ConfrontoGiocate.tsx:123-139`, `frontend/src/schede/live-confronto/dati.ts:30-50`): ora «fatti/massimo della giornata» e sotto «rimanenti N pt». Solo calcolo nel browser con dati già presenti. **È l'unica modifica non ancora online.**
- **Verificato:** nessuna nuova dipendenza (`git diff ff029e6..864b11f -- frontend/package.json frontend/package-lock.json` → vuoto); nessuna nuova richiesta di rete (l'unica `fetch` del browser resta `frontend/src/lib/api.ts:24`); nessun inserimento di HTML; nessun dato nuovo (i grafici e lo storico usano `classifica.giocatori[].punti_per_giornata`, già nello snapshot e già mostrato); Worker, `_headers`, `robots.txt`, `index.html` e `wrangler.jsonc` **non cambiati** (`git log ff029e6..864b11f -- frontend/worker frontend/public frontend/wrangler.jsonc frontend/index.html` → vuoto). Archiviazioni sul dispositivo: le tre già annotate (`tema`, `andamento-giocatori`, `toto-ricarica-dopo-deploy`), nessuna nuova.
- **Esito dei problemi del 24-25/10:**
  - problema 1 (nota privacy) → invariato, decisione dell'utente;
  - problema 2 (contrasto dei giocatori attenuati) → **ancora aperto**, file non cambiato (`frontend/src/componenti/SelettoreGiocatore.tsx:60`);
  - problema 3 (7 avvisi negli strumenti di sviluppo) → **invariato**, stesse versioni installate e stessi avvisi;
  - problemi 4 e 5 (info) → invariati;
  - problema 6 (ciclo di ricarica) → chiuso il 24/10, tolto dalla tabella.
- **Nuovo:** problema 4 (bassa), la chiave `andamento-giocatori` scritta senza una scelta del visitatore. **Corretto lo stesso giorno, prima della pubblicazione**: lo `useEffect` è stato tolto e la chiave si scrive solo quando il visitatore tocca «Tutti» o un giocatore (verificato in anteprima con memoria pulita: aprendo Statistiche la chiave non compare; toccando un giocatore sì).

## In breve
Sì, la versione 864b11f è pubblicabile: non ci sono problemi critici né alti, e rispetto a quella già online cambia solo il modo in cui Confronto Giocate mostra i punti (calcolo nel browser, nessun dato o richiesta nuovi). Il sito pubblicato oggi continua a fare quello che deve: nessun cookie, nessuna richiesta ad altri siti, tutte le intestazioni di sicurezza presenti, fuori dai motori di ricerca, console senza errori. Una sola cosa nuova da sapere: aprendo Statistiche il sito salva sul dispositivo i nomi dei primi tre giocatori anche se il visitatore non ha scelto niente. Non serve un banner (sono nomi già pubblici e non escono dal dispositivo), ma conviene salvarli solo quando si sceglie davvero: è più pulito e risolve anche un piccolo difetto (chi non ha mai scelto continua a vedere evidenziati i primi tre di quel giorno anche quando la classifica cambia). Da fare per primi: `npm audit fix` prima del prossimo `wrangler deploy` (10 minuti), poi il salvataggio della scelta solo al tocco (15 minuti), poi il contrasto dei giocatori attenuati.

## Problemi trovati
| # | Gravità | Problema in parole semplici | Dove / prova | Correzione proposta | Impegno |
|---|---------|-----------------------------|--------------|---------------------|---------|
| 1 | bassa | Il sito non ha una nota privacy. Decisione presa dall'utente il 04/10. Il rischio legale è basso (e ancora più basso con il sito fuori dai motori di ricerca), ma va saputo che pubblicare dati di persone su un sito aperto a chiunque di solito **non** rientra nell'esenzione per le attività «personali o domestiche» del GDPR (art. 2.2.c; Corte di giustizia UE, causa Lindqvist C-101/01) | `grep -rniE "privacy\|informativa" frontend/src frontend/index.html frontend/public` → nessun risultato | Far confermare a un consulente se serve. La soluzione più semplice resta la nota breve proposta più sotto (aggiornata), nel piè di pagina (`frontend/src/shell/PiePagina.tsx`) | 15 min |
| 2 | bassa | I giocatori senza schedina sono attenuati e il loro nome diventa difficile da leggere: contrasto 2,7:1 col tema chiaro e 3,6:1 con lo scuro, sotto il minimo consigliato di 4,5:1 | `frontend/src/componenti/SelettoreGiocatore.tsx:60` (`opacity-60` su tutto il pulsante), invariato (`git log ff029e6..864b11f -- frontend/src/componenti/SelettoreGiocatore.tsx` → vuoto) | Attenuare solo lo sfondo (o usare un bordo tratteggiato / un trattino «—» accanto al nome) e lasciare il testo a colore pieno. Il testo nascosto «, nessuna schedina» per i lettori di schermo c'è già e va bene | 15 min |
| 3 | bassa | Sette avvisi negli strumenti di sviluppo (5 alti, 2 medi): `vite` (costruisce il sito e fa da server di prova sul computer), `undici`/`sharp` (dentro `wrangler`, che serve a provare e pubblicare), `vitest` (i test). Non finiscono nel sito. Il più delicato riguarda il server di prova di `vite`, solo mentre è acceso sul computer | `npm audit --omit=dev` → `found 0 vulnerabilities`; `npm audit` → `7 vulnerabilities (2 moderate, 5 high)`: `vite 8.3.0 - 8.3.2`, `undici 7.0.0 - 7.30.0`, `sharp <0.35.5` (via `miniflare` → `wrangler 4.147.0`), `@vitest/mocker <=4.1.11`. `npm ls`: `vite@8.3.2`, `vitest@4.1.11`, `wrangler@4.147.0`, `undici@7.29.1` — identico al 24/10 | `npm audit fix` (mai `--force`), poi `npm run build`, `npx vitest run` e una prova con `npm run cf:dev` prima del prossimo `wrangler deploy` | 10 min |
| 4 | bassa | **Nuovo.** Aprendo la scheda Statistiche il sito salva sul dispositivo (`localStorage`, chiave `andamento-giocatori`) i nomi dei primi tre della classifica, anche se il visitatore non ha toccato niente. Non è un problema di consenso (nomi già pubblici, mai inviati a nessuno, solo per i grafici), ma salva più del necessario. E ha un effetto pratico: chi non ha mai scelto, alla visita dopo vede evidenziati i primi tre **di quel giorno**, non quelli attuali, per sempre su quel dispositivo | `frontend/src/schede/statistiche-coppa/AndamentoGrafici.tsx:71-77`: `useEffect(() => localStorage.setItem(CHIAVE, JSON.stringify(scelti)), [scelti])` gira anche alla prima apertura con la scelta predefinita (`sceltiIniziali`, riga 68). Sul sito vero, browser pulito: prima `localStorage` vuoto; dopo aver solo aperto Statistiche → chiave presente con 3 voci (slot 1, 2, 3) | Togliere lo `useEffect` e salvare solo nei tocchi del visitatore: una funzione `scegli(nuovi)` che fa `setScelti(nuovi)` e `localStorage.setItem(...)` (dentro try/catch), chiamata dal pulsante «Tutti» (riga 97) e dai pulsanti dei giocatori (riga 110). Un test: aprire la scheda senza toccare non scrive niente | 15 min |
| 5 | info | Con `curl`, l'indirizzo `http://` risponde senza passare a `https://` | `curl -sI http://toto-amici.totoamici.workers.dev/` → `HTTP/1.1 200 OK` | Nessuna azione: tutto il dominio `.dev` è nell'elenco HSTS precaricato dei browser, quindi i browser aprono sempre la versione `https`. Il sito invia comunque `Strict-Transport-Security` | — |
| 6 | info | Cloudflare aggiunge da sé le intestazioni `NEL`/`Report-To`: se una pagina non si carica per un errore di rete, il browser lo segnala a `a.nel.cloudflare.com` | `curl -sI $SITO/` → `nel: {"report_to":"cf-nel",…}` | Nessuna azione: è lo stesso fornitore che ospita il sito, solo in caso di errore. Se si scrive la nota privacy, è già coperta dalla frase su Cloudflare | — |

Gravità: critica = prima di pubblicare; alta = entro pochi giorni; media = alla prossima modifica; bassa = miglioramento; info = nessuna azione.

**Rischio residuo accettato (dal 04/10):** il tetto di 4 chiamate al minuto verso Football-Data vale per ogni copia del Worker; chi riuscisse a raggiungerne molte in parallelo potrebbe consumare il limite condiviso col bot (`frontend/worker/live.ts:27`, invariato). Contromisura, se un giorno servisse: dominio proprio + regola di rate limiting Cloudflare su `/api/live`.

## Dettaglio per area

### 1. Inventario dei dati personali — ok
Unica fonte di dati: lo snapshot che il bot pubblica su Cloudflare KV, letto da `/api/snapshot`. Controllati oggi solo i nomi dei campi e il conteggio di formati sensibili, senza riportare i dati: sezioni `versione_schema`, `generato_il`, `stagione`, `giornata_corrente`, `giocatori`, `classifica`, `cassa`, `partite`, `schedine`, `statistiche`, `coppa`, `regole` (come il 24/10); 0 indirizzi email, 0 numeri di telefono; 218 KB (cresce con le giornate). Le righe della classifica hanno `posizione`, `nome`, `punti_totali`, `variazione_posizione`, `punti_ultima_giornata`, `punti_per_giornata`: i grafici e lo storico ordinabile usano solo questi, già mostrati dallo storico per giornata. Nessun dato in più.

| Dato | Scopo | Base giuridica (proposta, da confermare) | Conservazione | Destinatario |
|---|---|---|---|---|
| Nome/soprannome, pronostici, punti, importi della cassa | Mostrare il torneo ai partecipanti | Consenso dei partecipanti (art. 6.1.a) o legittimo interesse dell'organizzatore (art. 6.1.f) | Per la stagione; poi `archivia_stagione()` del bot | Chiunque apra il sito (pubblico, ma fuori dai motori di ricerca); Cloudflare come fornitore |
| Indirizzo IP dei visitatori | Funzionamento e sicurezza del servizio | Legittimo interesse (art. 6.1.f) | Log tecnici di Cloudflare (`observability` in `frontend/wrangler.jsonc`); il Worker non scrive nulla nei log | Cloudflare |
| Scelta del tema chiaro/scuro (`localStorage`, `tema`) | Ricordare la preferenza | Strumento tecnico, nessun consenso necessario | Finché l'utente non la cancella | Resta sul dispositivo |
| Giocatori evidenziati nei grafici (`localStorage`, `andamento-giocatori`): nomi già pubblici sul sito, non identifica chi guarda | Ricordare quali linee mettere in risalto | Strumento tecnico/funzionale, nessun consenso necessario | Finché l'utente non la cancella; oggi scritta anche senza una scelta (problema 4) | Resta sul dispositivo, non viene inviata a nessuno |
| Orario dell'ultima ricarica automatica (`sessionStorage`, `toto-ricarica-dopo-deploy`): non è un dato personale | Evitare che la pagina si ricarichi in ciclo dopo un deploy | Strumento tecnico, nessun consenso necessario | Fino alla chiusura della scheda del browser | Resta sul dispositivo |

Nessun modulo, campo da compilare, login, analytics o pixel.

### 2. Informativa privacy e cookie policy — problema (bassa, decisione dell'utente)
Nessuna nota privacy (problema 1). Non serve una cookie policy perché non ci sono cookie. Niente ragione sociale o partita IVA: non è il sito di un'impresa.

### 3. Cookie — ok (con un ritocco, problema 4)
Sul sito vero, browser pulito, aperta la prima pagina: `document.cookie` vuoto, `localStorage` vuoto, `sessionStorage` vuoto, nessun service worker. `curl -sI` su `/`, `/classifica`, `/api/segnale` → nessun `set-cookie`. Dopo aver aperto Statistiche e Confronto Giocate (senza toccare altro): `document.cookie` sempre vuoto, `sessionStorage` vuoto, `localStorage` con la sola chiave `andamento-giocatori` (3 voci).

Nel codice (`grep -rnE "localStorage|sessionStorage|indexedDB|document.cookie|serviceWorker"` su `src`, `public`, `index.html`) le scritture sono tre:
- `localStorage.setItem("tema", …)` quando l'utente cambia tema a mano (`frontend/src/lib/tema.ts:31`; letta anche da `frontend/public/tema.js:3`);
- `localStorage.setItem("andamento-giocatori", …)` (`frontend/src/schede/statistiche-coppa/AndamentoGrafici.tsx:73`), dopo la correzione del 31/10 solo quando il visitatore tocca «Tutti» o un giocatore (problema 4, corretto). La lettura è protetta: `JSON.parse` dentro try/catch e `leggiScelti` (`andamento.ts:131-144`) tiene solo nomi presenti nello snapshot e colori numerati da 1 a 4, quindi un valore manomesso a mano nel browser non può inserire niente nella pagina;
- `sessionStorage.setItem("toto-ricarica-dopo-deploy", <orario>)` solo quando un blocco di codice non si trova dopo un deploy (`frontend/src/lib/ricaricaDopoDeploy.ts:22`).

Cosa si osserva su tutte e tre: nessun identificativo né profilazione, nessun invio al server o ad altri, servono solo a far funzionare quello che l'utente vede o ha chiesto. L'art. 122 del Codice privacy e le linee guida del Garante sui cookie (10/06/2021) esentano dal consenso gli strumenti tecnici, compresi quelli «di funzionalità» che ricordano scelte dell'utente: queste hanno le caratteristiche tipiche di quella categoria, **nessun banner necessario**. Il problema 4 non cambia questa valutazione: è una questione di minimizzazione e di comportamento, non di consenso. Da far confermare a un consulente solo se si scrive l'informativa completa; nella nota breve basta citarle (testo aggiornato più sotto).

### 4. Richieste ad altri siti — ok
Traffico reale del browser sul sito vero (Classifica, Statistiche, Confronto Giocate, scorse fino in fondo): 13 richieste, **tutte** a `toto-amici.totoamici.workers.dev` (`tema.js`, stile, script principale e blocchi di ClassificaCassa, Statistiche, ConfrontoGiocate, tre font, `/api/segnale`, `/api/snapshot`). Nessuna chiamata a `/api/live` (la scheda Schedine Live non è stata aperta di proposito). Nella build di 864b11f gli unici indirizzi esterni sono `http://www.w3.org` (19 volte, dentro gli SVG, non scaricato) e `https://react.dev` (2 volte, testo dei messaggi d'errore di React, non scaricato): `grep -rhoE "https?://[a-z0-9.-]+" dist | sort | uniq -c`. I grafici nuovi sono SVG scritti nel codice, senza librerie né immagini esterne. Identico al 24/10.

### 5. Fornitori e trasferimenti fuori UE — non verificato in parte
- **Cloudflare** (hosting, KV, log): sede USA. DPA incluso nei termini dell'account; certificazione EU-US Data Privacy Framework non controllata (vedi «Cosa non è stato verificato»).
- **Football-Data.org**: riceve solo la richiesta del Worker con la chiave del progetto; nessun dato dei visitatori.
- **Google Sheets / Gemini / Telegram / Render**: usati dal bot, non dal sito; fuori dall'ambito.
Nessun fornitore nuovo.

### 6. Intestazioni di sicurezza sul sito vero — ok
`curl -sI` su `/` e `/classifica`: presenti `Content-Security-Policy` (solo `'self'`, `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'none'`, `manifest-src 'self'`, `upgrade-insecure-requests`), `Strict-Transport-Security: max-age=31536000; includeSubDomains`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, `Cross-Origin-Opener-Policy: same-origin`, `X-Robots-Tag: noindex, nofollow`. Su `/api/segnale`: `nosniff`, `Referrer-Policy`, `Cross-Origin-Resource-Policy: same-origin`, CSP `default-src 'none'; frame-ancestors 'none'`, `x-robots-tag: noindex, nofollow`; nessun `Access-Control-Allow-Origin`. `robots.txt` → `200 text/plain`, `User-agent: * / Disallow: /`. Console del browser dopo Classifica, Statistiche (con i grafici) e Confronto Giocate: **nessun messaggio**, quindi nessuna violazione della CSP: gli attributi `style` dei grafici (colori `var(--serie-N)`) sono coperti da `style-src 'unsafe-inline'`, già ammesso (rischio basso: gli script restano solo del sito). La build 864b11f ha `_headers` e `robots.txt` identici a quelli online (`diff` di `frontend/public/_headers` con la versione ff029e6 e con `frontend/dist/_headers` → nessuna differenza). Il passaggio a `https`: problema 5.

### 7. Revisione del codice (OWASP Top 10) — ok
- XSS: `grep` di `dangerouslySetInnerHTML|innerHTML|outerHTML|insertAdjacentHTML|document.write|eval(|new Function(` su `src`, `worker`, `public`, `index.html` → nessun risultato. Nei grafici i nomi dei giocatori arrivano come testo React (`GraficoLinee.tsx:229-231`, `AndamentoGrafici.tsx:116`); gli unici valori messi in `style` sono `var(--serie-N)` con N intero da 1 a 4 (`andamento.ts:107`, controllato in `leggiScelti` riga 138) o colori fissi; i percorsi SVG sono costruiti solo da numeri (`GraficoLinee.tsx:84`).
- Redirect, `target="_blank"`, `window.open`, `postMessage`, `location.href/assign/replace`: nessun risultato. Le uniche azioni sulla pagina sono `location.reload()` della pagina stessa (`ricaricaDopoDeploy.ts:32`, `ErroreScheda.tsx:22`).
- Confronto Giocate (864b11f): `puntiMassimiGiornata` e `puntiRimanenti` (`dati.ts:40-50`) leggono `regole.punti[tipologia]` con la tipologia sempre una delle quattro fisse (`dati.ts:22-27`): nessun accesso a chiavi scelte dai dati.
- Storico ordinabile: `ordinaStorico` (`storico.ts:18-29`) riordina una copia delle righe; nessun dato nuovo, nessun parametro dall'indirizzo.
- Riquadro d'errore: mostra solo testo fisso, l'errore tecnico non arriva al giocatore.
- Test e controlli: `npx vitest run` → **72 test passati** (11 file; erano 54), `tsc` del sito e del Worker senza errori, `npm run build` riuscita.
- `/api/live`, SSRF, gestione errori, metodi HTTP: Worker **non cambiato** dal 24/10; valgono le verifiche del 17/10 (giornata accettata solo 1-38, URL di Football-Data fisso, messaggi d'errore fissi, 405 sui metodi diversi da GET/HEAD).
- Controllo accessi: nessuna area riservata; API pubbliche per scelta e solo in lettura.

### 8. Dipendenze, segreti, .gitignore, source map — ok (avvisi negli strumenti, problema 3)
- `npm audit --omit=dev` → 0 vulnerabilità per ciò che arriva nel sito. `npm audit` completo → 7 avvisi, solo strumenti (problema 3). `package-lock.json` presente e non cambiato dal 24/10.
- Segreti: i 9 commit `ff029e6..864b11f` (tutto il repository, non solo `frontend/`) controllati con `grep` sui formati di chiavi Google, Telegram, GitHub, GitLab, AWS, chiavi private, Slack, Stripe e stringhe di 32 caratteri esadecimali (formato della chiave Football-Data), più assegnazioni `api_key/secret/token/password =` → **0 risultati**. Stessa ricerca sulla build `dist` → 0 risultati. gitleaks non è installato.
- File sensibili tracciati: nessuno (controllo con `git ls-files` invariato dal 24/10; nessun file di configurazione o segreto tra i file cambiati, solo sorgenti, test e documenti).
- Source map: 0 file `.map` nella build (`find dist -name "*.map" | wc -l` → 0).

### 9. Accessi e abusi — ok
Nessun login, area protetta o modulo. Unico abuso possibile resta il consumo del limite di Football-Data via `/api/live` (rischio residuo accettato, vedi sopra). In questa verifica **nessuna** chiamata a `/api/live`.

### 10. Difese al bordo (Cloudflare) — ok per quanto visibile; pannello non verificato
`curl -sI` → `server: cloudflare`. Pagine in cache (`cf-cache-status: HIT`, `cache-control: public, max-age=0, must-revalidate`): corretto, sono uguali per tutti. `/api/segnale`: `cache-control: public, max-age=60` (dati pubblici, nessun login). Sull'indirizzo `*.workers.dev` WAF e regole di rate limiting del pannello non si applicano: servirebbe un dominio proprio.

### 11. Backup, ripristino, accesso agli account — in parte verificato
Invariato: codice su GitHub, GitLab e copia locale in `~/Backups/Toto_Amici` (`scripts/backup_locale.sh`); la fonte vera dei dati è Google Sheets, lo snapshot su KV viene rigenerato dal bot. Non verificabili dal codice: 2FA sugli account e un ripristino mai provato (vedi sotto).

### 12. Accessibilità — ok, con un ritocco (problema 2)
- Grafici: ogni grafico ha una descrizione a parole per i lettori di schermo, si usa con le frecce della tastiera, e c'è il pulsante «Mostra come tabella» con tutti i numeri. I colori 3 e 4 delle linee hanno poco contrasto sul tema chiaro (2,8:1 e 2,2:1 su bianco, sotto il 3:1 consigliato per gli elementi grafici; `frontend/src/index.css:58-63`, già annotato nel commento): compensato dal nome scritto in colore pieno in fondo a ogni linea e dalla vista tabella, quindi nessuna azione.
- Storico ordinabile: intestazioni come pulsanti con etichetta («Ordina per Giornata 3») e `aria-sort`; la colonna scelta usa testo pieno su un velo azzurro (18,5:1 chiaro, 14,6:1 scuro) e la colonna attiva `accento-testo` (5,8:1 chiaro, 11,5:1 scuro): ok.
- Confronto Giocate: «rimanenti» usa `text-ink-2` su `superficie-2`, come il «/massimo» (6,6:1 chiaro, 7,7:1 scuro); per i lettori di schermo una frase completa («N punti fatti su M possibili nella giornata; al massimo può ancora arrivare a R»).
- Resta aperto il contrasto dei giocatori attenuati (problema 2). Torneo privato senza attività commerciale: **probabilmente non soggetto** all'European Accessibility Act.

## Nota privacy proposta (se si cambia idea sul problema 1)
> **Privacy.** Questo sito è il tabellone di un torneo di pronostici fra amici. Mostra nomi, pronostici e importi della cassa dei partecipanti, che ne sono informati. Non usa cookie, non ha pubblicità né strumenti di statistica e non carica nulla da altri siti. Sul tuo dispositivo restano solo la scelta del tema chiaro/scuro, se la cambi, i giocatori che metti in risalto nei grafici delle Statistiche e, se il sito si ricarica da solo dopo un aggiornamento, l'orario di quella ricarica, che si cancella chiudendo la scheda. Niente di tutto questo viene inviato a noi o ad altri. Il sito è ospitato da Cloudflare, che registra temporaneamente l'indirizzo IP delle richieste per far funzionare il servizio. I risultati delle partite arrivano da football-data.org tramite il nostro server: il tuo IP non viene loro comunicato. Per chiedere la modifica o la rimozione dei tuoi dati scrivi a: **[contatto dell'organizzatore: da inserire]**.

## Cosa serve solo quando i dati diventano reali
I dati sono già reali. Quello che servirebbe solo se il sito si aprisse a persone esterne al gruppo o diventasse un'attività a pagamento:
- informativa completa (art. 13) con titolare e contatto, rivista da un consulente;
- registro dei trattamenti (art. 30) e conferma del DPA con Cloudflare;
- dominio proprio, per poter attivare WAF e rate limiting di Cloudflare;
- rivalutazione dell'European Accessibility Act.

## Cosa non è stato verificato
- **La versione 864b11f sul sito vero**: non è pubblicata (online `assets/index-CMNnkpr2.js` e `ConfrontoGiocate-BzsZgkcG.js`, che contiene ancora «ancora possibili» e non «rimanenti»; la build locale è `assets/index-CRunNTgf.js`). La modifica di Confronto Giocate è stata verificata su codice, test e build. Dopo il `wrangler deploy`: riaprire Confronto Giocate, controllare che la console resti vuota e che compaia la riga «rimanenti».
- **La ricarica dopo deploy, nel suo caso vero**: il codice è online, ma per vederla scattare servono due pubblicazioni con una pagina aperta nel mezzo. Prova suggerita al prossimo deploy: aprire il sito, pubblicare, poi aprire una scheda mai aperta prima; la pagina deve ricaricarsi una volta e mostrare la scheda, la console deve restare senza violazioni della CSP, e in *Strumenti per sviluppatori → Applicazione → Session storage* deve comparire solo la chiave `toto-ricarica-dopo-deploy` con un numero.
- **Scheda Schedine Live sul sito vero**: non aperta di proposito, per non chiamare `/api/live` (limite condiviso col bot). Non è cambiata dal 17/10, quando era stata verificata.
- **Lo storico ordinabile sul sito vero**: presente nel codice online (`ClassificaCassa-C0O6Jtqy.js`), ma le intestazioni non sono state toccate; verificato su codice e test.
- **Pannello Cloudflare**: 2FA, chi ha accesso, durata dei log di `observability`. Dove guardare: dash.cloudflare.com → *Manage Account* → *Members*; profilo → *Authentication*; *Workers & Pages* → `toto-amici` → *Observability*.
- **Account GitLab, GitHub, Google (Sheets) e Telegram**: 2FA attiva? Domanda da porre all'utente.
- **Ripristino**: mai provato un ripristino dal repository di backup o dei segreti.
- **Certificazione EU-US Data Privacy Framework di Cloudflare**: non controllata su dataprivacyframework.gov.
- **Indicizzazione**: non ricontrollata oggi con una ricerca web; `robots.txt` e `X-Robots-Tag` sono presenti e invariati.
- **Storia git completa con gitleaks**: non installato; usato `grep` sui formati di chiave principali, solo sui commit nuovi (la storia precedente era stata controllata il 04/10, il 17/10 e il 24/10).
- **Comportamento del tetto a Football-Data con molte copie del Worker**: non misurabile senza un test di carico, escluso dalle regole di questa verifica.
