/** Stato delle carte (una per partita) -> righe della schedina. Logica pura, provata in stato.test.ts. */
import { FISSE, VARIABILI_COMBO, type PartitaAperta, type Riga } from "../../../worker/schedina";

export interface Scelta {
  /** acceso: la carta chiede una fissa e una variabile da Combo */
  combo: boolean;
  /** pronostico unico (Combo spenta) */
  semplice: string | null;
  fissa: string | null;
  extra: string | null;
  /** «quota ≥ 3,50» */
  quota: boolean;
}
export type Scelte = Record<number, Scelta>;
export type Gruppo = "semplice" | "fissa" | "extra";

export const SCELTA_VUOTA: Scelta = { combo: false, semplice: null, fissa: null, extra: null, quota: false };

export const sceltaDi = (scelte: Scelte, id: number): Scelta => scelte[id] ?? SCELTA_VUOTA;

/** Pronostico della carta nel formato del bot («1», «X2», «1+OVER_2.5»); null se manca qualcosa. */
export function pronosticoDi(c: Scelta): string | null {
  if (!c.combo) return c.semplice;
  return c.fissa && c.extra ? `${c.fissa}+${c.extra}` : null;
}

/** Tocca un tasto: un altro tasto del gruppo sostituisce, lo stesso deseleziona. */
export function tocca(c: Scelta, gruppo: Gruppo, valore: string): Scelta {
  return { ...c, [gruppo]: c[gruppo] === valore ? null : valore };
}

/** Accende/spegne la Combo. Accendendo, un 1/X/2 o un Over/Goal gia' scelto non va perso. */
export function impostaCombo(c: Scelta, acceso: boolean): Scelta {
  if (acceso === c.combo) return c;
  if (!acceso) return { ...c, combo: false };
  const s = c.semplice ?? "";
  return {
    ...c,
    combo: true,
    fissa: c.fissa ?? ((FISSE as readonly string[]).includes(s) ? s : null),
    extra: c.extra ?? ((VARIABILI_COMBO as readonly string[]).includes(s) ? s : null),
  };
}

/** Righe da inviare, in ordine di partita. Le carte incomplete restano fuori: ci pensa erroriSchedina a segnalarle. */
export function righeDaScelte(partite: readonly PartitaAperta[], scelte: Scelte): Riga[] {
  const righe: Riga[] = [];
  for (const p of partite) {
    const c = sceltaDi(scelte, p.id);
    const pronostico = pronosticoDi(c);
    if (pronostico) righe.push({ partita_id: p.id, pronostico, quota_alta: c.quota });
  }
  return righe;
}
