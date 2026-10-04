import { describe, expect, it } from "vitest";
import {
  etichettaGiornata,
  formattaConSegno,
  formattaData,
  formattaDecimale,
  formattaDurata,
  formattaEuro,
  formattaEuroIntero,
  formattaFrazione,
  formattaIntero,
  formattaOra,
  formattaOrdinale,
  formattaPercentuale,
  formattaQuota,
  testoAggiornamento,
} from "./format";

// Intl mette spazi non separabili (U+00A0 / U+202F): nei test si normalizzano.
const n = (s: string) => s.replace(/[  ]/g, " ");

describe("numeri italiani", () => {
  it("raggruppa sempre le migliaia, anche a 4 cifre", () => {
    expect(formattaIntero(1200)).toBe("1.200");
    expect(formattaIntero(1674)).toBe("1.674");
    expect(formattaIntero(12345)).toBe("12.345");
    expect(formattaIntero(135)).toBe("135");
  });
  it("virgola decimale", () => {
    expect(formattaDecimale(2.35)).toBe("2,35");
    expect(formattaDecimale(2.5, 1)).toBe("2,5");
    expect(formattaDecimale(1674.56)).toBe("1.674,56");
  });
  it("euro con due decimali e simbolo dopo", () => {
    expect(n(formattaEuro(1674.56))).toBe("1.674,56 €");
    expect(n(formattaEuro(430))).toBe("430,00 €");
    expect(n(formattaEuro(0))).toBe("0,00 €");
    expect(n(formattaEuroIntero(3200))).toBe("3.200 €");
  });
  it("quota, percentuali, frazione", () => {
    expect(formattaQuota(2.35)).toBe("2,35");
    expect(formattaQuota(3)).toBe("3,00");
    expect(formattaQuota(null)).toBe("—");
    expect(formattaPercentuale(58.3)).toBe("58,3%");
    expect(formattaFrazione(0.264125)).toBe("26%");
    expect(formattaFrazione(1)).toBe("100%");
  });
  it("segno, ordinale, etichetta giornata", () => {
    expect(formattaConSegno(14)).toBe("+14");
    expect(formattaConSegno(-3)).toBe("−3");
    expect(formattaConSegno(0)).toBe("0");
    expect(formattaOrdinale(1)).toBe("1°");
    expect(etichettaGiornata(12)).toBe("Giornata 12");
  });
});

describe("date in Europe/Rome", () => {
  it("estate (UTC+2)", () => {
    expect(formattaOra("2026-10-04T15:45:03Z")).toBe("17:45");
    expect(formattaData("2026-10-04T15:45:03Z")).toBe("04/10");
    expect(testoAggiornamento("2026-10-04T15:45:03Z")).toBe("Aggiornato alle 17:45 del 04/10");
  });
  it("inverno (UTC+1)", () => {
    expect(formattaOra("2027-01-15T15:45:00Z")).toBe("16:45");
  });
  it("a cavallo di mezzanotte la data e' quella italiana", () => {
    expect(formattaData("2026-10-04T22:30:00Z")).toBe("05/10");
    expect(formattaOra("2026-10-04T22:30:00Z")).toBe("00:30");
  });
});

describe("durata", () => {
  it("minuti, ore, giorni", () => {
    expect(formattaDurata(45)).toBe("45 min");
    expect(formattaDurata(125)).toBe("2 h 05 min");
    expect(formattaDurata(60 * 26)).toBe("1 giorno 2 h");
    expect(formattaDurata(60 * 24 * 3)).toBe("3 giorni 0 h");
    expect(formattaDurata(-5)).toBe("0 min");
  });
});
