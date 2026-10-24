import { useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { motion, useReducedMotion } from "motion/react";
import { EASE_USCITA } from "../../lib/movimento";
import { coloreSerie, spaziaEtichette, type Scelto } from "./andamento";

/* Misure in px dello spazio di disegno (1 unita' = 1 px: il grafico non si scala, scorre). */
const ALTEZZA = 240;
const SOPRA = 14;
const SOTTO = 28; // fascia delle etichette G1, G2...
const SINISTRA = 14;
const DESTRA = 112; // i nomi in fondo alle linee evidenziate
const PASSO_MIN = 44; // larghezza minima di una giornata
const LARGHEZZA_ASSE = 34;
const MAX_NOME = 11;

export interface SerieGrafico {
  nome: string;
  valori: number[];
}

interface Props {
  titolo: string;
  sottotitolo: string;
  /** testo per i lettori di schermo: cosa mostra il grafico */
  riassunto: string;
  giornate: number[];
  serie: SerieGrafico[];
  scelti: Scelto[];
  /** true = il valore piu' basso sta in alto (posizioni) */
  invertito: boolean;
  min: number;
  max: number;
  tacche: number[];
  formatoValore: (n: number) => string;
}

export default function GraficoLinee({ titolo, sottotitolo, riassunto, giornate, serie, scelti, invertito, min, max, tacche, formatoValore }: Props) {
  const idDescr = useId();
  const ridotto = useReducedMotion();
  const scorrevole = useRef<HTMLDivElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const apertoInFondo = useRef(false);
  const [larghezzaVista, setLarghezzaVista] = useState(0);
  const [idx, setIdx] = useState<number | null>(null);
  const [daTastiera, setDaTastiera] = useState(false);

  // larghezza visibile del contenitore (il grafico e' largo almeno quanto lui)
  useLayoutEffect(() => {
    const el = scorrevole.current;
    if (!el) return;
    const misura = () => setLarghezzaVista(el.clientWidth);
    misura();
    const ro = new ResizeObserver(misura);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const n = giornate.length;
  const larghezza = Math.max(larghezzaVista || 300, n * PASSO_MIN + SINISTRA + DESTRA);
  const passo = n > 1 ? (larghezza - SINISTRA - DESTRA) / (n - 1) : 0;
  const x = (i: number) => (n > 1 ? SINISTRA + i * passo : SINISTRA + (larghezza - SINISTRA - DESTRA) / 2);
  const interno = ALTEZZA - SOPRA - SOTTO;
  const y = (v: number) => {
    const t = (v - min) / Math.max(max - min, 1);
    return SOPRA + (invertito ? t : 1 - t) * interno;
  };
  const scorre = larghezza > larghezzaVista + 1;

  // all'apertura si va in fondo: le giornate piu' recenti sono le piu' interessanti
  useLayoutEffect(() => {
    const el = scorrevole.current;
    if (el && larghezzaVista > 0 && !apertoInFondo.current) {
      apertoInFondo.current = true;
      el.scrollLeft = el.scrollWidth;
    }
  }, [larghezzaVista]);

  const evidenziati = scelti
    .map((s) => ({ ...s, serie: serie.find((r) => r.nome === s.nome) }))
    .filter((s): s is typeof s & { serie: SerieGrafico } => s.serie !== undefined);
  const nomiEvid = new Set(evidenziati.map((s) => s.nome));
  const senzaSelezione = evidenziati.length === 0;

  const percorso = (valori: number[]) => valori.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");

  // nomi a fine linea, distanziati se le linee finiscono vicine
  const yEtichette = spaziaEtichette(
    evidenziati.map((s) => y(s.serie.valori[n - 1]!)),
    14,
    SOPRA,
    ALTEZZA - SOTTO,
  );

  // righe del riquadro: gli evidenziati, o tutti se nessuno lo e'
  const righeTip =
    idx === null
      ? []
      : (senzaSelezione ? serie.map((r) => ({ nome: r.nome, slot: 0, valore: r.valori[idx]! })) : evidenziati.map((s) => ({ nome: s.nome, slot: s.slot, valore: s.serie.valori[idx]! }))).sort(
          (a, b) => (invertito ? a.valore - b.valore : b.valore - a.valore),
        );

  // il riquadro sta accanto alla linea verticale, sul lato dove c'e' posto nella parte visibile
  useLayoutEffect(() => {
    const t = tip.current;
    const sc = scorrevole.current;
    if (!t || !sc || idx === null) return;
    const w = t.offsetWidth;
    const cx = x(idx);
    let sinistra = cx + 12;
    if (sinistra + w > sc.scrollLeft + sc.clientWidth - 4) sinistra = cx - 12 - w;
    t.style.left = `${Math.max(sinistra, sc.scrollLeft + 4)}px`;
  });

  const daPuntatore = (ev: PointerEvent<SVGRectElement>) => {
    if (n === 0) return;
    const sinistra = ev.currentTarget.getBoundingClientRect().left;
    const i = n > 1 ? Math.round((ev.clientX - sinistra - SINISTRA) / passo) : 0;
    setDaTastiera(false);
    setIdx(Math.min(n - 1, Math.max(0, i)));
  };

  const alTasto = (ev: KeyboardEvent<HTMLDivElement>) => {
    let i: number | null;
    if (ev.key === "ArrowLeft") i = idx === null ? n - 1 : Math.max(0, idx - 1);
    else if (ev.key === "ArrowRight") i = idx === null ? n - 1 : Math.min(n - 1, idx + 1);
    else if (ev.key === "Home") i = 0;
    else if (ev.key === "End") i = n - 1;
    else if (ev.key === "Escape") i = null;
    else return;
    ev.preventDefault();
    setDaTastiera(true);
    setIdx(i);
    const sc = scorrevole.current;
    if (sc && i !== null) {
      const cx = x(i);
      if (cx - 40 < sc.scrollLeft) sc.scrollLeft = cx - 40;
      else if (cx + 40 > sc.scrollLeft + sc.clientWidth) sc.scrollLeft = cx + 40 - sc.clientWidth;
    }
  };

  const testoStato = idx === null ? "" : `Giornata ${giornate[idx]}: ${righeTip.map((r) => `${r.nome} ${formatoValore(r.valore)}`).join(", ")}`;
  const colonne = righeTip.length > 5;

  return (
    <div className="min-w-0">
      <h4 className="titolo-diretta text-xl text-ink">{titolo}</h4>
      <p className="mb-2 text-sm text-ink-2">{sottotitolo}</p>
      <p id={idDescr} className="solo-lettori">
        {riassunto}
      </p>

      <div className="flex">
        {/* asse verticale fisso: le giornate scorrono, i valori restano */}
        <svg width={LARGHEZZA_ASSE} height={ALTEZZA} aria-hidden="true" className="flex-none">
          {tacche.map((t) => (
            <text key={t} x={LARGHEZZA_ASSE - 6} y={y(t)} textAnchor="end" dominantBaseline="central" className="fill-ink-2 text-[11px]">
              {t}
            </text>
          ))}
        </svg>

        <div
          ref={scorrevole}
          role="region"
          aria-label={`${titolo}: grafico a linee, ${n} giornate. Frecce destra e sinistra per scegliere la giornata, Esc per chiudere.`}
          aria-describedby={idDescr}
          tabIndex={0}
          onKeyDown={alTasto}
          onBlur={() => setIdx(null)}
          className="min-w-0 flex-1 overflow-x-auto overscroll-x-contain"
        >
          <div className="relative" style={{ width: larghezza, height: ALTEZZA }}>
            <svg width={larghezza} height={ALTEZZA} aria-hidden="true" className="block">
              {/* griglia: linee continue, appena visibili; si fermano prima dei nomi per non attraversarli */}
              {tacche.map((t) => (
                <line key={t} x1={0} x2={x(n - 1) + 8} y1={y(t)} y2={y(t)} style={{ stroke: "var(--linea)" }} strokeWidth={1} />
              ))}

              {/* etichette delle giornate */}
              {giornate.map((g, i) => (
                <text key={g} x={x(i)} y={ALTEZZA - 8} textAnchor="middle" className={`text-[11px] ${idx === i ? "fill-ink font-bold" : "fill-ink-2"}`}>
                  G{g}
                </text>
              ))}

              {/* contesto: tutti gli altri, sottili e grigi */}
              {serie
                .filter((r) => !nomiEvid.has(r.nome))
                .map((r) => (
                  <path
                    key={r.nome}
                    d={percorso(r.valori)}
                    fill="none"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                    style={{ stroke: "var(--ink-2)" }}
                    strokeWidth={senzaSelezione ? 1.5 : 1}
                    opacity={senzaSelezione ? 0.55 : 0.28}
                  />
                ))}

              {/* linea verticale della giornata scelta */}
              {idx !== null && <line x1={x(idx)} x2={x(idx)} y1={SOPRA - 6} y2={ALTEZZA - SOTTO} style={{ stroke: "var(--ink-2)" }} strokeWidth={1} opacity={0.7} />}

              {/* evidenziati: 2px, colore della serie, nome in fondo */}
              {evidenziati.map((s, k) => {
                const ultimo = n - 1;
                const ex = x(ultimo);
                const ey = y(s.serie.valori[ultimo]!);
                const ly = yEtichette[k]!;
                const nome = s.nome.length > MAX_NOME ? `${s.nome.slice(0, MAX_NOME - 1)}…` : s.nome;
                return (
                  <g key={`${s.nome}-${s.slot}`}>
                    <motion.path
                      d={percorso(s.serie.valori)}
                      fill="none"
                      strokeWidth={2}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                      style={{ stroke: coloreSerie(s.slot) }}
                      initial={ridotto ? false : { pathLength: 0, opacity: 0 }}
                      animate={{ pathLength: 1, opacity: 1 }}
                      transition={{ duration: 0.6, ease: EASE_USCITA }}
                    />
                    <motion.g initial={ridotto ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3, delay: ridotto ? 0 : 0.4 }}>
                      {Math.abs(ly - ey) > 1 && <path d={`M${ex},${ey} L${ex + 12},${ly}`} fill="none" strokeWidth={1} style={{ stroke: coloreSerie(s.slot) }} />}
                      <circle cx={ex} cy={ey} r={4.5} strokeWidth={2} style={{ fill: coloreSerie(s.slot), stroke: "var(--superficie)" }} />
                      <line x1={ex + 12} x2={ex + 22} y1={ly} y2={ly} strokeWidth={3} strokeLinecap="round" style={{ stroke: coloreSerie(s.slot) }} />
                      <text x={ex + 27} y={ly} dominantBaseline="central" className="fill-ink text-xs font-semibold">
                        {nome}
                      </text>
                    </motion.g>
                    {idx !== null && idx !== ultimo && (
                      <circle cx={x(idx)} cy={y(s.serie.valori[idx]!)} r={4.5} strokeWidth={2} style={{ fill: coloreSerie(s.slot), stroke: "var(--superficie)" }} />
                    )}
                  </g>
                );
              })}

              {/* area sensibile: molto piu' larga dei segni; scatta sulla giornata piu' vicina */}
              <rect
                x={0}
                y={0}
                width={larghezza}
                height={ALTEZZA - SOTTO + 10}
                fill="transparent"
                onPointerMove={daPuntatore}
                onPointerDown={daPuntatore}
                onPointerLeave={(ev) => ev.pointerType === "mouse" && setIdx(null)}
              />
            </svg>

            {idx !== null && (
              <div ref={tip} className="pointer-events-none absolute top-2 z-10 max-w-[19rem] rounded-diretta border border-linea bg-superficie-2 px-3 py-2 shadow-card">
                <p className="titolo-diretta mb-1 text-base text-ink">Giornata {giornate[idx]}</p>
                <ul className={`m-0 grid list-none gap-y-0.5 p-0 ${colonne ? "grid-cols-2 gap-x-3 text-[13px]" : "grid-cols-1 gap-x-4 text-sm"}`}>
                  {righeTip.map((r) => (
                    <li key={r.nome} className={`flex min-w-0 items-center ${colonne ? "gap-1.5" : "gap-2"}`}>
                      <span
                        aria-hidden="true"
                        className="h-0.5 w-3 flex-none rounded-full"
                        style={{ background: r.slot ? coloreSerie(r.slot) : "var(--ink-2)", opacity: r.slot ? 1 : 0.6 }}
                      />
                      <strong className="tabulare font-semibold text-ink">{formatoValore(r.valore)}</strong>
                      <span className="truncate text-ink-2">{r.nome}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>

      {scorre && <p className="mt-1 text-xs text-ink-2">Scorri di lato per vedere tutte le giornate.</p>}
      <p role="status" className="solo-lettori">
        {daTastiera ? testoStato : ""}
      </p>
    </div>
  );
}
