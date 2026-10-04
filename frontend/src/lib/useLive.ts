/**
 * Risultati in diretta dal Worker (GET /api/live?giornata=N, cache 120 s lato Worker).
 * Abbinamento per id Football-Data: `partite[].id` dello snapshot === `PartitaLive.id`.
 * Mai chiamare per giornate gia' concluse senza bisogno: il Worker condivide il limite
 * di 10 richieste/minuto con il bot. Usalo solo nelle schede che mostrano risultati.
 */
import { useEffect, useState } from "react";
import { caricaLive } from "./api";
import type { PartitaLive } from "../tipi/snapshot";

const INTERVALLO_LIVE_MS = 120_000;

export interface StatoLive {
  /** per id Football-Data */
  partite: Map<number, PartitaLive>;
  caricamento: boolean;
  /** true se il Worker ha risposto con campo `errore` o la richiesta e' fallita */
  nonDisponibile: boolean;
}

const VUOTO: StatoLive = { partite: new Map(), caricamento: false, nonDisponibile: false };

export function useLive(giornata: number | null): StatoLive {
  const [stato, setStato] = useState<StatoLive>(VUOTO);

  useEffect(() => {
    if (giornata === null) {
      setStato(VUOTO);
      return;
    }
    let vivo = true;
    const ac = new AbortController();
    setStato((s) => ({ ...s, caricamento: true }));

    const leggi = async () => {
      if (document.visibilityState === "hidden") return;
      try {
        const r = await caricaLive(giornata, ac.signal);
        if (!vivo) return;
        setStato({
          partite: new Map(r.partite.map((p) => [p.id, p])),
          caricamento: false,
          nonDisponibile: Boolean(r.errore),
        });
      } catch {
        if (vivo && !ac.signal.aborted) setStato((s) => ({ ...s, caricamento: false, nonDisponibile: true }));
      }
    };
    void leggi();
    const timer = setInterval(() => void leggi(), INTERVALLO_LIVE_MS);
    const alRitorno = () => void leggi();
    document.addEventListener("visibilitychange", alRitorno);
    return () => {
      vivo = false;
      ac.abort();
      clearInterval(timer);
      document.removeEventListener("visibilitychange", alRitorno);
    };
  }, [giornata]);

  return stato;
}
