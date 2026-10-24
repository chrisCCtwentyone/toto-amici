import { expect, it } from "vitest";
import { descriviLive, haQuotaAlta, puntiMassimi, puntiSchedina, testoSceltaGruppo } from "./dati";
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
it("punti della schedina: somma delle righe, 0 senza righe", () => {
  const riga = (punti: number) => ({ partita_id: 1, tipologia: null, pronostico: "1", quota: null, esito: "vinta" as const, punti });
  expect(puntiSchedina([riga(12), riga(4), riga(0)])).toBe(16);
  expect(puntiSchedina([])).toBe(0);
});
it("punti massimi: fatti + righe ancora da decidere, perse e annullate a zero", () => {
  const regole = {
    soglia_quota_doppia: 3.5,
    punti: { combo: { base: 6, quota_alta: 12 }, fisse: { base: 4, quota_alta: 8 }, doppie_chance: { base: 1, quota_alta: 2 }, variabili: { base: 2, quota_alta: 4 } },
  };
  const r = (pronostico: string, esito: "vinta" | "persa" | "da_giocare" | "in_corso" | "annullata", punti = 0, quota: number | null = 1.5) =>
    ({ partita_id: 1, tipologia: null, pronostico, quota, esito, punti });
  // vinta 4 + combo da giocare 6 + fisse in corso a quota alta 8 + doppia da giocare 1 + variabile 2; persa e annullata 0
  expect(puntiMassimi([r("1", "vinta", 4), r("1+OVER_2.5", "da_giocare"), r("2", "in_corso", 0, 3.6),
    r("X2", "da_giocare"), r("GOAL", "da_giocare"), r("X", "persa"), r("12", "annullata")], regole)).toBe(21);
  // a giornata finita il massimo coincide con i punti fatti
  expect(puntiMassimi([r("1", "vinta", 4), r("GOAL", "persa")], regole)).toBe(4);
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
