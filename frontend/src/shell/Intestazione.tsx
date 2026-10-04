import { useDati } from "../lib/DatiContext";
import { testoAggiornamento } from "../lib/format";
import { useTema } from "../lib/tema";
import { PallinoLive } from "../componenti";

/** Titolo con la stagione (dallo snapshot), "Aggiornato alle HH:MM del gg/mm" e interruttore del tema. */
export default function Intestazione() {
  const { snapshot, segnale, vecchiaia, fase } = useDati();
  const { tema, alterna } = useTema();
  const vecchio = vecchiaia?.vecchio ?? false;
  const nelPassato = segnale ? new Date(segnale.ultimo_controllo_il) : null;

  return (
    <header className="mx-auto flex w-full max-w-5xl items-start justify-between gap-3 px-4 pb-3 pt-[max(1rem,env(safe-area-inset-top))]">
      <div className="min-w-0">
        <h1 className="titolo-diretta flex flex-wrap items-baseline gap-x-3 text-[2.5rem] text-ink sm:text-5xl">
          <span>Toto-Amici</span>
          {snapshot && <em className="not-italic text-accento-testo">{snapshot.stagione}</em>}
        </h1>
        <p className="mt-1.5 flex items-center gap-2 text-sm text-ink-2" aria-live="polite">
          {nelPassato ? (
            <>
              <PallinoLive tono={vecchio ? "oro" : "live"} lampeggia={!vecchio} />
              <span>{testoAggiornamento(nelPassato)}</span>
            </>
          ) : snapshot ? (
            <span>Aggiornamento non verificabile</span>
          ) : fase === "errore" ? null : (
            <span>Caricamento…</span>
          )}
        </p>
      </div>
      <button
        type="button"
        onClick={alterna}
        aria-label={tema === "scuro" ? "Passa al tema chiaro" : "Passa al tema scuro"}
        className="grid size-11 flex-none cursor-pointer place-items-center rounded-diretta border border-linea bg-superficie text-ink transition-colors hover:border-accento-testo"
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          {tema === "scuro" ? (
            <>
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
            </>
          ) : (
            <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
          )}
        </svg>
      </button>
    </header>
  );
}
