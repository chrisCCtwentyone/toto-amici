import { Card, StatoVuoto } from "../componenti";
import { useSnapshot } from "../lib/DatiContext";
import { formattaIntero } from "../lib/format";

/**
 * SEGNAPOSTO della scheda "Schedine Live": va sostituito per intero (lascia `export default`).
 * Legge: §7 partite e schedine (+ risultati dal Worker, useLive).
 * Campi dello snapshot: giornata_corrente, giocatori, schedine, partite. Vedi GUIDA-SCHEDE.md.
 */
export default function SchedineLive() {
  const snapshot = useSnapshot();
  return (
    <Card titolo="Schedine Live" evidenza="in costruzione" bandiera="accento">
      <StatoVuoto titolo="Scheda da costruire">
        I dati ci sono già: {formattaIntero(snapshot.schedine.length)} schedine in archivio.
      </StatoVuoto>
    </Card>
  );
}
