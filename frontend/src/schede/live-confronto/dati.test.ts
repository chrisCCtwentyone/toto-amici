import { expect, it } from "vitest";
import { descriviLive, haQuotaAlta, testoSceltaGruppo } from "./dati";
import type { PartitaLive } from "../../tipi/snapshot";

const live = (stato: string, gc: number | null = 1, go: number | null = 0, minuto?: number): PartitaLive => ({
  id: 1, stato, gol_casa: gc, gol_ospite: go, inizio_il: null, ...(minuto !== undefined ? { minuto } : {}),
});

it("testo della scelta del gruppo", () => {
  expect(testoSceltaGruppo({ tipo: "maggioranza", pronostici: ["1", "X"], voti: 3, su: 7 })).toBe("1 / X · 3 su 7");
  expect(testoSceltaGruppo({ tipo: "tutti_diversi", pronostici: [], voti: 1, su: 7 })).toBe("Tutti diversi");
  expect(testoSceltaGruppo({ tipo: "nessuna", pronostici: [], voti: 0, su: 0 })).toBe("—");
});
it("asterisco: soglia inclusa, quota nulla mai", () => {
  expect(haQuotaAlta(3.5, 3.5)).toBe(true);
  expect(haQuotaAlta(3.49, 3.5)).toBe(false);
  expect(haQuotaAlta(null, 3.5)).toBe(false);
});
it("live: in corso, intervallo, finale", () => {
  expect(descriviLive(live("IN_PLAY", 2, 1, 34), "da_giocare")).toEqual({ tipo: "in_corso", etichetta: "34'", punteggio: [2, 1] });
  expect(descriviLive(live("PAUSED"), "in_corso").etichetta).toBe("Intervallo");
  expect(descriviLive(live("FINISHED", 0, 0), "vinta")).toEqual({ tipo: "finita", etichetta: "Finale", punteggio: [0, 0] });
});
it("esito finale + live 'da giocare' = niente (non contraddire l'esito)", () => {
  expect(descriviLive(live("TIMED", null, null), "vinta").tipo).toBe("nessuno");
  expect(descriviLive(live("TIMED", null, null), "da_giocare").tipo).toBe("programmata");
});
it("punteggio null resta null", () => {
  expect(descriviLive(live("IN_PLAY", null, null), "da_giocare").punteggio).toBeNull();
  expect(descriviLive(undefined, "da_giocare").tipo).toBe("nessuno");
});
