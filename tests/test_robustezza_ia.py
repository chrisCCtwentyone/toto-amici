"""
Test delle due difese aggiunte in Sessione 15 dopo gli errori reali del
02/09/2026 durante il caricamento di una schedina di Giornata 3:

1. "Can't parse entities: can't find end of the entity starting at byte
   offset 522" — Telegram rifiutava il riepilogo perche' i pronostici
   normalizzati (OVER_2.5, UNDER_2.5) contengono underscore, che in Markdown
   legacy aprono il corsivo. La lettura IA era corretta: si perdeva solo per
   come veniva mostrata.
2. "503 UNAVAILABLE ... This model is currently experiencing high demand" —
   Gemini sovraccarico. Il primo rimedio (riprovare lo stesso modello) non e'
   bastato: la congestione dura minuti e si sposta tra i modelli, quindi serve
   una catena di riserve.
3. Lettura andata a buon fine ma con ZERO eventi riconosciuti su una schedina
   piena: il JSON era valido, ma con una forma diversa da quella che il codice
   pretendeva. Il fallimento peggiore, perche' silenzioso.
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

    @pytest.mark.parametrize("errore", ["503 UNAVAILABLE", "500 INTERNAL"])
    def test_considera_transitori_i_codici_giusti(self, errore):
        usati = []

        def chiamata(modello):
            usati.append(modello)
            raise Exception(errore)

        with pytest.raises(bt.GeminiSovraccarico):
            bt.chiama_gemini_con_fallback(chiamata)
        assert len(usati) == len(bt.MODELLI_GEMINI) * 2, f"'{errore}' doveva far scorrere tutta la catena"

    @pytest.mark.parametrize("errore", ["504 DEADLINE_EXCEEDED", "The read operation timed out"])
    def test_un_timeout_non_viene_ritentato_sullo_stesso_modello(self, errore):
        """Un 503 costa una frazione di secondo, un timeout ne ha gia' bruciati 60:
        riprovare lo stesso modello congestionato ne brucerebbe altri 60."""
        usati = []

        def chiamata(modello):
            usati.append(modello)
            raise Exception(errore)

        with pytest.raises(bt.GeminiSovraccarico):
            bt.chiama_gemini_con_fallback(chiamata)
        assert len(usati) == len(bt.MODELLI_GEMINI), "ogni modello doveva essere provato UNA volta sola"

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


QUOTA_BREVE = ("429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota', "
               "'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.RetryInfo', "
               "'retryDelay': '37s'}]}}")
QUOTA_GIORNALIERA = "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Quota exceeded for metric per day'}}"


class TestQuotaEsaurita:
    """16/10/2026: gemini-3.5-flash dava 429 (quota finita) e il bot, trattandolo
    come sovraccarico, bruciava tutti i tentativi in pochi secondi."""

    @pytest.fixture
    def attese(self, monkeypatch):
        """Orologio finto: sleep registra la durata e fa avanzare il tempo."""
        orologio = {"t": 0.0}
        registro = []

        def dormi(secondi):
            registro.append(secondi)
            orologio["t"] += secondi

        monkeypatch.setattr(bt, "time", type("T", (), {"time": staticmethod(lambda: orologio["t"]), "sleep": staticmethod(dormi)}))
        return registro

    @pytest.mark.parametrize("testo, atteso", [
        ("'retryDelay': '37s'", 37.0),
        ('"retryDelay": "37.5s"', 37.5),
        ("Please retry in 37.2s.", 37.2),
        ("429 RESOURCE_EXHAUSTED", None),
    ])
    def test_legge_il_ritardo_suggerito(self, testo, atteso):
        assert bt.ritardo_quota_secondi(testo) == atteso

    def test_429_con_ritardo_breve_aspetta_e_riesce(self, attese):
        usati = []

        def chiamata(modello):
            usati.append(modello)
            if len(usati) == 1:
                raise Exception(QUOTA_BREVE)
            return "letta"

        assert bt.chiama_gemini_con_fallback(chiamata) == "letta"
        assert usati == [bt.MODELLI_GEMINI[0]] * 2, "doveva riprovare lo STESSO modello dopo l'attesa"
        assert attese == [38.0], "37s suggeriti + 1s di margine"

    def test_429_senza_ritardo_passa_subito_al_successivo(self, attese):
        usati = []

        def chiamata(modello):
            usati.append(modello)
            if modello == bt.MODELLI_GEMINI[0]:
                raise Exception(QUOTA_GIORNALIERA)
            return "ok"

        assert bt.chiama_gemini_con_fallback(chiamata) == "ok"
        assert usati == [bt.MODELLI_GEMINI[0], bt.MODELLI_GEMINI[1]]
        assert attese == [], "quota giornaliera: aspettare non serve"

    def test_429_con_ritardo_troppo_lungo_non_aspetta(self, attese):
        with pytest.raises(bt.GeminiQuotaEsaurita):
            bt.chiama_gemini_con_fallback(lambda m: (_ for _ in ()).throw(Exception("429 RESOURCE_EXHAUSTED retryDelay: '300s'")))
        assert attese == []

    def test_tutti_429_solleva_quota_con_messaggio_giusto(self, attese):
        with pytest.raises(bt.GeminiQuotaEsaurita) as errore:
            bt.chiama_gemini_con_fallback(lambda m: (_ for _ in ()).throw(Exception(QUOTA_GIORNALIERA)))
        assert isinstance(errore.value, bt.GeminiSovraccarico), "i chiamanti esistenti devono continuare a funzionare"
        assert "Quota" in str(errore.value) and "sovraccaric" not in str(errore.value)
        assert errore.value.attesa_suggerita is None

    def test_attesa_totale_ha_un_tetto(self, attese):
        """4 modelli con 40s di ritardo ciascuno: si aspetta solo finche' c'e' budget."""
        quota_40 = "429 RESOURCE_EXHAUSTED retryDelay: '40s'"
        with pytest.raises(bt.GeminiQuotaEsaurita) as errore:
            bt.chiama_gemini_con_fallback(lambda m: (_ for _ in ()).throw(Exception(quota_40)))
        assert sum(attese) <= bt.MAX_ATTESA_QUOTA_TOTALE_S + len(attese)  # +1s di margine per attesa
        assert errore.value.attesa_suggerita == 40.0

    def test_quota_e_sovraccarico_misti(self, attese):
        errori = {bt.MODELLI_GEMINI[0]: QUOTA_GIORNALIERA}
        with pytest.raises(bt.GeminiQuotaEsaurita) as errore:
            bt.chiama_gemini_con_fallback(lambda m: (_ for _ in ()).throw(Exception(errori.get(m, SOVRACCARICO))))
        assert errore.value.anche_sovraccarico is True

    def test_503_resta_come_prima(self, attese):
        usati = []
        with pytest.raises(bt.GeminiSovraccarico) as errore:
            bt.chiama_gemini_con_fallback(lambda m: usati.append(m) or (_ for _ in ()).throw(Exception(SOVRACCARICO)))
        assert not isinstance(errore.value, bt.GeminiQuotaEsaurita)
        assert len(usati) == len(bt.MODELLI_GEMINI) * 2
        assert attese == [2.0] * len(bt.MODELLI_GEMINI), "backoff di 2s tra i due tentativi, come prima"

    def test_404_passa_al_successivo(self, attese):
        usati = []

        def chiamata(modello):
            usati.append(modello)
            if modello == bt.MODELLI_GEMINI[0]:
                raise Exception("404 NOT_FOUND")
            return "ok"

        assert bt.chiama_gemini_con_fallback(chiamata) == "ok"
        assert usati == [bt.MODELLI_GEMINI[0], bt.MODELLI_GEMINI[1]] and attese == []

    def test_chiave_non_valida_rilanciata_subito(self, attese):
        usati = []
        with pytest.raises(Exception, match="API key not valid"):
            bt.chiama_gemini_con_fallback(lambda m: usati.append(m) or (_ for _ in ()).throw(Exception("400 INVALID_ARGUMENT: API key not valid")))
        assert len(usati) == 1 and attese == []

    def test_tempo_massimo_di_scansione(self, attese, monkeypatch):
        """Ogni chiamata 'dura' 60s (timeout): ne partono 3 su 4 dentro i 180s."""
        usati = []
        orologio = bt.time

        def chiamata(modello):
            usati.append(modello)
            orologio.sleep(60)
            raise Exception("504 DEADLINE_EXCEEDED")

        with pytest.raises(bt.GeminiSovraccarico):
            bt.chiama_gemini_con_fallback(chiamata)
        assert sum(attese) <= bt.TEMPO_MAX_SCANSIONE_S
        assert len(usati) == 3, "il quarto modello non parte: finirebbe oltre i 180s"

def _quota_reale(quota_id, metrica, valore, modello="gemini-3.5-flash", ritardo="37s"):
    """Forma realistica del 429 di Gemini (repr Python, come lo stampa l'SDK)."""
    return ("429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, "
            "please check your plan and billing details.', 'status': 'RESOURCE_EXHAUSTED', 'details': ["
            "{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, "
            "{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{"
            f"'quotaMetric': '{metrica}', 'quotaId': '{quota_id}', "
            f"'quotaDimensions': {{'location': 'global', 'model': '{modello}'}}, 'quotaValue': '{valore}'}}]}}, "
            f"{{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '{ritardo}'}}]}}}}")


QUOTA_AL_GIORNO = _quota_reale("GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                               "generativelanguage.googleapis.com/generate_content_free_tier_requests", 20, ritardo="3600s")
QUOTA_AL_MINUTO_TOKEN = _quota_reale("GenerateContentInputTokensPerModelPerMinute-FreeTier",
                                     "generativelanguage.googleapis.com/generate_content_free_tier_input_token_count", 250000)


class TestDescriviQuota:
    """Serve a decidere come risparmiare quota senza pagare: sapere QUALE limite
    (giorno/minuto, richieste/token) e' stato colpito."""

    def test_richieste_al_giorno_con_limite_e_orario_di_reset(self):
        d = bt.descrivi_quota(QUOTA_AL_GIORNO)
        assert d.startswith("richieste al giorno, limite 20")
        assert f"alle {bt.ora_azzeramento_quota_giornaliera()} italiane" in d

    def test_token_al_minuto(self):
        assert bt.descrivi_quota(QUOTA_AL_MINUTO_TOKEN) == "token al minuto, limite 250000"

    def test_campi_assenti_non_rompono_niente(self):
        for testo in ("429 RESOURCE_EXHAUSTED", "", None, "quotaId", "quotaId: ,}"):
            assert bt.descrivi_quota(testo) in ("", "quota")

    def test_json_con_virgolette_doppie(self):
        assert "al minuto" in bt.descrivi_quota(QUOTA_AL_MINUTO_TOKEN.replace("'", '"'))

    def test_reset_di_mezzanotte_pacifico_e_alle_9_italiane_in_ottobre(self):
        from datetime import datetime, timezone
        assert bt.ora_azzeramento_quota_giornaliera(datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)) == "09:00"

    def test_l_eccezione_porta_il_limite_per_modello(self, monkeypatch):
        monkeypatch.setattr(bt.time, "sleep", lambda _: None)
        with pytest.raises(bt.GeminiQuotaEsaurita) as errore:
            bt.chiama_gemini_con_fallback(lambda m: (_ for _ in ()).throw(Exception(QUOTA_AL_GIORNO)))
        assert set(errore.value.limiti) == set(bt.MODELLI_GEMINI)
        assert "richieste al giorno" in errore.value.limiti[bt.MODELLI_GEMINI[0]]

    def test_diagnostica_mostra_quota_e_limite_non_il_json_grezzo(self, monkeypatch):
        class Finto:
            class models:
                @staticmethod
                def generate_content(**kw):
                    raise Exception(QUOTA_AL_GIORNO)

        monkeypatch.setattr(bt, "get_gemini_client", lambda: Finto())
        modello, _, motivo = bt._prova_un_modello("gemini-3.5-flash")
        assert motivo.startswith("quota esaurita (riprova fra 3600s): richieste al giorno, limite 20")
        assert "{" not in motivo and "sovraccarico" not in motivo

    def test_diagnostica_503_resta_sovraccarico(self, monkeypatch):
        class Finto:
            class models:
                @staticmethod
                def generate_content(**kw):
                    raise Exception(SOVRACCARICO)

        monkeypatch.setattr(bt, "get_gemini_client", lambda: Finto())
        assert bt._prova_un_modello("x")[2] == "sovraccarico"


class TestEstraiEventiPerCategoria:
    """Il 02/09/2026 il bot ha mostrato 0 eventi su una schedina piena: il JSON
    dell'IA era valido ma con una forma che il codice non riconosceva, e la
    lettura falliva in silenzio invece di segnalare l'errore."""

    EVENTO = {"partita": "Milan - Inter", "pronostico": "1", "quota": "2.10"}

    def test_forma_dichiarata_nello_schema(self):
        dati = {"vincita_potenziale": "72.50", "eventi": {"Combo": [self.EVENTO], "Fisse": [], "Doppie Chance": [], "Variabili": []}}
        assert bt.estrai_eventi_per_categoria(dati)["Combo"] == [self.EVENTO]

    def test_categorie_al_primo_livello_senza_wrapper(self):
        """Forma vista davvero da gemini-3.5-flash in una richiesta su due."""
        dati = {"vincita_potenziale": "72.50", "Combo": [self.EVENTO], "Fisse": []}
        assert bt.estrai_eventi_per_categoria(dati)["Combo"] == [self.EVENTO]

    @pytest.mark.parametrize("variante", [
        "Doppia Chance", "doppie chance", "DOPPIE CHANCE", "doppie_chance", "Doppie  Chance",
    ])
    def test_nomi_di_categoria_scritti_in_modo_diverso(self, variante):
        """Bastava 'Doppia Chance' invece di 'Doppie Chance' per perdere tutto."""
        dati = {"eventi": {variante: [self.EVENTO]}}
        assert bt.estrai_eventi_per_categoria(dati)["Doppie Chance"] == [self.EVENTO]

    def test_lista_piatta_con_campo_categoria(self):
        dati = {"eventi": [dict(self.EVENTO, categoria="Fisse"), dict(self.EVENTO, categoria="Variabili")]}
        estratti = bt.estrai_eventi_per_categoria(dati)
        assert len(estratti["Fisse"]) == 1 and len(estratti["Variabili"]) == 1

    def test_restituisce_sempre_tutte_le_categorie(self):
        """Il chiamante fa .get(categoria) su tutte e quattro: non devono mancare."""
        estratti = bt.estrai_eventi_per_categoria({})
        assert set(estratti.keys()) == set(bt.CATEGORIE_SCHEDINA)
        assert all(v == [] for v in estratti.values())

    @pytest.mark.parametrize("spazzatura", [None, [], "testo", 42, {"eventi": None}, {"eventi": "boh"}])
    def test_non_esplode_su_input_malformati(self, spazzatura):
        estratti = bt.estrai_eventi_per_categoria(spazzatura)
        assert set(estratti.keys()) == set(bt.CATEGORIE_SCHEDINA)

    def test_gli_eventi_restituiti_sono_gli_stessi_oggetti(self):
        """normalizza_nomi_partite modifica ev['partita'] sul posto: se l'helper
        restituisse copie, la normalizzazione dei nomi squadra andrebbe persa."""
        evento = dict(self.EVENTO)
        dati = {"eventi": {"Combo": [evento]}}
        bt.estrai_eventi_per_categoria(dati)["Combo"][0]["partita"] = "MODIFICATO"
        assert evento["partita"] == "MODIFICATO"

    def test_lo_schema_impone_le_quattro_categorie(self):
        proprieta = bt.SCHEMA_SCHEDINA["properties"]["eventi"]["properties"]
        assert set(proprieta.keys()) == set(bt.CATEGORIE_SCHEDINA)
        assert set(bt.SCHEMA_SCHEDINA["properties"]["eventi"]["required"]) == set(bt.CATEGORIE_SCHEDINA)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
