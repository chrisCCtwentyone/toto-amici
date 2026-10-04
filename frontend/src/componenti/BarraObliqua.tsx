import type { ReactNode } from "react";
import { motion } from "motion/react";
import { ENTRATA, SCATTO_LISTA_S } from "../lib/movimento";

/**
 * Riga della classifica "Diretta": parallelogramma con casella posizione (ciano),
 * barra proporzionale (blu, la prima rosa) e nome / valore a destra.
 * Rende un <li>: avvolgila in <ol className="list-none p-0 m-0">.
 *
 * `frazione` (0-1) e' la lunghezza della barra: calcolala con frazioneBarra() da lib/barre.
 * `indice` scagliona l'entrata (90 ms a barra); con movimento ridotto compare subito.
 */
interface Props {
  posizione: ReactNode;
  etichetta: ReactNode;
  /** valore grande a destra (di solito <NumeroAnimato/>) */
  valore?: ReactNode;
  /** dettaglio piccolo prima del valore (freccia di tendenza, "+14 pt") */
  dettaglio?: ReactNode;
  frazione: number;
  /** barra rosa: chi e' in testa */
  evidenza?: boolean;
  indice?: number;
  className?: string;
}

export default function BarraObliqua({ posizione, etichetta, valore, dettaglio, frazione, evidenza = false, indice = 0, className = "" }: Props) {
  const ritardo = indice * SCATTO_LISTA_S;
  return (
    // l'entrata (transform inline di motion) sta sul <li>; l'inclinazione sul figlio:
    // se stessero sullo stesso elemento motion sovrascriverebbe lo skew della classe CSS
    <motion.li
      className={`my-[7px] ${className}`}
      initial={{ opacity: 0, x: -40 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ ...ENTRATA, delay: ritardo }}
    >
      <div className="obliquo flex h-[46px]">
      <div className="grid w-[46px] flex-none place-items-center bg-accento font-display text-[1.75rem] font-extrabold text-su-accento">
        <span className="contro-obliquo block">{posizione}</span>
      </div>
      <div className="relative flex flex-1 items-center overflow-hidden bg-barra-traccia">
        <motion.div
          aria-hidden="true"
          className={`absolute inset-y-0 left-0 origin-left ${evidenza ? "bg-gradient-to-r from-live-scuro to-live" : "bg-gradient-to-r from-marchio-scuro to-marchio"}`}
          style={{ width: `${Math.round(frazione * 100)}%` }}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.9, ease: [0.2, 0.8, 0.2, 1], delay: ritardo }}
        />
        <div className="contro-obliquo relative flex w-full items-center justify-between gap-2 pl-3.5 pr-3 text-su-barra">
          <span className="min-w-0 truncate text-base font-semibold">{etichetta}</span>
          <span className="flex flex-none items-center gap-2.5">
            {dettaglio}
            {valore && <span className="font-display text-[1.75rem] font-extrabold leading-none">{valore}</span>}
          </span>
        </div>
      </div>
      </div>
    </motion.li>
  );
}
