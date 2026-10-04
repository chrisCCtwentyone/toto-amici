import { useState } from "react";
import { motion } from "motion/react";
import { Card, SelettoreGiornata, StatoVuoto } from "../componenti";
import { useSnapshot } from "../lib/DatiContext";
import { etichettaGiornata, formattaEuro, formattaQuota } from "../lib/format";
import { giornateDisponibili } from "../lib/selettori";
import CellaGiocata, { sfondoCella } from "./live-confronto/CellaGiocata";
import { testoOrario, testoSceltaGruppo } from "./live-confronto/dati";

// Celle: bordo in basso e a destra (tabella "separate" perche' la colonna fissa non perda i bordi).
const CELLA = "border-b border-r border-linea px-3 py-2.5 align-top";
// Prima colonna fissa: sfondo pieno, altrimenti le celle scorrono visibili "sotto" il nome della partita.
const FISSA = "sticky left-0 z-10 bg-superficie";

export default function ConfrontoGiocate() {
  const s = useSnapshot();
  const giornate = giornateDisponibili(s);
  const [giornata, setGiornata] = useState<number | null>(s.giornata_corrente ?? giornate.at(-1) ?? null);

  // uguaglianza di interi, mai per sottostringa (bug di Sessione 13); gli array sono gia' nell'ordine giusto (§7)
  const partite = s.partite.filter((p) => p.giornata === giornata);
  const schedine = s.schedine.filter((x) => x.giornata === giornata);
  const soglia = s.regole.soglia_quota_doppia;

  return (
    <div className="grid gap-4 pb-6">
      <Card titolo="Confronto" evidenza="Giocate" bandiera="marchio" azione={<SelettoreGiornata giornate={giornate} valore={giornata} onChange={setGiornata} />}>
        <p className="m-0 text-ink-2">Cosa ha giocato ogni partecipante sui vari eventi della giornata.</p>
      </Card>

      {partite.length === 0 || schedine.length === 0 ? (
        <StatoVuoto titolo="Nessuna giocata per questa giornata">
          Quando i giocatori caricano le schedine della {etichettaGiornata(giornata ?? 0)} il confronto compare qui.
        </StatoVuoto>
      ) : (
        <>
          <p className="m-0 text-sm text-ink-2">Scorri di lato per vedere tutti i giocatori: la colonna delle partite resta ferma.</p>
          {/* regione scorrevole con tastiera (tabIndex): lo scroll orizzontale e' dentro il contenitore, non nella pagina */}
          <div
            role="region"
            aria-label={`Tabella dei pronostici, ${etichettaGiornata(giornata ?? 0)}`}
            tabIndex={0}
            className="overflow-x-auto overscroll-x-contain rounded-diretta border-l border-t border-linea bg-superficie shadow-card"
          >
            <table className="w-max min-w-full border-separate border-spacing-0 text-left">
              <caption className="solo-lettori">
                Pronostici di ogni giocatore per le partite della {etichettaGiornata(giornata ?? 0)}, con la scelta del gruppo e la vincita potenziale.
              </caption>
              <thead>
                <tr>
                  <th scope="col" className={`${CELLA} ${FISSA} z-20 w-40 min-w-40 bg-superficie-2 sm:w-64 sm:min-w-64`}>
                    <span className="titolo-diretta text-lg text-ink-2">Partita</span>
                  </th>
                  <th scope="col" className={`${CELLA} min-w-36 bg-accento/10`}>
                    <span className="titolo-diretta text-lg text-accento-testo">Scelta del gruppo</span>
                  </th>
                  {schedine.map((x) => (
                    <th key={x.giocatore} scope="col" className={`${CELLA} min-w-32 bg-superficie-2`}>
                      <span className="titolo-diretta text-lg text-ink">{x.giocatore}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              {/* una sola dissolvenza all'apertura/cambio giornata: niente movimento sulle righe (la colonna fissa non deve ballare) */}
              <motion.tbody
                key={giornata}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.2 }}
              >
                {partite.map((p) => {
                  const orario = testoOrario(p.inizio_il);
                  return (
                    <tr key={p.id} className="group">
                      <th scope="row" className={`${CELLA} ${FISSA} w-40 min-w-40 font-normal group-hover:bg-superficie-2 sm:w-64 sm:min-w-64`}>
                        <span className="block font-display text-lg font-extrabold uppercase leading-tight tracking-wide text-ink [overflow-wrap:anywhere]">
                          {p.nome}
                        </span>
                        <span className="block text-sm text-ink-2">{orario ?? "Orario da definire"}</span>
                      </th>
                      <td className={`${CELLA} bg-accento/10 font-display text-lg font-extrabold leading-tight text-ink`}>
                        {testoSceltaGruppo(p.scelta_gruppo)}
                      </td>
                      {schedine.map((x) => {
                        const righe = x.righe.filter((r) => r.partita_id === p.id);
                        return (
                          <td key={x.giocatore} className={`${CELLA} ${sfondoCella(righe)}`}>
                            <CellaGiocata righe={righe} soglia={soglia} />
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </motion.tbody>
              <tfoot>
                <tr>
                  <th scope="row" className={`${CELLA} ${FISSA} bg-superficie-2 font-normal`}>
                    <span className="titolo-diretta text-lg text-ink-2">Vincita potenziale</span>
                  </th>
                  <td className={`${CELLA} bg-superficie-2`} />
                  {schedine.map((x) => (
                    <td key={x.giocatore} className={`${CELLA} tabulare bg-superficie-2 font-display text-xl font-extrabold text-accento-testo`}>
                      {formattaEuro(x.vincita_potenziale)}
                    </td>
                  ))}
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="m-0 text-sm text-ink-2">
            * quota ≥ {formattaQuota(soglia)}: punti raddoppiati. <span className="text-vinta">✓</span> vinta, <span className="text-persa">✕</span> persa: nelle altre celle l'esito non è ancora deciso.
          </p>
        </>
      )}
    </div>
  );
}
