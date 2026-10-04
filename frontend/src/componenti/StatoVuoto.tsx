import type { ReactNode } from "react";

/** "Niente da mostrare" (nessuna schedina, nessun movimento...). Sempre con una spiegazione. */
export default function StatoVuoto({ titolo, children }: { titolo: string; children?: ReactNode }) {
  return (
    <div className="border-l-[6px] border-l-linea bg-superficie-2 px-4 py-5">
      <p className="titolo-diretta text-2xl text-ink-2">{titolo}</p>
      {children && <p className="mt-1 text-ink-2">{children}</p>}
    </div>
  );
}
