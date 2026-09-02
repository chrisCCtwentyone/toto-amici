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


SOVRACCARICO = ("503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is "
                "currently experiencing high demand.', 'status': 'UNAVAILABLE'}}")


@pytest.fixture(autouse=True)
def niente_attese(monkeypatch):
    """I test non devono pagare il backoff reale."""
    monkeypatch.setattr(bt.time, "sleep", lambda _: None)


class TestChiamaGeminiConFallback:

    def test_successo_al_primo_colpo_non_riprova(self):
        usati = []
        assert bt.chiama_gemini_con_fallback(lambda m: usati.append(m) or "ok") == "ok"
        assert len(usati) == 1
        assert usati[0] == bt.MODELLI_GEMINI[0]

    def test_riprova_lo_stesso_modello_e_poi_riesce(self):
        """Il caso reale: 'This model is currently experiencing high demand'."""
        tentativi = []

        def chiamata(modello):
            tentativi.append(modello)
            if len(tentativi) < 2:
                raise Exception(SOVRACCARICO)
            return "letta"

        assert bt.chiama_gemini_con_fallback(chiamata) == "letta"
        assert tentativi == [bt.MODELLI_GEMINI[0], bt.MODELLI_GEMINI[0]]

    def test_passa_al_modello_di_riserva_se_il_primo_e_saturo(self):
        """Il cuore della correzione: riprovare lo stesso modello saturo non basta,
        perche' la congestione dura minuti. Deve cambiare modello."""
        usati = []

        def chiamata(modello):
            usati.append(modello)
            if modello == bt.MODELLI_GEMINI[0]:
                raise Exception(SOVRACCARICO)
            return "letta dal secondo"

        assert bt.chiama_gemini_con_fallback(chiamata) == "letta dal secondo"
        assert usati.count(bt.MODELLI_GEMINI[0]) == 2, "doveva riprovare il primo prima di cambiare"
        assert usati[-1] == bt.MODELLI_GEMINI[1]

    def test_modello_ritirato_passa_oltre_senza_riprovare(self):
        """gemini-2.5-flash e' gia' 'no longer available': la catena non deve
        sprecare tentativi su un modello che non esiste piu'."""
        usati = []

        def chiamata(modello):
            usati.append(modello)
            if modello == bt.MODELLI_GEMINI[0]:
                raise Exception("404 NOT_FOUND. This model is no longer available.")
            return "ok"

        assert bt.chiama_gemini_con_fallback(chiamata) == "ok"
        assert usati.count(bt.MODELLI_GEMINI[0]) == 1, "su un 404 non ha senso riprovare lo stesso modello"

    @pytest.mark.parametrize("errore", [
        "503 UNAVAILABLE", "429 RESOURCE_EXHAUSTED", "500 INTERNAL", "504 DEADLINE_EXCEEDED",
    ])
    def test_considera_transitori_i_codici_giusti(self, errore):
        usati = []

        def chiamata(modello):
            usati.append(modello)
            raise Exception(errore)

        with pytest.raises(bt.GeminiSovraccarico):
            bt.chiama_gemini_con_fallback(chiamata)
        assert len(usati) == len(bt.MODELLI_GEMINI) * 2, f"'{errore}' doveva far scorrere tutta la catena"

    def test_non_riprova_su_errore_definitivo(self):
        """Chiave sbagliata: riprovare (su 4 modelli!) fa solo perdere tempo."""
        usati = []

        def chiamata(modello):
            usati.append(modello)
            raise Exception("400 INVALID_ARGUMENT: API key not valid")

        with pytest.raises(Exception, match="API key not valid"):
            bt.chiama_gemini_con_fallback(chiamata)
        assert len(usati) == 1, "un errore non transitorio non deve far scorrere la catena"

    def test_se_tutti_sono_saturi_solleva_GeminiSovraccarico(self):
        """Serve un'eccezione dedicata per poter dire all'admin 'riprova tra
        qualche minuto' invece di mostrargli il JSON grezzo del 503."""
        with pytest.raises(bt.GeminiSovraccarico) as errore:
            bt.chiama_gemini_con_fallback(lambda m: (_ for _ in ()).throw(Exception(SOVRACCARICO)))
        assert "sovraccarichi" in str(errore.value)
        assert "high demand" in str(errore.value), "l'errore originale resta visibile nei log"

    def test_la_catena_contiene_piu_di_un_modello(self):
        """Invariante: con un solo modello il fallback non esisterebbe."""
        assert len(bt.MODELLI_GEMINI) >= 2
        assert len(set(bt.MODELLI_GEMINI)) == len(bt.MODELLI_GEMINI), "modelli duplicati nella catena"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
