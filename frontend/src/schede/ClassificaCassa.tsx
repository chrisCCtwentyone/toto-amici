import { useSnapshot } from "../lib/DatiContext";
import Podio from "./classifica-cassa-regolamento/Podio";
import ClassificaCompleta from "./classifica-cassa-regolamento/ClassificaCompleta";
import FondoCassa from "./classifica-cassa-regolamento/FondoCassa";

/** Scheda "Classifica & Cassa": legge solo §5 classifica e §6 cassa, non calcola nulla. */
export default function ClassificaCassa() {
  const { classifica, cassa } = useSnapshot();
  return (
    <div className="grid gap-4 pb-4">
      <Podio classifica={classifica} />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <ClassificaCompleta classifica={classifica} />
        <FondoCassa cassa={cassa} />
      </div>
    </div>
  );
}
