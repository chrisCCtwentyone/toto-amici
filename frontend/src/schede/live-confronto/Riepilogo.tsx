import { NumeroAnimato } from "../../componenti";
import type { RiepilogoSchedina } from "../../tipi/snapshot";
import { formattaEuro, formattaIntero } from "../../lib/format";

const PRINCIPALI: { chiave: keyof RiepilogoSchedina; etichetta: string; glifo: string; bordo: string; testo: string }[] = [
  { chiave: "vinte", etichetta: "Vinte", glifo: "✓", bordo: "border-t-vinta", testo: "text-vinta" },
  { chiave: "perse", etichetta: "Perse", glifo: "✕", bordo: "border-t-persa", testo: "text-persa" },
  { chiave: "in_corso", etichetta: "In corso", glifo: "●", bordo: "border-t-in-corso", testo: "text-in-corso" },
];

// Gli altri esiti: compaiono solo se ce n'e' almeno uno (la scheda Live li conta tutti, §13 P9c).
const ALTRI: { chiave: keyof RiepilogoSchedina; singolare: string; plurale: string }[] = [
  { chiave: "da_giocare", singolare: "da giocare", plurale: "da giocare" },
  { chiave: "rinviate", singolare: "rinviata", plurale: "rinviate" },
  { chiave: "da_verificare", singolare: "da verificare", plurale: "da verificare" },
  { chiave: "annullate", singolare: "annullata", plurale: "annullate" },
];

export default function Riepilogo({ riepilogo, vincita }: { riepilogo: RiepilogoSchedina; vincita: number }) {
  const altri = ALTRI.filter((a) => riepilogo[a.chiave] > 0);
  return (
    <div className="grid gap-2">
      <dl className="m-0 grid grid-cols-3 gap-2">
        {PRINCIPALI.map((p) => (
          <div key={p.chiave} className={`border-t-4 bg-superficie-2 px-2 py-2 text-center ${p.bordo}`}>
            <dt className={`flex items-center justify-center gap-1.5 font-display text-base font-extrabold uppercase tracking-[0.08em] ${p.testo}`}>
              <span aria-hidden="true">{p.glifo}</span>
              {p.etichetta}
            </dt>
            <dd className="tabulare m-0 font-display text-[2.5rem] font-extrabold leading-none text-ink">
              {formattaIntero(riepilogo[p.chiave])}
            </dd>
          </div>
        ))}
      </dl>
      {altri.length > 0 && (
        <p className="m-0 text-sm text-ink-2">
          Altro:{" "}
          {altri.map((a, i) => (
            <span key={a.chiave}>
              {i > 0 && " · "}
              <strong className="tabulare text-ink">{riepilogo[a.chiave]}</strong>{" "}
              {riepilogo[a.chiave] === 1 ? a.singolare : a.plurale}
            </span>
          ))}
        </p>
      )}
      <p className="m-0 flex flex-wrap items-baseline justify-between gap-x-4 border-l-[6px] border-l-accento bg-superficie-2 px-3 py-2">
        <span className="font-display text-lg font-extrabold uppercase tracking-[0.08em] text-ink-2">Vincita potenziale</span>
        <span className="font-display text-[2.25rem] font-extrabold leading-none text-accento-testo">
          <NumeroAnimato valore={vincita} formato={formattaEuro} durata={0.6} />
        </span>
      </p>
    </div>
  );
}
