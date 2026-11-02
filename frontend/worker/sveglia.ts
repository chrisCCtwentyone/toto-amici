/**
 * Sveglia del bot (Cron Trigger del Worker, ogni 10 minuti). Sostituisce cron-job.org, che il
 * 02/11/2026 non riusciva a riaccendere il bot dopo la pausa notturna: il bot impiega ~53 s a
 * partire su Render free e cron-job.org gratuito si arrende a 30 s. Il Worker puo' aspettare
 * la risposta fino a 2 minuti (l'attesa di rete non conta nei 10 ms di CPU del piano free).
 *
 * La pausa e' la stessa del bot (PAUSA_NOTTURNA_INIZIO / PAUSA_NOTTURNA_FINE in bot_telegram.py):
 * se cambia li', va cambiata anche qui. Fuori pausa ogni chiamata tiene sveglio il bot (Render lo
 * spegne dopo 15 minuti senza traffico in entrata); in pausa non lo si chiama, cosi' dorme.
 */
export const URL_BOT = "https://toto-amici-bot.onrender.com/";
const INIZIO_PAUSA_MIN = 2 * 60; // 02:00 ora italiana
const FINE_PAUSA_MIN = 7 * 60 + 30; // 07:30 ora italiana (esclusa)
const ATTESA_MAX_MS = 120_000;

const orarioRoma = new Intl.DateTimeFormat("it-IT", { timeZone: "Europe/Rome", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

/** True se `quando` cade nella pausa notturna [02:00, 07:30) ora italiana. Mai l'ora UTC: con l'ora legale cambia. */
export function inPausaNotturna(quando: Date): boolean {
  const parti = orarioRoma.formatToParts(quando);
  const ora = Number(parti.find((p) => p.type === "hour")?.value);
  const minuti = Number(parti.find((p) => p.type === "minute")?.value);
  const totale = ora * 60 + minuti;
  return totale >= INIZIO_PAUSA_MIN && totale < FINE_PAUSA_MIN;
}

/**
 * Chiama il bot e aspetta che risponda (un secondo tentativo se il primo fallisce).
 * Restituisce l'esito da scrivere nei log del Worker; non solleva mai.
 */
export async function svegliaBot(quando: Date, chiama: typeof fetch = fetch): Promise<string> {
  if (inPausaNotturna(quando)) return "pausa notturna: il bot dorme, nessuna chiamata";
  let ultimo = "";
  for (let tentativo = 1; tentativo <= 2; tentativo++) {
    const inizio = Date.now();
    try {
      const r = await chiama(URL_BOT, {
        headers: { "user-agent": "toto-amici-worker-cron/1.0" },
        signal: AbortSignal.timeout(ATTESA_MAX_MS),
      });
      const secondi = ((Date.now() - inizio) / 1000).toFixed(1);
      if (r.ok) return `bot sveglio: HTTP ${r.status} in ${secondi} s (tentativo ${tentativo})`;
      ultimo = `HTTP ${r.status} in ${secondi} s`;
    } catch (e) {
      ultimo = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
    }
  }
  return `bot NON raggiungibile dopo 2 tentativi: ${ultimo}`;
}
