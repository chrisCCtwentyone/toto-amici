import { expect, it } from "vitest";
import { frazioneBarra } from "./barre";

it("da 40% (ultimo) a 100% (primo)", () => {
  expect(frazioneBarra(150, 150, 214)).toBeCloseTo(0.4);
  expect(frazioneBarra(214, 150, 214)).toBe(1);
  expect(frazioneBarra(182, 150, 214)).toBeCloseTo(0.7);
});
it("tutti pari o un solo giocatore: barra piena", () => {
  expect(frazioneBarra(10, 10, 10)).toBe(1);
});
it("valori fuori scala restano nei limiti", () => {
  expect(frazioneBarra(500, 0, 100)).toBe(1);
  expect(frazioneBarra(-5, 0, 100)).toBeCloseTo(0.4);
});
