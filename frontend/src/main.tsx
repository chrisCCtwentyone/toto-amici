import { StrictMode, lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import "./font.css";
import "./index.css";
import App from "./App";

// Solo in sviluppo: /?vetrina mostra i componenti condivisi con dati veri.
const Vetrina = import.meta.env.DEV ? lazy(() => import("./vetrina/Vetrina")) : null;
const inVetrina = import.meta.env.DEV && new URLSearchParams(location.search).has("vetrina");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {inVetrina && Vetrina ? (
      <Suspense>
        <Vetrina />
      </Suspense>
    ) : (
      <App />
    )}
  </StrictMode>,
);
