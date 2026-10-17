# Conformità e sicurezza — Toto-Amici (sito 3.0)
Data: 17/10/2026 · Sito verificato: https://toto-amici.totoamici.workers.dev · Versione del codice: 5375957 (branch `rilascio-3.0`)
Dati: reali (nomi dei giocatori del torneo, pronostici, importi della cassa)

> Questo rapporto non è una consulenza legale. Dove serve un giudizio giuridico è scritto cosa si è osservato e cosa far confermare a un consulente.

## Cosa è cambiato rispetto alla verifica del 04/10/2026
- **Il sito ora è online.** Le verifiche che il 04/10 erano rimaste fuori sono state fatte sul sito vero: intestazioni di sicurezza, richieste ad altri siti, cookie e archiviazione, console senza errori della CSP, cache delle API, passaggio da `http` a `https`.
- **Modifiche al sito dal 04/10** (`git diff 22385f8..5375957 -- frontend/`, 20 file, 4 commit):
  - icona da app, `manifest.webmanifest` e icone per «Aggiungi a Home» (commit ceb1196, già online). La CSP ha una regola in più, `manifest-src 'self'`: è corretta e non apre nulla verso l'esterno;
  - Schedine Live e Confronto si aprono sulla giornata corrente e sul primo giocatore con la schedina (c7ad5a4); i giocatori senza schedina appaiono attenuati;
  - griglia della Classifica che scorre su telefono, riga/riquadro «Punti fatti» che somma dati già presenti nello snapshot (5375957, **non ancora online**: i file JavaScript del sito pubblicato sono diversi da quelli della build locale).
  - Nessuna nuova dipendenza, nessuna nuova richiesta di rete, nessun nuovo dato, nessuna nuova archiviazione sul dispositivo. Il Worker (`frontend/worker/`) non è cambiato.
- **Esito dei problemi del 04/10:** font di Google e intestazioni mancanti → corretti e confermati sul sito vero. Token Telegram nella storia git → chiuso (rigenerato, confermato dall'utente: `PROJECT_LOG.md:152`). Tetto alle chiamate a Football-Data → rischio residuo accettato dall'utente (`PROJECT_LOG.md:152`). Nota privacy → l'utente ha deciso di non metterla (`PROJECT_LOG.md:152`); qui sotto è ripresa solo come promemoria.
- **Nuovo:** il sito non dice ai motori di ricerca di non indicizzarlo (problema 1); un dettaglio di leggibilità nella modifica nuova (problema 3).

## Aggiornamento 17/10/2026, dopo la verifica
- Problema 1 (indicizzazione) corretto: `frontend/public/robots.txt` (`Disallow: /`), `X-Robots-Tag: noindex, nofollow` in `frontend/public/_headers` e nel Worker (`SICUREZZA`, `frontend/worker/index.ts`). Test del progetto passati (Python 1006, sito 51). Sul sito vero: `curl -s $SITO/robots.txt` → `User-agent: * / Disallow: /`; `curl -sI $SITO/` e `curl -sI $SITO/api/segnale` → `x-robots-tag: noindex, nofollow`.
- La modifica 5375957 è stata pubblicata: console senza errori su Confronto Giocate e Schedine Live del sito vero.

## In breve
Sì, la modifica è pubblicabile: non ci sono problemi critici né alti, e i cambiamenti di questa versione sono solo di presentazione. Il sito pubblicato fa quello che deve: nessun cookie, nessuna richiesta ad altri siti, tutte le intestazioni di sicurezza presenti, nessuna chiave nel codice del browser. La cosa da fare per prima è dire ai motori di ricerca di non indicizzare il sito, così nomi e importi degli amici non finiscono su Google (10 minuti). Poi, con calma, un ritocco al contrasto dei giocatori «attenuati» e l'aggiornamento degli strumenti di sviluppo.

## Problemi trovati
| # | Gravità | Problema in parole semplici | Dove / prova | Correzione proposta | Impegno |
|---|---------|-----------------------------|--------------|---------------------|---------|
| 1 | media | Il sito non chiede ai motori di ricerca di restare fuori dai risultati: nomi, pronostici e importi della cassa possono finire su Google. L'indirizzo `*.workers.dev` non è segreto: gli elenchi pubblici di sottodomini lo raccolgono | `curl -s -o /dev/null -w "%{http_code} %{content_type}" $SITO/robots.txt` → `200 text/html` (risponde la pagina del sito, non un `robots.txt`); nessuna intestazione `X-Robots-Tag` in `curl -sI $SITO/`; `grep -rniE "robots\|noindex" frontend/index.html frontend/public` → nessun risultato. Una ricerca web dell'indirizzo il 17/10 non ha trovato pagine indicizzate | 1) in `frontend/public/_headers`, sotto `/*`, aggiungere `X-Robots-Tag: noindex, nofollow`; 2) stessa riga nelle intestazioni del Worker (`SICUREZZA` in `frontend/worker/index.ts:17`) per le risposte `/api/*`; 3) file `frontend/public/robots.txt` con `User-agent: *` e `Disallow: /`. Nota: con `Disallow` i motori non leggono la pagina e quindi non vedono il `noindex`; va bene finché il sito non è indicizzato (oggi non risulta). Se un giorno lo fosse, togliere temporaneamente il `Disallow` e lasciare solo `noindex` | 10 min |
| 2 | bassa | Il sito non ha una nota privacy. Decisione presa dall'utente il 04/10. Il rischio legale è basso, ma va saputo che pubblicare dati di persone su un sito aperto a chiunque di solito **non** rientra nell'esenzione per le attività «personali o domestiche» del GDPR (art. 2.2.c; Corte di giustizia UE, causa Lindqvist C-101/01) | `grep -rniE "privacy\|cookie\|informativa" frontend/src frontend/index.html frontend/public` → nessun risultato; piè di pagina sul sito vero: solo «Toto-Amici 3.0 · sviluppato da …» | Far confermare a un consulente se serve. La soluzione più semplice resta la nota breve proposta più sotto, nel piè di pagina (`frontend/src/shell/PiePagina.tsx`). In alternativa, il problema 1 riduce molto l'esposizione | 15 min |
| 3 | bassa | Nella modifica nuova, i giocatori senza schedina sono attenuati e il loro nome diventa difficile da leggere: contrasto 2,7:1 col tema chiaro e 3,6:1 con lo scuro, sotto il minimo consigliato di 4,5:1 | `frontend/src/componenti/SelettoreGiocatore.tsx:60` (`opacity-60` su tutto il pulsante). Calcolo sui colori del tema (`frontend/src/index.css:22-33`): testo `ink-2` su `superficie-2`, attenuati al 60% sopra la card | Attenuare solo lo sfondo (o usare un bordo tratteggiato / un trattino «—» accanto al nome) e lasciare il testo a colore pieno. Il testo nascosto «, nessuna schedina» per i lettori di schermo c'è già e va bene | 15 min |
| 4 | bassa | Tre avvisi «alti» negli strumenti di sviluppo (il programma `wrangler`, che si usa solo sul computer per provare e pubblicare). Non finiscono nel sito | `npm audit --omit=dev` → `found 0 vulnerabilities`; `npm audit` → `sharp <0.35.5 … CVE-2026-96889`, tramite `miniflare` → `wrangler` (4.16.0 - 4.148.0) | `npm audit fix` (mai `--force`), poi `npm run build` e una prova con `npm run cf:dev` prima del prossimo `wrangler deploy` | 10 min |
| 5 | info | Con `curl`, l'indirizzo `http://` risponde senza passare a `https://` | `curl -sI http://toto-amici.totoamici.workers.dev/` → `HTTP/1.1 200 OK` | Nessuna azione: tutto il dominio `.dev` è nell'elenco HSTS precaricato dei browser, quindi Chrome, Safari, Firefox ed Edge aprono sempre la versione `https`. Il sito invia comunque `Strict-Transport-Security` | — |
| 6 | info | Cloudflare aggiunge da sé le intestazioni `NEL`/`Report-To`: se una pagina non si carica per un errore di rete, il browser lo segnala a `a.nel.cloudflare.com` | `curl -sI $SITO/` → `nel: {"report_to":"cf-nel","success_fraction":0.0,…}` | Nessuna azione: è lo stesso fornitore che ospita il sito, solo in caso di errore (`success_fraction 0.0`). Se si scrive la nota privacy, è già coperta dalla frase su Cloudflare | — |

Gravità: critica = prima di pubblicare; alta = entro pochi giorni; media = alla prossima modifica; bassa = miglioramento; info = nessuna azione.

**Rischio residuo accettato (dal 04/10):** il tetto di 4 chiamate al minuto verso Football-Data vale per ogni copia del Worker; chi riuscisse a raggiungerne molte in parallelo potrebbe consumare il limite condiviso col bot (`frontend/worker/live.ts:27`). Contromisura, se un giorno servisse: dominio proprio + regola di rate limiting Cloudflare su `/api/live`.

## Dettaglio per area

### 1. Inventario dei dati personali — ok
Unica fonte di dati: lo snapshot che il bot pubblica su Cloudflare KV, letto da `/api/snapshot`. Scaricato una volta (157 KB) e controllati i nomi dei campi, senza riportare i dati: solo classifica, cassa, coppa, partite, schedine, regole, statistiche. Nessun indirizzo email (0), nessun numero di telefono (0), nessun identificativo Telegram o chat. I 16 giocatori sono indicati con una sola parola (nome o soprannome); un movimento di cassa contiene il nome di un giocatore. Nessun dato dei nomi reali nei file del repository (`frontend/`, controllato confrontando i nomi dello snapshot con i file tracciati: 0 file).

| Dato | Scopo | Base giuridica (proposta, da confermare) | Conservazione | Destinatario |
|---|---|---|---|---|
| Nome/soprannome, pronostici, punti, importi della cassa | Mostrare il torneo ai partecipanti | Consenso dei partecipanti (art. 6.1.a) o legittimo interesse dell'organizzatore (art. 6.1.f) | Per la stagione; poi `archivia_stagione()` del bot | Chiunque apra il sito (pubblico); Cloudflare come fornitore |
| Indirizzo IP dei visitatori | Funzionamento e sicurezza del servizio | Legittimo interesse (art. 6.1.f) | Log tecnici di Cloudflare (`observability` in `frontend/wrangler.jsonc`); il Worker non scrive nulla nei log (`grep console. frontend/worker` → nessun risultato) | Cloudflare |
| Scelta del tema chiaro/scuro | Ricordare la preferenza | Strumento tecnico, nessun consenso necessario | Finché l'utente non la cancella | Resta sul dispositivo |

Il sito non ha moduli, campi da compilare, login, analytics o pixel (`grep` su `src/`, `index.html`, `public/`: nessun risultato).

### 2. Informativa privacy e cookie policy — problema (bassa, decisione dell'utente)
Nessuna nota privacy (problema 2). Non serve una cookie policy separata perché non ci sono cookie. Niente ragione sociale o partita IVA: non è il sito di un'impresa.

### 3. Cookie — ok
Sul sito vero, browser pulito, aperte tutte e sei le schede e scorse fino in fondo: `document.cookie` vuoto, `localStorage` vuoto, `sessionStorage` vuoto, nessun service worker. `curl -sI $SITO/` → nessun `set-cookie`. Il codice scrive in `localStorage` solo la chiave `tema` e solo quando l'utente cambia tema a mano (`frontend/src/lib/tema.ts:31`): è uno strumento tecnico, non serve nessun banner.

### 4. Richieste ad altri siti — ok
Traffico reale del browser sul sito vero, tutte le schede aperte: 18 richieste, **tutte** a `toto-amici.totoamici.workers.dev` (script, stile, font, `/api/segnale`, `/api/snapshot`, una sola `/api/live?giornata=7`). Nessun font di Google, CDN, mappa o video. Nel codice e nella build: unici indirizzi esterni sono `api.football-data.org` (chiamato dal Worker, non dal browser: il visitatore non vi è esposto, `frontend/worker/index.ts:75`), `www.w3.org` (dentro l'SVG dell'icona, non viene scaricato) e `react.dev` (testo dei messaggi d'errore di React, non viene scaricato). Unica eccezione, solo in caso di errore di rete: le segnalazioni NEL di Cloudflare (problema 6).

### 5. Fornitori e trasferimenti fuori UE — non verificato in parte
- **Cloudflare** (hosting, KV, log): sede USA. Il DPA è incluso nei termini dell'account Cloudflare; l'adesione all'EU-US Data Privacy Framework non è stata controllata su dataprivacyframework.gov (vedi «Cosa non è stato verificato»).
- **Football-Data.org**: riceve solo la richiesta del Worker con la chiave del progetto; nessun dato dei visitatori.
- **Google Sheets / Gemini / Telegram / Render**: usati dal bot, non dal sito; fuori dall'ambito di questa verifica.

Per un torneo privato non serve un registro dei trattamenti formale; se il sito diventasse aperto a estranei, vedi più sotto.

### 6. Intestazioni di sicurezza sul sito vero — ok
`curl -sI` su `/` e su `/classifica` (pagina interna): presenti `Content-Security-Policy` (solo `'self'`, `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'none'`, `manifest-src 'self'`), `Strict-Transport-Security: max-age=31536000; includeSubDomains`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, `Cross-Origin-Opener-Policy: same-origin`. Stesse intestazioni su `/manifest.webmanifest`. Sulle API (`/api/snapshot`, `/api/segnale`, `/api/live?giornata=abc`, `/api/inesistente`): `nosniff`, `Referrer-Policy`, `Cross-Origin-Resource-Policy: same-origin`, CSP `default-src 'none'`. Nessuna intestazione `Access-Control-Allow-Origin` (altri siti non possono leggere le API dal browser dei visitatori). Console del browser con tutte le schede aperte: nessun messaggio, quindi nessuna violazione della CSP. `style-src 'unsafe-inline'` resta ammesso per le animazioni: rischio basso, perché gli script restano solo del sito. Unica intestazione mancante consigliata: `X-Robots-Tag` (problema 1). Il passaggio a `https`: problema 5.

### 7. Revisione del codice (OWASP Top 10) — ok
- XSS: `grep` di `dangerouslySetInnerHTML|innerHTML|outerHTML|insertAdjacentHTML|document.write|eval(|new Function(` su `src`, `worker`, `public` → nessun risultato. I testi dello snapshot (nomi, pronostici scritti dal bot e dall'IA) passano da React, che li tratta sempre come testo.
- Redirect, `target="_blank"`, `window.open`, `postMessage`: nessun risultato.
- `/api/live?giornata=`: accetta solo 1-2 cifre fra 1 e 38 (`frontend/worker/live.ts:13-17`); sul sito vero `?giornata=abc` → `400` con messaggio fisso e `cache-control: no-store`, senza chiamare Football-Data. Metodi diversi da GET/HEAD → 405 (`frontend/worker/index.ts:97`).
- SSRF: l'indirizzo di Football-Data è fisso, solo il numero di giornata già validato entra nell'URL (`frontend/worker/index.ts:75`).
- Errori: solo messaggi fissi, nessun dettaglio interno. La risposta reale di `/api/live?giornata=7` contiene solo id, stato, gol e orario delle partite (`riduciPartite`, `frontend/worker/live.ts:38`), niente chiave né dati in più.
- Modifiche nuove: `scrollIntoView` della pillola attiva, filtri su `giornata === giornata` (uguaglianza di interi, `frontend/src/lib/selettori.ts:23`), somma dei punti già presenti nello snapshot: nessun rischio di sicurezza.
- Controllo accessi: non ci sono aree riservate; le API sono pubbliche per scelta e solo in lettura.

### 8. Dipendenze, segreti, .gitignore, source map — ok (un avviso negli strumenti, problema 4)
- `npm audit --omit=dev` → 0 vulnerabilità per ciò che arriva nel sito (`react`, `react-dom`, `motion`). `npm audit` completo → 3 alte in `sharp`/`miniflare`/`wrangler`, solo strumenti di sviluppo (problema 4). `package-lock.json` presente.
- Segreti: storia git dal 04/10 (`git log -p 22385f8..5375957`) e tutta la storia di `frontend/` controllate con `grep` sui formati di chiavi Google, Telegram, GitHub, GitLab, AWS, chiavi private e token Cloudflare → nessun risultato. Nessuna stringa di 32 caratteri esadecimali (formato della chiave Football-Data) in `src`, `worker`, `public`, `dist`. gitleaks non è installato.
- La chiave Football-Data è un secret del Worker (`FOOTBALL_DATA_KEY`), viaggia solo nell'intestazione verso Football-Data e non è nel codice del browser (`grep` su `dist/` → nessun risultato).
- `.gitignore` di `frontend/` copre `.dev.vars`, `.wrangler/`, `node_modules`, `dist`; il file dei segreti locali risulta ignorato (`git status --ignored`) e non è tracciato; tracciato solo l'esempio vuoto `.dev.vars.example`. Nel resto del repository nessun file `credenziali`, `chiave_api`, `secrets.toml` tracciato.
- Source map: `sourcemap: false` in `frontend/vite.config.ts`, nessun file `.map` in `dist/`.
- In `frontend/wrangler.jsonc` restano visibili l'id dell'account Cloudflare e l'id del KV: non sono segreti (servono a pubblicare, ma senza un token valido non danno accesso).

### 9. Accessi e abusi — ok
Nessun login, nessuna area protetta, nessun modulo. Unico abuso possibile: chiamate ripetute a `/api/live` per consumare il limite di Football-Data, mitigato dalla cache di 120 s per giornata e dal tetto di 4 chiamate al minuto per copia del Worker (rischio residuo accettato, vedi sopra). Durante la verifica è stata fatta **una sola** chiamata vera a `/api/live`.

### 10. Difese al bordo (Cloudflare) — ok per quanto visibile; pannello non verificato
`curl -sI` → `server: cloudflare`, `cf-ray` (punto di presenza di Roma, `FCO`). Le pagine sono in cache (`cf-cache-status: HIT`, `cache-control: public, max-age=0, must-revalidate`): corretto, sono uguali per tutti. Le API hanno `cache-control: public, max-age=60` (dati pubblici, nessun dato dietro login: va bene) e `no-store` sugli errori di validazione. Sull'indirizzo `*.workers.dev` il WAF e le regole di rate limiting del pannello non si applicano: servirebbe un dominio proprio. Protezione DDoS di base: automatica.

### 11. Backup, ripristino, accesso agli account — in parte verificato
Codice: tre copie remote (`origin` su GitHub, `gitlab` su GitLab, `backup` locale in `~/Backups/Toto_Amici`) più lo script `scripts/backup_locale.sh`, che copia anche i file segreti. Dati: la fonte vera è Google Sheets; lo snapshot su KV è una copia che il bot rigenera, quindi non ha bisogno di un backup proprio. Non verificabili dal codice: 2FA sugli account Cloudflare, GitLab, Google e Telegram, e un ripristino mai provato (vedi sotto).

### 12. Accessibilità — ok, con un ritocco (problema 3)
Sito vero: `lang="it"`, nessuna immagine senza testo alternativo (0), schede con ruoli `tab`/`tabpanel`, selettore giocatori come gruppo di scelta con frecce da tastiera. Modifica nuova: la riga «Punti fatti» usa un'intestazione di riga corretta (`th scope="row"`); il conteggio «N di M schedine caricate» viene letto dai lettori di schermo (`aria-live="polite"`). Contrasto dei giocatori attenuati sotto 4,5:1 (problema 3). Il sito è un torneo privato fra amici, senza attività commerciale: **probabilmente non soggetto** all'European Accessibility Act (da confermare solo se diventasse un servizio a pagamento).

## Nota privacy proposta (se si cambia idea sul problema 2)
> **Privacy.** Questo sito è il tabellone di un torneo di pronostici fra amici. Mostra nomi, pronostici e importi della cassa dei partecipanti, che ne sono informati. Non usa cookie, non ha pubblicità né strumenti di statistica e non carica nulla da altri siti. Sul tuo dispositivo resta solo la scelta del tema chiaro/scuro, se la cambi. Il sito è ospitato da Cloudflare, che registra temporaneamente l'indirizzo IP delle richieste per far funzionare il servizio. I risultati delle partite arrivano da football-data.org tramite il nostro server: il tuo IP non viene loro comunicato. Per chiedere la modifica o la rimozione dei tuoi dati scrivi a: **[contatto dell'organizzatore: da inserire]**.

## Cosa serve solo quando i dati diventano reali
I dati sono già reali (lo erano anche il 04/10). Quello che servirebbe solo se il sito si aprisse a persone esterne al gruppo o diventasse un'attività a pagamento:
- informativa completa (art. 13) con titolare e contatto, rivista da un consulente;
- registro dei trattamenti (art. 30) e conferma del DPA con Cloudflare (accettato nei termini dell'account);
- dominio proprio, per poter attivare WAF e rate limiting di Cloudflare;
- rivalutazione dell'European Accessibility Act.

## Cosa non è stato verificato
- **Pannello Cloudflare**: 2FA sull'account, chi ha accesso, durata dei log di `observability`. Dove guardare: dash.cloudflare.com → *Manage Account* → *Members* (accessi) e profilo → *Authentication* (2FA); *Workers & Pages* → `toto-amici` → *Observability* (log).
- **Account GitLab, Google (Sheets) e Telegram**: 2FA attiva? Domanda da porre all'utente.
- **Ripristino**: mai provato da questa verifica un ripristino dal repository di backup o dei segreti.
- **Certificazione EU-US Data Privacy Framework di Cloudflare**: non controllata su dataprivacyframework.gov.
- **Indicizzazione**: controllata solo con una ricerca web dell'indirizzo (nessun risultato, ricerca dagli USA); non con Google Search Console.
- **La versione 5375957 sul sito vero**: non è ancora pubblicata, quindi le modifiche nuove sono state verificate sul codice e sulla build locale, non online. Dopo il `wrangler deploy` basta riaprire Confronto Giocate e Schedine Live e controllare che la console resti vuota.
- **Storia git completa con gitleaks**: non installato; usato `grep` sui formati di chiave principali.
- **Comportamento del tetto a Football-Data con molte copie del Worker**: non misurabile senza un test di carico, che le regole di questa verifica escludono.
