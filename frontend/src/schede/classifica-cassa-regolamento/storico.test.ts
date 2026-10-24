import { expect, it } from "vitest";
import { ordinaStorico, type RigaStorico } from "./storico";

const r = (nome: string, g: (number | null)[], ritirato = false): RigaStorico => ({
  nome, g, ritirato, tot: g.reduce<number>((t, x) => t + (x ?? 0), 0),
});
const righe = [r("PAOLO", [10, 4]), r("DARIO", [5, 9]), r("MARIO", [5, null]), r("PULIZZER", [20, 20], true), r("NICO", [7, 9])];
const nomi = (l: RigaStorico[]) => l.map((x) => x.nome);

it("senza colonna resta l'ordine della Classifica", () => {
  expect(nomi(ordinaStorico(righe, null, "giu"))).toEqual(["PAOLO", "DARIO", "MARIO", "PULIZZER", "NICO"]);
});
it("per giornata: dal piu' alto, pari merito nell'ordine di Classifica, ritirati in fondo", () => {
  expect(nomi(ordinaStorico(righe, 1, "giu"))).toEqual(["DARIO", "NICO", "PAOLO", "MARIO", "PULIZZER"]);
  expect(nomi(ordinaStorico(righe, 0, "giu"))).toEqual(["PAOLO", "NICO", "DARIO", "MARIO", "PULIZZER"]);
});
it("verso opposto: dal piu' basso, ma chi non ha giocato resta in fondo", () => {
  expect(nomi(ordinaStorico(righe, 1, "su"))).toEqual(["PAOLO", "DARIO", "NICO", "MARIO", "PULIZZER"]);
});
it("per totale", () => {
  expect(nomi(ordinaStorico(righe, "tot", "giu"))).toEqual(["NICO", "PAOLO", "DARIO", "MARIO", "PULIZZER"]);
});
