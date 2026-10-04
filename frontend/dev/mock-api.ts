/**
 * API finte per `npm run dev` (nessun Cloudflare, nessuna chiamata a Football-Data).
 * Legge lo snapshot VERO locale (restyling/snapshot-locale.json, gitignored: genera con
 * `python3 scripts/genera_snapshot_locale.py`, una volta) e simula Worker e segnale del bot.
 *
 * Prove utili, aggiungendo un parametro all'indirizzo della pagina:
 *   ?devEta=300        il segnale risulta di 300 minuti fa (per vedere l'avviso "dati vecchi")
 *   ?devSegnale=assente   /api/segnale risponde 404
 *   ?devSnapshot=errore   /api/snapshot risponde 500
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Plugin } from "vite";

const FILE = resolve(import.meta.dirname, "../../restyling/snapshot-locale.json");

interface PartitaMin { id: number; giornata: number; inizio_il: string | null; ufficiale: boolean }

function json(res: import("node:http").ServerResponse, corpo: unknown, status = 200) {
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("cache-control", "no-store");
  res.end(typeof corpo === "string" ? corpo : JSON.stringify(corpo));
}

/** Risultato finto ma coerente con l'orario: passato = finita, in corso = IN_PLAY, futuro = TIMED. */
function liveFinto(partite: PartitaMin[], giornata: number, adesso: number) {
  return partite
    .filter((p) => p.giornata === giornata && p.ufficiale && p.id > 0)
    .map((p) => {
      const inizio = p.inizio_il ? Date.parse(p.inizio_il) : NaN;
      const min = (adesso - inizio) / 60_000;
      const gol = (s: number) => (p.id * s + 7) % 4; // deterministico
      if (Number.isNaN(inizio) || min < 0) {
        return { id: p.id, stato: "TIMED", gol_casa: null, gol_ospite: null, inizio_il: p.inizio_il };
      }
      if (min < 115) {
        return { id: p.id, stato: min >= 47 && min <= 62 ? "PAUSED" : "IN_PLAY", gol_casa: gol(3) % 3, gol_ospite: gol(5) % 2, inizio_il: p.inizio_il, minuto: Math.min(90, Math.floor(min)) };
      }
      return { id: p.id, stato: "FINISHED", gol_casa: gol(3), gol_ospite: gol(5) % 3, inizio_il: p.inizio_il };
    });
}

export function apiFinte(): Plugin {
  return {
    name: "toto-api-finte",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = new URL(req.url ?? "/", "http://localhost");
        if (!url.pathname.startsWith("/api/")) return next();

        if (!existsSync(FILE)) {
          return json(res, { errore: "manca restyling/snapshot-locale.json: python3 scripts/genera_snapshot_locale.py" }, 503);
        }
        const testo = readFileSync(FILE, "utf8");
        const snap = JSON.parse(testo) as { generato_il: string; partite: PartitaMin[] };

        if (url.pathname === "/api/snapshot") {
          return url.searchParams.get("devSnapshot") === "errore" ? json(res, { errore: "finto" }, 500) : json(res, testo);
        }
        if (url.pathname === "/api/segnale") {
          if (url.searchParams.get("devSegnale") === "assente") return json(res, { errore: "finto" }, 404);
          const eta = Number(url.searchParams.get("devEta") ?? 0);
          const ultimo = new Date(Date.now() - (Number.isFinite(eta) ? eta : 0) * 60_000).toISOString().replace(/\.\d+Z$/, "Z");
          // impronta stabile finche' il file non cambia: il sito non riscarica lo snapshot a ogni controllo
          const impronta = createHash("sha256").update(testo).digest("hex");
          return json(res, {
            versione_schema: 1,
            ultimo_controllo_il: ultimo,
            generato_il: snap.generato_il,
            impronta,
            soglia_allarme_minuti: 120,
            pausa_notturna: { inizio: "02:00", fine: "07:30", fuso: "Europe/Rome" },
          });
        }
        if (url.pathname === "/api/live") {
          const g = Number(url.searchParams.get("giornata"));
          if (!Number.isInteger(g) || g < 1 || g > 38) return json(res, { errore: "giornata non valida (1-38)" }, 400);
          return json(res, { giornata: g, partite: liveFinto(snap.partite, g, Date.now()) });
        }
        return json(res, { errore: "non trovato" }, 404);
      });
    },
  };
}
