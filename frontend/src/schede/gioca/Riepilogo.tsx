import { useEffect, useRef, useState } from "react";
import { Card, Pulsante } from "../../componenti";
import { ErroreInvio } from "../../lib/api";
import { formattaEuro } from "../../lib/format";
import { conteggio, etichettaPronostico, LIMITI, TIPI, type GiornataAperta, type Schedina } from "../../../worker/schedina";

export function Stella() {
  return (
    <>
      <span aria-hidden="true" className="text-oro-testo">★</span>
      <span className="solo-lettori"> quota 3,50 o più</span>
    </>
  );
}

interface Props {
  aperta: GiornataAperta;
  schedina: Schedina;
  errori: string[];
  inviando: boolean;
  erroreInvio: ErroreInvio | null;
  onIndietro: () => void;
  onInvia: () => void;
}

/** Ultimo controllo prima dell'invio: si vede la schedina com'è, con gli errori. Si invia solo spuntando la casella. */
export default function Riepilogo({ aperta, schedina, errori, inviando, erroreInvio, onIndietro, onInvia }: Props) {
  const [controllata, setControllata] = useState(false);
  const titolo = useRef<HTMLHeadingElement>(null);
  useEffect(() => titolo.current?.focus(), []);
  const n = conteggio(schedina.righe);

  return (
    <Card bandiera="accento" titolo="Controlla la" evidenza="schedina">
      <h3 ref={titolo} tabIndex={-1} className="solo-lettori">Riepilogo della tua schedina</h3>
      <p className="mb-3 text-ink-2">
        {schedina.giocatore || "Nessun nome scelto"} · Giornata {aperta.giornata}
      </p>

      <ul className="mb-3 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {TIPI.map((t) => {
          const giusto = n[t] === LIMITI[t];
          return (
            <li key={t} className={`rounded-diretta border-2 px-2 py-1 ${giusto ? "border-vinta text-vinta" : "border-persa text-persa"}`}>
              <span aria-hidden="true">{giusto ? "✓" : "✕"} </span>
              {t}: <span className="tabulare font-bold">{n[t]}/{LIMITI[t]}</span>
              <span className="solo-lettori">{giusto ? ", giusto" : ", da correggere"}</span>
            </li>
          );
        })}
      </ul>

      <ol className="divide-y divide-linea border-y border-linea">
        {aperta.partite.map((p) => {
          const r = schedina.righe.find((x) => x.partita_id === p.id);
          return (
            <li key={p.id} className="flex items-baseline justify-between gap-3 py-2">
              <span>{p.casa} – {p.ospite}</span>
              <span className="flex-none text-right font-bold">
                {r ? etichettaPronostico(r.pronostico) : <span className="text-persa">Manca</span>}
                {r?.quota_alta && <> <Stella /></>}
              </span>
            </li>
          );
        })}
      </ol>

      <p className="mt-3">
        Vincita potenziale:{" "}
        <strong className="tabulare">{Number.isFinite(schedina.vincita) ? formattaEuro(schedina.vincita) : "non scritta"}</strong>
      </p>

      {errori.length > 0 && (
        <div className="mt-3 border-l-[6px] border-l-persa bg-superficie-2 px-4 py-3">
          <p className="font-bold text-persa">Prima di inviare, sistema questo:</p>
          <ul className="list-disc pl-5 text-ink">
            {errori.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {erroreInvio && (
        <div role="alert" className="mt-3 border-l-[6px] border-l-persa bg-superficie-2 px-4 py-3">
          <p className="font-bold text-persa">{erroreInvio.message}</p>
          {erroreInvio.errori.length > 0 && (
            <ul className="list-disc pl-5 text-ink">
              {erroreInvio.errori.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <label className="mt-3 flex min-h-11 cursor-pointer items-center gap-3 text-ink">
        <input type="checkbox" checked={controllata} onChange={(e) => setControllata(e.target.checked)} className="h-6 w-6 flex-none cursor-pointer accent-marchio" />
        Ho controllato la mia schedina
      </label>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <Pulsante variante="primario" disabled={errori.length > 0 || !controllata || inviando} onClick={onInvia}>
          {inviando ? "Invio in corso…" : "Conferma e invia"}
        </Pulsante>
        <Pulsante onClick={onIndietro} disabled={inviando}>
          Torna a modificare
        </Pulsante>
      </div>
    </Card>
  );
}
