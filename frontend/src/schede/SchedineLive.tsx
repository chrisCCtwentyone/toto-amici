import { useEffect, useState } from "react";
import { Card, PallinoLive,SelettoreGiocatore, SelettoreGiornata, StatoVuoto } from "../componenti";
import { useSnapshot } from "../lib/DatiContext";
import { riepilogoVisualizzato } from "../lib/esiti";
import { etichettaGiornata, formattaQuota } from "../lib/format";
import { useLive } from "../lib/useLive";
import { giornateDisponibili, mappaPartite } from "../lib/selettori";
import CartaPronostico from "./live-confronto/CartaPronostico";
import Riepilogo from "./live-confronto/Riepilogo";
import { staGiocando } from "./live-confronto/dati";

/** Aspetta che la giornata smetta di cambiare: scorrendo con le frecce non parte una chiamata a Football-Data per ogni giornata. */
function useStabile<T>(valore: T, ms: number): T {
  const [stabile, setStabile] = useState(valore);
  useEffect(() => {
    const t = setTimeout(() => setStabile(valore), ms);
    return () => clearTimeout(t);
  }, [valore, ms]);
  return stabile;
}

export default function SchedineLive() {
  const s = useSnapshot();
  const giornate = giornateDisponibili(s);
  const [giornata, setGiornata] = useState<number | null>(s.giornata_corrente ?? giornate.at(-1) ?? null);
  const [giocatore, setGiocatore] = useState<string | null>(s.giocatori[0] ?? null);

  const giornataLive = useStabile(giornata, 600);
  const live = useLive(giornataLive);
  const partite = mappaPartite(s);

  // uguaglianza di interi, mai per sottostringa (bug di Sessione 13)
  const schedina = s.schedine.find((x) => x.giornata === giornata && x.giocatore === giocatore);
  const liveDi = (id: number) => live.partite.get(id);
  // "LIVE" se una partita QUALSIASI della giornata e' in corso (non solo quelle di questo giocatore)
  const inDiretta = [...live.partite.values()].some((p) => staGiocando(p)) && giornataLive === giornata;

  if (giornate.length === 0) {
    return (
      <Card titolo="Schedine" evidenza="Live" bandiera="accento">
        <StatoVuoto titolo="Nessuna giocata registrata">Appena un giocatore carica la schedina la troverai qui.</StatoVuoto>
      </Card>
    );
  }

  return (
    <div className="grid gap-4 pb-6">
      <Card
        titolo="Schedine"
        evidenza="Live"
        bandiera="live"
        azione={inDiretta ? <PallinoLive etichetta="LIVE" /> : undefined}
      >
        <div className="grid gap-3">
          <SelettoreGiornata giornate={giornate} valore={giornata} onChange={setGiornata} />
          <SelettoreGiocatore giocatori={s.giocatori} valore={giocatore} onChange={setGiocatore} />
        </div>
      </Card>

      {live.nonDisponibile && (
        <p role="status" className="m-0 border-l-[6px] border-l-avviso-bordo bg-avviso-fondo px-3 py-2 text-sm text-ink">
          Risultati in diretta non disponibili al momento: vedi gli esiti dell'ultimo aggiornamento. Riproviamo da soli.
        </p>
      )}

      {!schedina ? (
        <StatoVuoto titolo="Schedina non trovata">
          {giocatore ?? "Questo giocatore"} non ha una schedina per la {etichettaGiornata(giornata ?? 0)}.
        </StatoVuoto>
      ) : (
        <>
          <Riepilogo
            riepilogo={riepilogoVisualizzato(schedina.righe, liveDi)}
            vincita={schedina.vincita_potenziale}
          />
          {live.caricamento && live.partite.size === 0 && !live.nonDisponibile && (
            <p role="status" className="m-0 text-sm text-ink-2">Carico i risultati in diretta…</p>
          )}
          {/* la key riparte le entrate a ogni cambio di giornata o giocatore */}
          <ol key={`${schedina.giornata}-${schedina.giocatore}`} className="m-0 grid list-none gap-3 p-0">
            {schedina.righe.map((riga, i) => (
              <CartaPronostico
                key={`${riga.partita_id}-${riga.pronostico}-${i}`}
                riga={riga}
                partita={partite.get(riga.partita_id)}
                live={liveDi(riga.partita_id)}
                soglia={s.regole.soglia_quota_doppia}
                indice={i}
              />
            ))}
          </ol>
          <p className="m-0 text-sm text-ink-2">
            * quota ≥ {formattaQuota(s.regole.soglia_quota_doppia)}: punti raddoppiati. Le carte sono in ordine di calcio d'inizio.
          </p>
        </>
      )}
    </div>
  );
}
