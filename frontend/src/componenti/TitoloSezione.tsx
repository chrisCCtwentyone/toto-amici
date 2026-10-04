import type { ReactNode } from "react";

/** Titolo condensato maiuscolo con parte in evidenza (ciano), fuori da una Card. */
export default function TitoloSezione({ children, evidenza, livello = 2 }: { children: ReactNode; evidenza?: ReactNode; livello?: 2 | 3 }) {
  const H = livello === 2 ? "h2" : "h3";
  return (
    <H className="titolo-diretta mb-3 text-[1.9rem] text-ink">
      {children}
      {evidenza && <> <em className="not-italic text-accento-testo">{evidenza}</em></>}
    </H>
  );
}
