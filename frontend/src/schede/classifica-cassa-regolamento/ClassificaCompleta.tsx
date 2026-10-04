import { Card, BarraObliqua, NumeroAnimato, StatoVuoto } from "../../componenti";
import type { Classifica } from "../../tipi/snapshot";
import { frazioneBarra } from "../../lib/barre";
import Tendenza from "./Tendenza";
import StoricoGiornate from "./StoricoGiornate";

// scatto fra le barre: piu' corto del default (90 ms) perche' qui le righe sono 16, non 5
const SCATTO = 0.45;

export default function ClassificaCompleta({ classifica }: { classifica: Classifica }) {
  const { giocatori, ritirati } = classifica;
  if (giocatori.length === 0 && ritirati.length === 0) {
    return (
      <Card titolo="Classifica" evidenza="completa" bandiera="marchio">
        <StatoVuoto titolo="Classifica non ancora disponibile">Appena ci saranno dei punti la vedrai qui.</StatoVuoto>
      </Card>
    );
  }
  const punti = [...giocatori, ...ritirati].map((r) => r.punti_totali);
  const min = Math.min(...punti);
  const max = Math.max(...punti);
  const conTendenza = giocatori.some((r) => r.variazione_posizione !== null);
  // pari merito = stessa posizione esplicita (§5.2): lo si spiega solo se capita
  const conPari = new Set(giocatori.map((r) => r.posizione)).size < giocatori.length;

  return (
    <Card titolo="Classifica" evidenza="completa" bandiera="marchio">
      {(conTendenza || conPari) && (
        <p className="mb-3 text-sm text-ink-2">
          {conTendenza && "La freccia mostra quante posizioni ha guadagnato (▲) o perso (▼) rispetto alla giornata precedente. "}
          {conPari && "A pari punti e pronostici vinti la posizione è la stessa."}
        </p>
      )}
      <ol className="m-0 list-none p-0">
        {giocatori.map((r, i) => (
          <BarraObliqua
            key={r.nome}
            indice={i * SCATTO}
            posizione={r.posizione}
            etichetta={r.nome}
            frazione={frazioneBarra(r.punti_totali, min, max)}
            evidenza={r.posizione === 1}
            dettaglio={<Tendenza variazione={r.variazione_posizione} />}
            valore={<NumeroAnimato valore={r.punti_totali} />}
          />
        ))}
      </ol>

      {ritirati.length > 0 && (
        <>
          <h3 className="titolo-diretta mb-1 mt-4 border-t-2 border-dashed border-linea pt-3 text-xl text-ink-2">
            Ritirati
          </h3>
          <ol className="m-0 list-none p-0">
            {ritirati.map((r, i) => (
              <BarraObliqua
                key={r.nome}
                indice={(giocatori.length + i) * SCATTO}
                posizione={<span aria-hidden="true">—</span>}
                etichetta={
                  <>
                    {r.nome} <span className="text-sm font-normal opacity-80">· ritirato</span>
                  </>
                }
                frazione={frazioneBarra(r.punti_totali, min, max)}
                valore={<NumeroAnimato valore={r.punti_totali} />}
              />
            ))}
          </ol>
        </>
      )}

      <div className="mt-4">
        <StoricoGiornate classifica={classifica} />
      </div>
    </Card>
  );
}
