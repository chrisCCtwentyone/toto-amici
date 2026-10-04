import { motion } from "motion/react";
import { Card, NumeroAnimato, StatoVuoto } from "../../componenti";
import type { Classifica } from "../../tipi/snapshot";
import { etichettaGiornata, formattaConSegno } from "../../lib/format";
import { ENTRATA } from "../../lib/movimento";
import Tendenza from "./Tendenza";

/** Colori del podio per posizione ESPLICITA (a pari merito due tessere restano dello stesso colore). */
function stile(posizione: number) {
  if (posizione === 1) return { bordo: "border-t-oro", casella: "bg-oro text-su-oro" };
  if (posizione === 2) return { bordo: "border-t-accento", casella: "bg-accento text-su-accento" };
  return { bordo: "border-t-marchio", casella: "bg-marchio text-su-barra" };
}

// visivamente 2 - 1 - 3 (il primo al centro, piu' alto); nel DOM resta 1, 2, 3 per chi legge a voce
const ORDINE_VISIVO = ["order-2", "order-1", "order-3"];

export default function Podio({ classifica }: { classifica: Classifica }) {
  const { giocatori, ultima_giornata_giocata: ultima } = classifica;
  const podio = giocatori.slice(0, 3);
  return (
    <Card
      titolo="Podio"
      evidenza={ultima !== null ? etichettaGiornata(ultima) : undefined}
      bandiera="accento"
    >
      {podio.length === 0 ? (
        <StatoVuoto titolo="Classifica non ancora disponibile">
          Il podio comparirà dopo la prima giornata con dei punti.
        </StatoVuoto>
      ) : (
        <ol className="m-0 grid list-none grid-cols-3 items-end gap-2 p-0 sm:gap-4">
          {podio.map((r, i) => {
            const s = stile(r.posizione);
            const primo = r.posizione === 1;
            // entrano dal terzo al primo: il primo arriva per ultimo
            const ritardo = (podio.length - 1 - i) * 0.12;
            return (
              <motion.li
                key={r.nome}
                className={`${ORDINE_VISIVO[i]} flex min-w-0 flex-col items-center gap-1 border-t-[5px] bg-superficie-2 px-1.5 pb-3 text-center ${s.bordo} ${primo ? "pt-6" : "pt-3"}`}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...ENTRATA, delay: ritardo }}
              >
                <span className={`obliquo inline-block min-w-11 px-2 ${s.casella}`}>
                  <span className="contro-obliquo block font-display text-2xl font-extrabold leading-8">
                    {r.posizione}°
                  </span>
                </span>
                <span className="max-w-full truncate font-display text-xl font-extrabold uppercase leading-6 tracking-wide text-ink sm:text-2xl">
                  {r.nome}
                </span>
                <span className="font-display text-[2.5rem] font-extrabold leading-none text-accento-testo sm:text-5xl">
                  <NumeroAnimato valore={r.punti_totali} />
                  <span className="ml-1 text-base text-ink-2"> pt</span>
                </span>
                {/* A1: il delta compare quando l'ultima giornata giocata ha dato punti */}
                {r.punti_ultima_giornata !== null && r.punti_ultima_giornata > 0 && (
                  <span className="leading-tight">
                    <span className="block font-display text-lg font-extrabold text-sale">
                      {formattaConSegno(r.punti_ultima_giornata)} pt
                    </span>
                    <span className="block text-xs text-ink-2">ultima giornata</span>
                  </span>
                )}
                <Tendenza variazione={r.variazione_posizione} />
              </motion.li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
