import { useDati } from "../lib/DatiContext";
import { formattaDurata } from "../lib/format";
import { Pulsante } from "../componenti";

/**
 * Avvisi sulla freschezza dei dati (uno solo alla volta, il piu' grave):
 *  1. dati vecchi: il segnale del bot manca da piu' di 120 minuti (al netto della pausa notturna);
 *  2. segnale non leggibile: non si puo' dire se i dati sono aggiornati;
 *  3. ultimo aggiornamento fallito: si mostrano gli ultimi dati buoni.
 */
export default function BannerStato() {
  const { fase, vecchiaia, segnale, aggiornamentoFallito, ricarica } = useDati();
  if (fase !== "pronto") return null;

  let testo: string | null = null;
  if (vecchiaia?.vecchio) {
    const quanto = Number.isFinite(vecchiaia.minuti) ? ` da ${formattaDurata(vecchiaia.minuti)}` : "";
    testo = `Il sito non riceve aggiornamenti${quanto} (esclusa la pausa notturna): i dati qui sotto potrebbero essere vecchi.`;
  } else if (!segnale) {
    testo = "Non riesco a verificare quanto siano aggiornati i dati: potrebbero essere vecchi.";
  } else if (aggiornamentoFallito) {
    testo = "Non riesco ad aggiornare i dati in questo momento: vedi l'ultima versione ricevuta.";
  }
  if (!testo) return null;

  return (
    <div role="status" className="mx-auto w-full max-w-5xl px-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-l-[6px] border-avviso-bordo bg-avviso-fondo px-4 py-3 text-ink">
        <p className="min-w-0 flex-1 basis-60 font-medium">{testo}</p>
        <Pulsante onClick={ricarica}>Riprova</Pulsante>
      </div>
    </div>
  );
}
