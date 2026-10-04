import type { RigaSchedina } from "../../tipi/snapshot";
import { ETICHETTE_ESITO } from "../../lib/esiti";
import { formattaQuota } from "../../lib/format";
import { haQuotaAlta } from "./dati";

/** Sfondo della cella: solo se TUTTE le righe hanno lo stesso esito finale (vinta/persa); in una cella mista parlano i glifi. */
export function sfondoCella(righe: RigaSchedina[]): string {
  const primo = righe[0]?.esito;
  if (!primo || !righe.every((r) => r.esito === primo)) return "";
  if (primo === "vinta") return "bg-vinta/15";
  if (primo === "persa") return "bg-persa/15";
  return "";
}

/**
 * Cella del confronto: pronostico e quota (asterisco se alta), glifo e colore per vinta/persa.
 * Piu' righe sulla stessa partita (es. Combo + Fisse) stanno una sotto l'altra.
 * Il testo dell'esito e' per i lettori di schermo: il significato non sta nel solo colore.
 */
export default function CellaGiocata({ righe, soglia }: { righe: RigaSchedina[]; soglia: number }) {
  if (righe.length === 0) {
    return (
      <span className="text-ink-2">
        <span aria-hidden="true">—</span>
        <span className="solo-lettori">Nessun pronostico</span>
      </span>
    );
  }
  return (
    <ul className="m-0 grid list-none gap-1 p-0">
      {righe.map((r, i) => (
        <li key={`${r.pronostico}-${i}`} className="leading-tight">
          <span className="font-display text-lg font-extrabold text-ink [overflow-wrap:anywhere]">{r.pronostico}</span>{" "}
          <span className="tabulare whitespace-nowrap font-display text-base font-bold text-accento-testo">
            @{formattaQuota(r.quota)}
            {haQuotaAlta(r.quota, soglia) && <span aria-label="quota alta, punti raddoppiati">*</span>}
          </span>
          {r.esito === "vinta" && <span aria-hidden="true" className="ml-1 font-bold text-vinta">✓</span>}
          {r.esito === "persa" && <span aria-hidden="true" className="ml-1 font-bold text-persa">✕</span>}
          <span className="solo-lettori">. {ETICHETTE_ESITO[r.esito]}</span>
        </li>
      ))}
    </ul>
  );
}
