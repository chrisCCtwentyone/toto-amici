import { Card, StatoVuoto } from "../componenti";
import { useSnapshot } from "../lib/DatiContext";
import { formattaIntero } from "../lib/format";

/**
 * SEGNAPOSTO della scheda "Statistiche": va sostituito per intero (lascia `export default`).
 * Legge: §8 statistiche.
 * Campi dello snapshot: statistiche. Vedi GUIDA-SCHEDE.md.
 */
export default function Statistiche() {
  const snapshot = useSnapshot();
  return (
    <Card titolo="Statistiche" evidenza="in costruzione" bandiera="accento">
      <StatoVuoto titolo="Scheda da costruire">
        I dati ci sono già: {formattaIntero(snapshot.statistiche.giocatori.length)} giocatori con statistiche.
      </StatoVuoto>
    </Card>
  );
}
