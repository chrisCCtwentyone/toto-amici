import type { ReactNode } from "react";

/**
 * Striscia rosa scorrevole in basso (ticker della telecronaca). Decorativa: ripete
 * informazioni gia' presenti in pagina, quindi e' aria-hidden. Il contenuto e' raddoppiato
 * per far ripartire il ciclo senza stacco. Con movimento ridotto non scorre (si puo' scrollare).
 * Si ferma al passaggio del mouse.
 */
export default function Ticker({ voci, secondi = 26, className = "" }: { voci: ReactNode[]; secondi?: number; className?: string }) {
  if (voci.length === 0) return null;
  const giro = voci.map((v, i) => (
    <span key={i} className="px-[26px]">
      {v}
    </span>
  ));
  return (
    <div aria-hidden="true" className={`obliquo overflow-hidden bg-live text-su-live motion-reduce:overflow-x-auto ${className}`}>
      <div
        className="contro-obliquo flex w-max animate-[scorre-ticker_var(--durata-ticker)_linear_infinite] py-[5px] font-display text-lg font-extrabold uppercase tracking-[0.06em] hover:[animation-play-state:paused] motion-reduce:animate-none"
        style={{ ["--durata-ticker" as string]: `${secondi}s` }}
      >
        {giro}
        {giro}
      </div>
    </div>
  );
}
