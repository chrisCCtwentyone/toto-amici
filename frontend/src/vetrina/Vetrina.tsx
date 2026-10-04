/**
 * Vetrina dei componenti condivisi con dati veri. SOLO sviluppo: apri http://localhost:5173/?vetrina
 * (in produzione non esiste: main.tsx la importa solo se import.meta.env.DEV).
 * Copia da qui l'uso corretto di ogni componente.
 */
import { useState } from "react";
import { DatiProvider, useDati, useSnapshot } from "../lib/DatiContext";
import { frazioneBarra } from "../lib/barre";
import { formattaConSegno, formattaEuro, formattaIntero, formattaOrdinale } from "../lib/format";
import { giornateDisponibili } from "../lib/selettori";
import {
  BarraObliqua, Card, NumeroAnimato, PallinoLive, PillolaEsito, Pulsante, Scheletro,
  SelettoreGiocatore, SelettoreGiornata, StatoVuoto, Ticker, TitoloSezione,
} from "../componenti";
import type { Esito } from "../tipi/snapshot";

const ESITI: Esito[] = ["vinta", "persa", "in_corso", "rinviata", "da_verificare", "annullata", "da_giocare"];

function Corpo() {
  const s = useSnapshot();
  const giornate = giornateDisponibili(s);
  const [g, setG] = useState<number | null>(s.giornata_corrente);
  const [p, setP] = useState<string | null>(s.giocatori[0] ?? null);
  const righe = s.classifica.giocatori;
  const max = Math.max(...righe.map((r) => r.punti_totali));
  const min = Math.min(...righe.map((r) => r.punti_totali));

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4">
      <TitoloSezione evidenza="componenti">Vetrina</TitoloSezione>

      <Card titolo="Barra obliqua" evidenza="classifica" bandiera="accento" azione={<PallinoLive etichetta="LIVE" />}>
        <ol className="m-0 list-none p-0">
          {righe.slice(0, 6).map((r, i) => (
            <BarraObliqua
              key={r.nome}
              indice={i}
              posizione={r.posizione}
              etichetta={r.nome}
              frazione={frazioneBarra(r.punti_totali, min, max)}
              evidenza={r.posizione === 1}
              dettaglio={
                r.punti_ultima_giornata !== null && (
                  <span className="font-display text-[0.95rem] font-extrabold tracking-wide text-su-barra opacity-80">
                    {formattaConSegno(r.punti_ultima_giornata)}
                  </span>
                )
              }
              valore={<NumeroAnimato valore={r.punti_totali} />}
            />
          ))}
        </ol>
      </Card>

      <Card titolo="Pillole esito" livello={3}>
        <div className="flex flex-wrap gap-2">{ESITI.map((e) => <PillolaEsito key={e} esito={e} />)}</div>
      </Card>

      <Card titolo="Selettori" livello={3} bandiera="marchio">
        <div className="space-y-3">
          <SelettoreGiornata giornate={giornate} valore={g} onChange={setG} />
          <SelettoreGiocatore giocatori={s.giocatori} valore={p} onChange={setP} />
          <p className="text-ink-2">Scelti: giornata {g}, giocatore {p}</p>
        </div>
      </Card>

      <Card titolo="Numeri animati" livello={3} bandiera="oro">
        <p className="font-display text-5xl font-extrabold text-accento-testo">
          <NumeroAnimato valore={s.cassa.saldo} formato={formattaEuro} />
        </p>
        <p className="text-ink-2">Posizione: {formattaOrdinale(1)} · Punti: {formattaIntero(1674)}</p>
      </Card>

      <Card titolo="Pulsanti e stati" livello={3}>
        <div className="flex flex-wrap items-center gap-3">
          <Pulsante variante="primario">Primario</Pulsante>
          <Pulsante>Secondario</Pulsante>
          <Pulsante disabled>Disabilitato</Pulsante>
          <PallinoLive /> <PallinoLive tono="oro" /> <PallinoLive tono="vinta" lampeggia={false} />
        </div>
        <Scheletro righe={3} className="mt-3" />
        <div className="mt-3"><StatoVuoto titolo="Nessuna schedina">Per questa giornata non ci sono ancora schedine.</StatoVuoto></div>
      </Card>

      <Ticker voci={["Fondo cassa " + formattaEuro(s.cassa.saldo), "Giornata " + s.giornata_corrente, "Toto-Amici"]} />
    </div>
  );
}

function Attesa() {
  const { snapshot } = useDati();
  return snapshot ? <Corpo /> : <Scheletro righe={4} className="p-4" />;
}

export default function Vetrina() {
  return (
    <DatiProvider>
      <Attesa />
    </DatiProvider>
  );
}
