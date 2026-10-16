"""Foto piu' leggere per Gemini e piano B gratuito Cloudflare Workers AI (16/10/2026).

Tutto con mock: nessuna chiamata vera a Gemini o Cloudflare.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PIL import Image

import bot_telegram as bt
from google.genai import types

TOKEN_FINTO = "tok-segretissimo-123"
ACCOUNT_FINTO = "acc-0123456789"

JSON_BUONO = {
    "vincita_potenziale": "72.50",
    "eventi": {
        "Combo": [{"partita": "Milan - Inter", "pronostico": "1+OVER_2.5", "quota": "2.10"}],
        "Fisse": [], "Doppie Chance": [], "Variabili": [],
    },
}


@pytest.fixture(autouse=True)
def ambiente_pulito(monkeypatch):
    monkeypatch.setattr(bt.time, "sleep", lambda _: None)
    for nome in ("LETTURA_RISERVA_CLOUDFLARE", "CLOUDFLARE_AI_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        monkeypatch.delenv(nome, raising=False)


@pytest.fixture
def riserva_accesa(monkeypatch):
    monkeypatch.setenv("LETTURA_RISERVA_CLOUDFLARE", "1")
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", TOKEN_FINTO)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT_FINTO)


@pytest.fixture
def foto(tmp_path):
    p = tmp_path / "f.jpg"
    Image.new("RGB", (2000, 1500), "white").save(p)
    return [str(p)]


class FinteRisposta:
    def __init__(self, corpo):
        self._corpo = corpo

    def json(self):
        return self._corpo


def risposta_cf(contenuto):
    return FinteRisposta({"success": True, "result": {"response": contenuto}})


class TestFotoConfigurabili:

    def test_default_invariati(self):
        assert bt.dimensione_foto_da_ambiente(None) == (1000, 1000)
        assert bt.media_resolution_da_nome("") is None
        assert bt.media_resolution_da_nome(None) is None

    def test_dimensione_da_ambiente_e_valori_assurdi(self):
        assert bt.dimensione_foto_da_ambiente("700") == (700, 700)
        for assurdo in ("10", "99999", "abc", ""):
            assert bt.dimensione_foto_da_ambiente(assurdo) == (1000, 1000)

    def test_prepara_foto_rispetta_la_dimensione(self, foto):
        assert max(bt.prepara_foto(foto, (600, 600))[0].size) <= 600
        assert max(bt.prepara_foto(foto)[0].size) <= 1000

    def test_nomi_media_resolution(self):
        assert bt.media_resolution_da_nome("low") == types.MediaResolution.MEDIA_RESOLUTION_LOW
        assert bt.media_resolution_da_nome("MEDIA_RESOLUTION_HIGH") == types.MediaResolution.MEDIA_RESOLUTION_HIGH
        assert bt.media_resolution_da_nome("boh") is None

    def test_media_resolution_arriva_davvero_nella_config(self, monkeypatch):
        monkeypatch.setattr(bt, "MEDIA_RESOLUTION_GEMINI", None)
        assert bt.config_lettura_gemini().media_resolution is None
        low = types.MediaResolution.MEDIA_RESOLUTION_LOW
        cfg = bt.config_lettura_gemini(low)
        assert cfg.media_resolution == low
        assert cfg.response_schema == bt.SCHEMA_SCHEDINA  # lo schema resta sempre
        monkeypatch.setattr(bt, "MEDIA_RESOLUTION_GEMINI", low)
        assert bt.config_lettura_gemini().media_resolution == low

    def test_la_config_arriva_a_generate_content(self, monkeypatch, foto):
        viste = []

        class Modelli:
            def generate_content(self, model, contents, config):
                viste.append(config)
                return type("R", (), {"text": json.dumps(JSON_BUONO)})()

        client = type("C", (), {"models": Modelli()})()
        monkeypatch.setattr(bt, "get_gemini_client", lambda: client)
        monkeypatch.setattr(bt, "MEDIA_RESOLUTION_GEMINI", types.MediaResolution.MEDIA_RESOLUTION_LOW)
        bt.analizza_schedine_multiple(foto)
        assert viste[0].media_resolution == types.MediaResolution.MEDIA_RESOLUTION_LOW


class TestValidazioneRiserva:

    @pytest.mark.parametrize("grezzo", [
        "", "non e' json", "[]", "{}", '{"eventi": {}}',
        json.dumps({"eventi": {"Combo": []}}),
        json.dumps({"eventi": {"Combo": [{"partita": "A - B", "pronostico": "", "quota": "2"}]}}),
        json.dumps({"eventi": {"Combo": [{"partita": "A - B", "pronostico": "1"}]}}),
    ])
    def test_vuoto_o_malformato_e_un_fallimento(self, grezzo):
        with pytest.raises(bt.LetturaRiservaFallita):
            bt.valida_lettura_riserva(grezzo)

    def test_json_buono_passa_anche_con_recinto_markdown_e_categorie_al_primo_livello(self):
        assert json.loads(bt.valida_lettura_riserva("```json\n" + json.dumps(JSON_BUONO) + "\n```"))["vincita_potenziale"] == "72.50"
        piatto = {"vincita_potenziale": "5", "Combo": JSON_BUONO["eventi"]["Combo"]}
        assert bt.estrai_eventi_per_categoria(json.loads(bt.valida_lettura_riserva(piatto)))["Combo"]

    def test_accetta_anche_oggetto_gia_parsato(self):
        assert bt.valida_lettura_riserva(JSON_BUONO)


class TestCatenaConRiserva:

    @pytest.fixture
    def gemini_esaurito(self, monkeypatch):
        def esaurito(*a, **k):
            raise bt.GeminiQuotaEsaurita("quota")
        monkeypatch.setattr(bt, "get_gemini_client", lambda: object())
        monkeypatch.setattr(bt, "leggi_con_gemini", esaurito)

    def test_senza_interruttore_comportamento_di_oggi(self, gemini_esaurito, monkeypatch, foto):
        chiamate = []
        monkeypatch.setattr(bt, "richiedi_con_retry", lambda *a, **k: chiamate.append(1))
        with pytest.raises(bt.GeminiQuotaEsaurita):
            bt.analizza_schedine_multiple(foto)
        assert chiamate == []

    def test_interruttore_acceso_ma_token_mancante(self, gemini_esaurito, monkeypatch, foto):
        monkeypatch.setenv("LETTURA_RISERVA_CLOUDFLARE", "1")
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT_FINTO)
        assert not bt.lettura_riserva_attiva()
        with pytest.raises(bt.GeminiQuotaEsaurita):
            bt.analizza_schedine_multiple(foto)

    def test_token_presente_ma_interruttore_spento(self, gemini_esaurito, monkeypatch, foto):
        monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", TOKEN_FINTO)
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT_FINTO)
        assert not bt.lettura_riserva_attiva()
        with pytest.raises(bt.GeminiQuotaEsaurita):
            bt.analizza_schedine_multiple(foto)

    def test_gemini_ok_non_tocca_cloudflare(self, riserva_accesa, monkeypatch, foto):
        monkeypatch.setattr(bt, "get_gemini_client", lambda: object())
        monkeypatch.setattr(bt, "leggi_con_gemini", lambda *a, **k: json.dumps(JSON_BUONO))
        monkeypatch.setattr(bt, "richiedi_con_retry", lambda *a, **k: pytest.fail("Cloudflare chiamato"))
        assert json.loads(bt.analizza_schedine_multiple(foto))["vincita_potenziale"] == "72.50"

    def test_passa_a_cloudflare_solo_quando_gemini_fallisce(self, riserva_accesa, gemini_esaurito, monkeypatch, foto):
        visti = {}

        def finto(url, headers=None, timeout=None, tentativi=None, metodo=None, dati=None):
            visti.update(url=url, headers=headers, metodo=metodo, corpo=json.loads(dati), timeout=timeout)
            return risposta_cf(json.dumps(JSON_BUONO))

        monkeypatch.setattr(bt, "richiedi_con_retry", finto)
        out = json.loads(bt.analizza_schedine_multiple(foto))
        assert out["eventi"]["Combo"][0]["partita"] == "Milan - Inter"
        assert visti["metodo"] == "POST" and visti["timeout"] == bt.TIMEOUT_CLOUDFLARE_AI_S
        assert visti["url"].endswith("/ai/run/" + bt.MODELLI_CLOUDFLARE_AI[0][0])
        assert visti["headers"]["Authorization"] == "Bearer " + TOKEN_FINTO
        parti = visti["corpo"]["messages"][0]["content"]
        assert parti[0] == {"type": "text", "text": bt.PROMPT_LETTURA_SCHEDINA}
        assert parti[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert visti["corpo"]["max_tokens"] >= 1024
        assert "response_format" in visti["corpo"]
        assert bt.ultima_lettura_ia["cloudflare"] is True

    def test_secondo_modello_usa_guided_json(self, riserva_accesa, monkeypatch, foto):
        corpi = []

        def finto(url, **k):
            corpi.append((url, json.loads(k["dati"])))
            if len(corpi) == 1:
                raise Exception("boom " + url)
            return risposta_cf(json.dumps(JSON_BUONO))

        monkeypatch.setattr(bt, "richiedi_con_retry", finto)
        testo, modello = bt.leggi_con_cloudflare("p", bt.prepara_foto(foto))
        assert modello == bt.MODELLI_CLOUDFLARE_AI[1][0]
        assert "guided_json" in corpi[1][1] and "response_format" not in corpi[1][1]

    @pytest.mark.parametrize("risposta", ["", "{}", "testo libero", '{"eventi": {"Combo": []}}', None])
    def test_risposta_vuota_o_malformata_non_diventa_una_schedina(self, riserva_accesa, gemini_esaurito, monkeypatch, foto, risposta):
        monkeypatch.setattr(bt, "richiedi_con_retry", lambda *a, **k: risposta_cf(risposta))
        with pytest.raises(bt.GeminiQuotaEsaurita) as info:
            bt.analizza_schedine_multiple(foto)
        assert info.value.riserva_fallita is True  # l'admin viene avvisato, niente da salvare

    def test_errore_di_rete_cloudflare_rilancia_l_errore_gemini(self, riserva_accesa, gemini_esaurito, monkeypatch, foto):
        def rotto(*a, **k):
            raise ConnectionError("giu'")
        monkeypatch.setattr(bt, "richiedi_con_retry", rotto)
        with pytest.raises(bt.GeminiQuotaEsaurita):
            bt.analizza_schedine_multiple(foto)

    def test_nessun_segreto_nei_log(self, riserva_accesa, gemini_esaurito, monkeypatch, foto, caplog):
        def rotto(url, headers=None, **k):
            raise Exception(f"401 per url {url} con {headers['Authorization']}")
        monkeypatch.setattr(bt, "richiedi_con_retry", rotto)
        with caplog.at_level("DEBUG"):
            with pytest.raises(bt.GeminiQuotaEsaurita):
                bt.analizza_schedine_multiple(foto)
        assert caplog.records
        assert TOKEN_FINTO not in caplog.text and ACCOUNT_FINTO not in caplog.text

    def test_risposta_success_false_e_choices(self, riserva_accesa, monkeypatch):
        monkeypatch.setattr(bt, "richiedi_con_retry", lambda *a, **k: FinteRisposta({"success": False, "errors": []}))
        with pytest.raises(bt.LetturaRiservaFallita):
            bt.chiama_cloudflare_ai("m", "response_format", "p", [])
        sc = {"success": True, "result": {"choices": [{"message": {"content": "xx"}}]}}
        monkeypatch.setattr(bt, "richiedi_con_retry", lambda *a, **k: FinteRisposta(sc))
        assert bt.chiama_cloudflare_ai("m", "response_format", "p", []) == "xx"


class TestScriptProvaQualita:
    """Il confronto foto -> verita' dello script (offline, nessuna API)."""

    def test_confronto_conta_esatti_mancanti_e_inventati(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
        import prova_qualita_lettura as pq
        from statistiche import abbina_partita, estrai_numero
        partite = [{"id": 1, "homeTeam": {"name": "AC Milan", "shortName": "Milan"}, "awayTeam": {"name": "FC Internazionale Milano", "shortName": "Inter"}},
                   {"id": 2, "homeTeam": {"name": "AS Roma", "shortName": "Roma"}, "awayTeam": {"name": "SS Lazio", "shortName": "Lazio"}},
                   {"id": 3, "homeTeam": {"name": "SSC Napoli", "shortName": "Napoli"}, "awayTeam": {"name": "Juventus FC", "shortName": "Juventus"}}]
        verita = [{"partita": "Milan - Inter", "pronostico": "1", "quota": "2,10"},
                  {"partita": "Roma - Lazio", "pronostico": "X2", "quota": "1,85"},
                  {"partita": "Napoli - Juventus", "pronostico": "GOAL", "quota": "1,70"}]
        letti = [{"partita": "Milan Inter", "pronostico": "1", "quota": "2.10"},       # esatto (senza trattino)
                 {"partita": "Roma - Lazio", "pronostico": "2X", "quota": "1.95"},     # pronostico ok (alias), quota diversa
                 {"partita": "Fiorentina - Torino", "pronostico": "1", "quota": "2.0"}]  # inventato; Napoli mancante
        r = pq.confronta(letti, verita, partite, abbina_partita, bt.normalizza_pronostico, estrai_numero)
        assert (r["esatti"], r["quote_esatte"], r["mancanti"], r["inventati"]) == (2, 1, 1, 1)
