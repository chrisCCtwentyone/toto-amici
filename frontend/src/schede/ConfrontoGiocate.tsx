import { Card, StatoVuoto } from "../componenti";
import { useSnapshot } from "../lib/DatiContext";
import { formattaIntero } from "../lib/format";

/**
 * SEGNAPOSTO della scheda "Confronto Giocate": va sostituito per intero (lascia `export default`).
 * Legge: §7 partite (scelta_gruppo) e schedine, §10 regole.soglia_quota_doppia.
 * Campi dello snapshot: partite, schedine, regole. Vedi GUIDA-SCHEDE.md.
 */
export default function ConfrontoGiocate() {
  const snapshot = useSnapshot();
  return (
    <Card titolo="Confronto Giocate" evidenza="in costruzione" bandiera="accento">
      <StatoVuoto titolo="Scheda da costruire">
        I dati ci sono già: {formattaIntero(snapshot.partite.length)} partite in archivio.
      </StatoVuoto>
    </Card>
  );
}
