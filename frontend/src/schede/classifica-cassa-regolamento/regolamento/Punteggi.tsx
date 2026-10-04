import { Card } from "../../../componenti";
import type { Regole, Tipologia } from "../../../tipi/snapshot";
import { formattaDecimale, formattaIntero } from "../../../lib/format";

const RIGHE: { chiave: Tipologia; nome: string }[] = [
  { chiave: "combo", nome: "Combo" },
  { chiave: "doppie_chance", nome: "Doppie Chance" },
  { chiave: "variabili", nome: "Variabili (O/U, ecc.)" },
  { chiave: "fisse", nome: "Fisse" },
];

export default function Punteggi({ regole }: { regole: Regole }) {
  const soglia = formattaDecimale(regole.soglia_quota_doppia, 2);
  return (
    <Card titolo="2. Sistema" evidenza="punteggi" livello={3} bandiera="marchio">
      <table className="w-full border-collapse text-base">
        <thead>
          <tr className="font-display text-base font-extrabold uppercase tracking-wide text-ink-2">
            <th scope="col" className="py-1.5 pr-2 text-left">Tipo</th>
            <th scope="col" className="px-2 py-1.5 text-right">Punti base</th>
            <th scope="col" className="py-1.5 pl-2 text-right">Quota ≥ {soglia}</th>
          </tr>
        </thead>
        <tbody>
          {RIGHE.map((r) => (
            <tr key={r.chiave} className="border-t border-linea">
              <th scope="row" className="py-2 pr-2 text-left font-semibold">{r.nome}</th>
              <td className="tabulare px-2 py-2 text-right">{formattaIntero(regole.punti[r.chiave].base)}</td>
              <td className="tabulare py-2 pl-2 text-right font-bold text-accento-testo">
                {formattaIntero(regole.punti[r.chiave].quota_alta)}
              </td>
            </tr>
          ))}
          <tr className="border-t border-linea">
            <th scope="row" className="py-2 pr-2 text-left font-semibold">Bonus chiusura</th>
            <td className="tabulare px-2 py-2 text-right">+{formattaIntero(regole.bonus_chiusura)}</td>
            <td className="py-2 pl-2 text-right text-ink-2">
              <span aria-hidden="true">—</span>
              <span className="solo-lettori">nessun raddoppio</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p className="mb-0 mt-3 text-sm text-ink-2">
        Se la quota di un singolo evento è ≥ {soglia}, i punti raddoppiano. Fa fede la quota in bolletta.
      </p>
    </Card>
  );
}
