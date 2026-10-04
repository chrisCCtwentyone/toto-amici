import { motion } from "motion/react";
import { Card, NumeroAnimato } from "../../componenti";
import type { Premi } from "../../tipi/snapshot";
import { etichettaGiornata, formattaDecimale, formattaIntero } from "../../lib/format";
import { ENTRATA } from "../../lib/movimento";
import { raggruppa } from "./logica";

/** Chi ha vinto una card, con un'eventuale nota accanto al nome (giornata, squadra). */
interface Voce {
  nome: string;
  nota?: string;
}
/** I pari merito con lo stesso valore: un solo numero grande, tutti i nomi. */
interface Gruppo {
  voci: Voce[];
  numero: number;
  formato: (n: number) => string;
  /** cosa misura il numero ("win rate", "quota media"...) */
  unita: string;
  dettaglio?: string;
}
interface Scheda {
  chiave: keyof Premi;
  /** titoli e descrizioni sono testo del sito (§17.24) */
  titolo: string;
  descrizione: string;
  bandiera: "accento" | "live" | "oro" | "marchio";
  gruppi: Gruppo[] | null;
}

const percentuale = (n: number) => `${formattaDecimale(n, 1)}%`;
const quota = (n: number) => formattaDecimale(n, 2);
const conVolte = (n: number) => `${formattaIntero(n)}×`;
const intero = (n: number) => formattaIntero(n);

/** I pari merito dell'array dello snapshot hanno lo stesso valore esatto: qui si raggruppa per il valore mostrato. */
function gruppi<T>(
  elementi: readonly T[] | null,
  voce: (e: T) => Voce,
  valore: (e: T) => number,
  formato: (n: number) => string,
  unita: string,
  dettaglio?: (e: T) => string,
): Gruppo[] | null {
  if (!elementi || elementi.length === 0) return null;
  return raggruppa(elementi, (e) => `${formato(valore(e))}|${dettaglio?.(e) ?? ""}`).map((g) => ({
    voci: g.map(voce),
    numero: valore(g[0]!),
    formato,
    unita,
    dettaglio: dettaglio?.(g[0]!),
  }));
}

const presi = (e: { vinte: number; totali: number }) => `${formattaIntero(e.vinte)}/${formattaIntero(e.totali)} pronostici presi`;

function costruisci(p: Premi): { protagonisti: Scheda[]; squadre: Scheda[] } {
  return {
    protagonisti: [
      {
        chiave: "cecchino", titolo: "Il Cecchino", descrizione: "Il win rate più alto del gruppo.", bandiera: "oro",
        gruppi: gruppi(p.cecchino, (e) => ({ nome: e.giocatore }), (e) => e.win_rate, percentuale, "win rate", presi),
      },
      {
        chiave: "benedizione", titolo: "Quello che ha bisogno di una benedizione", descrizione: "Il win rate più basso del gruppo.", bandiera: "marchio",
        gruppi: gruppi(p.benedizione, (e) => ({ nome: e.giocatore }), (e) => e.win_rate, percentuale, "win rate", presi),
      },
      {
        chiave: "folle", titolo: "Quello pazzo in culo", descrizione: "Gioca le quote più alte del gruppo.", bandiera: "live",
        gruppi: gruppi(p.folle, (e) => ({ nome: e.giocatore }), (e) => e.quota_media, quota, "quota media"),
      },
      {
        chiave: "conservatore", titolo: "Il Conservatore", descrizione: "Va sul sicuro: le quote più basse del gruppo.", bandiera: "accento",
        gruppi: gruppi(p.conservatore, (e) => ({ nome: e.giocatore }), (e) => e.quota_media, quota, "quota media"),
      },
      {
        chiave: "giornata_da_incorniciare", titolo: "Giornata da incorniciare", descrizione: "Il punteggio più alto mai fatto in una singola giornata.", bandiera: "oro",
        gruppi: gruppi(p.giornata_da_incorniciare, (e) => ({ nome: e.giocatore, nota: etichettaGiornata(e.giornata) }), (e) => e.punti, intero, "punti"),
      },
      {
        chiave: "semper_fidelis", titolo: "Semper Fidelis", descrizione: "Punta sempre sulla stessa squadra, giornata dopo giornata.", bandiera: "marchio",
        gruppi: gruppi(p.semper_fidelis, (e) => ({ nome: e.giocatore, nota: e.squadra }), (e) => e.volte, conVolte, "puntato sulla squadra"),
      },
    ],
    squadre: [
      {
        chiave: "squadra_amuleto", titolo: "La squadra amuleto", descrizione: "La più fortunata per il gruppo.", bandiera: "accento",
        gruppi: gruppi(p.squadra_amuleto, (e) => ({ nome: e.squadra }), (e) => e.vittorie_portate, intero, "vittorie portate"),
      },
      {
        chiave: "squadra_maledetta", titolo: "La squadra maledetta", descrizione: "La più scomoda da giocare.", bandiera: "live",
        gruppi: gruppi(p.squadra_maledetta, (e) => ({ nome: e.squadra }), (e) => e.pronostici_bruciati, intero, "pronostici bruciati"),
      },
    ],
  };
}

function CardPremio({ scheda, indice }: { scheda: Scheda; indice: number }) {
  const { gruppi: gg } = scheda;
  const parimerito = gg ? gg.reduce((n, g) => n + g.voci.length, 0) : 0;
  return (
    // l'entrata sta sul div esterno: Card ha gia' un'ombra e non deve sapere di motion
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...ENTRATA, duration: 0.4, delay: indice * 0.05 }}
      className="h-full"
    >
      <Card bandiera={scheda.bandiera} className="h-full">
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
          <h3 className="titolo-diretta text-[1.4rem] leading-[1.05] text-ink">{scheda.titolo}</h3>
          {parimerito > 1 && (
            <span className="obliquo bg-oro px-2.5 text-su-oro">
              <span className="contro-obliquo block font-display text-sm font-extrabold uppercase leading-6 tracking-wider">
                Pari merito · {parimerito}
              </span>
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-ink-2">{scheda.descrizione}</p>

        {gg === null ? (
          <p role="img" className="mt-4 font-display text-4xl font-extrabold text-ink-2" aria-label="Nessun dato">—</p>
        ) : (
          <div className="mt-3 divide-y divide-linea">
            {gg.map((g) => (
              <div key={g.voci.map((v) => v.nome).join("|")} className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0">
                <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0">
                  {g.voci.map((v) => (
                    <li key={v.nome} className="min-w-0">
                      <span className="font-display text-[1.65rem] font-extrabold uppercase leading-7 tracking-wide text-ink [overflow-wrap:anywhere]">
                        {v.nome}
                      </span>
                      {v.nota && (
                        <span className="ml-2 text-sm font-semibold text-accento-testo">
                          <span aria-hidden="true">→ </span>
                          <span className="solo-lettori">, </span>
                          {v.nota}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
                <p className="m-0 flex flex-wrap items-baseline gap-x-2">
                  <span className="font-display text-[2.75rem] font-extrabold leading-none text-accento-testo">
                    <NumeroAnimato valore={g.numero} formato={g.formato} />
                  </span>
                  <span className="text-sm font-semibold text-ink-2">{g.unita}</span>
                </p>
                {g.dettaglio && <p className="m-0 text-sm text-ink-2">{g.dettaglio}</p>}
              </div>
            ))}
          </div>
        )}
      </Card>
    </motion.div>
  );
}

/** Le card «I protagonisti» (§8.2): chi non ha dati si nasconde, tranne amuleto e maledetta che mostrano «—». */
export function Protagonisti({ premi }: { premi: Premi }) {
  const { protagonisti } = costruisci(premi);
  const visibili = protagonisti.filter((s) => s.gruppi !== null);
  if (visibili.length === 0) return null;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {visibili.map((s, i) => <CardPremio key={s.chiave} scheda={s} indice={i} />)}
    </div>
  );
}

export function SquadreSerieA({ premi }: { premi: Premi }) {
  const { squadre } = costruisci(premi);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {squadre.map((s, i) => <CardPremio key={s.chiave} scheda={s} indice={i} />)}
    </div>
  );
}
