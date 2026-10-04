import type { ReactNode } from "react";
import { motion } from "motion/react";
import { Card, NumeroAnimato, StatoVuoto } from "../../componenti";
import type { Cassa } from "../../tipi/snapshot";
import { formattaEuro, formattaEuroIntero, formattaFrazione } from "../../lib/format";
import { EASE_USCITA } from "../../lib/movimento";
import GraficoVersamenti from "./GraficoVersamenti";
import MovimentiCassa from "./MovimentiCassa";

function Dato({ etichetta, children }: { etichetta: string; children: ReactNode }) {
  return (
    <div className="min-w-0 border-l-[3px] border-l-linea pl-3">
      <dt className="text-xs font-semibold uppercase tracking-wider text-ink-2">{etichetta}</dt>
      <dd className="m-0 font-display text-2xl font-extrabold leading-tight text-ink">{children}</dd>
    </div>
  );
}

export default function FondoCassa({ cassa }: { cassa: Cassa }) {
  const percento = Math.round(cassa.completamento * 100);
  return (
    <Card titolo="Fondo" evidenza="Cassa" bandiera="oro">
      <p className="m-0 text-sm text-ink-2">Montepremi attuale</p>
      <p className="m-0 font-display text-[3.25rem] font-extrabold leading-none text-ink">
        <NumeroAnimato valore={cassa.saldo} formato={formattaEuro} />
      </p>

      <dl className="mb-0 mt-4 grid grid-cols-2 gap-3">
        <Dato etichetta="Obiettivo">{formattaEuroIntero(cassa.obiettivo)}</Dato>
        <Dato etichetta="Completamento">{formattaFrazione(cassa.completamento, 1)}</Dato>
      </dl>

      {/* barra verso l'obiettivo: parallelogramma come le barre della classifica, riempita da sinistra */}
      <div
        role="progressbar"
        aria-label="Avanzamento verso l'obiettivo della Cassa"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percento}
        aria-valuetext={`${formattaFrazione(cassa.completamento, 1)} dell'obiettivo`}
        className="obliquo relative mt-4 h-5 overflow-hidden bg-barra-traccia"
      >
        <motion.div
          className="absolute inset-y-0 left-0 origin-left bg-oro"
          style={{ width: `${cassa.completamento * 100}%` }}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.9, ease: EASE_USCITA, delay: 0.2 }}
        />
      </div>
      <p className="tabulare mb-0 mt-1.5 text-sm text-ink-2">
        {formattaEuro(cassa.saldo)} / {formattaEuroIntero(cassa.obiettivo)}
      </p>

      {cassa.obiettivo_raggiunto && (
        <p className="mb-0 mt-3 border-l-[6px] border-l-oro bg-avviso-fondo px-3 py-2 font-semibold text-ink">
          <span aria-hidden="true">★ </span>Obiettivo raggiunto! I premi sono interamente coperti.
        </p>
      )}

      <div className="mt-5 space-y-4 border-t-2 border-dashed border-linea pt-4">
        {cassa.movimenti.length === 0 && cassa.versamenti_per_giornata.length === 0 ? (
          <StatoVuoto titolo="Nessun movimento registrato">
            Quando una schedina verrà chiusa, il versamento comparirà qui.
          </StatoVuoto>
        ) : (
          <>
            <GraficoVersamenti dati={cassa.versamenti_per_giornata} />
            <MovimentiCassa movimenti={cassa.movimenti} />
          </>
        )}
      </div>
    </Card>
  );
}
