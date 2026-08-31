"""
Helper condiviso da app.py e bot_telegram.py per le chiamate a servizi esterni
(Football-Data.org, e potenzialmente altri in futuro).

Perché esiste: prima ogni chiamata a requests.get() falliva subito al primo blip
di rete, facendo scattare i vari "Dati live non disponibili" / "Errore di
connessione" anche per un timeout isolato di una frazione di secondo — capitato
più volte durante l'incidente Football-Data del 30/08/2026. Un retry con
backoff esponenziale copre questi blip transitori senza mascherare un guasto
vero (dopo N tentativi, l'eccezione viene comunque rilanciata al chiamante,
che la gestisce come ha sempre fatto).
"""
import time
import requests


def richiedi_con_retry(url, headers=None, timeout=10, tentativi=3, backoff_base=1.5):
    """GET con retry ed exponential backoff.

    - tentativi=3: al massimo 3 richieste totali (1 + 2 retry).
    - backoff_base=1.5: attese di ~1.5s poi ~2.25s tra un tentativo e l'altro.
    - Rilancia raise_for_status(): un errore HTTP (es. 429, 500) viene trattato
      come fallimento vero e passa dai retry, invece di restituire silenziosamente
      un corpo d'errore che verrebbe letto come se fosse un JSON valido.
    - Se anche l'ultimo tentativo fallisce, rilancia l'eccezione originale: il
      chiamante continua a gestirla con il proprio try/except, come prima.
    """
    ultimo_errore = None
    for tentativo in range(1, tentativi + 1):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            ultimo_errore = e
            if tentativo < tentativi:
                time.sleep(backoff_base ** tentativo)
    raise ultimo_errore
