import { describe, expect, it } from "vitest";
import {
  alternaScelto,
  calcolaAndamento,
  leggiScelti,
  sceltiIniziali,
  spaziaEtichette,
  tacchePosizioni,
  tacchePunti,
  type GiocatoreIn,
} from "./andamento";

const g = (nome: string, posizione: number, p: (number | null)[]): GiocatoreIn => ({ nome, posizione, punti_per_giornata: p });

describe("calcolaAndamento", () => {
  it("somma progressiva, con null che conta 0", () => {
    const d = calcolaAndamento([g("A", 1, [10, null, 5]), g("B", 2, [3, 4, null])]);
    expect(d.giornate).toEqual([1, 2, 3]);
    expect(d.serie[0]!.punti).toEqual([10, 10, 15]);
    expect(d.serie[1]!.punti).toEqual([3, 7, 7]);
  });

  it("esclude le giornate senza nessun punteggio, ma non perde i punti", () => {
    const d = calcolaAndamento([g("A", 1, [10, null, null, 5, null]), g("B", 2, [3, null, null, 4, null])]);
    expect(d.giornate).toEqual([1, 4]);
    expect(d.serie[0]!.punti).toEqual([10, 15]);
  });

  it("pareggi: stessa posizione e la successiva salta (1, 1, 3)", () => {
    const d = calcolaAndamento([g("A", 1, [10, 1]), g("B", 2, [10, 1]), g("C", 3, [5, 1])]);
    expect(d.serie.map((s) => s.posizioni[0])).toEqual([1, 1, 3]);
  });

  it("l'ultima giornata usa la posizione ufficiale, anche a pari punti", () => {
    const d = calcolaAndamento([g("A", 2, [10, 5]), g("B", 1, [10, 5]), g("C", 3, [1, 1])]);
    // dopo G1 e' pareggio (1, 1, 3); dopo G2 pareggio ma vale la classifica ufficiale
    expect(d.serie.map((s) => s.posizioni[0])).toEqual([1, 1, 3]);
    expect(d.serie.map((s) => s.posizioni[1])).toEqual([2, 1, 3]);
  });

  it("nessun punteggio: nessuna giornata", () => {
    const d = calcolaAndamento([g("A", 1, [null, null]), g("B", 2, [])]);
    expect(d.giornate).toEqual([]);
    expect(d.serie[0]!.punti).toEqual([]);
  });

  it("uno zero e' un punteggio (la giornata resta), un null no", () => {
    expect(calcolaAndamento([g("A", 1, [0]), g("B", 2, [null])]).giornate).toEqual([1]);
  });
});

describe("tacche degli assi", () => {
  it("punti: parte da 0 e arriva a coprire il massimo", () => {
    expect(tacchePunti(135)).toEqual([0, 50, 100, 150]);
    expect(tacchePunti(0)).toEqual([0]);
    expect(tacchePunti(7)).toEqual([0, 2, 4, 6, 8]);
  });
  it("posizioni: intere, con 1 e l'ultima", () => {
    expect(tacchePosizioni(16)).toEqual([1, 5, 9, 13, 16]);
    expect(tacchePosizioni(1)).toEqual([1]);
    expect(tacchePosizioni(3)).toEqual([1, 2, 3]);
  });
});

describe("spaziaEtichette", () => {
  it("distanzia le etichette vicine e conserva l'ordine di ingresso", () => {
    const r = spaziaEtichette([50, 52, 51], 14, 0, 200);
    const ordinate = [...r].sort((a, b) => a - b);
    expect(ordinate[1]! - ordinate[0]!).toBeGreaterThanOrEqual(14);
    expect(ordinate[2]! - ordinate[1]!).toBeGreaterThanOrEqual(14);
    expect(r[0]).toBeLessThan(r[2]!); // 50 sta sopra 51
  });
  it("resta dentro i limiti", () => {
    const r = spaziaEtichette([198, 199, 200], 14, 10, 200);
    expect(Math.max(...r)).toBeLessThanOrEqual(200);
    expect(Math.min(...r)).toBeGreaterThanOrEqual(10);
  });
});

describe("selezione giocatori", () => {
  it("default: i primi 3 con i colori 1-3", () => {
    expect(sceltiIniziali(["A", "B", "C", "D"])).toEqual([{ nome: "A", slot: 1 }, { nome: "B", slot: 2 }, { nome: "C", slot: 3 }]);
  });
  it("il colore segue la persona e quello liberato viene riusato", () => {
    let s = sceltiIniziali(["A", "B", "C", "D"]);
    s = alternaScelto(s, "A");
    expect(s).toEqual([{ nome: "B", slot: 2 }, { nome: "C", slot: 3 }]);
    s = alternaScelto(s, "D");
    expect(s.find((x) => x.nome === "D")!.slot).toBe(1);
    expect(s.find((x) => x.nome === "B")!.slot).toBe(2);
  });
  it("al quinto non aggiunge", () => {
    let s = sceltiIniziali(["A", "B", "C", "D", "E"]);
    s = alternaScelto(s, "D");
    expect(s).toHaveLength(4);
    expect(alternaScelto(s, "E")).toBe(s);
  });
  it("rilettura da localStorage: scarta nomi sconosciuti e colori doppi, '[]' resta Tutti", () => {
    const nomi = ["A", "B"];
    expect(leggiScelti([{ nome: "A", slot: 2 }, { nome: "Z", slot: 1 }, { nome: "B", slot: 2 }], nomi)).toEqual([{ nome: "A", slot: 2 }]);
    expect(leggiScelti([], nomi)).toEqual([]);
    expect(leggiScelti("rotto", nomi)).toBeNull();
    expect(leggiScelti([{ nome: "Z", slot: 1 }], nomi)).toBeNull();
  });
});
