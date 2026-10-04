/**
 * Piccoli aiuti di PRESENTAZIONE delle schede Statistiche e Coppa (niente logica di dominio:
 * i numeri arrivano gia' calcolati dallo snapshot).
 */

export interface DurataScomposta {
  settimane: number;
  giorni: number;
  ore: number;
  minuti: number;
  secondi: number;
}

/** Secondi trascorsi -> settimane, giorni, ore, minuti, secondi (mai negativi: un orologio in anticipo non rompe il timer). */
export function scomponiDurata(secondi: number): DurataScomposta {
  let s = Math.max(0, Math.floor(secondi));
  const settimane = Math.floor(s / 604800);
  s %= 604800;
  const giorni = Math.floor(s / 86400);
  s %= 86400;
  const ore = Math.floor(s / 3600);
  s %= 3600;
  return { settimane, giorni, ore, minuti: Math.floor(s / 60), secondi: s % 60 };
}

/** Raggruppa mantenendo l'ordine di arrivo: i pari merito con lo stesso valore finiscono insieme. */
export function raggruppa<T>(elementi: readonly T[], chiave: (e: T) => string): T[][] {
  const gruppi = new Map<string, T[]>();
  for (const e of elementi) {
    const k = chiave(e);
    const g = gruppi.get(k);
    if (g) g.push(e);
    else gruppi.set(k, [e]);
  }
  return [...gruppi.values()];
}

/** Etichetta di un partecipante ancora ignoto: ottavi "Da definire", poi "Vincente ottavo 3" (indice di sfida 0-based). */
const SINGOLARE_TURNO = ["ottavo", "quarto", "semifinale"] as const;
export function etichettaDaDefinire(indiceTurno: number, indiceSfida: number, lato: 0 | 1): string {
  const precedente = SINGOLARE_TURNO[indiceTurno - 1];
  return precedente ? `Vincente ${precedente} ${2 * indiceSfida + lato + 1}` : "Da definire";
}
