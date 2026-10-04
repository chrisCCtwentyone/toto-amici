import { useEffect, useState } from "react";
import { Card, StatoVuoto } from "../../componenti";
import type { UltimaSchedinaVinta } from "../../tipi/snapshot";
import { etichettaGiornata, formattaData, formattaOra } from "../../lib/format";
import { scomponiDurata } from "./logica";

const UNITA = [
  ["settimana", "settimane"],
  ["giorno", "giorni"],
  ["ora", "ore"],
  ["minuto", "minuti"],
  ["secondo", "secondi"],
] as const;

/** Un secondo di lancetta: e' un'informazione, non un'animazione (per questo i numeri non si animano). */
function useAdesso(): number {
  const [adesso, setAdesso] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setAdesso(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  return adesso;
}

function Conteggio({ inizio }: { inizio: number }) {
  const d = scomponiDurata((useAdesso() - inizio) / 1000);
  const valori = [d.settimane, d.giorni, d.ore, d.minuti, d.secondi];
  // gli screen reader leggono una frase che cambia una volta al minuto, non 60 aggiornamenti
  const frase = [
    d.settimane && `${d.settimane} ${d.settimane === 1 ? "settimana" : "settimane"}`,
    d.giorni && `${d.giorni} ${d.giorni === 1 ? "giorno" : "giorni"}`,
    `${d.ore} ${d.ore === 1 ? "ora" : "ore"}`,
    `${d.minuti} ${d.minuti === 1 ? "minuto" : "minuti"}`,
  ].filter(Boolean).join(", ");

  return (
    <div role="timer" aria-label={`Tempo passato dall'ultima schedina vinta: ${frase}`}>
      <div className="grid grid-cols-5 gap-1.5 sm:gap-3" aria-hidden="true">
        {valori.map((v, i) => (
          <div key={UNITA[i]![1]} className="obliquo border-b-4 border-b-accento bg-superficie-2 py-2">
            <div className="contro-obliquo text-center">
              <div className="tabulare font-display text-[2rem] font-extrabold leading-none text-ink sm:text-5xl">
                {i < 2 ? v : String(v).padStart(2, "0")}
              </div>
              <div className="mt-1 text-[0.68rem] leading-tight text-ink-2 sm:text-sm">{UNITA[i]![v === 1 ? 0 : 1]}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** §8.1 — timer dall'ultima schedina vinta. L'istante di partenza e' dello snapshot; il conteggio scorre qui. */
export default function TimerUltimaVinta({ ultima }: { ultima: UltimaSchedinaVinta | null }) {
  const titolo = { titolo: "Tempo passato dall'ultima", evidenza: "schedina vinta" };

  if (ultima === null) {
    return (
      <Card {...titolo} livello={3} bandiera="live">
        <StatoVuoto titolo="Nessuna schedina vinta finora">Il timer partirà dalla prima.</StatoVuoto>
      </Card>
    );
  }

  const vincitori = ultima.vincitori.join(", ");
  const inizio = ultima.inizio_il === null ? null : Date.parse(ultima.inizio_il);

  return (
    <Card {...titolo} livello={3} bandiera="live">
      {inizio === null || Number.isNaN(inizio) ? (
        // meglio nessun timer che uno partito dal momento sbagliato
        <StatoVuoto titolo="Conteggio non disponibile">
          Ultima vinta: {vincitori} · {etichettaGiornata(ultima.giornata)}. Gli orari delle partite non sono raggiungibili al momento: riprova fra poco.
        </StatoVuoto>
      ) : (
        <>
          <Conteggio inizio={inizio} />
          <p className="mt-3 text-sm text-ink-2">
            Ultima vinta: <strong className="font-semibold text-ink">{vincitori}</strong> · {etichettaGiornata(ultima.giornata)}, chiusa il{" "}
            {formattaData(new Date(inizio))} verso le {formattaOra(new Date(inizio))} (fine dell'ultima partita). Si azzera alla prossima schedina vinta.
          </p>
        </>
      )}
    </Card>
  );
}
