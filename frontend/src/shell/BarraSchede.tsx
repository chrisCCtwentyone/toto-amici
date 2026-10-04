import { useEffect, useRef, type KeyboardEvent } from "react";
import { motion } from "motion/react";
import { SCHEDE } from "../schede/registro";
import { MOLLA } from "../lib/movimento";

/**
 * Le sei schede, come tab accessibili (WAI-ARIA): frecce / Home / End per spostarsi,
 * un solo tab stop. Su telefono la barra scorre in orizzontale e porta in vista la scheda attiva.
 */
interface Props {
  attiva: number;
  onSeleziona: (indice: number) => void;
}

export const idTab = (id: string) => `tab-${id}`;
export const idPannello = (id: string) => `pannello-${id}`;

export default function BarraSchede({ attiva, onSeleziona }: Props) {
  const lista = useRef<HTMLDivElement>(null);

  const precedente = useRef(attiva);

  useEffect(() => {
    // Solo quando la scheda cambia, non al primo render: scrollIntoView sposta il punto di partenza del Tab
    // e il primo Tab salterebbe intestazione e barra.
    const barra = lista.current;
    const tab = barra?.querySelector<HTMLElement>('[aria-selected="true"]');
    if (!barra || !tab) return;
    if (precedente.current === attiva) {
      // primo render (apertura con #scheda): centra la scheda a mano, senza toccare il punto di partenza del Tab
      barra.scrollLeft = tab.offsetLeft - (barra.clientWidth - tab.offsetWidth) / 2;
      return;
    }
    precedente.current = attiva;
    tab.scrollIntoView({ inline: "center", block: "nearest" });
  }, [attiva]);

  const alTasto = (e: KeyboardEvent<HTMLDivElement>) => {
    const n = SCHEDE.length;
    let i = attiva;
    if (e.key === "ArrowRight") i = (attiva + 1) % n;
    else if (e.key === "ArrowLeft") i = (attiva - 1 + n) % n;
    else if (e.key === "Home") i = 0;
    else if (e.key === "End") i = n - 1;
    else return;
    e.preventDefault();
    onSeleziona(i);
    lista.current?.querySelectorAll<HTMLElement>('[role="tab"]')[i]?.focus();
  };

  return (
    <div className="sticky top-0 z-20 bg-bg/90 py-2 backdrop-blur-md">
      <div
        ref={lista}
        role="tablist"
        aria-label="Sezioni del sito"
        onKeyDown={alTasto}
        className="scorri-nascosto mx-auto flex w-full max-w-5xl gap-1.5 overflow-x-auto scroll-px-6 px-4 py-1"
      >
        {SCHEDE.map((s, i) => {
          const on = i === attiva;
          return (
            <button
              key={s.id}
              id={idTab(s.id)}
              type="button"
              role="tab"
              aria-selected={on}
              aria-controls={on ? idPannello(s.id) : undefined}
              tabIndex={on ? 0 : -1}
              onClick={() => onSeleziona(i)}
              className={`obliquo relative min-h-11 flex-none cursor-pointer px-5 transition-colors duration-150 ${on ? "text-su-accento" : "bg-superficie text-ink-2 hover:text-ink"}`}
            >
              {on && <motion.span layoutId="scheda-attiva" transition={MOLLA} className="absolute inset-0 bg-accento" aria-hidden="true" />}
              <span className="contro-obliquo relative block whitespace-nowrap font-display text-lg font-extrabold uppercase tracking-wide">
                {s.etichetta}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
