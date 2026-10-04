import { StatoVuoto } from "../../componenti";
import type { Movimento } from "../../tipi/snapshot";
import { formattaEuro } from "../../lib/format";
import Scomparsa from "./Scomparsa";

const Vuoto = () => (
  <>
    <span aria-hidden="true" className="text-ink-2">–</span>
    <span className="solo-lettori">nessun importo</span>
  </>
);

/** Tabella dei movimenti di cassa, nell'ordine del foglio (§6). `giornata`/`entrata`/`saldo` possono essere null. */
export default function MovimentiCassa({ movimenti }: { movimenti: Movimento[] }) {
  return (
    <Scomparsa titolo="Movimenti di cassa">
      {movimenti.length === 0 ? (
        <StatoVuoto titolo="Nessun movimento registrato">Il fondo non ha ancora ricevuto versamenti.</StatoVuoto>
      ) : (
        <div role="region" aria-label="Movimenti di cassa, scorri in orizzontale" tabIndex={0} className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="font-display text-base font-extrabold uppercase tracking-wide text-ink-2">
                <th scope="col" className="py-1.5 pr-2 text-left">Giornata</th>
                <th scope="col" className="px-2 py-1.5 text-left">Descrizione</th>
                <th scope="col" className="px-2 py-1.5 text-right">Entrata</th>
                <th scope="col" className="py-1.5 pl-2 text-right">Saldo</th>
              </tr>
            </thead>
            <tbody>
              {movimenti.map((m, i) => (
                <tr key={i} className="border-t border-linea align-top">
                  <td className="tabulare py-1.5 pr-2">
                    {m.giornata === null ? <Vuoto /> : m.giornata}
                  </td>
                  <td className="min-w-32 px-2 py-1.5">{m.descrizione}</td>
                  <td className="tabulare whitespace-nowrap px-2 py-1.5 text-right">
                    {m.entrata === null ? <Vuoto /> : formattaEuro(m.entrata)}
                  </td>
                  <td className="tabulare whitespace-nowrap py-1.5 pl-2 text-right font-bold">
                    {m.saldo === null ? <Vuoto /> : formattaEuro(m.saldo)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Scomparsa>
  );
}
