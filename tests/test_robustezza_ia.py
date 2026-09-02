"""
Test delle due difese aggiunte in Sessione 15 dopo gli errori reali del
02/09/2026 durante il caricamento di una schedina di Giornata 3:

1. "Can't parse entities: can't find end of the entity starting at byte
   offset 522" — Telegram rifiutava il riepilogo perche' i pronostici
   normalizzati (OVER_2.5, UNDER_2.5) contengono underscore, che in Markdown
   legacy aprono il corsivo. La lettura IA era corretta: si perdeva solo per
   come veniva mostrata.
2. "503 UNAVAILABLE ... This model is currently experiencing high demand" —
   Gemini sovraccarico, nessun retry: l'admin doveva rifare tutto a mano.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt


class TestEscapeMarkdown:

    @pytest.mark.parametrize("pronostico", ["OVER_2.5", "UNDER_2.5", "1+OVER_2.5", "X2+UNDER_2.5"])
    def test_neutralizza_gli_underscore_dei_pronostici(self, pronostico):
        """Sono i valori esatti che il prompt chiede all'IA di restituire."""
        assert "\\_" in bt.escape_markdown(pronostico)
        assert "_" not in bt.escape_markdown(pronostico).replace("\\_", "")

    def test_il_caso_reale_che_ha_rotto_il_bot(self):
        """Numero DISPARI di underscore: e' la condizione che fa fallire Telegram.

        Con tre pronostici OVER_/UNDER_ il messaggio conteneva 3 underscore non
        chiusi. Dopo l'escape non deve restarne nessuno interpretabile.
        """
        eventi = [
            {"partita": "Milan - Inter", "pronostico": "1+OVER_2.5", "quota": "2.10"},
            {"partita": "Roma - Lazio", "pronostico": "UNDER_2.5", "quota": "1.85"},
            {"partita": "Napoli - Juventus", "pronostico": "X2+OVER_2.5", "quota": "3.40"},
        ]
        msg = "🤖 **Lettura IA Completata!**\n"
        for ev in eventi:
            msg += f"- {bt.escape_markdown(ev['partita'])} -> {bt.escape_markdown(ev['pronostico'])} (@{bt.escape_markdown(ev['quota'])})\n"

        underscore_liberi = msg.replace("\\_", "").count("_")
        assert underscore_liberi == 0, "restano underscore non neutralizzati: Telegram rifiuterebbe il messaggio"
        # il grassetto scritto da noi deve invece sopravvivere
        assert "**Lettura IA Completata!**" in msg

    @pytest.mark.parametrize("carattere", ["_", "*", "`", "["])
    def test_neutralizza_tutti_i_caratteri_di_formattazione(self, carattere):
        assert bt.escape_markdown(f"Test{carattere}nome") == f"Test\\{carattere}nome"

    def test_testo_pulito_resta_invariato(self):
        assert bt.escape_markdown("Milan - Inter") == "Milan - Inter"

    @pytest.mark.parametrize("vuoto, atteso", [(None, ""), ("", "")])
    def test_valori_vuoti(self, vuoto, atteso):
        """L'IA puo' non restituire un campo: non deve far esplodere il riepilogo."""
        assert bt.escape_markdown(vuoto) == atteso

    def test_accetta_valori_non_stringa(self):
        """quota puo' arrivare come numero dal JSON dell'IA."""
        assert bt.escape_markdown(2.10) == "2.1"


class TestChiamaGeminiConRetry:

    def test_successo_al_primo_colpo_non_riprova(self):
        chiamate = []

        def chiamata():
            chiamate.append(1)
            return "ok"

        assert bt.chiama_gemini_con_retry(chiamata) == "ok"
        assert len(chiamate) == 1

    def test_riprova_sul_503_e_poi_riesce(self, monkeypatch):
        """Il caso reale: 'This model is currently experiencing high demand'."""
        monkeypatch.setattr(bt.time, "sleep", lambda _: None)
        tentativi = []

        def chiamata():
            tentativi.append(1)
            if len(tentativi) < 3:
                raise Exception("503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand.', 'status': 'UNAVAILABLE'}}")
            return "letta"

        assert bt.chiama_gemini_con_retry(chiamata) == "letta"
        assert len(tentativi) == 3

    @pytest.mark.parametrize("errore", [
        "503 UNAVAILABLE",
        "429 RESOURCE_EXHAUSTED",
        "500 INTERNAL",
    ])
    def test_considera_transitori_i_codici_giusti(self, errore, monkeypatch):
        monkeypatch.setattr(bt.time, "sleep", lambda _: None)
        tentativi = []

        def chiamata():
            tentativi.append(1)
            raise Exception(errore)

        with pytest.raises(Exception):
            bt.chiama_gemini_con_retry(chiamata)
        assert len(tentativi) == 3, f"'{errore}' doveva passare dai retry"

    def test_non_riprova_su_errore_definitivo(self, monkeypatch):
        """Chiave sbagliata: riprovare fa solo perdere tempo all'admin."""
        monkeypatch.setattr(bt.time, "sleep", lambda _: None)
        tentativi = []

        def chiamata():
            tentativi.append(1)
            raise Exception("400 INVALID_ARGUMENT: API key not valid")

        with pytest.raises(Exception, match="API key not valid"):
            bt.chiama_gemini_con_retry(chiamata)
        assert len(tentativi) == 1, "un errore non transitorio non deve passare dai retry"

    def test_dopo_i_tentativi_rilancia_l_errore_originale(self, monkeypatch):
        """Il chiamante deve continuare a vedere l'errore vero da mostrare all'admin."""
        monkeypatch.setattr(bt.time, "sleep", lambda _: None)

        def chiamata():
            raise Exception("503 UNAVAILABLE high demand")

        with pytest.raises(Exception, match="high demand"):
            bt.chiama_gemini_con_retry(chiamata)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
