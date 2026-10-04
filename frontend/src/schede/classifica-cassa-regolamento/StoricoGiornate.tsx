import type { Classifica } from "../../tipi/snapshot";
import { formattaIntero } from "../../lib/format";
import Scomparsa from "./Scomparsa";

/** Punteggio di una giornata: `null` (nessuna schedina valutata) e' diverso da 0 (§5.2). */
function Cella({ v }: { v: number | null }) {
  return (
    <td className="tabulare px-2 py-1.5 text-right">
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

export default function StoricoGiornate({ classifica }: { classifica: Classifica }) {
  const righe = [
    ...classifica.giocatori.map((r) => ({ nome: r.nome, tot: r.punti_totali, g: r.punti_per_giornata })),
    ...classifica.ritirati.map((r) => ({ nome: `${r.nome} (ritirato)`, tot: r.punti_totali, g: r.punti_per_giornata })),
  ];
  if (righe.length === 0) return null;
  const lunghezza = Math.max(...righe.map((r) => r.g.length));
  // una giornata vuota per tutti si nasconde (§5.2)
  const colonne = Array.from({ length: lunghezza }, (_, i) => i).filter((i) => righe.some((r) => r.g[i] != null));
  if (colonne.length === 0) return null;

  return (
    <Scomparsa titolo="Storico punteggi per giornata">
      <div
        role="region"
        aria-label="Storico punteggi per giornata, scorri in orizzontale"
        tabIndex={0}
        className="overflow-x-auto"
      >
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="font-display text-base font-extrabold uppercase tracking-wide text-ink-2">
              <th scope="col" className="sticky left-0 bg-superficie py-1.5 pr-3 text-left">Giocatore</th>
              {colonne.map((i) => (
                <th key={i} scope="col" aria-label={`Giornata ${i + 1}`} className="px-2 py-1.5 text-right">
                  G{i + 1}
                </th>
              ))}
              <th scope="col" className="px-2 py-1.5 text-right text-ink">Tot.</th>
            </tr>
          </thead>
          <tbody>
            {righe.map((r) => (
              <tr key={r.nome} className="border-t border-linea">
                <th scope="row" className="sticky left-0 whitespace-nowrap bg-superficie py-1.5 pr-3 text-left font-semibold">
                  {r.nome}
                </th>
                {colonne.map((i) => (
                  <Cella key={i} v={r.g[i] ?? null} />
                ))}
                <td className="tabulare px-2 py-1.5 text-right font-bold">{formattaIntero(r.tot)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Scomparsa>
  );
}
