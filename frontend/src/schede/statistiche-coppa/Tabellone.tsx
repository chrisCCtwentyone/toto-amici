import { motion } from "motion/react";
import type { SfidaCoppa, TurnoCoppa, VoceCoppa } from "../../tipi/snapshot";
import { formattaIntero } from "../../lib/format";
import { ENTRATA } from "../../lib/movimento";
import { etichettaDaDefinire } from "./logica";

const TITOLO_TURNO: Record<TurnoCoppa["turno"], string> = {
  ottavi: "Ottavi",
  quarti: "Quarti",
  semifinali: "Semifinali",
  finale: "Finale",
};

/** Una riga della sfida: il significato (passa / eliminato) sta nel testo e nel glifo, non solo nel colore. */
function Giocatore({ voce, punti, esito, etichetta }: { voce: VoceCoppa | null; punti: number | null; esito: "passa" | "fuori" | null; etichetta: string }) {
  if (voce === null) {
    return <div className="flex h-9 items-center px-3 text-sm italic text-ink-2">{etichetta}</div>;
  }
  return (
    <div
      className={`flex h-9 items-center gap-2 border-l-4 px-2 ${
        esito === "passa" ? "border-l-vinta bg-vinta/15" : "border-l-transparent"
      } ${esito === "fuori" ? "text-ink-2" : "text-ink"}`}
    >
      <span className="tabulare w-7 shrink-0 text-xs font-semibold text-ink-2">{voce.posizione}°</span>
      <span className="min-w-0 flex-1 truncate font-display text-lg font-extrabold uppercase leading-none tracking-wide" title={voce.nome}>
        {voce.nome}
      </span>
      {esito === "passa" && (
        <>
          <span aria-hidden="true" className="text-sm font-bold text-vinta">✓</span>
          <span className="solo-lettori">passa il turno</span>
        </>
      )}
      {esito === "fuori" && <span className="solo-lettori">eliminato</span>}
      {punti !== null && (
        <span className="tabulare shrink-0 text-sm font-semibold">
          {formattaIntero(punti)}
          <span className="ml-0.5 text-xs font-normal text-ink-2">pt</span>
        </span>
      )}
    </div>
  );
}

function Sfida({ sfida, indiceTurno, indiceSfida }: { sfida: SfidaCoppa; indiceTurno: number; indiceSfida: number }) {
  const esito = (j: 0 | 1) => (sfida.vincente === null ? null : sfida.vincente === j ? "passa" : "fuori");
  return (
    <li className="m-0 list-none overflow-hidden rounded-diretta border border-linea bg-superficie-2">
      <Giocatore voce={sfida.giocatori[0]} punti={sfida.punti[0]} esito={esito(0)} etichetta={etichettaDaDefinire(indiceTurno, indiceSfida, 0)} />
      <div aria-hidden="true" className="border-t border-linea" />
      <Giocatore voce={sfida.giocatori[1]} punti={sfida.punti[1]} esito={esito(1)} etichetta={etichettaDaDefinire(indiceTurno, indiceSfida, 1)} />
    </li>
  );
}

/**
 * Tabellone §9: quattro colonne affiancate (8, 4, 2, 1 sfide). Le colonne hanno la stessa altezza e le sfide
 * sono centrate con justify-around: ogni sfida cade a meta' fra le due da cui proviene, senza calcoli.
 * Su telefono scorre di lato nel SUO contenitore (la pagina no).
 */
export default function Tabellone({ turni, campione }: { turni: readonly TurnoCoppa[]; campione: VoceCoppa | null }) {
  return (
    <div
      role="region"
      aria-label="Tabellone della Coppa, scorre di lato"
      tabIndex={0}
      className="scorri-nascosto -mx-4 scroll-pl-4 snap-x overflow-x-auto px-4 pb-2"
    >
      <div className="flex min-w-max gap-4">
        {turni.map((t, i) => (
          <motion.section
            key={t.turno}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...ENTRATA, duration: 0.4, delay: i * 0.06 }}
            aria-labelledby={`coppa-turno-${t.turno}`}
            className="flex w-[13rem] snap-start flex-col sm:w-[14.5rem]"
          >
            <h3 id={`coppa-turno-${t.turno}`} className="titolo-diretta text-center text-xl text-ink">
              {TITOLO_TURNO[t.turno]}
            </h3>
            <p className="mb-3 mt-0.5 text-center text-xs text-ink-2">{t.giornata}ª giornata</p>
            <ul className="m-0 flex flex-1 list-none flex-col justify-around gap-3 p-0">
              {t.sfide.map((s, k) => <Sfida key={k} sfida={s} indiceTurno={i} indiceSfida={k} />)}
            </ul>
            {i === turni.length - 1 && (
              <div className="mt-4 flex flex-col items-center text-center" aria-live="polite">
                <span aria-hidden="true" className="text-4xl leading-none">🏆</span>
                {campione ? (
                  <>
                    <span className="mt-1 text-xs font-semibold uppercase tracking-wider text-ink-2">Campione</span>
                    <span className="obliquo mt-1 bg-oro px-4">
                      <span className="contro-obliquo block font-display text-2xl font-extrabold uppercase leading-9 tracking-wide text-su-oro">
                        {campione.nome}
                      </span>
                    </span>
                  </>
                ) : (
                  <span className="mt-1 text-xs text-ink-2">Il campione sarà qui</span>
                )}
              </div>
            )}
          </motion.section>
        ))}
      </div>
    </div>
  );
}
