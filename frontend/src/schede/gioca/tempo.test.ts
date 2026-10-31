import { describe, expect, it } from "vitest";
import { contoAllaRovescia, testoConsegna, testoScadenza } from "./tempo";

describe("tempo", () => {
  it("scadenza in ora italiana (ora solare, UTC+1)", () => {
    expect(testoScadenza("2026-11-07T13:55:00Z")).toBe("sabato 7/11 alle 14:55");
  });
  it("consegna con i secondi", () => {
    expect(testoConsegna("2026-11-06T09:03:07Z")).toBe("10:03:07 del 06/11");
  });
  it("conto alla rovescia", () => {
    expect(contoAllaRovescia(252_000)).toBe("4 min 12 s");
    expect(contoAllaRovescia(3 * 3600_000 + 5 * 60_000)).toBe("3 h 05 min");
    expect(contoAllaRovescia(51 * 3600_000)).toBe("2 giorni 3 h");
    expect(contoAllaRovescia(-5)).toBe("0 min 00 s");
  });
});
