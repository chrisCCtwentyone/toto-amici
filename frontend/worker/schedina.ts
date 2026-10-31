// Schedina composta sul sito (prova dal 31/10/2026, docs/ANALISI-SCHEDINE-SEGRETE.md).
// Logica pura condivisa fra la scheda «Gioca» e il Worker: le regole sono le stesse nei due
// posti, ma quella che conta e' la verifica del Worker (il browser si puo' manomettere).
// I pronostici sono gia' nel formato normalizzato del bot (categoria_da_pronostico).

export type Tipo = "Combo" | "Fisse" | "Doppie Chance" | "Variabili";
export const TIPI: readonly Tipo[] = ["Combo", "Fisse", "Doppie Chance", "Variabili"];
export const LIMITI: Record<Tipo, number> = { Combo: 1, Fisse: 4, "Doppie Chance": 2, Variabili: 3 };
export const FISSE = ["1", "X", "2"] as const;
export const DOPPIE = ["1X", "X2", "12"] as const;
export const VARIABILI = ["OVER_2.5", "UNDER_2.5", "GOAL", "NOGOAL", "PARI", "DISPARI"] as const;
/** Regolamento: la Combo e' 1X2 + Over/Under 2.5 oppure 1X2 + Goal/NoGoal (niente Pari/Dispari). */
export const VARIABILI_COMBO = ["OVER_2.5", "UNDER_2.5", "GOAL", "NOGOAL"] as const;
export const VINCITA_MAX = 1_000_000;

/** Scritta in KV dal bot (pubblica_giornata_aperta): la prima giornata con la scadenza ancora futura. */
export interface PartitaAperta { id: number; casa: string; ospite: string; inizio_il: string }
export interface GiornataAperta {
  giornata: number;
  /** prima partita meno 5 minuti (regolamento), ISO UTC */
  scadenza_il: string;
  partite: PartitaAperta[];
  giocatori: string[];
}

export interface Riga { partita_id: number; pronostico: string; quota_alta: boolean }
export interface Schedina { giocatore: string; giornata: number; righe: Riga[]; vincita: number }
/** Come salvata dal Worker: ogni riga porta anche il nome della partita («Milan-Como»), cosi' una
 *  giornata chiusa si legge anche quando la giornata aperta e' gia' passata alla successiva. */
export interface RigaConsegnata extends Riga { partita: string }
export interface Consegna extends Omit<Schedina, "righe"> { righe: RigaConsegnata[]; consegnata_il: string }

const tra = (elenco: readonly string[], p: string) => elenco.includes(p);

export function tipoDi(pronostico: string): Tipo | null {
  if (tra(FISSE, pronostico)) return "Fisse";
  if (tra(DOPPIE, pronostico)) return "Doppie Chance";
  if (tra(VARIABILI, pronostico)) return "Variabili";
  const parti = pronostico.split("+");
  if (parti.length === 2 && tra(FISSE, parti[0]!) && tra(VARIABILI_COMBO, parti[1]!)) return "Combo";
  return null;
}

export function conteggio(righe: readonly { pronostico: string }[]): Record<Tipo, number> {
  const n: Record<Tipo, number> = { Combo: 0, Fisse: 0, "Doppie Chance": 0, Variabili: 0 };
  for (const r of righe) {
    const t = tipoDi(r.pronostico);
    if (t) n[t]++;
  }
  return n;
}

/** «OVER_2.5» -> «Over 2.5», «1+GOAL» -> «1 + Goal»: come lo legge un giocatore. */
export function etichettaPronostico(p: string): string {
  const una = (x: string) =>
    ({ "OVER_2.5": "Over 2.5", "UNDER_2.5": "Under 2.5", GOAL: "Goal", NOGOAL: "NoGoal", PARI: "Pari", DISPARI: "Dispari" })[x] ?? x;
  return p.split("+").map(una).join(" + ");
}

/** Cosa non va nella schedina, in parole semplici. Vuoto = si puo' inviare. */
export function erroriSchedina(s: Schedina, aperta: GiornataAperta): string[] {
  const errori: string[] = [];
  if (!aperta.giocatori.includes(s.giocatore)) errori.push("Scegli il tuo nome.");
  if (s.giornata !== aperta.giornata) errori.push(`Questa schedina non e' della Giornata ${aperta.giornata}.`);

  const perPartita = new Map<number, number>();
  for (const r of s.righe) perPartita.set(r.partita_id, (perPartita.get(r.partita_id) ?? 0) + 1);
  for (const p of aperta.partite) {
    const n = perPartita.get(p.id) ?? 0;
    if (n === 0) errori.push(`Manca il pronostico di ${p.casa}-${p.ospite}.`);
    if (n > 1) errori.push(`${p.casa}-${p.ospite} ha piu' di un pronostico.`);
  }
  const ids = new Set(aperta.partite.map((p) => p.id));
  if (s.righe.some((r) => !ids.has(r.partita_id))) errori.push("C'e' una partita che non e' di questa giornata.");
  if (s.righe.some((r) => tipoDi(r.pronostico) === null)) errori.push("C'e' un pronostico non valido.");

  const n = conteggio(s.righe);
  for (const t of TIPI) {
    if (n[t] !== LIMITI[t]) errori.push(`${t}: ne servono ${LIMITI[t]}, ne hai ${n[t]}.`);
  }
  if (!Number.isFinite(s.vincita) || s.vincita <= 0 || s.vincita > VINCITA_MAX) {
    errori.push("Scrivi la vincita potenziale della tua bolletta.");
  }
  return errori;
}

/**
 * Forma del corpo inviato al Worker. Solo controlli di TIPO: le regole le controlla
 * erroriSchedina. null = corpo malformato (non e' arrivato dalla nostra pagina).
 */
export function leggiInvio(dati: unknown): { schedina: Schedina; password: string } | null {
  const d = dati as Record<string, unknown> | null;
  if (!d || typeof d !== "object") return null;
  const { giocatore, giornata, righe, vincita, password } = d;
  if (typeof giocatore !== "string" || typeof password !== "string" || password.length > 100) return null;
  if (typeof giornata !== "number" || typeof vincita !== "number" || !Array.isArray(righe) || righe.length > 20) return null;
  const pulite: Riga[] = [];
  for (const r of righe as Record<string, unknown>[]) {
    if (!r || typeof r.partita_id !== "number" || typeof r.pronostico !== "string" || typeof r.quota_alta !== "boolean") return null;
    pulite.push({ partita_id: r.partita_id, pronostico: r.pronostico, quota_alta: r.quota_alta });
  }
  return { schedina: { giocatore, giornata, righe: pulite, vincita }, password };
}

/**
 * Impronta della password: SHA-256 esadecimale di sale + password, la stessa che calcola il bot
 * (impronta_password in bot_telegram.py). Basta un hash veloce perche' le password le genera il bot
 * a caso (~900.000 combinazioni) e i tentativi sono limitati; un hash lento (PBKDF2) sforerebbe
 * i 10 ms di CPU del piano gratuito.
 */
export async function improntaPassword(sale: string, password: string): Promise<string> {
  const byte = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(sale + password)));
  return Array.from(byte, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** «tigre-lago-pino-42», « Tigre-Lago-Pino-42 » e «tigre lago pino 42» sono la stessa password. */
export function normalizzaPassword(p: string): string {
  return p.trim().toLowerCase().replace(/\s+/g, "-");
}
