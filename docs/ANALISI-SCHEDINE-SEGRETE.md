# Schedine segrete fino al fischio d'inizio: analisi

Data: 31/10/2026 · Solo analisi: nessuna modifica a codice, fogli, Cloudflare o Render.
Fonti dei numeri: documentazione ufficiale consultata il 31/10/2026 (link nella sezione 5).

---

## 1. Il problema

Oggi ogni giocatore gioca la sua bolletta dal bookmaker e ne pubblica la foto nel gruppo WhatsApp. Il regolamento dice solo una scadenza: **«bolletta da pubblicare 5 minuti prima» della prima partita; in ritardo → 0 punti** (pagina Regolamento del sito, `RegoleErrori.tsx:17`).

Una scadenza sola, però, premia chi pubblica **per ultimo**: chi è in alto aspetta gli ultimi minuti, guarda le bollette già nel gruppo e gioca le stesse scelte dell'avversario vicino (per non perdere terreno) o le scelte opposte (per recuperare). La classifica smette di misurare chi pronostica meglio e premia chi aspetta di più.

Per risolverlo serve una cosa sola: **nessuno deve poter vedere le bollette degli altri prima di aver chiuso la propria.** È lo stesso principio della busta chiusa nelle gare d'appalto.

### Una seconda falla che c'è già oggi: il sito

Il sito mostra un pronostico **appena un admin salva la schedina nel bot**, anche se la partita non è ancora iniziata (Confronto Giocate, Schedine Live, la colonna «scelta del gruppo»). Nello snapshot non c'è nessun filtro del tipo «nascondi finché non comincia» (`statistiche.py:871`, `restyling/snapshot-schema.md` §7). Se un admin carica le bollette arrivate presto, chi non ha ancora giocato può copiarle dal sito oltre che da WhatsApp. **Qualunque soluzione si scelga, questa falla va chiusa** (vedi opzione F).

### Come funziona oggi il caricamento (in breve)
1. Il giocatore pubblica la foto su WhatsApp.
2. Un admin (Silvio o Salvatore) la manda al bot Telegram, sceglie a mano **giornata** e **giocatore**.
3. Il bot fa leggere le foto a Gemini (**una sola lettura per schedina**, anche con più foto), l'admin controlla e preme «Conferma e Salva».
4. Il bot scrive su Google Sheets e aggiorna il sito.

Cose che il bot **oggi non fa**: non salva l'orario di consegna, non conserva le foto (le cancella appena finito), non accetta messaggi da chi non è admin (li ignora in silenzio), non sa quale utente Telegram è quale giocatore. Sa invece l'orario di ogni partita (Football-Data) e già oggi programma un avviso «mancano queste schedine» 30 minuti prima della prima partita.

---

## 2. Le opzioni

### A. Regola nuova: le bollette si pubblicano solo DOPO il fischio d'inizio
*(prima idea dell'utente)*

**Come funziona per i giocatori.** Si gioca la bolletta come sempre, prima del via. Nel gruppo però si pubblica solo dopo l'inizio della prima partita, entro pochi minuti (per esempio entro 10). Prima del via nel gruppo non c'è niente da copiare. La prova che la bolletta è stata giocata in tempo è **l'orario stampato sulla ricevuta del bookmaker** (vedi opzione C).

**Risolve?** Quasi. Toglie la copiatura dal gruppo, ma apre una **falla nuova che oggi non esiste**:
- **Bollette multiple.** Chi vuole barare gioca 2 o 3 bollette diverse prima del via (5 € l'una) e, dopo il fischio, pubblica quella che sta andando meglio. Più lunga è la finestra per pubblicare, più è grave: con 10 minuti conta solo un gol a inizio partita, con un'ora conta molto. Oggi questo non succede, perché chi pubblica prima del via si è già impegnato.
- La foto della ricevuta si può ritoccare (orario cambiato). È raro e si scopre chiedendo lo screenshot di «Le mie giocate» nell'app del bookmaker.
- Gli accordi privati fra due amici («io gioco questo, tu quello») non li ferma nessuna regola né nessun programma. Vale per tutte le opzioni.

**Costo:** zero. Va cambiata una frase nel regolamento (e il testo sul sito, una riga). Gli admin devono solo caricare le bollette **dopo** il via, così anche il sito non le mostra prima.
**Fatica per i giocatori:** quasi nessuna. Chi se ne dimentica rischia gli 0 punti.

**Contromisure per le bollette multiple (tutte gratis):** finestra di pubblicazione breve; regola «una sola bolletta Toto-Amici a giornata; a richiesta dell'admin si mostra la lista delle giocate del giorno nell'app del bookmaker»; il bot che legge l'orario della ricevuta (opzione C).

### B. Busta chiusa via bot Telegram
*(la soluzione tecnica più solida)*

**Come funziona per i giocatori.** Una volta sola, ognuno scrive al bot in privato e un admin lo abbina al suo nome. Da lì, ogni giornata: il giocatore manda la foto della bolletta **al bot in privato, prima del via**. Il bot risponde «Ricevuta alle 14:52 per la Giornata 10» e non la mostra a nessuno, **nemmeno agli admin**. Al fischio d'inizio il bot «apre le buste»: manda le foto agli admin, che le caricano come oggi, e da quel momento le bollette compaiono sul sito (che diventa anche il posto dove tutti le vedono). Nel gruppo WhatsApp le foto le può girare un admin, o ognuno pubblica la sua dopo il via come nell'opzione A.

**Risolve?** Sì, è l'unica opzione che chiude sia la copiatura sia le bollette multiple:
- l'orario lo mette **Telegram**, non il giocatore: non si può ritoccare;
- ci si impegna **prima** del via, quindi non si può scegliere dopo la bolletta migliore;
- se il bot è spento o in pausa notturna, Telegram tiene il messaggio fino a 24 ore **con l'orario vero di invio** ([Bot API, getUpdates e Message.date](https://core.telegram.org/bots/api#getting-updates)): un bot addormentato non fa perdere una consegna;
- risolve anche un conflitto che oggi esiste se gli admin giocano: un admin oggi vede le bollette degli altri prima di chiudere la sua. Con la busta chiusa no.

**Chi può ancora barare?** Solo con accordi privati fra amici (come in tutte le opzioni). Un admin con accesso al codice o ai fogli potrebbe in teoria curiosare: per questo il bot **non** deve scrivere le giocate su Google Sheets prima del via (lì le vedrebbe chiunque abbia accesso al foglio), ma solo conservare la foto (in Telegram, con il suo codice, senza scaricarla) e l'orario.

**Costo sui servizi gratuiti:** praticamente invariato (dettaglio nella sezione 3). Le letture con Gemini restano 16 a giornata, come oggi. Le foto non vanno archiviate da nessuna parte: Telegram le conserva e il bot le rimanda con il loro codice, senza consumare banda.

**Costo di lavoro:** medio. Da aggiungere nel bot:
- l'abbinamento utente Telegram ↔ giocatore (un foglio piccolo);
- la ricezione delle foto in privato dai giocatori (oggi ignorate);
- il registro delle consegne con l'orario;
- l'apertura delle buste al fischio d'inizio, che deve funzionare **anche se il bot è appena ripartito** (non basta un promemoria in memoria: lo stato va nel foglio `Stato`, come prevede `CLAUDE.md`);
- il rifiuto delle consegne arrivate dopo il via;
- i test.

Stima: una o due sessioni di lavoro più una giornata di prova con gli admin.

**Rischi:**
- **Tutti i 16 giocatori devono avere Telegram** (da chiedere).
- Il passaggio iniziale di abbinamento va seguito dagli admin.
- Se il bot sbaglia l'apertura, le buste restano chiuse più a lungo, ma non si perde niente: le foto sono su Telegram con l'orario.
- Più codice da mantenere, nella parte più delicata del bot.

### C. Il bot legge l'orario sulla ricevuta del bookmaker
**Come funziona.** Gemini legge già ogni foto: gli si chiede anche «data e ora della giocata» stampata sulla ricevuta. Se l'orario è dopo il primo calcio d'inizio, il bot avvisa l'admin (non penalizza da solo).

**Risolve?** Da sola no (non impedisce la copiatura prima del via). È però **il complemento naturale dell'opzione A**: rende verificabile la regola «giocata prima del via, pubblicata dopo».

**Costo:** nessuna chiamata in più a Gemini (è la stessa lettura con un campo in più). Lavoro piccolo.

**Rischi:** non tutte le ricevute o gli screenshot mostrano l'orario; la lettura può sbagliare. Per questo vale la regola del progetto «mai far vincere per default»: orario mancante o dubbio → «da verificare», mai una penalità automatica.

### D. Impronta digitale (hash) della foto prima del via, foto dopo
**Come funziona.** Prima del via ognuno pubblica un codice calcolato dalla foto (l'«impronta»); dopo il via pubblica la foto, e chiunque può controllare che corrisponda.

**Risolve?** In teoria sì, ma **i giocatori dovrebbero calcolare l'impronta a mano** con un'app apposita: non è realistico per un gruppo di amici. Se la calcola il bot, la busta chiusa (B) fa già lo stesso lavoro in modo più semplice. **Sconsigliata.**

### E. Caricamento autonomo dal sito
*(seconda idea dell'utente)*

**Come funzionerebbe.** Nel sito compare «Carica la tua schedina». Il giocatore entra con un suo accesso, carica la foto, il sito la conserva nascosta con l'orario e al via la passa al bot.

**È fattibile?** Sì, tecnicamente, e i servizi gratuiti di Cloudflare basterebbero (sezione 3). Ma serve molto:
- **Login dei giocatori.** Oggi il sito non ha nessun accesso. La via più semplice è Cloudflare Access, gratis fino a 50 utenti, con un codice via e-mail. Richiede di raccogliere l'e-mail di ognuno, e il funzionamento sull'indirizzo `workers.dev` va verificato.
- **Un posto dove tenere le foto.** Workers KV basta (valori fino a 25 MiB, 1.000 scritture al giorno). R2 è più adatto ma probabilmente chiede una carta di credito per attivarsi, e la documentazione ufficiale non lo chiarisce.
- **Il sito oggi non scrive da nessuna parte** (accetta solo letture). Bisogna aprirgli una porta in scrittura, con controlli anti-abuso, e un modo per far arrivare le foto al bot, che resta l'unico a scrivere su Sheets (regola del progetto).
- **Chi controlla la lettura?** Oggi un admin guarda cosa ha letto Gemini prima di salvare. Con il sito, o lo fa ancora l'admin (e allora il sito ha solo sostituito il messaggio su Telegram) o lo fa il giocatore da solo, e allora serve un'interfaccia per correggere pronostici e quote, con il rischio che qualcuno si «corregga» un pronostico a favore.
- **Privacy.** Nuovi dati personali (e-mail, foto conservate su Cloudflare, accessi): va aggiornato `docs/CONFORMITA-SICUREZZA.md` e quasi certamente serve una nota privacy, che oggi il sito non ha.

**Il giudizio onesto:** dal punto di vista della copiatura fa **esattamente** quello che fa la busta chiusa via Telegram (B), ma costa molto di più da costruire e da mantenere. Il sito passerebbe da «pagina che si legge e basta» a «applicazione con utenti, password e caricamenti», cioè la parte che si rompe più spesso e che va tenuta sotto controllo per la sicurezza. Per un progetto curato da una persona che non programma è la scelta meno conveniente. Già in Sessione 7 era stata scartata la scrittura dal sito per gli stessi motivi (`PROJECT_LOG.md:890`). Ha senso solo se qualche giocatore non ha e non vuole Telegram.

### E2. Schedina composta sul sito con i pulsanti, protetta da password
*(proposta di Salvatore, 31/10/2026; aggiunta dopo la prima stesura)*

È diversa dalla E: **niente foto da caricare.** Il giocatore apre una pagina del sito e vede le partite della giornata. Per ogni partita tocca il pulsante della sua scelta (1, X, 2, 1X, X2, 12, Pari, Dispari, Over, Under, Goal, NoGoal). Con «Combo» in alto sceglie una fissa più una variabile sulla stessa partita. In fondo sceglie il suo nome, scrive la sua password e invia. Senza la password giusta la schedina non passa.

**Come funzionerebbe dietro le quinte:**
1. Il sito prende la lista delle partite e i loro orari da Football-Data, tramite il Worker che già oggi fa da ponte. Va aggiunto solo il nome delle squadre, che oggi il Worker scarta (`frontend/worker/live.ts:38`).
2. La pagina controlla la composizione (1 Combo, 4 Fisse, 2 Doppie Chance, 3 Variabili) e non fa inviare una schedina sbagliata.
3. Il Worker riceve l'invio e fa tre controlli:
   - la password è giusta;
   - **l'ora del server** è prima del primo fischio (non quella del telefono, che si può spostare);
   - poi salva la schedina con l'orario in Workers KV, dove nessuno può leggerla.

   Si può rimandare per correggere fino al via: vale l'ultima.
4. Al fischio d'inizio il bot (già collegato a KV) preleva le 16 schedine e le scrive su Google Sheets con lo stesso salvataggio di oggi (blocco anti-doppione compreso). Il bot resta l'unico che scrive su Sheets, come vuole la regola del progetto. Da lì compaiono sul sito e nel riepilogo.

**Risolve?** Sì, quanto la busta chiusa via Telegram (B):
- prima del via nessuno vede niente, nemmeno gli admin;
- l'orario è quello del server;
- ci si impegna prima del via, quindi chiude anche il trucco delle bollette multiple, **almeno per i punti**.

**In più rispetto a tutte le altre opzioni:**
- **Non serve più Gemini** per leggere le schedine, quindi sparisce il problema della quota gratuita. Spariscono anche gli errori di lettura (le sigle «U 2.5», le doppie chance di bet365 scritte a parole…), cioè la parte del bot che ha dato più problemi.
- **Gli admin non devono più caricare 16 schedine a giornata.**
- I pronostici escono già nel formato giusto, scelti da pulsanti e non letti da una foto.

**È complesso?** Meno della E (foto dal sito), più o meno quanto la busta chiusa via Telegram (B). Stima: due o tre sessioni di lavoro più una giornata di prova. I pezzi:
- la pagina con i pulsanti (deve essere comoda sul telefono, con il riepilogo prima dell'invio e una ricevuta dopo);
- un punto di ingresso nel Worker che accetta l'invio (oggi il sito accetta solo letture);
- il controllo delle password con un limite ai tentativi sbagliati;
- il prelievo da parte del bot all'apertura, che deve funzionare anche se il bot è appena ripartito;
- i test.

Ai servizi gratuiti non pesa niente: circa 16-50 scritture KV a giornata su 1.000 al giorno, poche centinaia di richieste su 100.000.

**Tre punti da correggere nella proposta:**
1. **Le password non possono stare in un file CSV del progetto.** Il repository è pubblico su GitHub: chiunque le leggerebbe. Decisione dell'utente del 31/10: **i poteri restano agli admin**, perché un giocatore che dimentica la password non deve restare chiuso fuori. Funzionamento:
   - un admin scrive al bot `/password DAVIDE`;
   - il bot genera una password facile da digitare (per esempio `tigre-lago-pino-42`) e la manda all'admin, che la gira al giocatore;
   - il bot avvisa l'altro admin («Silvio ha rigenerato la password di DAVIDE»).

   Password dimenticata? Si rigenera in un minuto. Il sito tiene la password solo in forma «tritata» (hash), così chi guarda il deposito non la legge. Per i giocatori non cambia niente, e non costa niente in più.
2. **Serve un limite ai tentativi.** Fra amici la tentazione di provare la password di un altro c'è. Dopo qualche errore il nome va bloccato per un po'.
3. **Le quote** (deciso: basta un sì/no). Per ogni partita una casella «quota ≥ 3,50», più la **vincita potenziale** scritta dal giocatore. Gli errori li corregge un admin (vedi «Le funzioni degli admin»).

*Scartata per semplicità:* la cifratura delle schedine nel deposito, che avrebbe impedito anche agli admin di leggerle prima del via. Si accetta il rischio, controllato dal fatto che gli admin sono due e che ogni loro intervento viene notificato all'altro. Si può aggiungere più avanti senza cambiare niente per i giocatori.

**Le funzioni degli admin: nel bot, non sul sito.** Il bot ha già il riconoscimento degli admin, le notifiche a tutti e due e la scrittura su Google Sheets. Un'area admin sul sito vorrebbe dire un secondo login e un secondo punto che scrive: il doppio del lavoro e dei rischi. Nel bot servono:
- **«Chi ha consegnato»**: per la giornata, chi ha mandato la schedina e a che ora. Il promemoria che oggi parte 30 minuti prima della prima partita diventa preciso.
- **«Inserisci per un giocatore»**: è il caricamento con foto che esiste già oggi. Si aggiunge solo l'avviso automatico all'altro admin.
- **«Correggi una schedina»**: cambiare la vincita potenziale e le caselle ≥ 3,50, con avviso all'altro admin. Il resto si corregge sul foglio Google. Serve per gli errori di inserimento (deciso: **se sito e bolletta non coincidono, vale la bolletta**).
- **`/password NOME`**, come sopra.

**Rischi:**
- Il sito diventa un posto dove si **scrive**, non solo si legge: va aggiornato `docs/CONFORMITA-SICUREZZA.md`. Non servono e-mail né foto, quindi i dati personali in più sono pochi (password e orari d'invio).
- Se il sito o Cloudflare non rispondono a ridosso della scadenza serve una via di riserva, per esempio mandare la schedina a un admin come oggi.
- Se schedina del sito e bolletta vera non coincidono vale la bolletta (deciso il 31/10). Le correzioni e la tempistica delle foto le gestiscono gli admin.

### F. Nascondere sul sito le giocate della giornata fino al fischio d'inizio
**Come funziona.** Il bot, quando prepara i dati per il sito, toglie le giocate della giornata in corso finché non è iniziata la prima partita. Dopo il via compaiono tutte insieme.

**Risolve?** Chiude la falla del sito descritta sopra. Da sola non basta (resta WhatsApp), ma serve con **ogni** altra opzione: è la rete di sicurezza se un admin carica una bolletta in anticipo.

**Costo:** piccolo, un filtro nella preparazione dello snapshot più un test. Zero impatto sui servizi.

**Rischi:** quasi nessuno. Da decidere se nascondere per giornata (più semplice) o partita per partita.

### G. Regole di torneo: penalità, sorteggio, ordine di pubblicazione
- **Penalità per chi copia:** non si può definire «copia». Due amici possono scegliere davvero lo stesso 1 su Inter-Lecce. Una regola così crea solo litigi. **Sconsigliata.**
- **Ordine di pubblicazione sorteggiato o per classifica:** sposta solo il vantaggio da uno all'altro (chi pubblica dopo vede chi ha pubblicato prima). **Non risolve.**
- **Penalità per chi pubblica fuori finestra** (con l'opzione A): sì, ed esiste già («in ritardo → 0 punti»). Va solo adattata alla nuova finestra.

### Confronto

| Opzione | Efficacia contro la copiatura | Costo (lavoro / servizi) | Fatica per i giocatori | Rischi principali |
|---|---|---|---|---|
| **A** Pubblicare solo dopo il via | Alta per la copiatura; **apre la falla delle bollette multiple** | Zero / zero | Bassa | Bollette multiple, ricevute ritoccate, dimenticanze |
| **B** Busta chiusa via bot Telegram | **Molto alta** (chiude anche le bollette multiple; orario non falsificabile) | Medio / invariato | Bassa (una registrazione iniziale) | Serve Telegram per tutti; più codice nel bot |
| **C** Orario letto dalla ricevuta | Bassa da sola; **rende verificabile A** | Piccolo / zero (stessa lettura) | Nessuna | Orario non sempre visibile; mai penalità automatiche |
| **D** Impronta (hash) | Alta in teoria | Piccolo / zero | **Alta** (calcolo a mano) | Nessuno la userebbe davvero |
| **E** Foto caricata dal sito | Molto alta (come B) | **Alto** / nei limiti gratuiti | Media (login, e-mail) | Login, sicurezza, privacy, manutenzione, controllo della lettura |
| **E2** Schedina composta sul sito con password (Salvatore) | **Molto alta** (come B) | Medio / nei limiti gratuiti; **toglie Gemini e il caricamento degli admin** | Bassa (pulsanti + password) | Quote scritte a mano (serve la foto dopo il via), password da custodire, sito che scrive |
| **F** Sito nasconde le giocate fino al via | Chiude la falla del sito; da sola non basta | Piccolo / zero | Nessuna | Quasi nessuno |
| **G** Penalità / sorteggio | Nulla o controproducente | Zero / zero | — | Litigi |

---

## 3. Il carico reale sui servizi gratuiti

Ipotesi: 16 giocatori, 1 schedina a testa a giornata, 1-3 foto (Telegram le comprime a circa 1280 pixel, qualche centinaio di KB), 38 giornate, cioè circa **608 schedine e al massimo 1.824 foto in una stagione**.

| Servizio | Limite gratuito | Carico con busta chiusa (B) | Carico con sito (E) | Esito |
|---|---|---|---|---|
| **Gemini** | 20 letture al giorno **per modello** (dato misurato, vedi memoria `quota-gemini`). La catena ha 7 modelli → teoricamente fino a ~140 al giorno | 16 a giornata, **come oggi** | 16 a giornata, come oggi | ✅ invariato. Attenzione solo se 16 buste vengono lette tutte insieme all'apertura: meglio leggerle all'arrivo o distribuite |
| **Render** (bot) | 750 ore/mese, 512 MB, si spegne dopo 15 min senza traffico in entrata | Nessuna ora in più: il bot è già acceso di giorno. Le foto restano su Telegram, non in memoria | Nessuna ora in più | ✅ |
| **Render**, banda in uscita | 5 GB/mese | Rimandare una foto con il suo codice Telegram non consuma banda | — | ✅ |
| **Telegram** | 1 messaggio/s per chat, 20/min in un gruppo, file fino a 20 MB | ~16 ricevute + l'apertura per giornata | — | ✅ ampiamente |
| **Google Sheets** | 300 richieste/min per progetto, 60/min per utente | Poche decine in più a giornata (registro consegne) | Uguale | ✅ ampiamente |
| **Workers** (sito) | 100.000 richieste/giorno, 10 ms di CPU per richiesta | Invariato | +~50 caricamenti a giornata | ✅ |
| **Workers KV** | 1.000 scritture/giorno, valore max 25 MiB, 1 GB in tutto | Invariato | ~48 scritture a giornata; una stagione di foto ≈ 0,5 GB se mai cancellate | ✅ (le foto vanno cancellate a fine giornata) |
| **R2** (alternativa per le foto) | 10 GB e 1 milione di scritture al mese gratis | — | Ampiamente dentro | ⚠️ attivazione probabilmente con carta di credito, da verificare |
| **Cloudflare Access** (login) | Gratis fino a 50 utenti | — | 16 utenti | ✅ (dato da ricerca, non letto sulla pagina ufficiale) |

**Conclusione sui costi:** nessuna delle opzioni esce dai limiti gratuiti. Il vero limite resta Gemini, ed è invariato: le schedine da leggere sono le stesse di oggi, cambia solo chi le manda.

---

## 4. Privacy (dati di persone reali)

- **Già oggi** le foto delle bollette vanno a Gemini sul piano gratuito, che per contratto può usare i contenuti per migliorare i prodotti Google, con possibile lettura da parte di revisori umani ([prezzi](https://ai.google.dev/gemini-api/docs/pricing), colonna «Used to improve our products»; [termini](https://ai.google.dev/gemini-api/terms)). Nessuna opzione peggiora questo punto. Conviene però chiedere ai giocatori di inquadrare **solo** la bolletta, senza nome utente o saldo del conto.
- **Busta chiusa (B):** in più, il legame utente Telegram ↔ nome giocatore e gli orari di consegna, salvati su Google Sheets. È poco ed è necessario. Va citato in `docs/CONFORMITA-SICUREZZA.md`.
- **Sito (E):** in più le e-mail, le foto conservate su Cloudflare e i registri degli accessi. Serve aggiornare `docs/CONFORMITA-SICUREZZA.md` e, con buona probabilità, scrivere la nota privacy che oggi manca (problema 1 di quel documento).

---

## 5. Fonti (consultate il 31/10/2026)

- Render free: https://render.com/docs/free (750 ore, spegnimento dopo 15 minuti, disco effimero); https://render.com/docs/compute-plans (512 MB, 0,1 CPU); https://render.com/docs/outbound-bandwidth (5 GB/mese).
- Cloudflare Workers: https://developers.cloudflare.com/workers/platform/limits/ (100.000 richieste/giorno, 10 ms di CPU).
- Workers KV: https://developers.cloudflare.com/kv/platform/pricing/ e https://developers.cloudflare.com/kv/platform/limits/ (1.000 scritture/giorno, 25 MiB per valore, 1 GB).
- R2: https://developers.cloudflare.com/r2/pricing/ (10 GB, egress gratis). Che serva la carta di credito **non** è confermato dalla documentazione ufficiale.
- D1 (alternativa per i dati): https://developers.cloudflare.com/d1/platform/pricing/ (100.000 righe scritte/giorno).
- Turnstile (anti-robot): https://developers.cloudflare.com/turnstile/plans/ (gratis, illimitato).
- Cloudflare Access: «fino a 50 utenti» sul piano Free, da pagina prodotto e ricerca. Non letto direttamente sulla documentazione tecnica.
- Google Sheets API: https://developers.google.com/workspace/sheets/api/limits (300/min per progetto, 60/min per utente). La pagina annuncia addebiti «più avanti nel 2026» **solo per chi supera** le quote.
- Gemini: https://ai.google.dev/gemini-api/docs/rate-limits (i numeri non sono più pubblicati: rimanda ad AI Studio); https://ai.google.dev/gemini-api/docs/pricing; https://ai.google.dev/gemini-api/terms. Il dato «20 al giorno per modello» è misurato dal progetto il 16/10/2026.
- Telegram: https://core.telegram.org/bots/faq (limiti di invio); https://core.telegram.org/bots/api (getFile 20 MB, aggiornamenti conservati 24 ore, `Message.date` = orario di invio). Nessuna funzione per programmare un messaggio: si fa con un job del bot.
- WhatsApp: https://developers.facebook.com/documentation/business-messaging/whatsapp/groups. I gruppi via API sono solo per account aziendali ufficiali, con **massimo 8 partecipanti**, e dal 01/10/2026 sono in parte a pagamento. **Un bot non può pubblicare in modo lecito e gratuito nel gruppo WhatsApp dei 16 giocatori.** Le alternative non ufficiali violano i termini di WhatsApp.

---

## 6. Raccomandazione

**Subito, a costo zero (dalla prossima giornata):**
1. **Regola A con finestra breve**: bolletta giocata prima del via, pubblicata nel gruppo **dopo** il fischio d'inizio della prima partita ed entro pochi minuti. Più la regola «una sola bolletta Toto-Amici a giornata; su richiesta dell'admin si mostra la lista delle giocate nell'app del bookmaker».
2. **Gli admin caricano le bollette nel bot solo dopo il via**, così il sito non le mostra prima.

**Dopo, con poco lavoro:**

3. **F**: il sito nasconde da solo le giocate della giornata fino al primo fischio. È la rete di sicurezza per il punto 2.
4. **C**: il bot legge l'orario sulla ricevuta e segnala agli admin quelle giocate dopo il via. Mai penalità automatiche.

**La soluzione definitiva (aggiornato dopo la proposta di Salvatore):**

5. **E2, la schedina composta sul sito con password**, insieme alla regola A per la foto della bolletta vera, da pubblicare dopo il via e usare per controllare le quote. Contro la copiatura vale quanto la busta chiusa via Telegram (B) e costa più o meno lo stesso lavoro. In più toglie di mezzo la lettura con Gemini (e i suoi limiti) e il caricamento a mano da parte degli admin, e funziona anche per chi non ha Telegram. **B** resta l'alternativa se si preferisce non far scrivere il sito.

**Non consigliati:** la foto caricata dal sito (E), superata dalla E2; l'impronta digitale (D); penalità per «copia» e sorteggi (G).

---

## 7. Domande aperte (da decidere tu, non le ho date per scontate)

1. **La regola nuova:** quanti minuti dopo il fischio d'inizio si può pubblicare la bolletta? E la scadenza per **giocarla** resta «5 minuti prima del via» o diventa «prima del via»?
2. **Bollette multiple:** è vietato giocare più bollette a giornata? Se un admin ha un sospetto, può chiedere lo screenshot delle giocate del giorno?
3. **Le ricevute** (Snai, bet365, ecc.) mostrano sempre data e ora della giocata, anche negli screenshot dall'app?
4. **Gli admin giocano?** Se Silvio e Salvatore partecipano al torneo, oggi vedono le bollette degli altri prima di chiudere la propria. Questo pesa a favore della busta chiusa (B).
5. **Tutti e 16 hanno Telegram** e sarebbero disposti a mandare la foto al bot invece che nel gruppo?
6. **Con la busta chiusa:** si può sostituire la bolletta prima del via (vale l'ultima mandata)? Chi la pubblica poi nel gruppo WhatsApp: un admin, ciascuno la sua, o basta il sito?
7. **Sul sito:** le giocate vanno nascoste fino alla **prima** partita della giornata (più semplice) o partita per partita?
8. **Chi decide le regole:** le modifiche al regolamento le approva il creatore del torneo? Vanno votate dal gruppo?
9. **Chi ha accesso al foglio Google** oltre ai due admin? Conta per capire dove possono restare «nascoste» le giocate prima del via.

**Proposta E2: deciso dall'utente (31/10/2026)**
- Quote: un sì/no «quota ≥ 3,50» per partita. La **vincita potenziale** la scrive il giocatore. Gli errori li corregge un admin.
- **Un solo pronostico per partita**, quindi ogni giocatore pronostica **tutte e 10** le partite della giornata.
- **Se schedina del sito e bolletta non coincidono, vale la bolletta** (il giocatore può aver sbagliato l'inserimento).
- Il sito chiude **5 minuti prima** della prima partita, come il regolamento di oggi.
- Partita rinviata: si pronostica lo stesso e si aspetta il recupero (lo dice già il regolamento sul sito, `RegoleErrori.tsx:21`).
- Fino alla scadenza si può rimandare la schedina: vale l'ultima.
- Un admin può inserire la schedina al posto di un giocatore, con avviso automatico all'altro admin.
- Password gestite dagli admin, rigenerabili in qualunque momento (non il codice di primo accesso, giudicato eccessivo).
- Le bollette vere si pubblicano comunque nel gruppo.
- **Si parte in prova dalla prossima giornata.**

**Proposta E2: deciso dall'utente (31/10/2026, seconda parte)**
- **Bollette multiple:** l'utente ritiene che il rischio nel gruppo non ci sia. Nessuna contromisura tecnica.
- **Foto della bolletta nel gruppo e orario massimo per pubblicarla:** li gestiscono gli admin, fuori dal sistema.
- **Correzioni** dovute a differenze fra sito e bolletta: le gestisce l'admin direttamente con i giocatori.
- **Funzioni di correzione nel bot:** vincita potenziale e caselle «quota ≥ 3,50». Il resto, se serve, si cambia a mano sul foglio Google.
- **La prova la compilano tutti.**
- **Prima della conferma, il sito mostra un riepilogo da controllare.** Contiene:
  - le 10 partite, ciascuna con il pronostico scelto;
  - il conteggio per tipo (1 Combo, 4 Fisse, 2 Doppie Chance, 3 Variabili), con un segno verde o rosso;
  - le caselle «quota ≥ 3,50» spuntate;
  - la vincita potenziale scritta.

  Il pulsante «Conferma» si attiva solo se la composizione è giusta e il giocatore spunta «Ho controllato la mia schedina». Dopo l'invio compare una ricevuta con l'orario di consegna, e si può ancora correggere fino alla scadenza.

**Proposta E2: una sola cosa da chiarire**

10. Fra le cose da correggere dal bot hai scritto «vincite potenziali, caselle e bu…»: l'ultima parola si è tagliata. Era «bonus», «bollette» o altro?

### Come arrivare alla prova della prossima giornata

Due o tre sessioni di lavoro non stanno comodamente in una settimana. Conviene allora dividere il lavoro in modo che la **prova** richieda solo il minimo:

1. **Per la prova (prossima giornata):**
   - la pagina con i pulsanti;
   - il Worker che controlla password e scadenza e salva la schedina;
   - `/password` nel bot;
   - una pagina che mostra le schedine consegnate **solo dopo la scadenza**.

   Il bot e Google Sheets non cambiano: i punti si calcolano come oggi, dalle foto. A fine giornata si confrontano le due versioni per trovare gli errori della pagina.
2. **Dopo la prova:**
   - il bot preleva le schedine del sito e le scrive su Sheets;
   - si aggiungono le funzioni admin («chi ha consegnato», «correggi», avvisi all'altro admin);
   - le giocate restano nascoste sul sito fino alla scadenza (opzione F);
   - si aggiornano regolamento, `docs/CONFORMITA-SICUREZZA.md`, `PROJECT_LOG.md` e `CLAUDE.md`.

   Da lì Gemini serve solo per le schedine inserite dagli admin con la foto.
