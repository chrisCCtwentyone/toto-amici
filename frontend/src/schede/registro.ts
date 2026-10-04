/**
 * Registro delle sei schede. Per aggiungere/rinominare una scheda si tocca SOLO qui
 * (e il file della scheda). Ogni scheda e' caricata a richiesta (un blocco di codice a parte):
 * il peso di una scheda non rallenta le altre.
 */
import { lazy, type ComponentType, type LazyExoticComponent } from "react";

export interface DefinizioneScheda {
  /** usato nell'indirizzo (#classifica) e negli id ARIA */
  id: string;
  etichetta: string;
  Componente: LazyExoticComponent<ComponentType>;
}

export const SCHEDE: readonly DefinizioneScheda[] = [
  { id: "classifica", etichetta: "Classifica & Cassa", Componente: lazy(() => import("./ClassificaCassa")) },
  { id: "live", etichetta: "Schedine Live", Componente: lazy(() => import("./SchedineLive")) },
  { id: "confronto", etichetta: "Confronto Giocate", Componente: lazy(() => import("./ConfrontoGiocate")) },
  { id: "statistiche", etichetta: "Statistiche", Componente: lazy(() => import("./Statistiche")) },
  { id: "coppa", etichetta: "Coppa", Componente: lazy(() => import("./Coppa")) },
  { id: "regolamento", etichetta: "Regolamento", Componente: lazy(() => import("./Regolamento")) },
];
