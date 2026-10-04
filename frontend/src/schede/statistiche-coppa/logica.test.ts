import { describe, expect, it } from "vitest";
import { etichettaDaDefinire, raggruppa, scomponiDurata } from "./logica";

describe("scomponiDurata", () => {
  it("scompone in settimane, giorni, ore, minuti, secondi", () => {
    expect(scomponiDurata(604800 + 2 * 86400 + 3 * 3600 + 4 * 60 + 5)).toEqual({ settimane: 1, giorni: 2, ore: 3, minuti: 4, secondi: 5 });
  });
  it("non va mai sotto zero", () => {
    expect(scomponiDurata(-50)).toEqual({ settimane: 0, giorni: 0, ore: 0, minuti: 0, secondi: 0 });
  });
});

describe("raggruppa", () => {
  it("tiene insieme i valori uguali nell'ordine di arrivo", () => {
    expect(raggruppa(["a1", "b2", "c1"], (x) => x.slice(1))).toEqual([["a1", "c1"], ["b2"]]);
  });
});

describe("etichettaDaDefinire", () => {
  it("ottavi: Da definire; poi vincente della sfida di provenienza", () => {
    expect(etichettaDaDefinire(0, 3, 0)).toBe("Da definire");
    expect(etichettaDaDefinire(1, 0, 0)).toBe("Vincente ottavo 1");
    expect(etichettaDaDefinire(1, 3, 1)).toBe("Vincente ottavo 8");
    expect(etichettaDaDefinire(2, 1, 0)).toBe("Vincente quarto 3");
    expect(etichettaDaDefinire(3, 0, 1)).toBe("Vincente semifinale 2");
  });
});
