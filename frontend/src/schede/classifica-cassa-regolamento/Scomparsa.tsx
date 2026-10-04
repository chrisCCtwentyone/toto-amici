import { useId, useState, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { EASE_USCITA } from "../../lib/movimento";

/**
 * Sezione "a scomparsa": bottone (aria-expanded) + contenuto che si apre in altezza.
 * Il contenuto non e' nel DOM da chiusa. Con movimento ridotto si apre di scatto.
 */
export default function Scomparsa({ titolo, children }: { titolo: ReactNode; children: ReactNode }) {
  const [aperto, setAperto] = useState(false);
  const id = useId();
  const ridotto = useReducedMotion();
  return (
    <div>
      <button
        type="button"
        aria-expanded={aperto}
        aria-controls={aperto ? id : undefined}
        onClick={() => setAperto((a) => !a)}
        className="flex min-h-11 w-full cursor-pointer items-center justify-between gap-3 rounded-diretta border border-linea bg-superficie-2 px-3 text-left font-display text-lg font-extrabold uppercase tracking-wide text-ink transition-colors duration-150 hover:border-accento-testo"
      >
        <span>{titolo}</span>
        <svg
          aria-hidden="true"
          viewBox="0 0 12 12"
          className={`size-3 flex-none transition-transform duration-150 motion-reduce:transition-none ${aperto ? "rotate-180" : ""}`}
        >
          <path d="M1.5 4 6 8.5 10.5 4" fill="none" stroke="currentColor" strokeWidth="2" />
        </svg>
      </button>
      <AnimatePresence initial={false}>
        {aperto && (
          <motion.div
            id={id}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={ridotto ? { duration: 0 } : { duration: 0.28, ease: EASE_USCITA }}
            className="overflow-hidden"
          >
            <div className="pt-3">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
