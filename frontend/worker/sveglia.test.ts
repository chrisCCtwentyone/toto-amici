import { describe, expect, it } from "vitest";
import { inPausaNotturna, svegliaBot, URL_BOT } from "./sveglia";

// Ora italiana -> istante UTC: a ottobre (prima del 25/10) ora legale UTC+2, a novembre ora solare UTC+1.
const legale = (hhmm: string) => new Date(`2026-10-20T${hhmm}:00+02:00`);
const solare = (hhmm: string) => new Date(`2026-11-03T${hhmm}:00+01:00`);

describe("inPausaNotturna", () => {
  for (const [nome, ora] of [["ora legale", legale], ["ora solare", solare]] as const) {
    it(`${nome}: confini 02:00 incluso, 07:30 escluso`, () => {
      expect(inPausaNotturna(ora("01:59"))).toBe(false);
      expect(inPausaNotturna(ora("02:00"))).toBe(true);
      expect(inPausaNotturna(ora("05:00"))).toBe(true);
      expect(inPausaNotturna(ora("07:29"))).toBe(true);
      expect(inPausaNotturna(ora("07:30"))).toBe(false);
      expect(inPausaNotturna(ora("23:50"))).toBe(false);
      expect(inPausaNotturna(ora("00:10"))).toBe(false);
    });
  }
});

describe("svegliaBot", () => {
  it("in pausa non chiama nessuno", async () => {
    let chiamate = 0;
    const finta = (async () => { chiamate++; return new Response("ok"); }) as typeof fetch;
    expect(await svegliaBot(solare("03:00"), finta)).toMatch(/pausa/);
    expect(chiamate).toBe(0);
  });

  it("fuori pausa chiama il bot e riferisce l'esito", async () => {
    const indirizzi: string[] = [];
    const finta = (async (url: string) => { indirizzi.push(url); return new Response("ok"); }) as typeof fetch;
    expect(await svegliaBot(solare("07:30"), finta)).toMatch(/HTTP 200/);
    expect(indirizzi).toEqual([URL_BOT]);
  });

  it("riprova una volta e non solleva mai", async () => {
    let chiamate = 0;
    const finta = (async () => { chiamate++; throw new Error("rete giu'"); }) as typeof fetch;
    expect(await svegliaBot(solare("09:00"), finta)).toMatch(/NON raggiungibile/);
    expect(chiamate).toBe(2);
  });
});
