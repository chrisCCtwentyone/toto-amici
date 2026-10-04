import { describe, expect, it } from "vitest";
import { riduciPartite, validaGiornata } from "./live";

describe("validaGiornata", () => {
  it("accetta 1-38", () => {
    expect(validaGiornata("1")).toBe(1);
    expect(validaGiornata("38")).toBe(38);
  });
  it("rifiuta tutto il resto", () => {
    for (const x of [null, "", "0", "39", "-1", "5.5", "1e1", "05x", "abc", "007"]) {
      expect(validaGiornata(x)).toBeNull();
    }
  });
});

describe("riduciPartite", () => {
  it("tiene solo i campi dello schema e il minuto se c'e'", () => {
    const fd = {
      matches: [
        { id: 1, status: "IN_PLAY", utcDate: "2026-10-04T16:00:00Z", minute: 37, homeTeam: { name: "X" }, score: { fullTime: { home: 1, away: 0 } } },
        { id: 2, status: "TIMED", utcDate: "2026-10-04T18:45:00Z", score: { fullTime: { home: null, away: null } } },
      ],
    };
    expect(riduciPartite(fd)).toEqual([
      { id: 1, stato: "IN_PLAY", gol_casa: 1, gol_ospite: 0, inizio_il: "2026-10-04T16:00:00Z", minuto: 37 },
      { id: 2, stato: "TIMED", gol_casa: null, gol_ospite: null, inizio_il: "2026-10-04T18:45:00Z" },
    ]);
  });
  it("forma inattesa: lista vuota, mai un'eccezione", () => {
    expect(riduciPartite(null)).toEqual([]);
    expect(riduciPartite({})).toEqual([]);
    expect(riduciPartite({ matches: [{ status: "X" }, null] })).toEqual([]);
  });
});
