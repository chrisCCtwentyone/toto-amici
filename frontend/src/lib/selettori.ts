import type { Snapshot } from "../tipi/snapshot";

/** Giornate che hanno almeno una schedina, in ordine crescente (per i selettori). */
export function giornateDisponibili(s: Snapshot): number[] {
  return [...new Set(s.schedine.map((x) => x.giornata))].sort((a, b) => a - b);
}

/** Partita per id (id Football-Data, negativo se non ufficiale). */
export function mappaPartite(s: Snapshot): Map<number, Snapshot["partite"][number]> {
  return new Map(s.partite.map((p) => [p.id, p]));
}
