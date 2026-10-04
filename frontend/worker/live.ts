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
