/**
 * Larghezza delle barre oblique della classifica: proporzionale ai punti ma con un minimo
 * visibile (come nella proposta "Diretta": da 40% a 100%). E' scala grafica, non logica di dominio.
 */
export function frazioneBarra(valore: number, minimo: number, massimo: number, base = 0.4): number {
  if (massimo <= minimo) return 1;
  const f = base + (1 - base) * ((valore - minimo) / (massimo - minimo));
  return Math.min(1, Math.max(base, f));
}
