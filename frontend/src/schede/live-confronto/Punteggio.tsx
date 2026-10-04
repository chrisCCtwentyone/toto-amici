import { useEffect, useRef } from "react";
import { animate, useReducedMotion } from "motion/react";
import type { StatoVisto } from "./dati";

/**
 * Punteggio in diretta di una partita + didascalia (Finale, 34', Da giocare...).
 * Quando il punteggio CAMBIA mentre la pagina e' aperta (un gol) la cifra fa un breve
 * "colpo": e' l'unica informazione nuova che arriva da sola, quindi merita l'attenzione.
 * Alla prima comparsa non si anima.
 */
export default function Punteggio({ stato }: { stato: StatoVisto }) {
  const cifre = useRef<HTMLSpanElement>(null);
  const prima = useRef<string | null>(null);
  const ridotto = useReducedMotion();
  const chiave = stato.punteggio ? `${stato.punteggio[0]}-${stato.punteggio[1]}` : null;

  useEffect(() => {
    const el = cifre.current;
    if (el && !ridotto && chiave !== null && prima.current !== null && prima.current !== chiave) {
      animate(el, { scale: [1.35, 1] }, { duration: 0.45, ease: [0.2, 0.8, 0.2, 1] });
    }
    prima.current = chiave;
  }, [chiave, ridotto]);

  if (stato.tipo === "nessuno") return null;
  const dal = stato.tipo === "in_corso";
  return (
    <div className="flex shrink-0 flex-col items-end text-right leading-none">
      {stato.punteggio && (
        <>
          <span
            ref={cifre}
            aria-hidden="true"
            className={`tabulare inline-block origin-right font-display text-[2.5rem] font-extrabold ${dal ? "text-live" : "text-ink"}`}
          >
            {stato.punteggio[0]} – {stato.punteggio[1]}
          </span>
          <span className="solo-lettori">Risultato {stato.punteggio[0]} a {stato.punteggio[1]}.</span>
        </>
      )}
      <span
        className={`mt-1 inline-flex items-center gap-1.5 font-display text-base font-extrabold uppercase tracking-[0.08em] ${
          dal ? "text-live" : "text-ink-2"
        }`}
      >
        {dal && <i aria-hidden="true" className="block size-2 animate-[lampeggia_1s_infinite] rounded-full bg-live motion-reduce:animate-none" />}
        {stato.etichetta}
      </span>
    </div>
  );
}
