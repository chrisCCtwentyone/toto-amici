import { consumaBudget, riduciPartite, validaGiornata } from "./live";
import {
  erroriSchedina, improntaPassword, leggiInvio, normalizzaPassword, type Consegna, type GiornataAperta,
} from "./schedina";

interface Env {
  SNAPSHOT: KVNamespace;
  ASSETS: Fetcher;
  /** secret: wrangler secret put FOOTBALL_DATA_KEY (mai nel browser, mai nel repo) */
  FOOTBALL_DATA_KEY?: string;
}

const JSON_HDR = "application/json; charset=utf-8";
// Cache condivisa dei risultati live: il tetto di Football-Data (10 richieste/minuto)
// e' CONDIVISO col bot in produzione, quindi una sola chiamata ogni 120 s per giornata.
const TTL_LIVE_S = 120;
const TTL_LIVE_ERRORE_S = 30; // anche l'errore va in cache: niente raffica di retry su un 429

// Intestazioni di sicurezza anche sulle risposte /api/* (il file public/_headers vale solo per i file statici).
const SICUREZZA = {
  "x-content-type-options": "nosniff",
  "referrer-policy": "strict-origin-when-cross-origin",
  "cross-origin-resource-policy": "same-origin",
  "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
  "x-robots-tag": "noindex, nofollow",
};

function risposta(corpo: BodyInit | null, extra: HeadersInit = {}, status = 200): Response {
  return new Response(corpo, {
    status,
    headers: { "content-type": JSON_HDR, ...SICUREZZA, ...extra },
  });
}

/** snapshot / segnale: il corpo di KV passa cosi' com'e', senza JSON.parse (10 ms di CPU). */
async function daKV(env: Env, chiave: "snapshot" | "segnale"): Promise<Response> {
  // cacheTtl 60 = minimo di KV: la lettura resta in cache nel punto di presenza piu' vicino.
  const corpo = await env.SNAPSHOT.get(chiave, { type: "stream", cacheTtl: 60 });
  if (corpo === null) {
    return risposta(JSON.stringify({ errore: `${chiave} non ancora pubblicato` }), { "cache-control": "no-store" }, 404);
  }
  return risposta(corpo, { "cache-control": "public, max-age=60" });
}

// ==========================================
// SCHEDINE DAL SITO (prova dal 31/10/2026, docs/ANALISI-SCHEDINE-SEGRETE.md)
// ==========================================
// Chiavi KV (stesso archivio dello snapshot):
//   giornata_aperta            scritta dal bot a ogni pubblicazione (pubblica_giornata_aperta)
//   password_NOME              {sale, impronta}, scritta dal bot con /password NOME
//   consegna_G<n>_NOME         la schedina, scritta qui; si sovrascrive fino alla scadenza
// Le schedine NON escono da qui prima della scadenza: e' tutto il senso della funzione.

const MAX_CORPO = 8_000;
// Le consegne restano in KV 60 giorni: bastano per la prova e per il prelievo del bot, e la
// stagione dopo non trova le schedine di quella prima sotto la stessa chiave.
const DURATA_CONSEGNA_S = 60 * 24 * 3600;
// Ogni /api/consegne costa 16 letture KV: senza questa memoria ~6.000 richieste esaurirebbero
// le 100.000 letture gratuite del giorno e il sito smetterebbe di caricare (verifica del 31/10,
// problema 8). Si tiene la LETTURA, non la risposta: aperta o chiusa si decide a ogni richiesta.
const MEMORIA_CONSEGNE_MS = 30_000;
const consegneInMemoria = new Map<number, { scade: number; trovate: Consegna[] }>();
const MAX_TENTATIVI = 5;
const BLOCCO_MS = 15 * 60_000;
// ponytail: contatore dei tentativi per isolate e in memoria (niente scritture KV: uno spam di
// password sbagliate brucerebbe le 1.000 scritture/giorno che servono al bot). Se servisse un
// tetto globale: binding Rate Limiting di Workers.
const tentativi = new Map<string, { n: number; fino: number }>();

const NO_STORE = { "cache-control": "no-store" };
const errore = (status: number, testo: string, extra: Record<string, unknown> = {}) =>
  risposta(JSON.stringify({ errore: testo, ...extra }), NO_STORE, status);

async function leggiAperta(env: Env): Promise<GiornataAperta | null> {
  return env.SNAPSHOT.get<GiornataAperta>("giornata_aperta", { type: "json", cacheTtl: 60 });
}

const scaduta = (aperta: GiornataAperta, ora: number) => ora >= Date.parse(aperta.scadenza_il);

async function riceviSchedina(request: Request, env: Env): Promise<Response> {
  if (Number(request.headers.get("content-length") ?? 0) > MAX_CORPO) return errore(413, "Schedina troppo grande.");
  const testo = await request.text();
  if (testo.length > MAX_CORPO) return errore(413, "Schedina troppo grande.");
  let dati: unknown;
  try {
    dati = JSON.parse(testo);
  } catch {
    return errore(400, "Dati non validi.");
  }
  const invio = leggiInvio(dati);
  if (!invio) return errore(400, "Dati non validi.");
  const { schedina, password } = invio;

  const aperta = await leggiAperta(env);
  if (!aperta) return errore(503, "La giornata non e' ancora disponibile: riprova fra qualche minuto.");
  const ora = Date.now();
  if (scaduta(aperta, ora)) return errore(409, `Tempo scaduto: le schedine della Giornata ${aperta.giornata} sono chiuse.`);
  const errori = erroriSchedina(schedina, aperta);
  if (errori.length) return errore(422, "La schedina non e' completa.", { errori });

  const chiaveTentativi = `${schedina.giocatore}|${request.headers.get("cf-connecting-ip") ?? "?"}`;
  const t = tentativi.get(chiaveTentativi);
  if (t && t.n >= MAX_TENTATIVI && t.fino > ora) {
    return errore(429, "Troppi tentativi con la password sbagliata: riprova fra 15 minuti.");
  }
  const credenziali = await env.SNAPSHOT.get<{ sale: string; impronta: string }>(
    `password_${schedina.giocatore}`, { type: "json" },
  );
  if (!credenziali) return errore(403, "Non hai ancora una password: chiedila a un admin.");
  const enc = new TextEncoder();
  const calcolata = enc.encode(await improntaPassword(credenziali.sale, normalizzaPassword(password)));
  const attesa = enc.encode(credenziali.impronta);
  if (calcolata.byteLength !== attesa.byteLength || !crypto.subtle.timingSafeEqual(calcolata, attesa)) {
    const n = t && t.fino > ora ? t.n + 1 : 1;
    tentativi.set(chiaveTentativi, { n, fino: ora + BLOCCO_MS });
    return errore(403, "Password sbagliata.");
  }
  tentativi.delete(chiaveTentativi);

  const nomi = new Map(aperta.partite.map((p) => [p.id, `${p.casa}-${p.ospite}`]));
  const consegna: Consegna = {
    ...schedina,
    righe: schedina.righe.map((r) => ({ ...r, partita: nomi.get(r.partita_id) ?? "?" })),
    consegnata_il: new Date(ora).toISOString().replace(/\.\d{3}Z$/, "Z"),
  };
  try {
    await env.SNAPSHOT.put(`consegna_G${aperta.giornata}_${schedina.giocatore}`, JSON.stringify(consegna), {
      expirationTtl: DURATA_CONSEGNA_S,
    });
  } catch {
    return errore(503, "Non sono riuscito a salvare la schedina: riprova fra un minuto. Se non va, mandala a un admin.");
  }
  consegneInMemoria.delete(aperta.giornata);
  return risposta(JSON.stringify({ consegnata_il: consegna.consegnata_il }), NO_STORE);
}

async function consegne(env: Env, giornata: number): Promise<Response> {
  const aperta = await leggiAperta(env);
  if (!aperta) return errore(404, "La giornata non e' ancora disponibile.");
  if (giornata > aperta.giornata) return errore(404, "Giornata non ancora aperta.");
  const chiusa = giornata < aperta.giornata || scaduta(aperta, Date.now());
  const ora = Date.now();
  let trovate = consegneInMemoria.get(giornata);
  if (!trovate || trovate.scade <= ora) {
    // Una lettura per giocatore (16): niente list(), che sul piano gratuito ne ha solo 1.000 al giorno.
    const lette = await Promise.all(
      aperta.giocatori.map((g) => env.SNAPSHOT.get<Consegna>(`consegna_G${giornata}_${g}`, { type: "json" })),
    );
    trovate = { scade: ora + MEMORIA_CONSEGNE_MS, trovate: lette.filter((c): c is Consegna => c !== null) };
    consegneInMemoria.set(giornata, trovate);
  }
  const corpo = chiusa
    ? { giornata, chiusa, schedine: trovate.trovate }
    : { giornata, chiusa, consegnate: trovate.trovate.map(({ giocatore, consegnata_il }) => ({ giocatore, consegnata_il })) };
  return risposta(JSON.stringify(corpo), { "cache-control": chiusa ? "public, max-age=300" : "no-store" });
}

// Secondo livello: memoria dell'isolate. La Cache API non funziona su *.workers.dev,
// questa tiene comunque il limite finche' il Worker resta caldo (best effort).
const memoria = new Map<number, { scade: number; corpo: string }>();

const chiamateUpstream: number[] = [];

async function live(env: Env, ctx: ExecutionContext, giornata: number): Promise<Response> {
  const ora = Date.now();
  const inMemoria = memoria.get(giornata);
  if (inMemoria && inMemoria.scade > ora) {
    return risposta(inMemoria.corpo, { "cache-control": "public, max-age=60" });
  }

  const cache = caches.default;
  const chiaveCache = new Request(`https://cache.toto-amici.internal/live/${giornata}`);
  const trovata = await cache.match(chiaveCache);
  if (trovata) return trovata;

  let corpo: string;
  let ttl = TTL_LIVE_S;
  const fallito = (errore: string) => {
    ttl = TTL_LIVE_ERRORE_S;
    return JSON.stringify({ giornata, partite: [], errore });
  };

  if (!env.FOOTBALL_DATA_KEY) {
    corpo = fallito("chiave Football-Data non configurata");
  } else if (!consumaBudget(chiamateUpstream, ora)) {
    // troppe chiamate in un minuto: meglio un dato scaduto (o vuoto) che bruciare il limite del bot
    corpo = inMemoria?.corpo ?? fallito("troppe richieste, riprova fra poco");
    ttl = TTL_LIVE_ERRORE_S;
  } else {
    try {
      const r = await fetch(
        `https://api.football-data.org/v4/competitions/SA/matches?matchday=${giornata}`,
        { headers: { "X-Auth-Token": env.FOOTBALL_DATA_KEY }, signal: AbortSignal.timeout(8000) },
      );
      corpo = r.ok
        ? JSON.stringify({ giornata, partite: riduciPartite(await r.json()) })
        : fallito(`Football-Data ha risposto ${r.status}`);
    } catch {
      corpo = fallito("Football-Data non raggiungibile");
    }
  }

  memoria.set(giornata, { scade: ora + ttl * 1000, corpo });
  const daSalvare = risposta(corpo, { "cache-control": `public, max-age=${ttl}` });
  ctx.waitUntil(cache.put(chiaveCache, daSalvare.clone()));
  return daSalvare;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);

    if (url.pathname === "/api/schedina") {
      if (request.method !== "POST") {
        return risposta(JSON.stringify({ errore: "metodo non ammesso" }), { allow: "POST" }, 405);
      }
      return riceviSchedina(request, env);
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return risposta(JSON.stringify({ errore: "metodo non ammesso" }), { allow: "GET, HEAD" }, 405);
    }

    switch (url.pathname) {
      case "/api/snapshot":
        return daKV(env, "snapshot");
      case "/api/segnale":
        return daKV(env, "segnale");
      case "/api/live": {
        const giornata = validaGiornata(url.searchParams.get("giornata"));
        if (giornata === null) {
          return risposta(JSON.stringify({ errore: "giornata non valida (1-38)" }), { "cache-control": "no-store" }, 400);
        }
        return live(env, ctx, giornata);
      }
      case "/api/giornata-aperta": {
        const corpo = await env.SNAPSHOT.get("giornata_aperta", { type: "stream", cacheTtl: 60 });
        return corpo === null
          ? errore(404, "La giornata non e' ancora disponibile.")
          : risposta(corpo, { "cache-control": "public, max-age=60" });
      }
      case "/api/consegne": {
        const giornata = validaGiornata(url.searchParams.get("giornata"));
        if (giornata === null) return errore(400, "giornata non valida (1-38)");
        return consegne(env, giornata);
      }
      default:
        return risposta(JSON.stringify({ errore: "non trovato" }), {}, 404);
    }
  },
} satisfies ExportedHandler<Env>;
