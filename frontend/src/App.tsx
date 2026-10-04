import { MotionConfig } from "motion/react";
import { DatiProvider, useDati } from "./lib/DatiContext";
import Intestazione from "./shell/Intestazione";
import BannerStato from "./shell/BannerStato";
import Schede from "./shell/Schede";
import StatiPagina from "./shell/StatiPagina";
import TickerShell from "./shell/TickerShell";
import PiePagina from "./shell/PiePagina";

function Contenuto() {
  const { fase } = useDati();
  return (
    <div className="flex min-h-dvh flex-col">
      <Intestazione />
      <BannerStato />
      <main className="flex flex-1 flex-col">{fase === "pronto" ? <Schede /> : <StatiPagina />}</main>
      <PiePagina />
      <TickerShell />
    </div>
  );
}

export default function App() {
  return (
    // reducedMotion="user": con "riduci movimento" attivo motion toglie gli spostamenti e tiene solo le dissolvenze
    <MotionConfig reducedMotion="user">
      <DatiProvider>
        <Contenuto />
      </DatiProvider>
    </MotionConfig>
  );
}
