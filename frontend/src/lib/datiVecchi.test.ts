import { describe, expect, it } from "vitest";
import { minutiInPausa, minutiSenzaSegnale, statoDati } from "./datiVecchi";
import type { Segnale } from "../tipi/snapshot";

const segnale = (ultimo: string, soglia = 120): Segnale => ({
  versione_schema: 1,
  ultimo_controllo_il: ultimo,
  generato_il: ultimo,
  impronta: "x",
  soglia_allarme_minuti: soglia,
  pausa_notturna: { inizio: "02:00", fine: "07:30", fuso: "Europe/Rome" },
});
const pausa = segnale("2026-10-04T00:00:00Z").pausa_notturna;
const t = (iso: string) => Date.parse(iso);

// 4 ottobre 2026: ora legale (CEST, UTC+2). 15 gennaio 2027: ora solare (CET, UTC+1).

describe("minutiSenzaSegnale", () => {
  it("senza pausa di mezzo e' la differenza semplice", () => {
    // 12:00 -> 13:30 italiane (estate)
    expect(minutiSenzaSegnale(segnale("2026-10-04T10:00:00Z"), t("2026-10-04T11:30:00Z"))).toBe(90);
  });

  it("esempio dello schema: 01:55 -> 07:31 italiane = 6 minuti, nessun falso allarme", () => {
    // 01:55 CEST = 23:55Z del giorno prima; 07:31 CEST = 05:31Z
    const s = segnale("2026-10-03T23:55:00Z");
    const adesso = t("2026-10-04T05:31:00Z");
    expect(minutiSenzaSegnale(s, adesso)).toBe(6);
    expect(statoDati(s, adesso).vecchio).toBe(false);
  });

  it("stesso esempio in ora solare (CET)", () => {
    // 01:55 CET = 00:55Z; 07:31 CET = 06:31Z
    expect(minutiSenzaSegnale(segnale("2027-01-15T00:55:00Z"), t("2027-01-15T06:31:00Z"))).toBe(6);
  });

  it("ultimo controllo dentro la pausa: la pausa gia' trascorsa non conta", () => {
    // 03:00 CEST (01:00Z) -> 08:00 CEST (06:00Z): restano 30 minuti (07:30-08:00)
    expect(minutiSenzaSegnale(segnale("2026-10-04T01:00:00Z"), t("2026-10-04T06:00:00Z"))).toBe(30);
  });

  it("nel mezzo della pausa il tempo non scorre", () => {
    expect(minutiSenzaSegnale(segnale("2026-10-04T01:00:00Z"), t("2026-10-04T04:00:00Z"))).toBe(0);
  });

  it("tre notti attraversate sottraggono tre pause", () => {
    // 01:55 CEST sabato -> 07:31 CEST lunedi = 2 giorni + 5h36, meno le pause di sabato, domenica e lunedi
    const s = segnale("2026-10-02T23:55:00Z");
    expect(minutiSenzaSegnale(s, t("2026-10-05T05:31:00Z"))).toBe(2 * 24 * 60 + 336 - 3 * 330);
  });

  it("segnale vecchio davvero: oltre soglia anche tolta la pausa", () => {
    const s = segnale("2026-10-04T06:00:00Z"); // 08:00 CEST
    const dopo = statoDati(s, t("2026-10-04T08:30:01Z")); // 10:30 CEST = 150 min
    expect(dopo).toEqual({ vecchio: true, minuti: 150 });
  });

  it("alla soglia esatta non avvisa, un minuto oltre si", () => {
    const s = segnale("2026-10-04T10:00:00Z");
    expect(statoDati(s, t("2026-10-04T12:00:00Z")).vecchio).toBe(false);
    expect(statoDati(s, t("2026-10-04T12:01:00Z")).vecchio).toBe(true);
  });

  it("orologio del telefono indietro rispetto al bot: mai negativo", () => {
    expect(minutiSenzaSegnale(segnale("2026-10-04T10:00:00Z"), t("2026-10-04T09:00:00Z"))).toBe(0);
  });

  it("segnale illeggibile = vecchio", () => {
    const s = segnale("non-una-data");
    expect(statoDati(s, Date.now()).vecchio).toBe(true);
  });
});

describe("minutiInPausa", () => {
  it("giornata intera contiene una pausa di 330 minuti", () => {
    expect(minutiInPausa(t("2026-10-04T08:00:00Z"), t("2026-10-05T08:00:00Z"), pausa)).toBe(330);
  });
  it("intervallo che finisce prima della pausa: zero", () => {
    expect(minutiInPausa(t("2026-10-04T10:00:00Z"), t("2026-10-04T20:00:00Z"), pausa)).toBe(0);
  });
  it("cambio d'ora solare (25 ottobre 2026): la pausa resta 02:00-07:30 italiane", () => {
    // notte di 25h: dalle 00:00 CEST (22:00Z del 24) alle 12:00 CET (11:00Z del 25)
    const m = minutiInPausa(t("2026-10-24T22:00:00Z"), t("2026-10-25T11:00:00Z"), pausa);
    // 02:00 CEST = 00:00Z; 07:30 CET = 06:30Z -> 6h30 = 390 min (la notte ha un'ora in piu')
    expect(m).toBe(390);
  });
});
