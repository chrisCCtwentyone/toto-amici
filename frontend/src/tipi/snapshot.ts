/**
 * Tipi del contratto bot <-> sito (restyling/snapshot-schema.md, versione_schema 1).
 * Scritti a mano dallo schema §3-§10: se lo schema cambia, si cambia QUI e basta.
 * Timestamp = stringhe ISO 8601 UTC con la Z. Importi in euro come number.
 * `null` = valore assente (mai 0 finto).
 */

export const VERSIONE_SCHEMA_SUPPORTATA = 1;

/** §12 */
export type Esito =
  | "vinta"
  | "persa"
  | "in_corso"
  | "rinviata"
  | "da_verificare"
  | "annullata"
  | "da_giocare";
export type Tipologia = "combo" | "fisse" | "doppie_chance" | "variabili";
export type TipoSceltaGruppo = "maggioranza" | "tutti_diversi" | "nessuna";
export type NomeTurno = "ottavi" | "quarti" | "semifinali" | "finale";

/** §4 — chiave KV `segnale`, documento piccolo riletto spesso. */
export interface Segnale {
  versione_schema: number;
  ultimo_controllo_il: string;
  generato_il: string;
  impronta: string;
  soglia_allarme_minuti: number;
  pausa_notturna: { inizio: string; fine: string; fuso: string };
}

/** §5 */
export interface RigaClassifica {
  posizione: number;
  nome: string;
  punti_totali: number;
  variazione_posizione: number | null;
  punti_ultima_giornata: number | null;
  punti_per_giornata: (number | null)[];
}
export interface Ritirato {
  nome: string;
  punti_totali: number;
  punti_per_giornata: (number | null)[];
}
export interface Classifica {
  ultima_giornata_giocata: number | null;
  giocatori: RigaClassifica[];
  ritirati: Ritirato[];
}

/** §6 */
export interface Movimento {
  giornata: number | null;
  descrizione: string;
  entrata: number | null;
  saldo: number | null;
}
export interface Cassa {
  saldo: number;
  obiettivo: number;
  completamento: number;
  obiettivo_raggiunto: boolean;
  movimenti: Movimento[];
  versamenti_per_giornata: { giornata: number; versato: number }[];
}

/** §7 */
export interface SceltaGruppo {
  tipo: TipoSceltaGruppo;
  pronostici: string[];
  voti: number;
  su: number;
}
export interface Partita {
  id: number;
  giornata: number;
  nome: string;
  ufficiale: boolean;
  inizio_il: string | null;
  scelta_gruppo: SceltaGruppo;
}
export interface RigaSchedina {
  partita_id: number;
  tipologia: Tipologia | null;
  pronostico: string;
  quota: number | null;
  esito: Esito;
  punti: number;
}
export interface RiepilogoSchedina {
  vinte: number;
  perse: number;
  in_corso: number;
  rinviate: number;
  da_verificare: number;
  annullate: number;
  da_giocare: number;
}
export interface Schedina {
  giornata: number;
  giocatore: string;
  vincita_potenziale: number;
  riepilogo: RiepilogoSchedina;
  righe: RigaSchedina[];
}

/** §8 */
export interface StatGiocatore {
  nome: string;
  win_rate: number;
  quota_media: number | null;
  vinte: number;
  totali: number;
}
export interface UltimaSchedinaVinta {
  giornata: number;
  vincitori: string[];
  inizio_il: string | null;
}
export interface Premi {
  cecchino: { giocatore: string; win_rate: number; vinte: number; totali: number }[] | null;
  benedizione: { giocatore: string; win_rate: number; vinte: number; totali: number }[] | null;
  folle: { giocatore: string; quota_media: number }[] | null;
  conservatore: { giocatore: string; quota_media: number }[] | null;
  giornata_da_incorniciare: { giocatore: string; giornata: number; punti: number }[] | null;
  semper_fidelis: { giocatore: string; squadra: string; volte: number }[] | null;
  squadra_amuleto: { squadra: string; vittorie_portate: number }[] | null;
  squadra_maledetta: { squadra: string; pronostici_bruciati: number }[] | null;
}
export interface PerUnSoffio {
  giocatore: string;
  giornata: number;
  partita: string;
  pronostico: string;
  quota: number | null;
}
export interface Statistiche {
  ultima_schedina_vinta: UltimaSchedinaVinta | null;
  premi: Premi;
  per_un_soffio: PerUnSoffio[];
  giocatori: StatGiocatore[];
  ritirati: StatGiocatore[];
}

/** §9 */
export interface VoceCoppa {
  posizione: number;
  nome: string;
}
export interface SfidaCoppa {
  giocatori: [VoceCoppa | null, VoceCoppa | null];
  punti: [number | null, number | null];
  vincente: 0 | 1 | null;
}
export interface TurnoCoppa {
  turno: NomeTurno;
  giornata: number;
  sfide: SfidaCoppa[];
}
export interface Coppa {
  definitiva: boolean;
  partecipanti: number;
  tabellone_disponibile: boolean;
  prima_giornata: number;
  ultima_giornata_tabellone: number;
  turni: TurnoCoppa[];
  campione: VoceCoppa | null;
}

/** §10 */
export interface PuntiTipologia {
  base: number;
  quota_alta: number;
}
export interface Regole {
  costo_giornata: number;
  quota_partecipazione: number;
  scadenza_quota_giornata: number;
  quota_cassa_su_vincita: number;
  minuti_pubblicazione_prima_partita: number;
  soglia_quota_doppia: number;
  bonus_chiusura: number;
  giocatori: number;
  obiettivo_cassa: number;
  composizione: Record<Tipologia, number>;
  punti: Record<Tipologia, PuntiTipologia>;
  ripartizione_premi: { posizione: number; percentuale: number }[];
}

/** §3 — chiave KV `snapshot`. */
export interface Snapshot {
  versione_schema: number;
  generato_il: string;
  stagione: string;
  giornata_corrente: number | null;
  giocatori: string[];
  classifica: Classifica;
  cassa: Cassa;
  partite: Partita[];
  schedine: Schedina[];
  statistiche: Statistiche;
  coppa: Coppa;
  regole: Regole;
}

/** Risposta del Worker GET /api/live?giornata=N (non fa parte dello snapshot, Fase 3). */
export type StatoPartitaLive =
  | "SCHEDULED"
  | "TIMED"
  | "IN_PLAY"
  | "PAUSED"
  | "FINISHED"
  | "POSTPONED"
  | "SUSPENDED"
  | "CANCELLED"
  | "AWARDED"
  | string;
export interface PartitaLive {
  /** id Football-Data, uguale a Partita.id (le partite con id negativo non arrivano al Worker). */
  id: number;
  stato: StatoPartitaLive;
  gol_casa: number | null;
  gol_ospite: number | null;
  inizio_il: string | null;
  minuto?: number;
}
export interface RispostaLive {
  giornata: number;
  partite: PartitaLive[];
  /** Presente solo se Football-Data non ha risposto: `partite` e' allora vuota. */
  errore?: string;
}
