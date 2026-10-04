/**
 * Presentazione degli esiti (snapshot-schema §12). Niente logica di dominio:
 * solo etichette e la regola di presentazione della decisione 8 (da_giocare -> in_corso
 * quando il live dice che la partita e' iniziata).
 */
import type { Esito, PartitaLive, RigaSchedina, RiepilogoSchedina } from "../tipi/snapshot";

export const ETICHETTE_ESITO: Record<Esito, string> = {
  vinta: "Vinta",
  persa: "Persa",
  in_corso: "In corso",
  rinviata: "Rinviata",
  da_verificare: "Da verificare",
  annullata: "Annullata",
  da_giocare: "Da giocare",
};

const FINALI: ReadonlySet<Esito> = new Set(["vinta", "persa", "annullata"]);
const STATI_IN_CORSO = new Set(["IN_PLAY", "PAUSED"]);

/** Esito da mostrare: se e' finale non si tocca; "da giocare" diventa "in corso" a partita iniziata. */
export function esitoVisualizzato(esito: Esito, live?: PartitaLive): Esito {
  if (FINALI.has(esito)) return esito;
  if (esito === "da_giocare" && live && STATI_IN_CORSO.has(live.stato)) return "in_corso";
  return esito;
}

/** Riepilogo ricalcolato a video con il live (stessa forma dello snapshot). */
export function riepilogoVisualizzato(
  righe: RigaSchedina[],
  liveDi: (partitaId: number) => PartitaLive | undefined,
): RiepilogoSchedina {
  const r: RiepilogoSchedina = { vinte: 0, perse: 0, in_corso: 0, rinviate: 0, da_verificare: 0, annullate: 0, da_giocare: 0 };
  const chiave: Record<Esito, keyof RiepilogoSchedina> = {
    vinta: "vinte", persa: "perse", in_corso: "in_corso", rinviata: "rinviate",
    da_verificare: "da_verificare", annullata: "annullate", da_giocare: "da_giocare",
  };
  for (const riga of righe) r[chiave[esitoVisualizzato(riga.esito, liveDi(riga.partita_id))]]++;
  return r;
}
