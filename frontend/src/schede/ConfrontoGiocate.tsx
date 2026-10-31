import { useState } from "react";
import { motion } from "motion/react";
import { Card, SelettoreGiornata, StatoVuoto } from "../componenti";
import { useSnapshot } from "../lib/DatiContext";
import { etichettaGiornata, formattaEuro, formattaIntero, formattaQuota } from "../lib/format";
import { giornataEffettiva, giornateDisponibili } from "../lib/selettori";
import CellaGiocata, { sfondoCella } from "./live-confronto/CellaGiocata";
import { puntiMassimiGiornata, puntiRimanenti, puntiSchedina, testoOrario, testoSceltaGruppo } from "./live-confronto/dati";

// Celle: bordo in basso e a destra (tabella "separate" perche' la colonna fissa non perda i bordi).
const CELLA = "border-b border-r border-linea px-3 py-2.5 align-top";
// Prima colonna fissa: sfondo pieno, altrimenti le celle scorrono visibili "sotto" il nome della partita.
const FISSA = "sticky left-0 z-10 bg-superficie";
// Riga dei nomi fissa in alto mentre si scorre: serve uno sfondo pieno per lo stesso motivo.
const TESTATA = "sticky top-0 z-10";
// Colonna di un giocatore: larghezza fissa (la tabella e' w-max e altrimenti ogni colonna prenderebbe la riga piu' lunga).
// 112px lasciano 88px di testo: "2+OVER_2.5" sta su una riga (la quota va sotto), e cosi' "rimanenti 30 pt".
const GIOCATORE = "w-28 min-w-28";

export default function ConfrontoGiocate() {
  const s = useSnapshot();
  const giornate = giornateDisponibili(s);
  // finche' l'utente non sceglie, segue la giornata corrente dello snapshot
  const [giornataScelta, setGiornata] = useState<number | null>(null);
  const giornata = giornataEffettiva(s, giornataScelta);

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
          <p className="m-0 text-sm text-ink-2">
            {schedine.length} di {s.giocatori.length} schedine caricate.
            {schedine.length > 1
              ? " Scorri di lato per vedere tutti i giocatori: la colonna delle partite e i nomi restano fermi."
              : " Scorri di lato per vedere anche la scelta del gruppo: la colonna delle partite e i nomi restano fermi."}
          </p>
          {/* regione scorrevole con tastiera (tabIndex): lo scroll orizzontale e' dentro il contenitore, non nella pagina.
              "relative" serve: i testi .solo-lettori sono absolute e, senza un antenato posizionato, uscirebbero dal
              contenitore e allargherebbero la pagina; min-w-0 evita che la griglia genitrice si allarghi al contenuto.
              "isolate": le z-index della colonna fissa (z-10/z-20) restano dentro la tabella, altrimenti la cella
              "Partita" scorrendo passava sopra la barra delle schede (anch'essa z-20) e sopra il ticker in basso.
              Scorrimento anche verticale, con altezza massima = schermo meno barra delle schede (4,25rem) e ticker:
              con overflow-x la tabella e' comunque il contenitore di scorrimento anche in verticale, quindi la riga
              dei nomi puo' restare ferma solo in cima alla tabella, non sotto la barra della pagina. */}
          <div
            role="region"
            aria-label={`Tabella dei pronostici, ${etichettaGiornata(giornata ?? 0)}`}
            tabIndex={0}
            className="relative isolate max-h-[calc(100dvh-9rem)] min-w-0 overflow-auto overscroll-x-contain rounded-diretta border-l border-t border-linea bg-superficie shadow-card"
          >
            <table className="w-max min-w-full border-separate border-spacing-0 text-left">
              <caption className="solo-lettori">
                Pronostici di ogni giocatore per le partite della {etichettaGiornata(giornata ?? 0)}, con la scelta del gruppo e la vincita potenziale.
              </caption>
              <thead>
                <tr>
                  <th scope="col" className={`${CELLA} ${FISSA} top-0 z-20 w-36 min-w-36 bg-superficie-2 sm:w-64 sm:min-w-64`}>
                    <span className="titolo-diretta text-lg text-ink-2">Partita</span>
                  </th>
                  {schedine.map((x) => (
                    <th key={x.giocatore} scope="col" className={`${CELLA} ${TESTATA} ${GIOCATORE} bg-superficie-2`}>
                      <span className="titolo-diretta text-lg text-ink">{x.giocatore}</span>
                    </th>
                  ))}
                  <th scope="col" className={`${CELLA} ${TESTATA} min-w-40 bg-[color-mix(in_srgb,var(--accento)_10%,var(--superficie))]`}>
                    <span className="titolo-diretta text-lg text-accento-testo">Scelta del gruppo</span>
                  </th>
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
                      <th scope="row" className={`${CELLA} ${FISSA} w-36 min-w-36 font-normal group-hover:bg-superficie-2 sm:w-64 sm:min-w-64`}>
                        <span className="block font-display text-lg font-extrabold uppercase leading-tight tracking-wide text-ink [overflow-wrap:anywhere]">
                          {p.nome}
                        </span>
                        <span className="block text-sm text-ink-2">{orario ?? "Orario da definire"}</span>
                      </th>
                      {schedine.map((x) => {
                        const righe = x.righe.filter((r) => r.partita_id === p.id);
                        return (
                          <td key={x.giocatore} className={`${CELLA} ${sfondoCella(righe)}`}>
                            <CellaGiocata righe={righe} soglia={soglia} />
                          </td>
                        );
                      })}
                      <td className={`${CELLA} bg-accento/10 font-display text-lg font-extrabold leading-tight text-ink`}>
                        {testoSceltaGruppo(p.scelta_gruppo)}
                      </td>
                    </tr>
                  );
                })}
              </motion.tbody>
              <tfoot>
                <tr>
                  <th scope="row" className={`${CELLA} ${FISSA} bg-superficie-2 font-normal`}>
                    <span className="titolo-diretta text-lg text-ink-2">Vincita potenziale</span>
                  </th>
                  {schedine.map((x) => (
                    <td key={x.giocatore} className={`${CELLA} tabulare bg-superficie-2 font-display text-xl font-extrabold text-accento-testo`}>
                      {formattaEuro(x.vincita_potenziale)}
                    </td>
                  ))}
                  <td className={`${CELLA} bg-superficie-2`} />
                </tr>
                <tr>
                  <th scope="row" className={`${CELLA} ${FISSA} bg-superficie-2 font-normal`}>
                    <span className="titolo-diretta text-lg text-ink-2">Punti fatti</span>
                  </th>
                  {schedine.map((x) => {
                    const fatti = puntiSchedina(x.righe);
                    const massimo = puntiMassimiGiornata(x.righe, s.regole);
                    const rimanenti = puntiRimanenti(x.righe, s.regole);
                    return (
                      <td key={x.giocatore} className={`${CELLA} tabulare bg-superficie-2 font-display text-xl font-extrabold text-ink`}>
                        <span aria-hidden="true">
                          <span className="block">
                            {formattaIntero(fatti)}
                            <span className="text-ink-2">/{formattaIntero(massimo)}</span> pt
                          </span>
                          <span className="block font-testo text-xs font-normal text-ink-2">rimanenti {formattaIntero(rimanenti)} pt</span>
                        </span>
                        <span className="solo-lettori">
                          {fatti} punti fatti su {massimo} possibili nella giornata; con le partite ancora da decidere può fare ancora {rimanenti} punti
                        </span>
                      </td>
                    );
                  })}
                  <td className={`${CELLA} bg-superficie-2`} />
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="m-0 text-sm text-ink-2">
            «Punti fatti»: punti ottenuti / massimo della giornata (tutti i pronostici azzeccati); sotto, «rimanenti»: i punti che può ancora fare con le partite non ancora decise, che scendono a ogni partita finita. Bonus di chiusura escluso. * quota ≥ {formattaQuota(soglia)}: punti raddoppiati. <span className="text-vinta">✓</span> vinta, <span className="text-persa">✕</span> persa: nelle altre celle l'esito non è ancora deciso.
          </p>
        </>
      )}
    </div>
  );
}
