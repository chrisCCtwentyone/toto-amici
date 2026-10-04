/** Costanti di movimento condivise (stessi valori dei token CSS --durata-*). */
import type { Transition } from "motion/react";

export const EASE_USCITA = [0.2, 0.8, 0.2, 1] as const;
/** Entrata di barre e carte: veloce, senza rimbalzi (stile telecronaca, non giocattolo). */
export const ENTRATA: Transition = { duration: 0.5, ease: EASE_USCITA };
/** Scatto fra le barre di una lista: 90 ms, come nella proposta Diretta. */
export const SCATTO_LISTA_S = 0.09;
/** Molla per elementi che seguono il dito/puntatore (indicatore scheda). */
export const MOLLA: Transition = { type: "spring", stiffness: 520, damping: 40, mass: 0.8 };
