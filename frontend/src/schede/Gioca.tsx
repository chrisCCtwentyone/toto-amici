import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Card, Pulsante, Scheletro, StatoVuoto } from "../componenti";
import { caricaGiornataAperta, ErroreHttp, ErroreInvio, inviaSchedina } from "../lib/api";
import { formattaEuro } from "../lib/format";
import { erroriSchedina, type GiornataAperta } from "../../worker/schedina";
import CartaPartita from "./gioca/CartaPartita";
import Consegne from "./gioca/Consegne";
import Contatori from "./gioca/Contatori";
import Riepilogo from "./gioca/Riepilogo";
import { righeDaScelte, sceltaDi, type Scelte } from "./gioca/stato";
import { contoAllaRovescia, testoConsegna, testoScadenza } from "./gioca/tempo";
import { parseVincita } from "./gioca/vincita";

const CHIAVE_NOME = "gioca-giocatore";

// Solo il nome si ricorda fra una visita e l'altra: pronostici e password MAI nello storage del browser.
function nomeSalvato(giocatori: string[]): string {
  try {
    const n = localStorage.getItem(CHIAVE_NOME);
    return n !== null && giocatori.includes(n) ? n : "";
  } catch {
    return "";
  }
}

// Bozza in memoria: passando a un'altra scheda e tornando non si perde quanto composto (sparisce ricaricando la pagina).
let bozza: { giornata: number; scelte: Scelte; vincita: string } | null = null;

function ConteggioFinale({ scadenza, onScaduta }: { scadenza: string; onScaduta: () => void }) {
  const [ora, setOra] = useState(Date.now);
  useEffect(() => {
    const t = setInterval(() => setOra(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const manca = Date.parse(scadenza) - ora;
  const finita = manca <= 0;
  useEffect(() => {
    if (finita) onScaduta();
  }, [finita, onScaduta]);
  return (
    <p>
      Mancano <strong role="timer" className="tabulare">{contoAllaRovescia(manca)}</strong>
    </p>
  );
}

type Fase = "modulo" | "riepilogo" | "inviato";

function Giornata({ aperta }: { aperta: GiornataAperta }) {
  const partite = useMemo(() => [...aperta.partite].sort((a, b) => a.inizio_il.localeCompare(b.inizio_il)), [aperta]);
  const inizio = bozza?.giornata === aperta.giornata ? bozza : null;
  const [giocatore, setGiocatore] = useState(() => nomeSalvato(aperta.giocatori));
  const [scelte, setScelte] = useState<Scelte>(inizio?.scelte ?? {});
  const [vincitaTesto, setVincitaTesto] = useState(inizio?.vincita ?? "");
  const [password, setPassword] = useState("");
  const [fase, setFase] = useState<Fase>("modulo");
  const [scaduta, setScaduta] = useState(() => Date.parse(aperta.scadenza_il) <= Date.now());
  const [inviando, setInviando] = useState(false);
  const [erroreInvio, setErroreInvio] = useState<ErroreInvio | null>(null);
  const [consegnataIl, setConsegnataIl] = useState("");
  const [versione, setVersione] = useState(0);
  const cima = useRef<HTMLDivElement>(null);
  const titoloRicevuta = useRef<HTMLHeadingElement>(null);
  const segnaScaduta = useCallback(() => setScaduta(true), []);

  useEffect(() => {
    bozza = { giornata: aperta.giornata, scelte, vincita: vincitaTesto };
  }, [aperta.giornata, scelte, vincitaTesto]);

  const vincita = parseVincita(vincitaTesto);
  const righe = righeDaScelte(partite, scelte);
  const schedina = { giocatore, giornata: aperta.giornata, righe, vincita: vincita ?? NaN };
  const errori = [...erroriSchedina(schedina, aperta), ...(password.trim() === "" ? ["Scrivi la password."] : [])];

  const vai = (f: Fase) => {
    setFase(f);
    cima.current?.scrollIntoView({ block: "start" });
  };

  useEffect(() => {
    if (fase === "inviato") titoloRicevuta.current?.focus();
  }, [fase]);

  const scegliNome = (n: string) => {
    setGiocatore(n);
    try {
      if (n) localStorage.setItem(CHIAVE_NOME, n);
    } catch {
      /* il nome vale solo per questa visita */
    }
  };

  const invia = async () => {
    if (inviando) return;
    setInviando(true);
    setErroreInvio(null);
    try {
      const r = await inviaSchedina(schedina, password);
      setConsegnataIl(r.consegnata_il);
      setVersione((v) => v + 1);
      vai("inviato");
    } catch (e) {
      setErroreInvio(e instanceof ErroreInvio ? e : new ErroreInvio(0, "Qualcosa non ha funzionato: la schedina non è stata consegnata. Riprova fra poco."));
    } finally {
      setInviando(false);
    }
  };

  const controlla = (e: FormEvent) => {
    e.preventDefault();
    setErroreInvio(null);
    vai("riepilogo");
  };

  return (
    <div ref={cima} className="grid gap-4 pb-6">
      <Card titolo="Giornata" evidenza={aperta.giornata} bandiera="accento">
        <p className="font-semibold text-ink">Si chiude {testoScadenza(aperta.scadenza_il)}</p>
        {!scaduta && <ConteggioFinale scadenza={aperta.scadenza_il} onScaduta={segnaScaduta} />}
        <p className="mt-2 text-ink-2">
          Componi la tua schedina: resta segreta fino alla scadenza, poi la vedono tutti. Puoi correggerla e rimandarla fino ad allora: vale l'ultima.
        </p>
        <p className="mt-3 border-l-[6px] border-l-avviso-bordo bg-avviso-fondo px-3 py-2 text-ink">
          Questa è una prova: per i punti conta ancora la bolletta pubblicata nel gruppo.
        </p>
      </Card>

      {scaduta ? (
        <Card bandiera="oro">
          <StatoVuoto titolo={`Le schedine della Giornata ${aperta.giornata} sono chiuse`}>Non si possono più consegnare o correggere.</StatoVuoto>
        </Card>
      ) : fase === "riepilogo" ? (
        <Riepilogo aperta={{ ...aperta, partite }} schedina={schedina} errori={errori} inviando={inviando} erroreInvio={erroreInvio} onIndietro={() => vai("modulo")} onInvia={() => void invia()} />
      ) : fase === "inviato" ? (
        <Card bandiera="accento" titolo="Schedina" evidenza="consegnata">
          <h3 ref={titoloRicevuta} tabIndex={-1} className="font-bold text-vinta">
            <span aria-hidden="true">✓ </span>Schedina consegnata alle {testoConsegna(consegnataIl)}
          </h3>
          <p className="mt-1 text-ink-2">Puoi correggerla fino alla scadenza: vale l'ultima che invii.</p>
          <Pulsante className="mt-3" onClick={() => vai("modulo")}>Correggi e rimanda</Pulsante>
        </Card>
      ) : (
        <form onSubmit={controlla} className="grid gap-4">
          <Card>
            <label htmlFor="gioca-nome" className="mb-1 block font-semibold text-ink">Il tuo nome</label>
            <select
              id="gioca-nome"
              value={giocatore}
              onChange={(e) => scegliNome(e.target.value)}
              className="min-h-11 w-full rounded-diretta border-2 border-linea bg-superficie-2 px-3 text-ink"
            >
              <option value="">Scegli il tuo nome</option>
              {aperta.giocatori.map((g) => (
                <option key={g} value={g}>{g}</option>
              ))}
            </select>
          </Card>

          <div>
            <Contatori righe={righe} />
            <ol className="mt-2 grid gap-3">
              {partite.map((p) => (
                <CartaPartita key={p.id} partita={p} scelta={sceltaDi(scelte, p.id)} onChange={(s) => setScelte((prima) => ({ ...prima, [p.id]: s }))} />
              ))}
            </ol>
          </div>

          <Card>
            <label htmlFor="gioca-vincita" className="mb-1 block font-semibold text-ink">Vincita potenziale (in euro)</label>
            <input
              id="gioca-vincita"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              placeholder="Es. 1.674,56"
              value={vincitaTesto}
              onChange={(e) => setVincitaTesto(e.target.value)}
              aria-describedby="gioca-vincita-aiuto"
              className="min-h-11 w-full rounded-diretta border-2 border-linea bg-superficie-2 px-3 text-ink"
            />
            <p id="gioca-vincita-aiuto" className="mt-1 text-sm text-ink-2">
              {vincitaTesto.trim() === ""
                ? "Copiala dalla bolletta."
                : vincita === null
                  ? "Non capisco questa cifra: scrivila come 1.674,56 oppure 150."
                  : `Letto: ${formattaEuro(vincita)}`}
            </p>

            <label htmlFor="gioca-password" className="mb-1 mt-4 block font-semibold text-ink">Password</label>
            <input
              id="gioca-password"
              type="password"
              autoComplete="current-password"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby="gioca-password-aiuto"
              className="min-h-11 w-full rounded-diretta border-2 border-linea bg-superficie-2 px-3 text-ink"
            />
            <p id="gioca-password-aiuto" className="mt-1 text-sm text-ink-2">La password te la dà un admin.</p>
          </Card>

          <Pulsante type="submit" variante="primario" className="w-full sm:w-auto sm:justify-self-start">Controlla la schedina</Pulsante>
        </form>
      )}

      <Consegne aperta={{ ...aperta, partite }} versione={versione} chiusa={scaduta} onChiusa={segnaScaduta} />
    </div>
  );
}

/** Scheda «Gioca»: la schedina si compone sul sito (prova). Il Worker e' l'unico a decidere se vale. */
export default function Gioca() {
  const [aperta, setAperta] = useState<GiornataAperta | null>(null);
  const [problema, setProblema] = useState<"assente" | "errore" | null>(null);
  const [tentativo, setTentativo] = useState(0);

  useEffect(() => {
    const ac = new AbortController();
    setProblema(null);
    caricaGiornataAperta(ac.signal)
      .then(setAperta)
      .catch((e: unknown) => {
        if (!ac.signal.aborted) setProblema(e instanceof ErroreHttp && e.stato === 404 ? "assente" : "errore");
      });
    return () => ac.abort();
  }, [tentativo]);

  if (problema === "assente") {
    return (
      <Card titolo="Gioca" bandiera="accento">
        <StatoVuoto titolo="Ancora niente da giocare">La prossima giornata non è ancora disponibile. Riprova più tardi.</StatoVuoto>
      </Card>
    );
  }
  if (problema === "errore") {
    return (
      <Card titolo="Gioca" bandiera="accento">
        <StatoVuoto titolo="Non riesco a caricare la giornata">Controlla la connessione e riprova.</StatoVuoto>
        <Pulsante className="mt-3" onClick={() => setTentativo((t) => t + 1)}>Riprova</Pulsante>
      </Card>
    );
  }
  if (!aperta) return <Scheletro righe={5} />;
  return <Giornata aperta={aperta} />;
}
