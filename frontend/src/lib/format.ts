/**
 * Formattatori italiani: UNICO posto in cui si trasformano numeri e date in testo.
 * I dati dello snapshot sono numeri veri e ISO UTC: qui diventano "1.674,56 €" e "17:45".
 * Mai concatenare a mano ne' fare replace('.', ','): i bug sui separatori sono gia' costati cari.
 */

export const FUSO = "Europe/Rome";
const LOCALE = "it-IT";

// useGrouping "always": it-IT di default NON raggruppa i numeri a 4 cifre ("1200"),
// ma il progetto scrive sempre "1.200" (come il bot e il sito attuale).
const fmtIntero = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0, useGrouping: "always" });
const fmtEuro = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  useGrouping: "always",
});
const fmtEuroIntero = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
  useGrouping: "always",
});

const cacheDecimali = new Map<number, Intl.NumberFormat>();
function fmtDecimali(n: number): Intl.NumberFormat {
  let f = cacheDecimali.get(n);
  if (!f) {
    f = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: n, maximumFractionDigits: n, useGrouping: "always" });
    cacheDecimali.set(n, f);
  }
  return f;
}

/** 1674 -> "1.674" */
export const formattaIntero = (n: number): string => fmtIntero.format(n);

/** (2.35, 2) -> "2,35" */
export const formattaDecimale = (n: number, decimali = 2): string => fmtDecimali(decimali).format(n);

/** 1674.56 -> "1.674,56 €" (spazio non separabile, come Intl). */
export const formattaEuro = (n: number): string => fmtEuro.format(n);

/** 3200 -> "3.200 €" (senza centesimi, per cifre tonde come obiettivo e premi). */
export const formattaEuroIntero = (n: number): string => fmtEuroIntero.format(n);

/** Quota: 2.35 -> "2,35"; null -> "—". */
export const formattaQuota = (q: number | null): string => (q === null ? "—" : formattaDecimale(q, 2));

/** Percentuale da 0-100 (win_rate): 58.3 -> "58,3%". */
export const formattaPercentuale = (n: number, decimali = 1): string => `${formattaDecimale(n, decimali)}%`;

/** Frazione 0-1 (completamento Cassa): 0.264 -> "26%". */
export const formattaFrazione = (f: number, decimali = 0): string => formattaPercentuale(f * 100, decimali);

/** Punti con segno: 14 -> "+14", -3 -> "−3" (meno tipografico), 0 -> "0". */
export function formattaConSegno(n: number): string {
  if (n > 0) return `+${formattaIntero(n)}`;
  if (n < 0) return `−${formattaIntero(-n)}`;
  return "0";
}

/** 3 -> "3°" */
export const formattaOrdinale = (n: number): string => `${n}°`;

/** 12 -> "Giornata 12" (l'etichetta si compone qui: nello snapshot la giornata e' un intero). */
export const etichettaGiornata = (n: number): string => `Giornata ${n}`;

// ---- Date e orari (sempre Europe/Rome) ----

const fmtOra = new Intl.DateTimeFormat(LOCALE, { timeZone: FUSO, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fmtData = new Intl.DateTimeFormat(LOCALE, { timeZone: FUSO, day: "2-digit", month: "2-digit" });
const fmtGiornoEsteso = new Intl.DateTimeFormat(LOCALE, { timeZone: FUSO, weekday: "short", day: "numeric", month: "short" });

const comeData = (iso: string | Date): Date => (iso instanceof Date ? iso : new Date(iso));

/** "2026-10-04T15:45:03Z" -> "17:45" (ora italiana) */
export const formattaOra = (iso: string | Date): string => fmtOra.format(comeData(iso));

/** -> "04/10" */
export const formattaData = (iso: string | Date): string => fmtData.format(comeData(iso));

/** -> "dom 4 ott" */
export const formattaGiornoEsteso = (iso: string | Date): string => fmtGiornoEsteso.format(comeData(iso));

/** "Aggiornato alle 17:45 del 04/10" */
export const testoAggiornamento = (iso: string | Date): string =>
  `Aggiornato alle ${formattaOra(iso)} del ${formattaData(iso)}`;

/** Durata in minuti -> "2 h 05 min" / "45 min" / "3 giorni 2 h". Per "dati vecchi" e timer. */
export function formattaDurata(minuti: number): string {
  const m = Math.max(0, Math.floor(minuti));
  if (m < 60) return `${m} min`;
  const ore = Math.floor(m / 60);
  if (ore < 24) return `${ore} h ${String(m % 60).padStart(2, "0")} min`;
  const giorni = Math.floor(ore / 24);
  return `${giorni} ${giorni === 1 ? "giorno" : "giorni"} ${ore % 24} h`;
}
