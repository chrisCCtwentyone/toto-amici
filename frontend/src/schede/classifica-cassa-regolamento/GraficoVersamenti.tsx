import { useState } from "react";
import { motion } from "motion/react";
import { StatoVuoto } from "../../componenti";
import { etichettaGiornata, formattaEuro, formattaEuroIntero } from "../../lib/format";
import { EASE_USCITA } from "../../lib/movimento";

type Dato = { giornata: number; versato: number };

/** Estremo del grafico: scala grafica (non dominio). Primo valore "tondo" >= massimo, con tre tacche 0 / meta' / cima. */
const PASSI = [50, 100, 200, 400, 500, 1000, 2000, 4000, 5000];
function cima(massimo: number): number {
  return PASSI.find((p) => p >= massimo) ?? Math.ceil(massimo / 1000) * 1000;
}

const ALTEZZA = "h-40";

/**
 * Versamenti in cassa per giornata (§6 `versamenti_per_giornata`, gia' ordinati, anche a zero).
 * Una sola serie: niente legenda, il titolo dice cosa e'. Colonne sottili con spigolo arrotondato in alto,
 * un solo valore scritto (il massimo), il resto in suggerimento al passaggio/tocco/tastiera e in tabella.
 */
export default function GraficoVersamenti({ dati }: { dati: Dato[] }) {
  const [tabella, setTabella] = useState(false);
  const [attivo, setAttivo] = useState<number | null>(null);
  if (dati.length === 0) return null;

  const massimo = Math.max(...dati.map((d) => d.versato));
  const top = cima(massimo);
  const iMax = massimo > 0 ? dati.findIndex((d) => d.versato === massimo) : -1;
  const n = dati.length;
  // con molte giornate si scrive il numero solo ogni tanto: la lettura esatta e' nel suggerimento e in tabella
  const passo = n <= 10 ? 1 : n <= 20 ? 2 : 5;

  const sel = (testo: string, attiva: boolean, onClick: () => void) => (
    <button
      type="button"
      aria-pressed={attiva}
      onClick={onClick}
      className={`min-h-11 cursor-pointer px-3 font-display text-base font-extrabold uppercase tracking-wide transition-colors duration-150 ${
        attiva ? "bg-accento text-su-accento" : "text-ink-2 hover:text-ink"
      }`}
    >
      {testo}
    </button>
  );

  return (
    <figure className="m-0">
      <div className="flex flex-wrap items-center justify-between gap-x-3">
        <figcaption className="font-display text-xl font-extrabold uppercase leading-none tracking-wide text-ink">
          Versamenti per giornata
        </figcaption>
        <div role="group" aria-label="Vista" className="flex border border-linea">
          {sel("Grafico", !tabella, () => setTabella(false))}
          {sel("Tabella", tabella, () => setTabella(true))}
        </div>
      </div>

      {tabella ? (
        <div role="region" aria-label="Versamenti per giornata, tabella" tabIndex={0} className="mt-2 max-h-72 overflow-y-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="font-display text-base font-extrabold uppercase tracking-wide text-ink-2">
                <th scope="col" className="py-1.5 text-left">Giornata</th>
                <th scope="col" className="py-1.5 text-right">Versato</th>
              </tr>
            </thead>
            <tbody>
              {dati.map((d) => (
                <tr key={d.giornata} className="border-t border-linea">
                  <th scope="row" className="py-1.5 text-left font-normal">{d.giornata}</th>
                  <td className="tabulare py-1.5 text-right">{formattaEuro(d.versato)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : massimo === 0 ? (
        <div className="mt-2">
          <StatoVuoto titolo="Nessun versamento finora">Per ora nessuna giornata ha versato in cassa.</StatoVuoto>
        </div>
      ) : (
        <div className="mt-3" onMouseLeave={() => setAttivo(null)}>
          <div className="flex gap-2 pt-5">
            {/* asse Y: tre tacche, testo in inchiostro secondario */}
            <div className={`relative ${ALTEZZA} w-12 flex-none text-xs text-ink-2`} aria-hidden="true">
              {[100, 50, 0].map((p) => (
                <span
                  key={p}
                  className="tabulare absolute right-0 translate-y-1/2 leading-none"
                  style={{ bottom: `${p}%` }}
                >
                  {formattaEuroIntero((top * p) / 100)}
                </span>
              ))}
            </div>

            <div className="relative min-w-0 flex-1">
              <div className={`relative ${ALTEZZA}`}>
                {[0, 50, 100].map((p) => (
                  <div key={p} aria-hidden="true" className="absolute inset-x-0 border-t border-linea" style={{ bottom: `${p}%` }} />
                ))}
                <ul className="absolute inset-0 m-0 flex list-none p-0">
                  {dati.map((d, i) => {
                    const altezza = (d.versato / top) * 100;
                    return (
                      <li key={d.giornata} className="relative min-w-0 flex-1">
                        <button
                          type="button"
                          aria-label={`${etichettaGiornata(d.giornata)}: ${formattaEuro(d.versato)}`}
                          onMouseEnter={() => setAttivo(i)}
                          onFocus={() => setAttivo(i)}
                          onBlur={() => setAttivo(null)}
                          onClick={() => setAttivo((a) => (a === i ? null : i))}
                          className="flex h-full w-full cursor-pointer items-end justify-center border-0 bg-transparent p-0 px-px"
                        >
                          <motion.span
                            aria-hidden="true"
                            className={`block w-full max-w-6 origin-bottom rounded-t-[4px] bg-marchio transition-opacity duration-150 ${
                              attivo !== null && attivo !== i ? "opacity-45" : ""
                            }`}
                            style={{ height: `${altezza}%` }}
                            initial={{ scaleY: 0 }}
                            animate={{ scaleY: 1 }}
                            transition={{ duration: 0.6, ease: EASE_USCITA, delay: Math.min(i, 12) * 0.03 }}
                          />
                        </button>
                        {i === iMax && attivo === null && (
                          <span
                            aria-hidden="true"
                            className="tabulare pointer-events-none absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-xs font-bold text-ink"
                            style={{ bottom: `calc(${altezza}% + 4px)` }}
                          >
                            {formattaEuro(d.versato)}
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>

                {attivo !== null && (
                  <div
                    aria-hidden="true"
                    className="tabulare pointer-events-none absolute z-10 whitespace-nowrap border border-linea bg-superficie-2 px-2 py-1 text-xs text-ink shadow-card"
                    style={{
                      left: `${((attivo + 0.5) / n) * 100}%`,
                      bottom: `calc(${(dati[attivo]!.versato / top) * 100}% + 8px)`,
                      // il suggerimento resta dentro il grafico: ancorato a sinistra sul primo, a destra sull'ultimo
                      transform: `translateX(-${n === 1 ? 50 : (attivo / (n - 1)) * 100}%)`,
                    }}
                  >
                    <span className="font-semibold">{etichettaGiornata(dati[attivo]!.giornata)}</span>
                    {" · "}
                    {formattaEuro(dati[attivo]!.versato)}
                  </div>
                )}
              </div>
              <ul className="m-0 mt-1 flex list-none p-0 text-xs text-ink-2" aria-hidden="true">
                {dati.map((d, i) => (
                  <li key={d.giornata} className="tabulare min-w-0 flex-1 text-center">
                    {i % passo === 0 ? d.giornata : ""}
                  </li>
                ))}
              </ul>
              <p className="m-0 mt-0.5 text-center text-xs text-ink-2" aria-hidden="true">giornata</p>
            </div>
          </div>
        </div>
      )}
    </figure>
  );
}
