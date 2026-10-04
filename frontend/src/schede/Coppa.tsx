import { Card, StatoVuoto } from "../componenti";
import { useSnapshot } from "../lib/DatiContext";
import { formattaIntero } from "../lib/format";

/**
 * SEGNAPOSTO della scheda "Coppa": va sostituito per intero (lascia `export default`).
 * Legge: §9 coppa (+ §10 per i numeri delle giornate).
 * Campi dello snapshot: coppa. Vedi GUIDA-SCHEDE.md.
 */
export default function Coppa() {
  const snapshot = useSnapshot();
  return (
    <Card titolo="Coppa" evidenza="in costruzione" bandiera="accento">
      <StatoVuoto titolo="Scheda da costruire">
        I dati ci sono già: {formattaIntero(snapshot.coppa.partecipanti)} partecipanti al tabellone.
      </StatoVuoto>
    </Card>
  );
}
