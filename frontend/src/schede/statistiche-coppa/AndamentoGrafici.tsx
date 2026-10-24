import { useEffect, useMemo, useState } from "react";
import { Card, Pulsante, StatoVuoto } from "../../componenti";
import { formattaIntero, formattaOrdinale } from "../../lib/format";
import type { RigaClassifica } from "../../tipi/snapshot";
import { alternaScelto, calcolaAndamento, coloreSerie, leggiScelti, MAX_EVIDENZIATI, sceltiIniziali, tacchePosizioni, tacchePunti, type DatiAndamento, type Scelto } from "./andamento";
import GraficoLinee from "./GraficoLinee";

const CHIAVE = "andamento-giocatori";

function leggiSalvati(nomi: string[]): Scelto[] | null {
  try {
    const grezzo = localStorage.getItem(CHIAVE);
    return grezzo === null ? null : leggiScelti(JSON.parse(grezzo), nomi);
  } catch {
    return null; // storage bloccato o contenuto rotto: si parte dal default
  }
}

/** Sintesi a parole per i lettori di schermo: ultima giornata, evidenziati (o primi tre). */
function riassunto(dati: DatiAndamento, scelti: Scelto[], dove: "punti" | "posizioni", unita: (n: number) => string): string {
  const k = dati.giornate.length - 1;
  const scelta = scelti.length > 0 ? dati.serie.filter((s) => scelti.some((c) => c.nome === s.nome)) : dati.serie.slice(0, 3);
  const elenco = scelta.map((s) => `${s.nome} ${unita(s[dove][k]!)}`).join(", ");
  return `Dopo la giornata ${dati.giornate[k]}: ${elenco}. I numeri di tutti i giocatori e di tutte le giornate sono nella vista tabella.`;
}

function Tabella({ titolo, dati, dove, scelti, formato }: { titolo: string; dati: DatiAndamento; dove: "punti" | "posizioni"; scelti: Scelto[]; formato: (n: number) => string }) {
  return (
    <div>
      <h4 className="titolo-diretta mb-2 text-xl text-ink">{titolo}</h4>
      <div role="region" aria-label={`${titolo}, tabella: scorri in orizzontale`} tabIndex={0} className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <caption className="solo-lettori">{titolo}, giocatore per giornata</caption>
          <thead>
            <tr className="font-display text-base font-extrabold uppercase tracking-wide text-ink-2">
              <th scope="col" className="sticky left-0 bg-superficie py-1.5 pr-3 text-left">Giocatore</th>
              {dati.giornate.map((g) => (
                <th key={g} scope="col" aria-label={`Giornata ${g}`} className="px-2 py-1.5 text-right">G{g}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dati.serie.map((s) => {
              const c = scelti.find((x) => x.nome === s.nome);
              return (
                <tr key={s.nome} className="border-t border-linea">
                  <th scope="row" className="sticky left-0 whitespace-nowrap bg-superficie py-1.5 pr-3 text-left font-semibold">
                    <span aria-hidden="true" className="mr-2 inline-block h-2 w-2 rounded-full align-middle" style={{ background: c ? coloreSerie(c.slot) : "transparent" }} />
                    {s.nome}
                  </th>
                  {s[dove].map((v, i) => (
                    <td key={dati.giornate[i]} className="tabulare px-2 py-1.5 text-right">{formato(v)}</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** «L'andamento»: due grafici a linee (punti e posizione) con i giocatori scelti messi in risalto. Solo presentazione. */
export default function Andamento({ giocatori }: { giocatori: RigaClassifica[] }) {
  const dati = useMemo(() => calcolaAndamento(giocatori), [giocatori]);
  const nomi = useMemo(() => giocatori.map((g) => g.nome), [giocatori]);
  const [scelti, setScelti] = useState<Scelto[]>(() => leggiSalvati(nomi) ?? sceltiIniziali(nomi));
  const [tabella, setTabella] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(CHIAVE, JSON.stringify(scelti));
    } catch {
      /* la scelta vale solo per questa visita */
    }
  }, [scelti]);

  if (dati.giornate.length === 0) {
    return <StatoVuoto titolo="Ancora nessun punteggio">I grafici compariranno dopo la prima giornata con dei punti.</StatoVuoto>;
  }

  // un giocatore salvato che non c'e' piu' nello snapshot non si disegna
  const attivi = scelti.filter((s) => nomi.includes(s.nome));
  const pieno = attivi.length >= MAX_EVIDENZIATI;
  const maxPunti = Math.max(1, ...dati.serie.map((s) => s.punti[s.punti.length - 1]!));
  const tPunti = tacchePunti(maxPunti);
  const n = giocatori.length;

  return (
    <Card>
      <div role="group" aria-label="Giocatori da mettere in risalto" className="mb-1">
        <div className="scorri-nascosto -mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0">
          <button
            type="button"
            aria-pressed={attivi.length === 0}
            onClick={() => setScelti([])}
            className={`obliquo min-h-11 flex-none cursor-pointer px-4 transition-colors duration-150 ${attivi.length === 0 ? "bg-accento text-su-accento" : "border border-linea bg-superficie-2 text-ink-2 hover:text-ink"}`}
          >
            <span className="contro-obliquo block font-display text-lg font-extrabold uppercase tracking-wide">Tutti</span>
          </button>
          {nomi.map((nome) => {
            const c = attivi.find((s) => s.nome === nome);
            return (
              <button
                key={nome}
                type="button"
                aria-pressed={c !== undefined}
                disabled={!c && pieno}
                onClick={() => setScelti(alternaScelto(attivi, nome))}
                className={`obliquo min-h-11 flex-none cursor-pointer px-4 transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40 ${c ? "border-b-4 bg-superficie-2 text-ink" : "border border-linea text-ink-2 hover:text-ink"}`}
                style={c ? { borderBottomColor: coloreSerie(c.slot) } : undefined}
              >
                <span className="contro-obliquo flex items-center gap-2 font-display text-lg font-extrabold uppercase tracking-wide">
                  {c && <span aria-hidden="true" className="h-2.5 w-2.5 flex-none rounded-full" style={{ background: coloreSerie(c.slot) }} />}
                  {nome}
                </span>
              </button>
            );
          })}
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <p role="status" className="text-sm text-ink-2">
            {pieno ? "Massimo 4 alla volta: togline uno per sceglierne un altro." : "Scegli fino a 4 giocatori da mettere in risalto."}
          </p>
          <Pulsante aria-pressed={tabella} onClick={() => setTabella((t) => !t)} className="text-base">
            {tabella ? "Mostra come grafico" : "Mostra come tabella"}
          </Pulsante>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-[minmax(0,1fr)] gap-6">
        {tabella ? (
          <>
            <Tabella titolo="Punti in classifica" dati={dati} dove="punti" scelti={attivi} formato={formattaIntero} />
            <Tabella titolo="Posizione in classifica" dati={dati} dove="posizioni" scelti={attivi} formato={formattaOrdinale} />
          </>
        ) : (
          <>
            <GraficoLinee
              titolo="Punti in classifica"
              sottotitolo="I punti messi insieme giornata dopo giornata: più la linea sale, meglio va."
              riassunto={riassunto(dati, attivi, "punti", (v) => `${formattaIntero(v)} punti`)}
              giornate={dati.giornate}
              serie={dati.serie.map((s) => ({ nome: s.nome, valori: s.punti }))}
              scelti={attivi}
              invertito={false}
              min={0}
              max={tPunti[tPunti.length - 1]!}
              tacche={tPunti}
              formatoValore={formattaIntero}
            />
            <GraficoLinee
              titolo="Posizione in classifica"
              sottotitolo="In che posto eri dopo ogni giornata: il 1° è in cima."
              riassunto={riassunto(dati, attivi, "posizioni", (v) => `${formattaOrdinale(v)} posto`)}
              giornate={dati.giornate}
              serie={dati.serie.map((s) => ({ nome: s.nome, valori: s.posizioni }))}
              scelti={attivi}
              invertito
              min={1}
              max={n}
              tacche={tacchePosizioni(n)}
              formatoValore={formattaOrdinale}
            />
          </>
        )}
      </div>
    </Card>
  );
}
