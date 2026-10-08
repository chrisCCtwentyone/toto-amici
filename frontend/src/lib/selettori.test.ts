import { describe, expect, it } from "vitest";
import { giocatoreEffettivo, giocatoriConSchedina, giornataEffettiva } from "./selettori";
import type { Snapshot } from "../tipi/snapshot";

function snap(corrente: number | null, schedine: [number, string][]): Snapshot {
  return {
    giornata_corrente: corrente,
    giocatori: ["Anna", "Bruno", "Carla"],
    schedine: schedine.map(([giornata, giocatore]) => ({ giornata, giocatore, righe: [] })),
  } as unknown as Snapshot;
}

const g5 = [5, 6].flatMap((g) => ["Anna", "Bruno", "Carla"].map((n): [number, string] => [g, n])).filter(([g]) => g === 5);
const base = snap(6, [...g5, [6, "Carla"]]);

describe("giocatore di default", () => {
  it("e' il primo, in ordine, che ha la schedina nella giornata", () => {
    expect(giocatoreEffettivo(base, 6, null)).toBe("Carla");
    expect(giocatoreEffettivo(base, 5, null)).toBe("Anna");
  });
  it("nessuno ha la schedina: primo della lista", () => {
    expect(giocatoreEffettivo(base, 7, null)).toBe("Anna");
  });
  it("giornata 1 non matcha 12 (niente sottostringhe)", () => {
    expect(giocatoriConSchedina(snap(12, [[12, "Bruno"]]), 1).size).toBe(0);
  });
});

describe("cambio giornata", () => {
  it("scelta a mano rispettata se ha la schedina nella nuova giornata", () => {
    expect(giocatoreEffettivo(base, 5, { giocatore: "Bruno", giornata: 5 })).toBe("Bruno");
    expect(giocatoreEffettivo(base, 6, { giocatore: "Carla", giornata: 5 })).toBe("Carla");
  });
  it("scelta a mano senza schedina nella nuova giornata: passa al primo che ce l'ha", () => {
    expect(giocatoreEffettivo(base, 6, { giocatore: "Bruno", giornata: 5 })).toBe("Carla");
  });
  it("giocatore senza schedina cliccato apposta in questa giornata: resta (si vede il messaggio)", () => {
    expect(giocatoreEffettivo(base, 6, { giocatore: "Anna", giornata: 6 })).toBe("Anna");
  });
});

describe("snapshot nuovo", () => {
  it("senza scelta a mano segue la giornata corrente", () => {
    expect(giornataEffettiva(snap(5, g5), null)).toBe(5);
    expect(giornataEffettiva(base, null)).toBe(6);
  });
  it("con scelta a mano resta dov'e'", () => {
    expect(giornataEffettiva(base, 5)).toBe(5);
  });
  it("senza giornata corrente: l'ultima disponibile", () => {
    expect(giornataEffettiva(snap(null, g5), null)).toBe(5);
  });
});
