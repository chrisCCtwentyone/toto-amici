/**
 * Strato dati: carica snapshot + segnale UNA volta, poi li tiene aggiornati
 * (ogni 5 minuti e al ritorno sulla pagina). Le schede NON fanno fetch: usano useSnapshot().
 *
 * Il segnale e' il documento piccolo (<400 byte) riletto spesso; lo snapshot (~50 KB gzip)
 * si riscarica solo se cambia `impronta` (snapshot-schema §2).
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { caricaSegnale, caricaSnapshot } from "./api";
import { statoDati, type StatoDati } from "./datiVecchi";
import { VERSIONE_SCHEMA_SUPPORTATA, type Segnale, type Snapshot } from "../tipi/snapshot";

export const INTERVALLO_REFRESH_MS = 5 * 60_000;
const MIN_TRA_REFRESH_MS = 30_000; // il ritorno sulla pagina non deve martellare
const TICK_OROLOGIO_MS = 60_000;

export type FaseDati = "caricamento" | "pronto" | "errore" | "schema_non_supportato";

export interface Dati {
  fase: FaseDati;
  snapshot: Snapshot | null;
  /** null se il bot non ha mai pubblicato il segnale o non si riesce a leggerlo */
  segnale: Segnale | null;
  /** valutazione "dati vecchi" ricalcolata ogni minuto; null se manca il segnale */
  vecchiaia: StatoDati | null;
  /** true se l'ultimo tentativo di aggiornamento e' fallito (si mostrano gli ultimi dati buoni) */
  aggiornamentoFallito: boolean;
  /** istante dell'ultimo aggiornamento riuscito (ms epoch) */
  ultimoAggiornamentoMs: number | null;
  ricarica: () => void;
}

const Ctx = createContext<Dati | null>(null);

export function DatiProvider({ children }: { children: ReactNode }) {
  const [fase, setFase] = useState<FaseDati>("caricamento");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [segnale, setSegnale] = useState<Segnale | null>(null);
  const [fallito, setFallito] = useState(false);
  const [ultimoMs, setUltimoMs] = useState<number | null>(null);
  const [adesso, setAdesso] = useState(() => Date.now());

  const impronta = useRef<string | null>(null);
  const inCorso = useRef(false);
  const ultimoTentativo = useRef(0);
  const haSnapshot = useRef(false);

  const carica = useCallback(async (forza: boolean) => {
    if (inCorso.current) return;
    if (!forza && Date.now() - ultimoTentativo.current < MIN_TRA_REFRESH_MS) return;
    inCorso.current = true;
    ultimoTentativo.current = Date.now();
    try {
      const primaVolta = !haSnapshot.current;
      // segnale sempre; snapshot subito alla prima volta, poi solo se l'impronta cambia
      const [esSegnale, esSnapshot] = await Promise.allSettled([
        caricaSegnale(),
        primaVolta ? caricaSnapshot() : Promise.resolve(null),
      ]);
      const nuovoSegnale = esSegnale.status === "fulfilled" ? esSegnale.value : null;

      let nuovoSnapshot: Snapshot | null = esSnapshot.status === "fulfilled" ? esSnapshot.value : null;
      if (!primaVolta && nuovoSegnale && nuovoSegnale.impronta !== impronta.current) {
        try {
          nuovoSnapshot = await caricaSnapshot();
        } catch {
          setFallito(true);
          setSegnale(nuovoSegnale);
          return;
        }
      }

      if (nuovoSegnale && nuovoSegnale.versione_schema !== VERSIONE_SCHEMA_SUPPORTATA) {
        setFase("schema_non_supportato");
        return;
      }
      if (nuovoSnapshot && nuovoSnapshot.versione_schema !== VERSIONE_SCHEMA_SUPPORTATA) {
        setFase("schema_non_supportato");
        return;
      }

      if (nuovoSnapshot) {
        haSnapshot.current = true;
        setSnapshot(nuovoSnapshot);
        impronta.current = nuovoSegnale?.impronta ?? impronta.current;
        setFase("pronto");
      } else if (primaVolta) {
        setFase("errore");
        return;
      }
      setSegnale(nuovoSegnale);
      // segnale illeggibile ma snapshot buono: non si butta via il lavoro, si segnala il problema
      setFallito(nuovoSegnale === null);
      if (nuovoSegnale) setUltimoMs(Date.now());
    } finally {
      inCorso.current = false;
      setAdesso(Date.now());
    }
  }, []);

  useEffect(() => {
    void carica(true);
    const timer = setInterval(() => void carica(true), INTERVALLO_REFRESH_MS);
    const alRitorno = () => {
      if (document.visibilityState === "visible") void carica(false);
    };
    const online = () => void carica(false);
    document.addEventListener("visibilitychange", alRitorno);
    window.addEventListener("online", online);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", alRitorno);
      window.removeEventListener("online", online);
    };
  }, [carica]);

  // orologio per ricalcolare "dati vecchi" anche senza nuove richieste
  useEffect(() => {
    const t = setInterval(() => setAdesso(Date.now()), TICK_OROLOGIO_MS);
    return () => clearInterval(t);
  }, []);

  const valore = useMemo<Dati>(
    () => ({
      fase,
      snapshot,
      segnale,
      vecchiaia: segnale ? statoDati(segnale, adesso) : null,
      aggiornamentoFallito: fallito,
      ultimoAggiornamentoMs: ultimoMs,
      ricarica: () => void carica(true),
    }),
    [fase, snapshot, segnale, adesso, fallito, ultimoMs, carica],
  );

  return <Ctx value={valore}>{children}</Ctx>;
}

export function useDati(): Dati {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDati fuori da <DatiProvider>");
  return v;
}

/** Per le schede: lo snapshot e' garantito (la shell le monta solo a dati pronti). */
export function useSnapshot(): Snapshot {
  const { snapshot } = useDati();
  if (!snapshot) throw new Error("useSnapshot: scheda montata senza snapshot");
  return snapshot;
}
