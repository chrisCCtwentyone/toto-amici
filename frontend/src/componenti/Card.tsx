import type { ElementType, ReactNode } from "react";

/**
 * Superficie base delle schede. `bandiera` = barra laterale colorata (stile "bug" della telecronaca).
 * Il titolo e' un h2/h3 a scelta (`livello`) per non rompere la gerarchia dei titoli.
 */
interface Props {
  titolo?: ReactNode;
  /** parte del titolo evidenziata (ciano), es. "CLASSIFICA <em>GIORNATA 6</em>" */
  evidenza?: ReactNode;
  livello?: 2 | 3;
  bandiera?: "accento" | "live" | "oro" | "marchio";
  /** elemento a destra del titolo (selettori, pulsanti) */
  azione?: ReactNode;
  as?: ElementType;
  className?: string;
  children?: ReactNode;
}

const BANDIERE = {
  accento: "border-l-[6px] border-l-accento",
  live: "border-l-[6px] border-l-live",
  oro: "border-l-[6px] border-l-oro",
  marchio: "border-l-[6px] border-l-marchio",
} as const;

export default function Card({ titolo, evidenza, livello = 2, bandiera, azione, as: Tag = "section", className = "", children }: Props) {
  const H = livello === 2 ? "h2" : "h3";
  return (
    <Tag className={`rounded-diretta bg-superficie p-4 shadow-card ${bandiera ? BANDIERE[bandiera] : ""} ${className}`}>
      {(titolo || azione) && (
        <header className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          {titolo && (
            <H className="titolo-diretta text-[1.75rem] text-ink">
              {titolo}
              {evidenza && <> <em className="not-italic text-accento-testo">{evidenza}</em></>}
            </H>
          )}
          {azione}
        </header>
      )}
      {children}
    </Tag>
  );
}
