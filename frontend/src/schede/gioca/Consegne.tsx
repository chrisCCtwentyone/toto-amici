import { useEffect, useState } from "react";
import { Card, Pulsante, Scheletro, StatoVuoto } from "../../componenti";
import { caricaConsegne, type RispostaConsegne } from "../../lib/api";
import { formattaData, formattaEuro, formattaOra } from "../../lib/format";
import { etichettaPronostico, type GiornataAperta } from "../../../worker/schedina";
import { Stella } from "./Riepilogo";

interface Props {
  aperta: GiornataAperta;
  /** cambia dopo un invio riuscito: l'elenco si ricarica */
  versione: number;
  chiusa: boolean;
  /** il server dice che e' scaduta anche se l'orologio del telefono no */
  onChiusa: () => void;
}

/** «Chi ha consegnato»: i nomi finche' la giornata e' aperta, tutte le schedine dopo la scadenza. */
export default function Consegne({ aperta, versione, chiusa, onChiusa }: Props) {
  const [dati, setDati] = useState<RispostaConsegne | null>(null);
  const [errore, setErrore] = useState(false);
  const [tentativo, setTentativo] = useState(0);

  useEffect(() => {
    const ac = new AbortController();
    caricaConsegne(aperta.giornata, ac.signal)
      .then((r) => {
        setDati(r);
        setErrore(false);
        if (r.chiusa) onChiusa();
      })
      .catch(() => {
        if (!ac.signal.aborted) setErrore(true);
      });
    return () => ac.abort();
  }, [aperta.giornata, versione, chiusa, tentativo, onChiusa]);

  if (errore && !dati) {
    return (
      <Card titolo="Chi ha" evidenza="consegnato">
        <p className="mb-3 text-ink-2">Non riesco a caricare l'elenco in questo momento.</p>
        <Pulsante onClick={() => setTentativo((t) => t + 1)}>Riprova</Pulsante>
      </Card>
    );
  }
  if (!dati) {
    return (
      <Card titolo="Chi ha" evidenza="consegnato">
        <Scheletro righe={2} />
      </Card>
    );
  }

  if (!dati.chiusa) {
    const hanno = new Set(dati.consegnate.map((c) => c.giocatore));
    const mancano = aperta.giocatori.filter((g) => !hanno.has(g));
    return (
      <Card titolo="Chi ha" evidenza="consegnato">
        <p className="mb-2 text-ink-2">
          {dati.consegnate.length} su {aperta.giocatori.length}. Le schedine restano segrete fino alla scadenza.
        </p>
        {dati.consegnate.length > 0 ? (
          <ul className="divide-y divide-linea border-y border-linea">
            {dati.consegnate.map((c) => (
              <li key={c.giocatore} className="flex justify-between gap-3 py-2">
                <span className="font-bold"><span aria-hidden="true" className="text-vinta">✓ </span>{c.giocatore}</span>
                <span className="tabulare text-ink-2">{formattaOra(c.consegnata_il)} del {formattaData(c.consegnata_il)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <StatoVuoto titolo="Ancora nessuna schedina">Sarai il primo?</StatoVuoto>
        )}
        {mancano.length > 0 && dati.consegnate.length > 0 && <p className="mt-2 text-ink-2">Mancano: {mancano.join(", ")}.</p>}
      </Card>
    );
  }

  const schedine = [...dati.schedine].sort((a, b) => a.giocatore.localeCompare(b.giocatore, "it"));
  return (
    <Card titolo="Schedine" evidenza={`Giornata ${dati.giornata}`}>
      {schedine.length === 0 ? (
        <StatoVuoto titolo="Nessuna schedina consegnata">Per questa giornata nessuno ha usato il sito.</StatoVuoto>
      ) : (
        <ul className="grid gap-2">
          {schedine.map((s) => (
            <li key={s.giocatore}>
              <details className="rounded-diretta bg-superficie-2 px-3">
                <summary className="flex min-h-11 cursor-pointer items-center justify-between gap-3 font-display text-lg font-extrabold uppercase tracking-wide">
                  <span>{s.giocatore}</span>
                  <span className="tabulare text-sm font-semibold normal-case text-ink-2">{formattaEuro(s.vincita)}</span>
                </summary>
                <ol className="divide-y divide-linea pb-2">
                  {s.righe.map((r) => (
                    <li key={r.partita_id} className="flex items-baseline justify-between gap-3 py-1.5">
                      <span>{r.partita}</span>
                      <span className="flex-none font-bold">
                        {etichettaPronostico(r.pronostico)}
                        {r.quota_alta && <> <Stella /></>}
                      </span>
                    </li>
                  ))}
                </ol>
              </details>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
