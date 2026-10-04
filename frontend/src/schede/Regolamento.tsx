import { Card, StatoVuoto } from "../componenti";
import { useSnapshot } from "../lib/DatiContext";
import { formattaIntero } from "../lib/format";

/**
 * SEGNAPOSTO della scheda "Regolamento": va sostituito per intero (lascia `export default`).
 * Legge: §10 regole.
 * Campi dello snapshot: regole. Vedi GUIDA-SCHEDE.md.
 */
export default function Regolamento() {
  const snapshot = useSnapshot();
  return (
    <Card titolo="Regolamento" evidenza="in costruzione" bandiera="accento">
      <StatoVuoto titolo="Scheda da costruire">
        I dati ci sono già: {formattaIntero(snapshot.regole.giocatori)} giocatori in regolamento.
      </StatoVuoto>
    </Card>
  );
}
