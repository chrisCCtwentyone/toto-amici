import type { RispostaLive, Segnale, Snapshot } from "../tipi/snapshot";

export class ErroreHttp extends Error {
  constructor(public stato: number, percorso: string) {
    super(`${percorso} -> HTTP ${stato}`);
  }
}

// Solo in sviluppo: parametri dell'indirizzo della pagina (?devEta=300 ...) passati alle API finte
// per provare avvisi e stati d'errore (vedi dev/mock-api.ts). In produzione non esistono.
function paramDev(): string {
  if (!import.meta.env.DEV) return "";
  const q = new URLSearchParams(location.search);
  const out = new URLSearchParams();
  for (const k of ["devEta", "devSegnale", "devSnapshot"]) {
    const v = q.get(k);
    if (v) out.set(k, v);
  }
  const s = out.toString();
  return s ? `?${s}` : "";
}

async function leggiJson<T>(percorso: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(percorso, { signal, headers: { accept: "application/json" } });
  if (!r.ok) throw new ErroreHttp(r.status, percorso);
  return (await r.json()) as T;
}

export const caricaSegnale = (signal?: AbortSignal) => leggiJson<Segnale>(`/api/segnale${paramDev()}`, signal);
export const caricaSnapshot = (signal?: AbortSignal) => leggiJson<Snapshot>(`/api/snapshot${paramDev()}`, signal);
export const caricaLive = (giornata: number, signal?: AbortSignal) =>
  leggiJson<RispostaLive>(`/api/live?giornata=${giornata}`, signal);
