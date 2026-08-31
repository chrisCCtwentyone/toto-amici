"""
Test di api_utils.richiedi_con_retry — il retry con backoff usato da app.py
e bot_telegram.py per le chiamate a Football-Data.org.

Nessuna chiamata di rete reale: requests.get viene sempre sostituito con un
finto che simula successo/fallimento secondo lo scenario del test.
"""
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import requests

from api_utils import richiedi_con_retry


def _risposta_ok():
    r = MagicMock()
    r.status_code = 200
    r.raise_for_status.return_value = None
    return r


class TestRichiediConRetry:

    @patch("api_utils.requests.get")
    def test_successo_al_primo_tentativo_non_ritenta(self, mock_get):
        mock_get.return_value = _risposta_ok()
        r = richiedi_con_retry("https://esempio.test/api")
        assert r.status_code == 200
        assert mock_get.call_count == 1

    @patch("api_utils.time.sleep", return_value=None)  # niente attese reali nei test
    @patch("api_utils.requests.get")
    def test_fallisce_due_volte_poi_riesce(self, mock_get, mock_sleep):
        mock_get.side_effect = [
            requests.exceptions.ConnectionError("blip di rete"),
            requests.exceptions.Timeout("blip di rete"),
            _risposta_ok(),
        ]
        r = richiedi_con_retry("https://esempio.test/api", tentativi=3)
        assert r.status_code == 200
        assert mock_get.call_count == 3

    @patch("api_utils.time.sleep", return_value=None)
    @patch("api_utils.requests.get")
    def test_guasto_persistente_viene_rilanciato_non_mascherato(self, mock_get, mock_sleep):
        """Un guasto vero (non un blip) deve arrivare al chiamante come eccezione,
        non essere inghiottito silenziosamente: il chiamante deve poterlo gestire
        (es. mostrare "Dati live non disponibili")."""
        mock_get.side_effect = requests.exceptions.ConnectionError("server giu'")
        with pytest.raises(requests.exceptions.ConnectionError):
            richiedi_con_retry("https://esempio.test/api", tentativi=3)
        assert mock_get.call_count == 3

    @patch("api_utils.time.sleep", return_value=None)
    @patch("api_utils.requests.get")
    def test_rispetta_il_numero_di_tentativi_richiesto(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.exceptions.ConnectionError("sempre giu'")
        with pytest.raises(requests.exceptions.ConnectionError):
            richiedi_con_retry("https://esempio.test/api", tentativi=5)
        assert mock_get.call_count == 5

    @patch("api_utils.time.sleep", return_value=None)
    @patch("api_utils.requests.get")
    def test_errore_http_fa_scattare_il_retry(self, mock_get, mock_sleep):
        """Un 429/500 non deve essere letto come se fosse un JSON valido:
        raise_for_status() lo trasforma in un'eccezione vera, quindi ritenta."""
        risposta_errore = MagicMock()
        risposta_errore.status_code = 429
        risposta_errore.raise_for_status.side_effect = requests.exceptions.HTTPError("429 Too Many Requests")
        mock_get.side_effect = [risposta_errore, _risposta_ok()]

        r = richiedi_con_retry("https://esempio.test/api", tentativi=3)
        assert r.status_code == 200
        assert mock_get.call_count == 2

    @patch("api_utils.time.sleep", return_value=None)
    @patch("api_utils.requests.get")
    def test_attesa_cresce_ad_ogni_tentativo(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.exceptions.ConnectionError("giu'")
        with pytest.raises(requests.exceptions.ConnectionError):
            richiedi_con_retry("https://esempio.test/api", tentativi=3, backoff_base=2.0)
        attese = [c.args[0] for c in mock_sleep.call_args_list]
        assert attese == sorted(attese), "il backoff deve crescere, non restare piatto o diminuire"
        assert len(attese) == 2  # tra tentativo 1->2 e 2->3, non dopo l'ultimo fallimento
