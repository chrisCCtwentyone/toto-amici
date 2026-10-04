/**
 * Logica "dati vecchi" (RESTYLING.md decisioni 2-3, snapshot-schema §4).
 *
 *   minuti_senza_segnale = (adesso - ultimo_controllo_il) - (minuti di quell'intervallo
 *                           che cadono dentro la pausa notturna, in ora italiana)
 *
 * Si avvisa se supera `soglia_allarme_minuti` (oggi 120). Senza la sottrazione
 * alle 07:31 scatterebbe un falso allarme ogni mattina: il bot dorme di proposito 02:00-07:30.
 *
 * Funzioni pure: l'ora "adesso" si passa da fuori, cosi' si testa senza orologio.
 */
import { FUSO } from "./format";
import type { Segnale } from "../tipi/snapshot";

type Pausa = Segnale["pausa_notturna"];
const MS_MINUTO = 60_000;

const fmtParti = new Intl.DateTimeFormat("en-US", {
  timeZone: FUSO,
  hourCycle: "h23",
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "numeric",
  second: "numeric",
});

/** Scarto (ms) fra l'ora italiana e UTC in un dato istante (3.600.000 in inverno, 7.200.000 in estate). */
function scartoRoma(istanteMs: number): number {
  const p: Record<string, number> = {};
  for (const { type, value } of fmtParti.formatToParts(new Date(istanteMs))) {
    if (type !== "literal") p[type] = Number(value);
  }
  const comeUtc = Date.UTC(p.year!, p.month! - 1, p.day!, p.hour!, p.minute!, p.second!);
  return comeUtc - Math.floor(istanteMs / 1000) * 1000;
}

/**
 * Istante UTC (ms) in cui in Italia sono le `minutiDelGiorno` del giorno civile `giornoUtcMs`
 * (Date.UTC a mezzanotte). L'Italia e' a UTC+1 (CET) o UTC+2 (CEST): si provano i due scarti.
 * - ora ripetuta (ritorno all'ora solare, 02:00-03:00): vale la PRIMA, cosi' la pausa resta continua;
 * - ora inesistente (passaggio all'ora legale, 02:00-03:00): vale l'istante del salto.
 */
function romaAUtc(giornoUtcMs: number, minutiDelGiorno: number): number {
  const ingenuo = giornoUtcMs + minutiDelGiorno * MS_MINUTO;
  const candidati = [ingenuo - 2 * 3_600_000, ingenuo - 3_600_000];
  const validi = candidati.filter((c) => c + scartoRoma(c) === ingenuo);
  return validi.length > 0 ? Math.min(...validi) : candidati[1]!;
}

const inMinuti = (hhmm: string): number => {
  const [h, m] = hhmm.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
};

/** Quanti minuti dell'intervallo [daMs, aMs] cadono dentro la pausa notturna (ora italiana). */
export function minutiInPausa(daMs: number, aMs: number, pausa: Pausa): number {
  if (aMs <= daMs) return 0;
  const inizio = inMinuti(pausa.inizio);
  const fine = inMinuti(pausa.fine);
  // giorni civili italiani toccati dall'intervallo, piu' uno prima (pausa a cavallo di mezzanotte)
  const giornoDi = (ms: number) => {
    const d = new Date(ms + scartoRoma(ms));
    return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  };
  const GIORNO = 86_400_000;
  let totaleMs = 0;
  for (let g = giornoDi(daMs) - GIORNO; g <= giornoDi(aMs); g += GIORNO) {
    const p0 = romaAUtc(g, inizio);
    const p1 = fine > inizio ? romaAUtc(g, fine) : romaAUtc(g + GIORNO, fine);
    const da = Math.max(p0, daMs);
    const a = Math.min(p1, aMs);
    if (a > da) totaleMs += a - da;
  }
  return totaleMs / MS_MINUTO;
}

/** Minuti trascorsi dall'ultimo controllo del bot, al netto della pausa notturna. Mai negativo. */
export function minutiSenzaSegnale(segnale: Segnale, adesso: Date | number): number {
  const aMs = typeof adesso === "number" ? adesso : adesso.getTime();
  const daMs = Date.parse(segnale.ultimo_controllo_il);
  if (Number.isNaN(daMs)) return Number.POSITIVE_INFINITY; // segnale illeggibile = dati da considerare vecchi
  const totali = (aMs - daMs) / MS_MINUTO;
  return Math.max(0, totali - minutiInPausa(daMs, aMs, segnale.pausa_notturna));
}

export interface StatoDati {
  vecchio: boolean;
  /** minuti senza segnale al netto della pausa (arrotondati per difetto) */
  minuti: number;
}

export function statoDati(segnale: Segnale, adesso: Date | number): StatoDati {
  const minuti = minutiSenzaSegnale(segnale, adesso);
  return {
    vecchio: minuti > segnale.soglia_allarme_minuti,
    minuti: Number.isFinite(minuti) ? Math.floor(minuti) : Number.POSITIVE_INFINITY,
  };
}
