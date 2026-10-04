import { etichettaGiornata } from "../lib/format";

/**
 * Selettore di giornata: [‹] [menu nativo] [›]. Il menu nativo e' la scelta giusta su telefono.
 * `giornate` arriva da giornateDisponibili() (lib/selettori) ed e' gia' ordinato.
 */
interface Props {
  giornate: number[];
  valore: number | null;
  onChange: (giornata: number) => void;
  className?: string;
}

const BTN =
  "grid size-11 place-items-center rounded-diretta border border-linea bg-superficie-2 font-display text-3xl font-extrabold leading-none text-ink transition-opacity enabled:hover:border-accento-testo disabled:cursor-not-allowed disabled:opacity-35";

export default function SelettoreGiornata({ giornate, valore, onChange, className = "" }: Props) {
  const i = valore === null ? -1 : giornate.indexOf(valore);
  const prec = i > 0 ? giornate[i - 1] : undefined;
  const succ = i >= 0 && i < giornate.length - 1 ? giornate[i + 1] : undefined;
  return (
    <div className={`inline-flex items-center gap-2 ${className}`}>
      <button type="button" className={BTN} aria-label="Giornata precedente" disabled={prec === undefined} onClick={() => prec !== undefined && onChange(prec)}>
        ‹
      </button>
      <label className="solo-lettori" htmlFor="selettore-giornata">Giornata</label>
      <select
        id="selettore-giornata"
        className="min-h-11 min-w-40 cursor-pointer rounded-diretta border border-linea bg-superficie-2 px-3 font-display text-xl font-extrabold uppercase tracking-wide text-ink"
        value={valore ?? ""}
        onChange={(e) => onChange(Number(e.target.value))}
      >
        {giornate.map((g) => (
          <option key={g} value={g}>
            {etichettaGiornata(g)}
          </option>
        ))}
      </select>
      <button type="button" className={BTN} aria-label="Giornata successiva" disabled={succ === undefined} onClick={() => succ !== undefined && onChange(succ)}>
        ›
      </button>
    </div>
  );
}
