import { Card } from "../../../componenti";
import type { Regole, Tipologia } from "../../../tipi/snapshot";
import { formattaEuroIntero } from "../../../lib/format";

/** Nome e giocate ammesse per tipologia: testo del regolamento (copia statica). Il numero di eventi viene dallo snapshot. */
const TIPOLOGIE: { chiave: Tipologia; nome: string; ammesse: string }[] = [
  { chiave: "combo", nome: "Combo", ammesse: "1X2 + O/U 2.5, 1X2 + GG/NG" },
  { chiave: "doppie_chance", nome: "Doppie Chance", ammesse: "1X, X2, 12" },
  { chiave: "variabili", nome: "Variabili", ammesse: "Over/Under 2.5, Goal/NoGoal, Pari/Dispari" },
  { chiave: "fisse", nome: "Fisse", ammesse: "1, X, 2" },
];

export default function Bolletta({ regole }: { regole: Regole }) {
  return (
    <Card titolo="1. La" evidenza="bolletta" livello={3} bandiera="accento">
      <p className="m-0">
        Costo: <strong>{formattaEuroIntero(regole.costo_giornata)}</strong> a giornata.
      </p>
      <h4 className="mb-1 mt-3 text-sm font-semibold uppercase tracking-wider text-ink-2">Composizione obbligatoria</h4>
      <ul className="m-0 grid list-none gap-2 p-0">
        {TIPOLOGIE.map((t) => (
          <li key={t.chiave} className="flex items-start gap-3">
            <span className="obliquo mt-0.5 grid h-8 w-8 flex-none place-items-center bg-accento text-su-accento">
              <span className="contro-obliquo font-display text-xl font-extrabold leading-none">{regole.composizione[t.chiave]}</span>
            </span>
            <span className="min-w-0">
              <strong>{t.nome}</strong>
              <span className="block text-sm text-ink-2">{t.ammesse}</span>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
