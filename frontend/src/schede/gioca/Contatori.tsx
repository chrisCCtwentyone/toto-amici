import { conteggio, LIMITI, TIPI, type Riga } from "../../../worker/schedina";

/** Quanti pronostici per tipo: verde quando giusti, rosso se troppi. Fissi in alto mentre si scorre. */
export default function Contatori({ righe }: { righe: readonly Riga[] }) {
  const n = conteggio(righe);
  return (
    <div className="sticky top-[4.25rem] z-10 -mx-4 bg-bg/95 px-4 py-2 backdrop-blur-md">
      <ul aria-label="Pronostici scelti per tipo" className="grid grid-cols-4 gap-1.5">
        {TIPI.map((t) => {
          const giusto = n[t] === LIMITI[t];
          const troppi = n[t] > LIMITI[t];
          return (
            <li
              key={t}
              className={`rounded-diretta border-2 bg-superficie px-1 py-1 text-center ${giusto ? "border-vinta text-vinta" : troppi ? "border-persa text-persa" : "border-linea text-ink"}`}
            >
              <span className="block font-display text-sm font-extrabold uppercase leading-tight tracking-wide">{t}</span>
              <span className="tabulare block font-display text-xl font-extrabold leading-tight">
                {giusto && <span aria-hidden="true">✓ </span>}
                {troppi && <span aria-hidden="true">! </span>}
                {n[t]}/{LIMITI[t]}
                <span className="solo-lettori">{giusto ? ", giusto" : troppi ? ", troppi" : ""}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
