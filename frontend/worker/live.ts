// Logica pura del ponte verso Football-Data (testabile senza Workers runtime).

export interface PartitaLive {
  id: number;
  stato: string;
  gol_casa: number | null;
  gol_ospite: number | null;
  inizio_il: string | null;
  minuto?: number;
}

/** Giornata valida: intero 1-38, solo cifre. Altrimenti null. */
export function validaGiornata(testo: string | null): number | null {
  if (testo === null || !/^\d{1,2}$/.test(testo)) return null;
  const n = Number(testo);
  return n >= 1 && n <= 38 ? n : null;
}

/**
 * Tetto alle chiamate verso Football-Data fatte da UN isolate del Worker: al massimo `max`
 * ogni `finestraMs`. Football-Data concede 10/min in tutto, e il bot in produzione ne usa
 * una parte: senza questo tetto, chi scorre ?giornata=1..38 le brucerebbe tutte.
 * Muta `registro` (istanti delle chiamate recenti). Ritorna true se la chiamata e' permessa.
 * ponytail: il tetto e' per isolate (la Cache API non lavora su *.workers.dev); con un
 * dominio proprio si passa alla Cache API / a una regola di rate limiting Cloudflare.
 */
export function consumaBudget(registro: number[], ora: number, max = 4, finestraMs = 60_000): boolean {
  while (registro.length && registro[0]! <= ora - finestraMs) registro.shift();
  if (registro.length >= max) return false;
  registro.push(ora);
  return true;
}

const numeroOnull = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;

/** Tiene solo i campi che servono al sito; ignora le partite senza id numerico. */
export function riduciPartite(risposta: unknown): PartitaLive[] {
  const matches = (risposta as { matches?: unknown })?.matches;
  if (!Array.isArray(matches)) return [];
  const fuori: PartitaLive[] = [];
  for (const m of matches) {
    if (typeof m?.id !== "number") continue;
    const p: PartitaLive = {
      id: m.id,
      stato: typeof m.status === "string" ? m.status : "SCHEDULED",
      gol_casa: numeroOnull(m.score?.fullTime?.home),
      gol_ospite: numeroOnull(m.score?.fullTime?.away),
      inizio_il: typeof m.utcDate === "string" ? m.utcDate : null,
    };
    const minuto = numeroOnull(m.minute);
    if (minuto !== null) p.minuto = minuto;
    fuori.push(p);
  }
  return fuori;
}
