import type { ReactNode } from "react";
import { Card } from "../../componenti";
import { formattaGiornoEsteso, formattaOra } from "../../lib/format";
import { DOPPIE, etichettaPronostico, FISSE, VARIABILI, VARIABILI_COMBO, type PartitaAperta } from "../../../worker/schedina";
import { impostaCombo, pronosticoDi, tocca, type Gruppo, type Scelta } from "./stato";

function Tasto({ attivo, onClick, children }: { attivo: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={attivo}
      onClick={onClick}
      className={`min-h-11 min-w-11 cursor-pointer rounded-diretta border-2 px-2 font-display text-lg font-extrabold uppercase tracking-wide transition-colors duration-150 ${
        attivo ? "border-ink bg-accento text-su-accento" : "border-linea bg-superficie-2 text-ink hover:border-accento-testo"
      }`}
    >
      {/* il segno ✓ dice «premuto» anche a chi non distingue i colori */}
      {attivo && <span aria-hidden="true">✓ </span>}
      {children}
    </button>
  );
}

function Gruppo({ nome, valori, scelto, colonne, onScegli }: { nome: string; valori: readonly string[]; scelto: string | null; colonne: string; onScegli: (v: string) => void }) {
  return (
    <div role="group" aria-label={nome}>
      <p className="mb-1 text-sm font-semibold text-ink-2" aria-hidden="true">{nome}</p>
      <div className={`grid gap-2 ${colonne}`}>
        {valori.map((v) => (
          <Tasto key={v} attivo={scelto === v} onClick={() => onScegli(v)}>
            {etichettaPronostico(v)}
          </Tasto>
        ))}
      </div>
    </div>
  );
}

/** Cosa manca, a parole: sotto il titolo della carta. */
function stato(c: Scelta): string {
  const p = pronosticoDi(c);
  if (p) return `Scelta: ${etichettaPronostico(p)}`;
  if (!c.combo) return "Da scegliere";
  if (!c.fissa && !c.extra) return "Combo: scegli un 1 X 2 e un Over, Under, Goal o NoGoal";
  return c.fissa ? "Combo: manca Over, Under, Goal o NoGoal" : "Combo: manca il 1 X 2";
}

/** Una partita: tasti dei pronostici, interruttore Combo, casella «quota ≥ 3,50». Solo presentazione. */
export default function CartaPartita({ partita, scelta, onChange }: { partita: PartitaAperta; scelta: Scelta; onChange: (s: Scelta) => void }) {
  const metti = (g: Gruppo) => (v: string) => onChange(tocca(scelta, g, v));
  const fatta = pronosticoDi(scelta) !== null;
  return (
    <Card
      as="li"
      livello={3}
      bandiera={fatta ? "accento" : undefined}
      titolo={`${partita.casa} – ${partita.ospite}`}
      azione={
        <button
          type="button"
          role="switch"
          aria-checked={scelta.combo}
          onClick={() => onChange(impostaCombo(scelta, !scelta.combo))}
          className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-diretta px-1 font-display text-lg font-extrabold uppercase tracking-wide text-ink"
        >
          Combo
          <span aria-hidden="true" className={`relative h-6 w-11 rounded-full border-2 transition-colors duration-150 ${scelta.combo ? "border-ink bg-accento" : "border-linea bg-superficie-2"}`}>
            <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-ink transition-[left] duration-150 ${scelta.combo ? "left-5" : "left-0.5"}`} />
          </span>
        </button>
      }
    >
      <p className="text-sm text-ink-2">
        {formattaGiornoEsteso(partita.inizio_il)}, ore {formattaOra(partita.inizio_il)}
      </p>
      <p className="mb-3 mt-1 font-semibold text-ink">{stato(scelta)}</p>
      <div className="grid gap-3">
        {scelta.combo ? (
          <>
            <Gruppo nome="Esito (1 X 2)" valori={FISSE} scelto={scelta.fissa} colonne="grid-cols-3" onScegli={metti("fissa")} />
            <Gruppo nome="In più" valori={VARIABILI_COMBO} scelto={scelta.extra} colonne="grid-cols-2" onScegli={metti("extra")} />
          </>
        ) : (
          <>
            <Gruppo nome="Fisse" valori={FISSE} scelto={scelta.semplice} colonne="grid-cols-3" onScegli={metti("semplice")} />
            <Gruppo nome="Doppie Chance" valori={DOPPIE} scelto={scelta.semplice} colonne="grid-cols-3" onScegli={metti("semplice")} />
            <Gruppo nome="Variabili" valori={VARIABILI} scelto={scelta.semplice} colonne="grid-cols-3" onScegli={metti("semplice")} />
          </>
        )}
      </div>
      <label className="mt-3 flex min-h-11 cursor-pointer items-center gap-3 border-t border-linea pt-2 text-ink">
        <input
          type="checkbox"
          checked={scelta.quota}
          onChange={(e) => onChange({ ...scelta, quota: e.target.checked })}
          className="h-6 w-6 flex-none cursor-pointer accent-marchio"
        />
        Quota ≥ 3,50
      </label>
    </Card>
  );
}
