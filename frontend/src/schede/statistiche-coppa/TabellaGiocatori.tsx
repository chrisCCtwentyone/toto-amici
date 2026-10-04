import { Card } from "../../componenti";
import type { StatGiocatore } from "../../tipi/snapshot";
import { formattaIntero, formattaPercentuale, formattaQuota } from "../../lib/format";

function Riga({ s, ritirato = false }: { s: StatGiocatore; ritirato?: boolean }) {
  return (
    <tr className="border-t border-linea">
      <th scope="row" className={`py-2 pl-3 pr-2 text-left font-display text-lg font-extrabold uppercase tracking-wide ${ritirato ? "text-ink-2" : "text-ink"}`}>
        {s.nome}
      </th>
      <td className="tabulare py-2 pr-3 text-right">
        <span className="font-display text-lg font-extrabold text-ink">{formattaPercentuale(s.win_rate, 1)}</span>
        {/* la barra e' la stessa cifra in forma grafica: scala 0-100, non un calcolo */}
        <span aria-hidden="true" className="mt-0.5 ml-auto block h-1 w-full bg-traccia">
          <span className="block h-full bg-marchio" style={{ width: `${Math.min(100, Math.max(0, s.win_rate))}%` }} />
        </span>
      </td>
      <td className="tabulare py-2 pr-3 text-right text-ink">{formattaQuota(s.quota_media)}</td>
      <td className="tabulare py-2 pr-3 text-right text-ink">{formattaIntero(s.vinte)}</td>
      <td className="tabulare py-2 pr-3 text-right text-ink-2">{formattaIntero(s.totali)}</td>
    </tr>
  );
}

const TH = "py-2 pr-3 text-right font-display text-sm font-extrabold uppercase tracking-wider text-ink-2";

/** §8 — tabella completa per giocatore; i ritirati in fondo, in un gruppo a parte. */
export default function TabellaGiocatori({ giocatori, ritirati }: { giocatori: readonly StatGiocatore[]; ritirati: readonly StatGiocatore[] }) {
  return (
    <Card titolo="Tabella completa" evidenza="giocatori" livello={3} bandiera="accento">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[19rem] border-collapse text-base">
          <caption className="solo-lettori">Statistiche di ogni giocatore, dal win rate più alto al più basso</caption>
          <thead>
            <tr>
              <th scope="col" className="py-2 pl-3 pr-2 text-left font-display text-sm font-extrabold uppercase tracking-wider text-ink-2">Giocatore</th>
              <th scope="col" className={TH}>Win rate</th>
              <th scope="col" className={TH}>Quota media</th>
              <th scope="col" className={TH}>Vinte</th>
              <th scope="col" className={TH}>Totali</th>
            </tr>
          </thead>
          <tbody>{giocatori.map((s) => <Riga key={s.nome} s={s} />)}</tbody>
          {ritirati.length > 0 && (
            <tbody>
              <tr className="border-t-2 border-linea bg-superficie-2">
                <th scope="rowgroup" colSpan={5} className="py-1.5 pl-3 text-left font-display text-sm font-extrabold uppercase tracking-wider text-ink-2">
                  Ritirati · statistiche congelate
                </th>
              </tr>
              {ritirati.map((s) => <Riga key={s.nome} s={s} ritirato />)}
            </tbody>
          )}
        </table>
      </div>
      <p className="mt-3 text-sm text-ink-2">
        Win rate = pronostici presi sul totale di quelli già giocati. Quota media «—» = nessuna quota leggibile.
      </p>
    </Card>
  );
}
