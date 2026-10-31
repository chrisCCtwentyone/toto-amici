import { describe, expect, it } from "vitest";
import { conteggio, erroriSchedina, type GiornataAperta } from "../../../worker/schedina";
import { impostaCombo, pronosticoDi, righeDaScelte, SCELTA_VUOTA, tocca, type Scelte } from "./stato";

const aperta: GiornataAperta = {
  giornata: 9,
  scadenza_il: "2026-11-07T13:55:00Z",
  giocatori: ["ANNA"],
  partite: Array.from({ length: 10 }, (_, i) => ({ id: 100 + i, casa: `C${i}`, ospite: `O${i}`, inizio_il: "2026-11-07T14:00:00Z" })),
};

describe("carta", () => {
  it("un tasto sostituisce, lo stesso deseleziona", () => {
    let c = tocca(SCELTA_VUOTA, "semplice", "1");
    expect(pronosticoDi(c)).toBe("1");
    c = tocca(c, "semplice", "X2");
    expect(pronosticoDi(c)).toBe("X2");
    c = tocca(c, "semplice", "X2");
    expect(pronosticoDi(c)).toBeNull();
  });
  it("combo: serve la fissa E la variabile", () => {
    let c = impostaCombo(SCELTA_VUOTA, true);
    c = tocca(c, "fissa", "1");
    expect(pronosticoDi(c)).toBeNull();
    c = tocca(c, "extra", "OVER_2.5");
    expect(pronosticoDi(c)).toBe("1+OVER_2.5");
    c = tocca(c, "extra", "GOAL");
    expect(pronosticoDi(c)).toBe("1+GOAL");
  });
  it("accendendo la combo non si perde la fissa gia' scelta", () => {
    const c = impostaCombo(tocca(SCELTA_VUOTA, "semplice", "2"), true);
    expect(c.fissa).toBe("2");
    expect(c.extra).toBeNull();
    expect(impostaCombo(tocca(SCELTA_VUOTA, "semplice", "NOGOAL"), true).extra).toBe("NOGOAL");
    expect(impostaCombo(tocca(SCELTA_VUOTA, "semplice", "PARI"), true).extra).toBeNull();
  });
  it("spegnendo la combo vale di nuovo il tasto singolo", () => {
    const c = impostaCombo({ ...SCELTA_VUOTA, combo: true, fissa: "1", extra: "GOAL" }, false);
    expect(pronosticoDi(c)).toBeNull();
  });
});

describe("righeDaScelte", () => {
  const scelte: Scelte = {};
  const metti = (i: number, p: string, quota = false) => {
    scelte[100 + i] = { ...SCELTA_VUOTA, semplice: p, quota };
  };
  [["1", false], ["X", false], ["2", true], ["1", false], ["1X", false], ["12", false], ["OVER_2.5", false], ["PARI", false], ["GOAL", false]].forEach(([p, q], i) =>
    metti(i, p as string, q as boolean),
  );
  scelte[109] = { combo: true, semplice: null, fissa: "X", extra: "UNDER_2.5", quota: true };

  it("una riga per carta completa, in ordine, con la quota alta", () => {
    const righe = righeDaScelte(aperta.partite, scelte);
    expect(righe).toHaveLength(10);
    expect(righe[2]).toEqual({ partita_id: 102, pronostico: "2", quota_alta: true });
    expect(righe[9]).toEqual({ partita_id: 109, pronostico: "X+UNDER_2.5", quota_alta: true });
    expect(conteggio(righe)).toEqual({ Combo: 1, Fisse: 4, "Doppie Chance": 2, Variabili: 3 });
  });
  it("una schedina giusta non ha errori", () => {
    const s = { giocatore: "ANNA", giornata: 9, righe: righeDaScelte(aperta.partite, scelte), vincita: 1674.56 };
    expect(erroriSchedina(s, aperta)).toEqual([]);
  });
  it("carta incompleta o mancante: fuori dalle righe, errore chiaro", () => {
    const parziale: Scelte = { ...scelte, 109: { ...SCELTA_VUOTA, combo: true, fissa: "X" } };
    const righe = righeDaScelte(aperta.partite, parziale);
    expect(righe).toHaveLength(9);
    expect(erroriSchedina({ giocatore: "ANNA", giornata: 9, righe, vincita: 10 }, aperta).join(" ")).toContain("Manca il pronostico di C9-O9");
  });
});
