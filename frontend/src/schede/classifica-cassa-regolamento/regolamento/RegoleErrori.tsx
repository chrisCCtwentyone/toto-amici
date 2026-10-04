import { Card } from "../../../componenti";
import type { Regole } from "../../../tipi/snapshot";

export default function RegoleErrori({ regole }: { regole: Regole }) {
  return (
    <Card titolo="3. Regole ed" evidenza="errori" livello={3} bandiera="live">
      <ul className="m-0 grid list-disc gap-2.5 pl-5 marker:text-ink-2">
        <li>
          <strong>Bolletta errata</strong> (es. troppe fisse): le selezioni in eccesso vengono annullate (0 pt). Le corrette
          restano valide. La bolletta è valida economicamente.
        </li>
        <li>
          <strong>Errore in buona fede:</strong> Over 1.5 → vale solo se la partita finisce Over 2.5. Economicamente fa fede
          la bolletta reale.
        </li>
        <li>
          <strong>Scadenza:</strong> bolletta da pubblicare <strong>{regole.minuti_pubblicazione_prima_partita} minuti prima</strong>{" "}
          dell&apos;inizio della prima partita. In ritardo → 0 pt e bolletta nulla economicamente.
        </li>
        <li>
          <strong>Partite rinviate:</strong> per i punti si aspetta il recupero. Economicamente, se il sito chiude la giocata,
          la vincita si divide a metà.
        </li>
      </ul>
    </Card>
  );
}
