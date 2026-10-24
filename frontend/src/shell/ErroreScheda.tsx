import { Component, type ReactNode } from "react";
import { Card, Pulsante } from "../componenti";

/**
 * Riquadro al posto della pagina bianca quando una scheda non parte. Il caso tipico: il suo
 * blocco di codice e' sparito con un deploy e la ricarica automatica (lib/ricaricaDopoDeploy)
 * non e' scattata. Senza questo React smonterebbe tutto il sito, barra delle schede compresa.
 * Sta dentro il pannello della scheda: cambiando scheda riparte da zero.
 */
export default class ErroreScheda extends Component<{ children: ReactNode }, { errore: boolean }> {
  state = { errore: false };

  static getDerivedStateFromError() {
    return { errore: true };
  }

  render() {
    if (!this.state.errore) return this.props.children;
    return (
      <Card titolo="Il sito è stato aggiornato: ricarica la pagina" bandiera="oro">
        <p className="text-ink-2">Se dopo la ricarica il problema continua, avvisa chi gestisce il torneo.</p>
        <Pulsante variante="primario" className="mt-4" onClick={() => location.reload()}>
          Ricarica la pagina
        </Pulsante>
      </Card>
    );
  }
}
