/**
 * Pagina aperta da prima di un deploy: le schede sono blocchi di codice a parte, quelli
 * vecchi spariscono col deploy e il server risponde con l'HTML (fallback SPA). Vite lo
 * segnala con l'evento `vite:preloadError`: si ricarica la pagina, che prende i blocchi nuovi.
 *
 * Una sola volta: se dopo la ricarica il blocco manca ancora (deploy rotto) si lascia
 * passare l'errore invece di ricaricare all'infinito. L'orario dell'ultima ricarica sta in
 * sessionStorage; se sessionStorage non si legge o non si scrive, niente ricarica (meglio
 * una scheda rotta che un ciclo senza fine).
 */
const CHIAVE = "toto-ricarica-dopo-deploy";
const PAUSA_MS = 60_000;

type Archivio = Pick<Storage, "getItem" | "setItem">;

/** true = ricarica avviata (l'errore va soppresso), false = l'errore deve passare. */
export function ricaricaUnaVolta(archivio: () => Archivio, adesso: number, ricarica: () => void): boolean {
  try {
    const s = archivio();
    const ultima = Number(s.getItem(CHIAVE));
    if (ultima && adesso - ultima < PAUSA_MS) return false;
    s.setItem(CHIAVE, String(adesso));
  } catch {
    return false;
  }
  ricarica();
  return true;
}

export function installaRicaricaDopoDeploy(): void {
  window.addEventListener("vite:preloadError", (evento) => {
    if (ricaricaUnaVolta(() => sessionStorage, Date.now(), () => location.reload())) evento.preventDefault();
  });
}
