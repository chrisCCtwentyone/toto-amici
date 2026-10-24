import { describe, expect, it, vi } from "vitest";
import { ricaricaUnaVolta } from "./ricaricaDopoDeploy";

function archivioFinto() {
  const dati = new Map<string, string>();
  return { getItem: (k: string) => dati.get(k) ?? null, setItem: (k: string, v: string) => void dati.set(k, v) };
}

describe("ricaricaUnaVolta", () => {
  it("ricarica al primo errore, non al secondo subito dopo, di nuovo dopo la pausa", () => {
    const a = archivioFinto();
    const ricarica = vi.fn();
    expect(ricaricaUnaVolta(() => a, 1_000_000, ricarica)).toBe(true);
    expect(ricaricaUnaVolta(() => a, 1_003_000, ricarica)).toBe(false); // stesso blocco ancora mancante: niente ciclo
    expect(ricaricaUnaVolta(() => a, 1_070_000, ricarica)).toBe(true); // un deploy successivo
    expect(ricarica).toHaveBeenCalledTimes(2);
  });

  it("senza sessionStorage non ricarica (nessuna protezione dai cicli)", () => {
    const ricarica = vi.fn();
    const rotto = () => {
      throw new Error("SecurityError");
    };
    expect(ricaricaUnaVolta(rotto, 1_000_000, ricarica)).toBe(false);
    const nonScrive = { getItem: () => null, setItem: () => { throw new Error("QuotaExceeded"); } };
    expect(ricaricaUnaVolta(() => nonScrive, 1_000_000, ricarica)).toBe(false);
    expect(ricarica).not.toHaveBeenCalled();
  });
});
