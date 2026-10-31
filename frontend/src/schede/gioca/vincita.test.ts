import { describe, expect, it } from "vitest";
import { parseVincita } from "./vincita";

describe("parseVincita", () => {
  it("formato italiano", () => {
    expect(parseVincita("1.674,56")).toBe(1674.56);
    expect(parseVincita("150")).toBe(150);
    expect(parseVincita("150,5")).toBe(150.5);
    expect(parseVincita("12.345.678,9")).toBe(12345678.9);
    expect(parseVincita("0,75")).toBe(0.75);
  });
  it("il punto delle migliaia non diventa un decimale", () => {
    expect(parseVincita("1.674")).toBe(1674);
    expect(parseVincita("1.000")).toBe(1000);
  });
  it("punto decimale all'americana, con 1-2 cifre", () => {
    expect(parseVincita("150.5")).toBe(150.5);
    expect(parseVincita("1674.56")).toBe(1674.56);
  });
  it("tollera euro e spazi", () => {
    expect(parseVincita(" 1.674,56 € ")).toBe(1674.56);
    expect(parseVincita("€150")).toBe(150);
  });
  it("rifiuta quello che non si capisce", () => {
    for (const x of ["", "  ", "abc", "1,2,3", "1.67", "1.6742", "150,555", "1.674.5", "-5", ",5", "150,", "1,674.56"]) {
      // "1.67" e' un decimale valido (1,67): lo si controlla a parte
      if (x === "1.67") continue;
      expect(parseVincita(x), x).toBeNull();
    }
    expect(parseVincita("1.67")).toBe(1.67);
  });
});
