import { expect, it } from "vitest";
import { esitoVisualizzato } from "./esiti";
import type { PartitaLive } from "../tipi/snapshot";

const live = (stato: string): PartitaLive => ({ id: 1, stato, gol_casa: 0, gol_ospite: 0, inizio_il: null });

it("da_giocare diventa in_corso solo se il live dice che e' iniziata", () => {
  expect(esitoVisualizzato("da_giocare", live("IN_PLAY"))).toBe("in_corso");
  expect(esitoVisualizzato("da_giocare", live("PAUSED"))).toBe("in_corso");
  expect(esitoVisualizzato("da_giocare", live("TIMED"))).toBe("da_giocare");
  expect(esitoVisualizzato("da_giocare")).toBe("da_giocare");
});
it("un esito finale non si tocca mai", () => {
  for (const e of ["vinta", "persa", "annullata"] as const) {
    expect(esitoVisualizzato(e, live("IN_PLAY"))).toBe(e);
  }
});
