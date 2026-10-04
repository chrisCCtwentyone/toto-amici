import { consumaBudget, riduciPartite, validaGiornata } from "./live";

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
      default:
        return risposta(JSON.stringify({ errore: "non trovato" }), {}, 404);
    }
  },
} satisfies ExportedHandler<Env>;
