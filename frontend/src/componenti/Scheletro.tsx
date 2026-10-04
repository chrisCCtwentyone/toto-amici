/** Segnaposto di caricamento: barre oblique con riflesso. Il riflesso si ferma con movimento ridotto. */
export default function Scheletro({ righe = 5, className = "" }: { righe?: number; className?: string }) {
  return (
    <div className={className} role="status" aria-label="Caricamento in corso">
      {Array.from({ length: righe }, (_, i) => (
        <div
          key={i}
          className="obliquo my-[7px] h-[46px] animate-[luccica_1.6s_linear_infinite] bg-[length:200%_100%] bg-[linear-gradient(90deg,var(--traccia)_25%,var(--linea)_50%,var(--traccia)_75%)] motion-reduce:animate-none"
          style={{ width: `${100 - i * 6}%` }}
        />
      ))}
    </div>
  );
}
