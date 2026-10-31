import { formattaData, formattaDurata, formattaOra, FUSO } from "../../lib/format";

const fmtGiorno = new Intl.DateTimeFormat("it-IT", { timeZone: FUSO, weekday: "long" });
const fmtGm = new Intl.DateTimeFormat("it-IT", { timeZone: FUSO, day: "numeric" });
const fmtMese = new Intl.DateTimeFormat("it-IT", { timeZone: FUSO, month: "numeric" });
const fmtOraSec = new Intl.DateTimeFormat("it-IT", { timeZone: FUSO, hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });

/** "2026-11-07T13:55:00Z" -> "sabato 7/11 alle 14:55" (ora italiana) */
export const testoScadenza = (iso: string): string => {
  const d = new Date(iso);
  return `${fmtGiorno.format(d)} ${fmtGm.format(d)}/${fmtMese.format(d)} alle ${formattaOra(d)}`;
};

/** -> "14:55:03 del 07/11" */
export const testoConsegna = (iso: string): string => {
  const d = new Date(iso);
  return `${fmtOraSec.format(d)} del ${formattaData(d)}`;
};

/** Millisecondi mancanti -> "2 giorni 3 h" / "3 h 05 min" / "4 min 12 s" */
export function contoAllaRovescia(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s >= 3600) return formattaDurata(Math.floor(s / 60));
  return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
}
