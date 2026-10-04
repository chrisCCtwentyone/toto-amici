import { Card, StatoVuoto } from "../componenti";
import { useSnapshot } from "../lib/DatiContext";
import { formattaIntero } from "../lib/format";

/**
 * SEGNAPOSTO della scheda "Classifica & Cassa": va sostituito per intero (lascia `export default`).
 * Legge: §5 classifica, §6 cassa.
 * Campi dello snapshot: classifica, cassa. Vedi GUIDA-SCHEDE.md.
 */
export default function ClassificaCassa() {
  const snapshot = useSnapshot();
  return (
    <Card titolo="Classifica & Cassa" evidenza="in costruzione" bandiera="accento">
      <StatoVuoto titolo="Scheda da costruire">
        I dati ci sono già: {formattaIntero(snapshot.classifica.giocatori.length)} giocatori in classifica.
      </StatoVuoto>
    </Card>
  );
}
