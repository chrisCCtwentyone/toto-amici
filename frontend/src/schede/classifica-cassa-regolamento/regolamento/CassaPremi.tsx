import { Card } from "../../../componenti";
import type { Regole } from "../../../tipi/snapshot";
import { formattaEuroIntero, formattaFrazione, formattaIntero, formattaPercentuale, formattaOrdinale } from "../../../lib/format";

/** Colori delle prime tre posizioni, come il podio della Classifica. */
const CASELLA: Record<number, string> = {
  1: "bg-oro text-su-oro",
  2: "bg-accento text-su-accento",
  3: "bg-marchio text-su-barra",
};

export default function CassaPremi({ regole }: { regole: Regole }) {
  return (
    <Card titolo="4. Cassa e" evidenza="montepremi" livello={3} bandiera="oro">
      <ul className="m-0 grid list-disc gap-2.5 pl-5 marker:text-ink-2">
        <li>
          <strong>Quota di partecipazione:</strong> <strong>{formattaEuroIntero(regole.quota_partecipazione)}</strong> a persona,
          entro la {formattaIntero(regole.scadenza_quota_giornata)}ª giornata.
        </li>
        <li>
          <strong>Vincite:</strong> il {formattaFrazione(regole.quota_cassa_su_vincita)} al Fondo Cassa, il resto al giocatore{" "}
          <em>(da versare subito dopo la vincita)</em>.
        </li>
      </ul>

      <h4 className="mb-1 mt-4 text-sm font-semibold uppercase tracking-wider text-ink-2">
        Esempio ripartizione premi · {formattaIntero(regole.giocatori)} giocatori · {formattaEuroIntero(regole.obiettivo_cassa)}
      </h4>
      <table className="w-full border-collapse text-base">
        <thead>
          <tr className="font-display text-base font-extrabold uppercase tracking-wide text-ink-2">
            <th scope="col" className="py-1.5 pr-2 text-left">Posizione</th>
            <th scope="col" className="px-2 py-1.5 text-right">Quota</th>
            <th scope="col" className="py-1.5 pl-2 text-right">Premio</th>
          </tr>
        </thead>
        <tbody>
          {regole.ripartizione_premi.map((p) => (
            <tr key={p.posizione} className="border-t border-linea">
              <th scope="row" className="py-1.5 pr-2 text-left font-normal">
                <span
                  className={`obliquo inline-block min-w-9 px-1.5 text-center ${CASELLA[p.posizione] ?? "bg-superficie-2 text-ink"}`}
                >
                  <span className="contro-obliquo block font-display text-xl font-extrabold leading-7">
                    {formattaOrdinale(p.posizione)}
                  </span>
                </span>
              </th>
              <td className="tabulare px-2 py-1.5 text-right text-ink-2">{formattaPercentuale(p.percentuale, 0)}</td>
              {/* importo = obiettivo x percentuale / 100: e' solo il conto della tabella, la regola (le percentuali) viene dallo snapshot */}
              <td className="tabulare py-1.5 pl-2 text-right font-bold">
                {formattaEuroIntero((regole.obiettivo_cassa * p.percentuale) / 100)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
