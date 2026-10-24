import { useState, type ReactNode } from "react";
import type { Classifica } from "../../tipi/snapshot";
import { formattaIntero } from "../../lib/format";
import Scomparsa from "./Scomparsa";
import { ordinaStorico, type ColonnaOrdine, type RigaStorico, type Verso } from "./storico";

/** Punteggio di una giornata: `null` (nessuna schedina valutata) e' diverso da 0 (§5.2). */
function Cella({ v, evidenza = false }: { v: number | null; evidenza?: boolean }) {
  return (
    <td className={`tabulare px-2 py-1.5 text-right ${evidenza ? "bg-accento/10 font-bold text-ink" : ""}`}>
      {v === null ? (
        <>
          <span aria-hidden="true" className="text-ink-2">–</span>
          <span className="solo-lettori">nessun punteggio</span>
        </>
      ) : (
        formattaIntero(v)
      )}
    </td>
  );
}

/** Intestazione cliccabile: ordina per quella colonna (prima dal piu' alto, al secondo tocco dal piu' basso). */
function Intestazione({ colonna, ordine, onOrdina, etichetta, children, className = "" }: {
  colonna: ColonnaOrdine;
  ordine: { colonna: ColonnaOrdine; verso: Verso };
  onOrdina: (c: ColonnaOrdine) => void;
  etichetta: string;
  children: ReactNode;
  className?: string;
}) {
  const attiva = ordine.colonna === colonna;
  const ariaSort = !attiva ? "none" : colonna === null ? "ascending" : ordine.verso === "giu" ? "descending" : "ascending";
  return (
    <th scope="col" aria-sort={ariaSort} className={className}>
      <button
        type="button"
        onClick={() => onOrdina(colonna)}
        aria-label={colonna === null ? "Ordina come la Classifica" : `Ordina per ${etichetta}`}
        className={`inline-flex min-h-8 cursor-pointer items-center gap-0.5 uppercase tracking-wide underline-offset-4 hover:underline ${attiva ? "text-accento-testo" : ""}`}
      >
        {children}
        {attiva && colonna !== null && <span aria-hidden="true" className="text-xs">{ordine.verso === "giu" ? "▼" : "▲"}</span>}
      </button>
    </th>
  );
}

export default function StoricoGiornate({ classifica }: { classifica: Classifica }) {
  const [ordine, setOrdine] = useState<{ colonna: ColonnaOrdine; verso: Verso }>({ colonna: null, verso: "giu" });
  const onOrdina = (colonna: ColonnaOrdine) =>
    setOrdine((o) => (colonna !== null && o.colonna === colonna ? { colonna, verso: o.verso === "giu" ? "su" : "giu" } : { colonna, verso: "giu" }));
  const tutte: RigaStorico[] = [
    ...classifica.giocatori.map((r) => ({ nome: r.nome, tot: r.punti_totali, g: r.punti_per_giornata, ritirato: false })),
    ...classifica.ritirati.map((r) => ({ nome: `${r.nome} (ritirato)`, tot: r.punti_totali, g: r.punti_per_giornata, ritirato: true })),
  ];
  const righe = ordinaStorico(tutte, ordine.colonna, ordine.verso);
  if (righe.length === 0) return null;
  const lunghezza = Math.max(...righe.map((r) => r.g.length));
  // una giornata vuota per tutti si nasconde (§5.2)
  const colonne = Array.from({ length: lunghezza }, (_, i) => i).filter((i) => righe.some((r) => r.g[i] != null));
  if (colonne.length === 0) return null;

  return (
    <Scomparsa titolo="Storico punteggi per giornata">
      <p className="mb-2 mt-0 text-sm text-ink-2">Tocca una giornata (G1, G2…) per vedere chi ha fatto più punti quel turno; tocca di nuovo per invertire, «Giocatore» per tornare alla Classifica.</p>
      <div
        role="region"
        aria-label="Storico punteggi per giornata, scorri in orizzontale"
        tabIndex={0}
        className="relative isolate overflow-x-auto"
      >
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="font-display text-base font-extrabold uppercase tracking-wide text-ink-2">
              <Intestazione colonna={null} ordine={ordine} onOrdina={onOrdina} etichetta="Classifica" className="sticky left-0 z-10 bg-superficie py-1.5 pr-3 text-left">
                Giocatore
              </Intestazione>
              {colonne.map((i) => (
                <Intestazione key={i} colonna={i} ordine={ordine} onOrdina={onOrdina} etichetta={`Giornata ${i + 1}`} className="px-2 py-1.5 text-right">
                  G{i + 1}
                </Intestazione>
              ))}
              <Intestazione colonna="tot" ordine={ordine} onOrdina={onOrdina} etichetta="punti totali" className="px-2 py-1.5 text-right text-ink">
                Tot.
              </Intestazione>
            </tr>
          </thead>
          <tbody>
            {righe.map((r) => (
              <tr key={r.nome} className="border-t border-linea">
                <th scope="row" className="sticky left-0 whitespace-nowrap bg-superficie py-1.5 pr-3 text-left font-semibold">
                  {r.nome}
                </th>
                {colonne.map((i) => (
                  <Cella key={i} v={r.g[i] ?? null} evidenza={ordine.colonna === i} />
                ))}
                <td className={`tabulare px-2 py-1.5 text-right font-bold ${ordine.colonna === "tot" ? "bg-accento/10" : ""}`}>{formattaIntero(r.tot)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Scomparsa>
  );
}
