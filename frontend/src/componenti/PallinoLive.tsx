/**
 * Pallino che lampeggia. Da solo = indicatore; con `etichetta` = bollino "LIVE" rosa obliquo.
 * Usalo dove i dati sono "in diretta" (partite in corso, aggiornamento recente).
 */
interface Props {
  etichetta?: string;
  /** colore del pallino da solo: live (rosa) | oro (attenzione) | vinta (ok) */
  tono?: "live" | "oro" | "vinta";
  /** false = pallino fermo (es. dati vecchi) */
  lampeggia?: boolean;
  className?: string;
}

const TONI = { live: "bg-live", oro: "bg-oro", vinta: "bg-vinta" } as const;

export default function PallinoLive({ etichetta, tono = "live", lampeggia = true, className = "" }: Props) {
  const anim = lampeggia ? "animate-[lampeggia_1s_infinite] motion-reduce:animate-none" : "";
  if (etichetta) {
    return (
      <span
        className={`obliquo inline-flex items-center bg-live py-0.5 pl-2.5 pr-3.5 text-su-live ${className}`}
      >
        <span className="contro-obliquo inline-flex items-center gap-2 font-display text-xl font-extrabold leading-none tracking-[0.1em]">
          <i className={`block size-[9px] rounded-full bg-su-live ${anim}`} aria-hidden="true" />
          {etichetta}
        </span>
      </span>
    );
  }
  return <i className={`block size-2.5 shrink-0 rounded-full ${TONI[tono]} ${anim} ${className}`} aria-hidden="true" />;
}
