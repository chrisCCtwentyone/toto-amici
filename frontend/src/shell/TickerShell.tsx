import { useDati } from "../lib/DatiContext";
import { formattaEuro, formattaIntero } from "../lib/format";
import { Ticker } from "../componenti";

/** Ticker in basso: sempre visibile, ripete i numeri chiave dello snapshot. */
export default function TickerShell() {
  const { snapshot } = useDati();
  if (!snapshot) return null;
  const { classifica, cassa, giornata_corrente } = snapshot;
  const primi = classifica.giocatori.filter((g) => g.posizione === 1);
  const voci = [
    giornata_corrente !== null && `Giornata ${giornata_corrente}`,
    `Fondo cassa ${formattaEuro(cassa.saldo)}`,
    primi.length > 0 && `In testa ${primi.map((g) => g.nome).join(" / ")} · ${formattaIntero(primi[0]!.punti_totali)} pt`,
  ].filter((v): v is string => typeof v === "string");
  return (
    <div className="sticky bottom-0 z-10 mx-auto w-full max-w-5xl px-4 pb-[max(0.5rem,env(safe-area-inset-bottom))]">
      <Ticker voci={voci} />
    </div>
  );
}
