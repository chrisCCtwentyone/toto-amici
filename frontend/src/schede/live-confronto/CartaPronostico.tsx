import { motion } from "motion/react";
import { PillolaEsito } from "../../componenti";
import type { Esito, Partita, PartitaLive, RigaSchedina } from "../../tipi/snapshot";
import { esitoVisualizzato } from "../../lib/esiti";
import { formattaConSegno, formattaQuota } from "../../lib/format";
import { descriviLive, haQuotaAlta, testoOrario, TIPOLOGIA } from "./dati";
import Punteggio from "./Punteggio";

const BORDO: Record<Esito, string> = {
  vinta: "border-l-vinta",
  persa: "border-l-persa",
  in_corso: "border-l-in-corso",
  rinviata: "border-l-ink-2",
  da_verificare: "border-l-in-corso",
  annullata: "border-l-ink-2",
  da_giocare: "border-l-linea",
};
const COLORE_PUNTI: Record<Esito, string> = {
  vinta: "text-vinta",
  persa: "text-persa",
  in_corso: "text-in-corso",
  rinviata: "text-ink-2",
  da_verificare: "text-in-corso",
  annullata: "text-ink-2",
  da_giocare: "text-ink-2",
};

interface Props {
  riga: RigaSchedina;
  /** assente solo se lo snapshot e' incoerente: la carta si mostra lo stesso */
  partita: Partita | undefined;
  live: PartitaLive | undefined;
  soglia: number;
  /** posizione nella lista, per lo scalino d'entrata */
  indice: number;
}

export default function CartaPronostico({ riga, partita, live, soglia, indice }: Props) {
  const esito = esitoVisualizzato(riga.esito, live);
  const stato = descriviLive(live, riga.esito);
  const orario = testoOrario(live?.inizio_il ?? partita?.inizio_il);
  const alta = haQuotaAlta(riga.quota, soglia);
  const nome = partita?.nome ?? "Partita non trovata";
  return (
    <motion.li
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      // scalino breve e limitato: a 10 carte l'ultima non arriva mai oltre ~0,3 s
      transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1], delay: Math.min(indice, 9) * 0.03 }}
      className={`rounded-diretta border-l-[6px] bg-superficie p-3 shadow-card sm:p-4 ${BORDO[esito]}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="m-0 flex flex-wrap items-center gap-x-2 text-sm text-ink-2">
            {riga.tipologia && (
              <span className="font-display text-base font-extrabold uppercase tracking-[0.08em] text-marchio-testo">
                {TIPOLOGIA[riga.tipologia]}
              </span>
            )}
            <span>{partita && !partita.ufficiale ? "Partita senza risultato in diretta" : (orario ?? "Orario da definire")}</span>
          </p>
          <h3 className="m-0 mt-0.5 font-display text-[1.65rem] font-extrabold uppercase leading-[1.05] tracking-wide text-ink [overflow-wrap:anywhere]">
            {nome}
          </h3>
        </div>
        <Punteggio stato={stato} />
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-linea pt-3">
        <p className="m-0 flex flex-wrap items-baseline gap-x-2">
          <span className="text-sm uppercase tracking-wide text-ink-2">Pronostico</span>
          <strong className="font-display text-2xl font-extrabold leading-none text-ink [overflow-wrap:anywhere]">{riga.pronostico}</strong>
          <span className="tabulare font-display text-xl font-bold text-accento-testo">
            @{formattaQuota(riga.quota)}
            {alta && <span role="img" aria-label="quota alta, punti raddoppiati">*</span>}
          </span>
        </p>
        <div className="flex items-center gap-3">
          <PillolaEsito esito={esito} />
          <span className={`tabulare font-display text-[1.75rem] font-extrabold leading-none ${COLORE_PUNTI[esito]}`}>
            {formattaConSegno(riga.punti)} pt
          </span>
        </div>
      </div>
    </motion.li>
  );
}
