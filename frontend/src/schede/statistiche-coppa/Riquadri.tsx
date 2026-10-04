import { Card } from "../../componenti";
import type { Coppa } from "../../tipi/snapshot";

const ord = (n: number) => `${n}ª`;
const LISTA = "m-0 grid list-disc gap-2 pl-5 marker:text-ink-2";

/** I due riquadri esplicativi di app.py. Le giornate vengono dallo snapshot, il resto e' testo del sito. */
export function ComeFunziona({ coppa }: { coppa: Coppa }) {
  const p = coppa.prima_giornata;
  return (
    <Card titolo="Come" evidenza="funziona" livello={3} bandiera="accento">
      <ul className={LISTA}>
        <li><strong>Partecipano tutti e 16</strong> i giocatori: nessuno resta fuori.</li>
        <li>
          Si gioca sulle <strong>ultime 4 giornate</strong> di campionato: ottavi alla {ord(p)}, quarti alla {ord(p + 1)}, semifinali alla{" "}
          {ord(p + 2)} e finale alla {ord(p + 3)}.
        </li>
        <li>Ogni turno è uno <strong>scontro diretto su una giornata</strong>: passa chi fa più punti in quella giornata.</li>
        <li>La Coppa è <strong>parallela al campionato</strong>: gli stessi punti valgono per entrambi, non serve giocare una schedina in più.</li>
      </ul>
    </Card>
  );
}

export function Accoppiamenti({ coppa }: { coppa: Coppa }) {
  return (
    <Card titolo="Gli" evidenza="accoppiamenti" livello={3} bandiera="marchio">
      <ul className={LISTA}>
        <li>Negli ottavi il <strong>1° in classifica sfida il 16°</strong>, il 2° il 15°, e così via.</li>
        <li>
          Il tabellone segue la classifica e cambia a ogni giornata <strong>fino alla {ord(coppa.ultima_giornata_tabellone)}</strong>: da lì in poi è
          definitivo.
        </li>
        <li>I primi due possono incontrarsi <strong>solo in finale</strong>.</li>
        <li>In caso di <strong>parità di punti</strong> in una sfida, passa chi era più in alto nella classifica del tabellone.</li>
        <li>Il regolamento definitivo verrà confermato dal creatore del torneo prima dell&apos;inizio.</li>
      </ul>
    </Card>
  );
}
