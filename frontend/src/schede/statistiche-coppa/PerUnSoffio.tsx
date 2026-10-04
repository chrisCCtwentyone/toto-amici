import { Card, StatoVuoto } from "../../componenti";
import type { PerUnSoffio as Soffio } from "../../tipi/snapshot";
import { etichettaGiornata, formattaQuota } from "../../lib/format";

/** §8.3 — schedine perse per un solo evento. L'ordine (giornata piu' recente, poi nome) e' dello snapshot. */
export default function PerUnSoffio({ soffi }: { soffi: readonly Soffio[] }) {
  return (
    <Card titolo="Per un" evidenza="soffio" livello={3} bandiera="live">
      {soffi.length === 0 ? (
        <StatoVuoto titolo="Nessun «per un soffio»">Nessuna schedina persa per un solo evento, finora.</StatoVuoto>
      ) : (
        <>
          <p className="mb-3 text-sm text-ink-2">
            Schedine con tutto giusto tranne un evento. Contano solo quelle con tutte le partite già giocate.
          </p>
          <ul className="m-0 grid list-none gap-2 p-0 md:grid-cols-2">
            {soffi.map((s) => (
              <li
                key={`${s.giornata}-${s.giocatore}-${s.partita}`}
                className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-0.5 border-l-4 border-l-persa bg-superficie-2 py-2.5 pl-3 pr-3"
              >
                <span className="font-display text-xl font-extrabold uppercase leading-6 tracking-wide text-ink">{s.giocatore}</span>
                <span className="obliquo justify-self-end bg-accento px-2.5 text-su-accento">
                  <span className="contro-obliquo block font-display text-xl font-extrabold leading-7">{s.pronostico}</span>
                </span>
                <span className="min-w-0 text-sm text-ink [overflow-wrap:anywhere]">{s.partita}</span>
                <span className="tabulare justify-self-end text-sm text-ink-2">quota {formattaQuota(s.quota)}</span>
                <span className="col-span-2 text-xs font-semibold uppercase tracking-wider text-ink-2">
                  {etichettaGiornata(s.giornata)} · evento sbagliato
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
