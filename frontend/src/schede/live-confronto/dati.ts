/**
 * Solo presentazione per Schedine Live e Confronto Giocate: etichette, testi, stato del live.
 * Nessun calcolo di dominio (i totali, la scelta del gruppo e il riepilogo arrivano dallo snapshot).
 */
import type { Esito, PartitaLive, SceltaGruppo, Tipologia } from "../../tipi/snapshot";
import { formattaOra, formattaGiornoEsteso } from "../../lib/format";

export const TIPOLOGIA: Record<Tipologia, string> = {
  combo: "Combo",
  fisse: "Fisse",
  doppie_chance: "Doppie Chance",
  variabili: "Variabili",
};

/** `soglia_quota_doppia` viene da regole (§10): non e' scritta nel React. */
export const haQuotaAlta = (quota: number | null, soglia: number): boolean => quota !== null && quota >= soglia;

/** "1 / X · 3 su 7", "Tutti diversi", "—" (§7.1 scelta_gruppo). */
export function testoSceltaGruppo(s: SceltaGruppo): string {
  if (s.tipo === "nessuna") return "—";
  if (s.tipo === "tutti_diversi") return "Tutti diversi";
  return `${s.pronostici.join(" / ")} · ${s.voti} su ${s.su}`;
}

/** "sab 19 set · 18:45", oppure null se l'orario non e' noto. */
export function testoOrario(iso: string | null | undefined): string | null {
  if (!iso) return null;
  return `${formattaGiornoEsteso(iso)} · ${formattaOra(iso)}`;
}

const FINALI: ReadonlySet<Esito> = new Set(["vinta", "persa", "annullata"]);

export interface StatoVisto {
  /** nessuno = niente da mostrare (live assente o non significativo) */
  tipo: "nessuno" | "programmata" | "in_corso" | "finita" | "altro";
  /** didascalia sotto il punteggio: "Finale", "34'", "Intervallo", "Da giocare", "Rinviata"... */
  etichetta: string;
  /** [casa, ospite]; null se la partita non ha (ancora) un punteggio */
  punteggio: [number, number] | null;
}

const NESSUNO: StatoVisto = { tipo: "nessuno", etichetta: "", punteggio: null };

/**
 * Cosa mostrare del live per una riga. Regola gia' presente nel sito di oggi (app.py:742-751):
 * se l'esito scritto dal bot e' finale non si mostra "Da giocare" (il live puo' essere in ritardo:
 * meglio nulla di un'informazione che contraddice l'esito).
 */
export function descriviLive(live: PartitaLive | undefined, esitoSnapshot: Esito): StatoVisto {
  if (!live) return NESSUNO;
  const punteggio: [number, number] | null =
    live.gol_casa !== null && live.gol_ospite !== null ? [live.gol_casa, live.gol_ospite] : null;
  switch (live.stato) {
    case "IN_PLAY":
      return { tipo: "in_corso", etichetta: live.minuto !== undefined ? `${live.minuto}'` : "In corso", punteggio };
    case "PAUSED":
      return { tipo: "in_corso", etichetta: "Intervallo", punteggio };
    case "FINISHED":
    case "AWARDED":
      return { tipo: "finita", etichetta: "Finale", punteggio };
    case "SCHEDULED":
    case "TIMED":
      return FINALI.has(esitoSnapshot) ? NESSUNO : { tipo: "programmata", etichetta: "Da giocare", punteggio: null };
    case "POSTPONED":
      return { tipo: "altro", etichetta: "Rinviata", punteggio: null };
    case "SUSPENDED":
      return { tipo: "altro", etichetta: "Sospesa", punteggio };
    case "CANCELLED":
      return { tipo: "altro", etichetta: "Annullata", punteggio: null };
    default:
      return NESSUNO;
  }
}

/** Stati in cui la partita e' in svolgimento (per il bollino LIVE). */
export const staGiocando = (live: PartitaLive | undefined): boolean => live?.stato === "IN_PLAY" || live?.stato === "PAUSED";
