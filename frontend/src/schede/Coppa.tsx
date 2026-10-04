import { Card } from "../componenti";
import { useSnapshot } from "../lib/DatiContext";
import { formattaIntero } from "../lib/format";
import { Accoppiamenti, ComeFunziona } from "./statistiche-coppa/Riquadri";
import Tabellone from "./statistiche-coppa/Tabellone";

/** Scheda "Coppa" (§9): il tabellone e i vincitori arrivano gia' decisi dallo snapshot; qui solo presentazione. */
export default function Coppa() {
  const { coppa } = useSnapshot();

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 pb-4">
      <Card
        titolo="Coppa"
        evidenza="Toto-Amici"
        bandiera="oro"
        azione={
          <span className={`obliquo px-3 ${coppa.definitiva ? "bg-oro text-su-oro" : "bg-superficie-2 text-ink"}`}>
            <span className="contro-obliquo block font-display text-base font-extrabold uppercase leading-7 tracking-wider">
              {coppa.definitiva ? "Definitivo" : "Provvisorio"}
            </span>
          </span>
        }
      >
        <p className="mb-4 text-sm text-ink-2">
          {coppa.definitiva
            ? `Tabellone definitivo, fatto con la classifica dopo la ${coppa.ultima_giornata_tabellone}ª giornata.`
            : `Tabellone provvisorio: gli accoppiamenti di oggi. Diventa definitivo con la classifica dopo la ${coppa.ultima_giornata_tabellone}ª giornata.`}
        </p>

        {!coppa.tabellone_disponibile && (
          <p role="status" className="mb-4 border-l-[6px] border-l-avviso-bordo bg-avviso-fondo px-4 py-3 text-ink">
            Il tabellone è pensato per 16 partecipanti, in classifica ora ce ne sono {formattaIntero(coppa.partecipanti)}: gli accoppiamenti
            compariranno quando i conti tornano.
          </p>
        )}

        <p className="mb-2 text-xs text-ink-2 lg:hidden">Scorri di lato per vedere tutti i turni →</p>
        <Tabellone turni={coppa.turni} campione={coppa.campione} />

        <p className="mt-4 text-sm text-ink-2">
          {coppa.definitiva
            ? "Chi passa il turno compare solo quando tutte le partite della giornata sono finite: fino ad allora vedi i punti che maturano."
            : "Accoppiamenti aggiornati alla classifica di oggi: dai un'occhiata a chi ti toccherebbe."}
        </p>
      </Card>

      <div className="grid items-start gap-4 md:grid-cols-2">
        <ComeFunziona coppa={coppa} />
        <Accoppiamenti coppa={coppa} />
      </div>
    </div>
  );
}
