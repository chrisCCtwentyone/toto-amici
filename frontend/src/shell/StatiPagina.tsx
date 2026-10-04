import { Card, Pulsante, Scheletro } from "../componenti";
import { useDati } from "../lib/DatiContext";

/** Stati a tutta pagina: caricamento, errore, schema non riconosciuto. */
export default function StatiPagina() {
  const { fase, ricarica } = useDati();

  if (fase === "caricamento") {
    return (
      <div className="mx-auto w-full max-w-5xl px-4 pt-4">
        <Scheletro righe={6} />
      </div>
    );
  }
  if (fase === "schema_non_supportato") {
    return (
      <div className="mx-auto w-full max-w-5xl px-4 pt-4">
        <Card titolo="Aggiornamento in corso" bandiera="oro">
          <p className="text-ink-2">Stiamo aggiornando il sito: i dati hanno un formato nuovo. Riprova fra qualche minuto.</p>
          <Pulsante variante="primario" className="mt-4" onClick={() => location.reload()}>
            Ricarica la pagina
          </Pulsante>
        </Card>
      </div>
    );
  }
  return (
    <div className="mx-auto w-full max-w-5xl px-4 pt-4">
      <Card titolo="Non riesco a caricare i dati" bandiera="live">
        <p className="text-ink-2">
          Probabilmente è solo un problema di connessione o un aggiornamento in corso. Riprova: se continua, avvisa chi gestisce il torneo.
        </p>
        <Pulsante variante="primario" className="mt-4" onClick={ricarica}>
          Riprova
        </Pulsante>
      </Card>
    </div>
  );
}
