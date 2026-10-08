import type { Snapshot } from "../tipi/snapshot";

/** Giornate che hanno almeno una schedina, in ordine crescente (per i selettori). */
export function giornateDisponibili(s: Snapshot): number[] {
  return [...new Set(s.schedine.map((x) => x.giornata))].sort((a, b) => a - b);
}

/** Partita per id (id Football-Data, negativo se non ufficiale). */
export function mappaPartite(s: Snapshot): Map<number, Snapshot["partite"][number]> {
  return new Map(s.partite.map((p) => [p.id, p]));
}

/**
 * Giornata mostrata: quella scelta a mano, altrimenti la corrente dello snapshot (segue gli aggiornamenti).
 * `scelta` e' null finche' l'utente non tocca il selettore.
 */
export function giornataEffettiva(s: Snapshot, scelta: number | null): number | null {
  return scelta ?? s.giornata_corrente ?? giornateDisponibili(s).at(-1) ?? null;
}

/** Giocatori (in ordine di `s.giocatori`) che hanno una schedina nella giornata. Uguaglianza di interi, mai sottostringa. */
export function giocatoriConSchedina(s: Snapshot, giornata: number | null): Set<string> {
  return new Set(s.schedine.filter((x) => x.giornata === giornata).map((x) => x.giocatore));
}

/** Scelta esplicita del giocatore, legata alla giornata in cui e' stata fatta. */
export interface SceltaGiocatore {
  giocatore: string;
  giornata: number | null;
}

/**
 * Giocatore mostrato: la scelta a mano vale se ha la schedina in questa giornata o se e' stata fatta proprio qui
 * (cosi' chi clicca un giocatore senza schedina vede il messaggio); altrimenti il primo che ce l'ha.
 */
export function giocatoreEffettivo(s: Snapshot, giornata: number | null, scelta: SceltaGiocatore | null): string | null {
  const con = giocatoriConSchedina(s, giornata);
  if (scelta && (con.has(scelta.giocatore) || scelta.giornata === giornata)) return scelta.giocatore;
  return s.giocatori.find((g) => con.has(g)) ?? s.giocatori[0] ?? null;
}
