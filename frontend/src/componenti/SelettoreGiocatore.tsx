import { useEffect, useRef, type KeyboardEvent } from "react";

/**
 * Selettore di giocatore a "pillole" (radiogroup: frecce per spostarsi, un solo tab stop).
 * Su telefono scorre in orizzontale, da tablet va a capo.
 */
interface Props {
  giocatori: string[];
  valore: string | null;
  onChange: (nome: string) => void;
  etichetta?: string;
  /** Giocatori senza dati per la giornata: restano selezionabili ma attenuati, con testo per i lettori di schermo. */
  senzaScheda?: ReadonlySet<string>;
  className?: string;
}

export default function SelettoreGiocatore({ giocatori, valore, onChange, etichetta = "Giocatore", senzaScheda, className = "" }: Props) {
  const gruppo = useRef<HTMLDivElement>(null);
  const attivo = valore ?? giocatori[0];

  // la pillola attiva (anche scelta in automatico) deve essere visibile nella riga scorrevole
  useEffect(() => {
    gruppo.current?.querySelector('[aria-checked="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [attivo]);

  const alTasto = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = giocatori.findIndex((g) => g === attivo);
    let n = i;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") n = (i + 1) % giocatori.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") n = (i - 1 + giocatori.length) % giocatori.length;
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = giocatori.length - 1;
    else return;
    e.preventDefault();
    const nome = giocatori[n];
    if (nome === undefined) return;
    onChange(nome);
    gruppo.current?.querySelectorAll<HTMLElement>('[role="radio"]')[n]?.focus();
  };

  return (
    <div
      ref={gruppo}
      role="radiogroup"
      aria-label={etichetta}
      onKeyDown={alTasto}
      className={`scorri-nascosto -mx-4 flex gap-2 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 ${className}`}
    >
      {giocatori.map((g) => {
        const on = g === attivo;
        const vuoto = senzaScheda?.has(g) ?? false;
        return (
          <button
            key={g}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(g)}
            className={`obliquo min-h-11 flex-none cursor-pointer px-4 transition-colors duration-150 ${on ? "bg-accento text-su-accento" : "bg-superficie-2 text-ink-2 hover:text-ink"} ${vuoto && !on ? "opacity-60" : ""}`}
          >
            <span className="contro-obliquo block font-display text-lg font-extrabold uppercase tracking-wide">{g}</span>
            {vuoto && <span className="solo-lettori">, nessuna schedina</span>}
          </button>
        );
      })}
    </div>
  );
}
