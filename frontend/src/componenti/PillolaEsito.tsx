import type { Esito } from "../tipi/snapshot";
import { ETICHETTE_ESITO } from "../lib/esiti";

/**
 * Esito di una riga di schedina (enum §12). Colore + glifo + testo: il significato
 * non dipende mai dal solo colore. Per l'esito "a video" con il live usa
 * esitoVisualizzato() da lib/esiti prima di passarlo qui.
 */
const STILE: Record<Esito, { colore: string; glifo: string; pulsa?: boolean }> = {
  vinta: { colore: "text-vinta border-vinta", glifo: "✓" },
  persa: { colore: "text-persa border-persa", glifo: "✕" },
  in_corso: { colore: "text-in-corso border-in-corso", glifo: "●", pulsa: true },
  rinviata: { colore: "text-ink-2 border-ink-2", glifo: "‖" },
  da_verificare: { colore: "text-in-corso border-in-corso", glifo: "!" },
  annullata: { colore: "text-ink-2 border-ink-2", glifo: "–" },
  da_giocare: { colore: "text-ink-2 border-linea", glifo: "○" },
};

export default function PillolaEsito({ esito, className = "" }: { esito: Esito; className?: string }) {
  const s = STILE[esito];
  return (
    <span
      className={`inline-flex items-center gap-1.5 border-l-4 bg-superficie-2 py-0.5 pl-2 pr-2.5 font-display text-sm font-extrabold uppercase leading-5 tracking-[0.08em] ${s.colore} ${className}`}
    >
      <span aria-hidden="true" className={s.pulsa ? "animate-[lampeggia_1.2s_infinite] motion-reduce:animate-none" : ""}>
        {s.glifo}
      </span>
      {ETICHETTE_ESITO[esito]}
    </span>
  );
}
