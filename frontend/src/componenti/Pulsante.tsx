import type { ButtonHTMLAttributes } from "react";

/** Pulsante con target touch >= 44px. `primario` = ciano pieno, `secondario` = bordo. */
interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: "primario" | "secondario";
}

export default function Pulsante({ variante = "secondario", className = "", type = "button", ...resto }: Props) {
  const stile =
    variante === "primario"
      ? "bg-accento text-su-accento hover:brightness-110"
      : "border border-linea bg-superficie-2 text-ink hover:border-accento-testo";
  return (
    <button
      type={type}
      className={`inline-flex min-h-11 min-w-11 cursor-pointer items-center justify-center gap-2 rounded-diretta px-4 font-display text-lg font-extrabold uppercase tracking-wide transition-[filter,border-color,opacity] duration-150 disabled:cursor-not-allowed disabled:opacity-40 ${stile} ${className}`}
      {...resto}
    />
  );
}
