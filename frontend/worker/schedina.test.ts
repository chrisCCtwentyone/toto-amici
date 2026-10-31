import { describe, expect, it } from "vitest";
import {
  conteggio, erroriSchedina, etichettaPronostico, improntaPassword, leggiInvio, normalizzaPassword, tipoDi,
  type GiornataAperta, type Riga,
} from "./schedina";

const aperta: GiornataAperta = {
  giornata: 11,
  scadenza_il: "2026-11-07T13:55:00Z",
  partite: Array.from({ length: 10 }, (_, i) => ({ id: 100 + i, casa: `Casa${i}`, ospite: `Ospite${i}`, inizio_il: "2026-11-07T14:00:00Z" })),
  giocatori: ["DAVIDE", "SILVIO"],
};

// 1 Combo, 4 Fisse, 2 Doppie Chance, 3 Variabili: una per partita.
const PRONOSTICI = ["1+OVER_2.5", "1", "X", "2", "1", "1X", "X2", "GOAL", "PARI", "UNDER_2.5"];
const righe = (pronostici = PRONOSTICI): Riga[] =>
  pronostici.map((p, i) => ({ partita_id: 100 + i, pronostico: p, quota_alta: false }));
const schedina = (r = righe()) => ({ giocatore: "DAVIDE", giornata: 11, righe: r, vincita: 150.5 });

describe("tipoDi", () => {
  it("riconosce le quattro categorie del regolamento", () => {
    expect(tipoDi("X")).toBe("Fisse");
    expect(tipoDi("12")).toBe("Doppie Chance");
    expect(tipoDi("NOGOAL")).toBe("Variabili");
    expect(tipoDi("2+GOAL")).toBe("Combo");
  });
  it("non indovina: Combo con Pari/Dispari o forme strane non valgono", () => {
    for (const p of ["1+PARI", "1X+GOAL", "1+", "OVER_1.5", "over_2.5", "1+OVER_2.5+GOAL", ""]) {
      expect(tipoDi(p)).toBeNull();
    }
  });
});

describe("erroriSchedina", () => {
  it("una schedina giusta non ha errori", () => {
    expect(erroriSchedina(schedina(), aperta)).toEqual([]);
    expect(conteggio(righe())).toEqual({ Combo: 1, Fisse: 4, "Doppie Chance": 2, Variabili: 3 });
  });
  it("partita mancante, doppione e composizione sbagliata", () => {
    const r = righe();
    r[9] = { ...r[9]!, partita_id: 100 }; // due pronostici sulla prima partita, nessuno sull'ultima
    const errori = erroriSchedina(schedina(r), aperta);
    expect(errori).toContain("Manca il pronostico di Casa9-Ospite9.");
    expect(errori).toContain("Casa0-Ospite0 ha piu' di un pronostico.");
  });
  it("conteggio per tipo", () => {
    const errori = erroriSchedina(schedina(righe(["1+OVER_2.5", "1", "X", "2", "1", "1", "X2", "GOAL", "PARI", "UNDER_2.5"])), aperta);
    expect(errori).toContain("Fisse: ne servono 4, ne hai 5.");
    expect(errori).toContain("Doppie Chance: ne servono 2, ne hai 1.");
  });
  it("giocatore, giornata, partita estranea e vincita", () => {
    const r = righe();
    r[0] = { ...r[0]!, partita_id: 999 };
    const errori = erroriSchedina({ giocatore: "PIPPO", giornata: 10, righe: r, vincita: 0 }, aperta);
    expect(errori).toEqual(expect.arrayContaining([
      "Scegli il tuo nome.",
      "Questa schedina non e' della Giornata 11.",
      "C'e' una partita che non e' di questa giornata.",
      "Scrivi la vincita potenziale della tua bolletta.",
    ]));
  });
});

describe("leggiInvio", () => {
  it("accetta il corpo della nostra pagina", () => {
    const corpo = { ...schedina(), password: "tigre-42-lago" };
    expect(leggiInvio(JSON.parse(JSON.stringify(corpo)))).toEqual({ schedina: schedina(), password: "tigre-42-lago" });
  });
  it("rifiuta corpi malformati invece di indovinare", () => {
    for (const d of [null, "x", {}, { ...schedina(), password: 3 }, { ...schedina(), righe: [{ partita_id: "1" }], password: "a" },
      { ...schedina(), vincita: "150", password: "a" }]) {
      expect(leggiInvio(d)).toBeNull();
    }
  });
});

describe("password", () => {
  it("impronta identica a quella del bot (hashlib.sha256 di sale + password)", async () => {
    // python3 -c "import hashlib;print(hashlib.sha256(('0123abcd'+'tigre-42-lago').encode()).hexdigest())"
    expect(await improntaPassword("0123abcd", "tigre-42-lago"))
      .toBe("71b6a864e3cb6769455b6fa10237087c06e08791ce6d6c6bc264955196ec3d15");
  });
  it("maiuscole e spazi non contano", () => {
    expect(normalizzaPassword("  Tigre 42  Lago ")).toBe("tigre-42-lago");
  });
});

it("etichette leggibili", () => {
  expect(etichettaPronostico("1+OVER_2.5")).toBe("1 + Over 2.5");
  expect(etichettaPronostico("NOGOAL")).toBe("NoGoal");
});
