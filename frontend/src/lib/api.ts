import type { RispostaLive, Segnale, Snapshot } from "../tipi/snapshot";
import { normalizzaPassword, type Consegna, type GiornataAperta, type Schedina } from "../../worker/schedina";

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

// ---- Schedina composta sul sito (scheda «Gioca») ----

export const caricaGiornataAperta = (signal?: AbortSignal) => leggiJson<GiornataAperta>("/api/giornata-aperta", signal);

export type RispostaConsegne =
  | { giornata: number; chiusa: false; consegnate: { giocatore: string; consegnata_il: string }[] }
  | { giornata: number; chiusa: true; schedine: Consegna[] };

export const caricaConsegne = (giornata: number, signal?: AbortSignal) =>
  leggiJson<RispostaConsegne>(`/api/consegne?giornata=${giornata}`, signal);

/** Errore del server all'invio: `messaggio` e `errori` sono gia' testi da mostrare cosi' come sono. */
export class ErroreInvio extends Error {
  constructor(public stato: number, messaggio: string, public errori: string[] = []) {
    super(messaggio);
  }
}

export async function inviaSchedina(s: Schedina, password: string): Promise<{ consegnata_il: string }> {
  let r: Response;
  try {
    r = await fetch("/api/schedina", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({ ...s, password: normalizzaPassword(password) }),
    });
  } catch {
    throw new ErroreInvio(0, "Non riesco a collegarmi. Controlla la connessione e riprova: la schedina non è stata consegnata.");
  }
  const dati = (await r.json().catch(() => null)) as { errore?: string; errori?: string[]; consegnata_il?: string } | null;
  if (r.ok && typeof dati?.consegnata_il === "string") return { consegnata_il: dati.consegnata_il };
  throw new ErroreInvio(
    r.status,
    typeof dati?.errore === "string" ? dati.errore : "Qualcosa non ha funzionato: la schedina non è stata consegnata. Riprova fra poco.",
    Array.isArray(dati?.errori) ? dati.errori : [],
  );
}
