/**
 * Logica pura dei grafici «L'andamento»: punti cumulati, posizione giornata per giornata,
 * assi e scelta dei giocatori evidenziati. Nessun React qui, cosi' si prova con vitest.
 *
 * I punti di ogni giornata e la posizione finale arrivano gia' calcolati dallo snapshot (§5):
 * qui si fa solo la somma progressiva e l'ordinamento per il disegno (vedi `calcolaAndamento`).
 */

export interface GiocatoreIn {
  nome: string;
  posizione: number;
  /** indice 0 = Giornata 1; `null` = nessuna schedina valutata (nella somma conta 0) */
  punti_per_giornata: (number | null)[];
}

export interface SerieGiocatore {
  nome: string;
  /** punti cumulati dopo ciascuna giornata mostrata (stessa lunghezza di `giornate`) */
  punti: number[];
  /** posizione dopo ciascuna giornata mostrata */
  posizioni: number[];
}

export interface DatiAndamento {
  /** numeri di giornata (1-based) con almeno un punteggio, in ordine */
  giornate: number[];
  /** nello stesso ordine di ingresso (= ordine della classifica) */
  serie: SerieGiocatore[];
}

/** Posizione "a pari merito": 1, 1, 3 (chi ha strettamente piu' punti sta davanti). */
function posizioniPerPunti(punti: number[]): number[] {
  return punti.map((p) => 1 + punti.filter((altro) => altro > p).length);
}

export function calcolaAndamento(giocatori: GiocatoreIn[]): DatiAndamento {
  const lunghezza = Math.max(0, ...giocatori.map((g) => g.punti_per_giornata.length));
  const indici = Array.from({ length: lunghezza }, (_, i) => i).filter((i) => giocatori.some((g) => g.punti_per_giornata[i] != null));
  if (indici.length === 0) return { giornate: [], serie: giocatori.map((g) => ({ nome: g.nome, punti: [], posizioni: [] })) };

  // cumulato fino a ciascuna giornata mostrata (le giornate vuote per tutti aggiungerebbero 0)
  const punti = giocatori.map((g) => {
    let somma = 0;
    let fatte = 0;
    return indici.map((i) => {
      for (; fatte <= i; fatte++) somma += g.punti_per_giornata[fatte] ?? 0;
      return somma;
    });
  });

  const posizioni = giocatori.map(() => [] as number[]);
  indici.forEach((_, k) => {
    const ultima = k === indici.length - 1;
    const pos = posizioniPerPunti(punti.map((p) => p[k]!));
    giocatori.forEach((g, j) => posizioni[j]!.push(ultima ? g.posizione : pos[j]!));
  });

  return {
    giornate: indici.map((i) => i + 1),
    serie: giocatori.map((g, j) => ({ nome: g.nome, punti: punti[j]!, posizioni: posizioni[j]! })),
  };
}

/** Tacche "tonde" dell'asse dei punti: da 0 fino al primo multiplo di passo >= max (3-5 tacche). */
export function tacchePunti(max: number): number[] {
  const passi = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000];
  const passo = passi.find((p) => max / p <= 4) ?? 1000;
  const tacche: number[] = [];
  for (let v = 0; v < max + passo; v += passo) {
    tacche.push(v);
    if (v >= max) break;
  }
  return tacche;
}

/** Tacche intere dell'asse delle posizioni: 1, poi a passo costante, sempre fino all'ultima. */
export function tacchePosizioni(n: number): number[] {
  if (n <= 1) return [1];
  const passo = Math.max(1, Math.ceil(n / 5));
  const tacche: number[] = [];
  for (let p = 1; p < n; p += passo) tacche.push(p);
  // l'ultima non resta attaccata alla penultima
  if (n - tacche[tacche.length - 1]! < passo / 2) tacche.pop();
  tacche.push(n);
  return tacche;
}

/** Distanzia le etichette a fine linea (in px) di almeno `minimo`, restando dentro [da, a]. Ordine di ingresso conservato. */
export function spaziaEtichette(ys: number[], minimo: number, da: number, a: number): number[] {
  const ordine = ys.map((y, i) => ({ y, i })).sort((p, q) => p.y - q.y || p.i - q.i);
  const out = ordine.map((o) => Math.min(a, Math.max(da, o.y)));
  for (let k = 1; k < out.length; k++) out[k] = Math.max(out[k]!, out[k - 1]! + minimo);
  // se si e' sforato in fondo, si ritorna indietro
  const sforo = (out[out.length - 1] ?? 0) - a;
  if (sforo > 0) {
    out[out.length - 1] = a;
    for (let k = out.length - 2; k >= 0; k--) out[k] = Math.min(out[k]!, out[k + 1]! - minimo);
  }
  const risultato = new Array<number>(ys.length);
  ordine.forEach((o, k) => (risultato[o.i] = out[k]!));
  return risultato;
}

/* ---- giocatori evidenziati ---- */

/** Colore della serie: i token --serie-1..4 di index.css (tema chiaro e scuro). */
export const coloreSerie = (slot: number) => `var(--serie-${slot})`;

export const MAX_EVIDENZIATI = 4;
export const DEFAULT_EVIDENZIATI = 3;

/** `slot` 1..4 = colore --serie-N: resta alla persona finche' e' selezionata. */
export interface Scelto {
  nome: string;
  slot: number;
}

export function sceltiIniziali(nomi: string[]): Scelto[] {
  return nomi.slice(0, DEFAULT_EVIDENZIATI).map((nome, i) => ({ nome, slot: i + 1 }));
}

/** Seleziona/deseleziona. Un nuovo giocatore prende il primo colore libero; oltre il massimo non fa niente. */
export function alternaScelto(scelti: Scelto[], nome: string): Scelto[] {
  if (scelti.some((s) => s.nome === nome)) return scelti.filter((s) => s.nome !== nome);
  if (scelti.length >= MAX_EVIDENZIATI) return scelti;
  const slot = [1, 2, 3, 4].find((n) => !scelti.some((s) => s.slot === n))!;
  return [...scelti, { nome, slot }];
}

/** Rilegge la selezione salvata. `null` = niente di valido (si usa il default); `[]` = «Tutti», scelta valida. */
export function leggiScelti(salvato: unknown, nomi: string[]): Scelto[] | null {
  if (!Array.isArray(salvato)) return null;
  const visti = new Set<number>();
  const ok: Scelto[] = [];
  for (const v of salvato) {
    const s = v as Partial<Scelto> | null;
    if (!s || typeof s.nome !== "string" || !nomi.includes(s.nome)) continue;
    if (typeof s.slot !== "number" || !Number.isInteger(s.slot) || s.slot < 1 || s.slot > MAX_EVIDENZIATI || visti.has(s.slot)) continue;
    if (ok.some((o) => o.nome === s.nome)) continue;
    visti.add(s.slot);
    ok.push({ nome: s.nome, slot: s.slot });
  }
  return ok.length === 0 && salvato.length > 0 ? null : ok;
}
