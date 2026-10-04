import { useSnapshot } from "../lib/DatiContext";
import Bolletta from "./classifica-cassa-regolamento/regolamento/Bolletta";
import Punteggi from "./classifica-cassa-regolamento/regolamento/Punteggi";
import RegoleErrori from "./classifica-cassa-regolamento/regolamento/RegoleErrori";
import CassaPremi from "./classifica-cassa-regolamento/regolamento/CassaPremi";
import { TitoloSezione } from "../componenti";

/**
 * Scheda "Regolamento": i testi sono del sito (copia statica), i numeri vengono da §10 `regole`
 * (costi, punti, soglia, premi): cosi' non esistono tre copie da tenere allineate.
 */
export default function Regolamento() {
  const { regole } = useSnapshot();
  return (
    <div className="pb-4">
      <TitoloSezione evidenza="ufficiale">Regolamento</TitoloSezione>
      <div className="grid items-start gap-4 md:grid-cols-2">
        <div className="grid gap-4">
          <Bolletta regole={regole} />
          <Punteggi regole={regole} />
        </div>
        <div className="grid gap-4">
          <RegoleErrori regole={regole} />
          <CassaPremi regole={regole} />
        </div>
      </div>
    </div>
  );
}
