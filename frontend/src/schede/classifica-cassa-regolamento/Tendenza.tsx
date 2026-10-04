import { formattaIntero } from "../../lib/format";

/**
 * Freccia di tendenza (variazione_posizione, §5.2): positivo = salito, 0 = invariata, null = niente da mostrare.
 * Chip con fondo proprio: i colori sale/scende sono leggibili su `superficie` in entrambi i temi,
 * anche quando il chip sta sopra una barra scura. Il significato e' in glifo + numero + testo per i lettori.
 */
export default function Tendenza({ variazione }: { variazione: number | null }) {
  if (variazione === null) return null;
  const n = Math.abs(variazione);
  const [glifo, colore, testo] =
    variazione > 0
      ? ["▲", "text-sale", `salito di ${n} ${n === 1 ? "posizione" : "posizioni"}`]
      : variazione < 0
        ? ["▼", "text-scende", `sceso di ${n} ${n === 1 ? "posizione" : "posizioni"}`]
        : ["–", "text-ink-2", "posizione invariata"];
  return (
    <span className={`inline-flex items-center bg-superficie px-1.5 font-display text-base font-extrabold leading-6 ${colore}`}>
      <span aria-hidden="true">
        {glifo}
        {n > 0 && formattaIntero(n)}
      </span>
      <span className="solo-lettori">{testo}</span>
    </span>
  );
}
