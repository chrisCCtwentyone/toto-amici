import { useEffect, useRef } from "react";
import { animate, useReducedMotion } from "motion/react";
import { formattaIntero } from "../lib/format";

/**
 * Numero che "sale" fino al valore (e si riassesta se il valore cambia).
 * `formato` e' uno dei formattatori di lib/format (es. formattaEuro, o
 * (n) => formattaDecimale(n, 1)). Con movimento ridotto mostra subito il valore finale.
 * Gli screen reader leggono solo il valore finale (aria-label), una volta sola, non i passaggi intermedi.
 */
interface Props {
  valore: number;
  formato?: (n: number) => string;
  durata?: number;
  className?: string;
}

export default function NumeroAnimato({ valore, formato = formattaIntero, durata = 0.9, className = "" }: Props) {
  const rif = useRef<HTMLSpanElement>(null);
  const ridotto = useReducedMotion();
  const ultimo = useRef(ridotto ? valore : 0);

  useEffect(() => {
    const el = rif.current;
    if (!el) return;
    if (ridotto) {
      el.textContent = formato(valore);
      ultimo.current = valore;
      return;
    }
    const ctrl = animate(ultimo.current, valore, {
      duration: durata,
      ease: [0.2, 0.8, 0.2, 1],
      onUpdate: (v) => {
        ultimo.current = v;
        el.textContent = formato(v);
      },
    });
    return () => ctrl.stop();
  }, [valore, formato, durata, ridotto]);

  // Un solo nodo nel DOM: role="img" + aria-label = il valore finale, letto UNA volta;
  // le cifre che salgono sono contenuto presentazionale (non vengono lette ne' estratte come testo doppio).
  return (
    <span ref={rif} role="img" aria-label={formato(valore)} className={`tabulare ${className}`}>
      {formato(ridotto ? valore : ultimo.current)}
    </span>
  );
}
