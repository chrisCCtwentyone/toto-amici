/**
 * Vincita potenziale scritta a mano dal giocatore (la copia dalla bolletta).
 * Accetta il formato italiano: «1.674,56», «150», «150,5», anche con «€» e spazi.
 * Il punto vale come migliaia SOLO in gruppi da tre cifre («1.674» = 1674), altrimenti e' un decimale
 * («150.5» = 150,5): mai parseFloat(x.replace(',', '.')), che con «1.674,56» sbaglia (bug gia' avuto sulla Cassa).
 * null = non si capisce.
 */
export function parseVincita(testo: string): number | null {
  const t = testo.replace(/[€\s]/g, "");
  let numero: string;
  if (/^\d{1,3}(\.\d{3})+(,\d{1,2})?$/.test(t)) numero = t.replace(/\./g, "").replace(",", ".");
  else if (/^\d+(,\d{1,2})?$/.test(t)) numero = t.replace(",", ".");
  else if (/^\d+\.\d{1,2}$/.test(t)) numero = t;
  else return null;
  return Number(numero);
}
