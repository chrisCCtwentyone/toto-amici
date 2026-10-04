import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { SCHEDE } from "../schede/registro";
import BarraSchede, { idPannello, idTab } from "./BarraSchede";
import { Scheletro } from "../componenti";

const daHash = (): number => {
  const i = SCHEDE.findIndex((s) => `#${s.id}` === location.hash);
  return i >= 0 ? i : 0;
};

/** Barra + pannello della scheda attiva, con transizione direzionale (la scheda arriva dal lato giusto). */
export default function Schede() {
  const [attiva, setAttiva] = useState(daHash);
  const direzione = useRef(1);

  const seleziona = useCallback((i: number) => {
    setAttiva((prima) => {
      direzione.current = i >= prima ? 1 : -1;
      return i;
    });
    history.replaceState(null, "", `#${SCHEDE[i]!.id}`);
  }, []);

  useEffect(() => {
    const alHash = () => seleziona(daHash());
    window.addEventListener("hashchange", alHash);
    return () => window.removeEventListener("hashchange", alHash);
  }, [seleziona]);

  const scheda = SCHEDE[attiva]!;
  const Corpo = scheda.Componente;

  return (
    <>
      <BarraSchede attiva={attiva} onSeleziona={seleziona} />
      <div className="mx-auto w-full max-w-5xl flex-1 overflow-x-clip px-4 pt-3">
        <AnimatePresence mode="wait" initial={false} custom={direzione.current}>
          <motion.div
            key={scheda.id}
            id={idPannello(scheda.id)}
            role="tabpanel"
            aria-labelledby={idTab(scheda.id)}
            tabIndex={0}
            custom={direzione.current}
            variants={{
              entra: (d: number) => ({ opacity: 0, x: 24 * d }),
              resta: { opacity: 1, x: 0 },
              esce: (d: number) => ({ opacity: 0, x: -16 * d }),
            }}
            initial="entra"
            animate="resta"
            exit="esce"
            transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
            className="outline-offset-4"
          >
            <Suspense fallback={<Scheletro righe={5} />}>
              <Corpo />
            </Suspense>
          </motion.div>
        </AnimatePresence>
      </div>
    </>
  );
}
