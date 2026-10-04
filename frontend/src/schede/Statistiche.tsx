import { StatoVuoto, TitoloSezione } from "../componenti";
import { useSnapshot } from "../lib/DatiContext";
import { Protagonisti, SquadreSerieA } from "./statistiche-coppa/Premi";
import PerUnSoffio from "./statistiche-coppa/PerUnSoffio";
import TabellaGiocatori from "./statistiche-coppa/TabellaGiocatori";
import TimerUltimaVinta from "./statistiche-coppa/TimerUltimaVinta";

/** Scheda "Statistiche" (§8): solo presentazione, tutti i numeri e i vincitori arrivano gia' calcolati dallo snapshot. */
export default function Statistiche() {
  const { statistiche: s } = useSnapshot();
  const vuota = s.giocatori.length === 0 && s.ritirati.length === 0 && s.ultima_schedina_vinta === null && s.per_un_soffio.length === 0;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 pb-4">
      <div>
        <TitoloSezione evidenza="& curiosità">Hall of Fame</TitoloSezione>
        <p className="-mt-1 text-sm text-ink-2">
          Analisi basata sulle partite già giocate (escluse le gare ancora in corso o non ancora disputate).
        </p>
      </div>

      {vuota ? (
        <StatoVuoto titolo="Nessuna giocata registrata">Le statistiche compariranno appena ci sarà qualche partita giocata.</StatoVuoto>
      ) : (
        <>
          <TimerUltimaVinta ultima={s.ultima_schedina_vinta} />
          <section>
            <TitoloSezione livello={3} evidenza="protagonisti">
              I
            </TitoloSezione>
            <Protagonisti premi={s.premi} />
          </section>
          <section>
            <TitoloSezione livello={3} evidenza="di Serie A">
              Le squadre
            </TitoloSezione>
            <SquadreSerieA premi={s.premi} />
          </section>
          <PerUnSoffio soffi={s.per_un_soffio} />
          <TabellaGiocatori giocatori={s.giocatori} ritirati={s.ritirati} />
        </>
      )}
    </div>
  );
}
