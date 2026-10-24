/** Ordinamento dello "Storico punteggi per giornata": solo presentazione, i numeri arrivano dallo snapshot (§5.2). */
export interface RigaStorico {
  nome: string;
  tot: number;
  g: (number | null)[];
  ritirato: boolean;
}

/** null = ordine della Classifica; "tot" o l'indice della giornata (0 = G1). */
export type ColonnaOrdine = number | "tot" | null;
export type Verso = "giu" | "su";

/**
 * Righe ordinate per la colonna scelta: dal piu' alto ("giu") o dal piu' basso ("su").
 * Una giornata senza schedina (null) va sempre in fondo; a parita' resta l'ordine della Classifica
 * (sort stabile). I ritirati restano dopo gli attivi: non sono piu' in gara.
 */
export function ordinaStorico(righe: RigaStorico[], colonna: ColonnaOrdine, verso: Verso): RigaStorico[] {
  if (colonna === null) return righe;
  const valore = (r: RigaStorico) => (colonna === "tot" ? r.tot : (r.g[colonna] ?? null));
  const segno = verso === "giu" ? -1 : 1;
  const ordina = (lista: RigaStorico[]) =>
    [...lista].sort((a, b) => {
      const va = valore(a), vb = valore(b);
      if (va === null || vb === null) return va === vb ? 0 : va === null ? 1 : -1;
      return segno * (va - vb);
    });
  return [...ordina(righe.filter((r) => !r.ritirato)), ...ordina(righe.filter((r) => r.ritirato))];
}
