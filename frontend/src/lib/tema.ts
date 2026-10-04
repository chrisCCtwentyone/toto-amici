import { useCallback, useEffect, useState } from "react";

export type Tema = "chiaro" | "scuro";
const COLORE_BARRA: Record<Tema, string> = { scuro: "#040a22", chiaro: "#eaf0ff" };

function temaAttuale(): Tema {
  const scelto = document.documentElement.dataset.tema;
  if (scelto === "chiaro" || scelto === "scuro") return scelto;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "scuro" : "chiaro";
}

/** Tema effettivo + interruttore. Di base segue il sistema; la scelta manuale resta in localStorage. */
export function useTema(): { tema: Tema; alterna: () => void } {
  const [tema, setTema] = useState<Tema>(temaAttuale);

  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const alCambio = () => setTema(temaAttuale());
    mq.addEventListener("change", alCambio);
    return () => mq.removeEventListener("change", alCambio);
  }, []);

  useEffect(() => {
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", COLORE_BARRA[tema]);
  }, [tema]);

  const alterna = useCallback(() => {
    const nuovo: Tema = temaAttuale() === "scuro" ? "chiaro" : "scuro";
    document.documentElement.dataset.tema = nuovo;
    try {
      localStorage.setItem("tema", nuovo);
    } catch {
      /* modalita' privata: la scelta vale solo per questa visita */
    }
    setTema(nuovo);
  }, []);

  return { tema, alterna };
}
