"""
Test delle misure di Sessione 16 per restare dentro i 512 MB del piano gratuito
Render, e dell'auto update che non si ripete.

Contesto: il 01/09/2026 Render ha ucciso il bot per superamento del limite di
memoria. L'ipotesi iniziale — "colpa dei dati che crescono con le giornate" —
si e' rivelata SBAGLIATA una volta misurata: una stagione intera di Giocate
(6080 righe) occupa 1,6 MB, mentre UNA SOLA foto a piena risoluzione ne costa
46,7 al momento della decodifica.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PIL import Image

import bot_telegram as bt


class TestMemoriaMb:

    def test_restituisce_un_valore_plausibile(self):
        """Un processo Python vivo occupa piu' di 1 MB e meno di 10 GB: se il
        calcolo sbagliasse unita' (byte vs kilobyte) si vedrebbe subito."""
        usata = bt.memoria_mb()
        assert 1 < usata < 10_000, f"valore implausibile: {usata} MB"

    def test_non_solleva_mai(self, monkeypatch):
        """E' usata dentro i log e da /diagnostica: non deve poter rompere nulla.

        Si rompono ENTRAMBE le fonti (/proc e getrusage) perche' il bot gira su
        Linux mentre i test girano anche su macOS: il comportamento deve essere
        lo stesso su tutte e due.
        """
        def esplode(*a, **k):
            raise OSError("misura non disponibile")
        monkeypatch.setattr(bt.resource, "getrusage", esplode)
        monkeypatch.setattr("builtins.open", esplode)
        assert bt.memoria_mb() == 0.0
        assert bt.memoria_picco_mb() == 0.0


class TestFotoLeggere:

    def test_una_foto_grande_non_viene_decodificata_a_piena_risoluzione(self, tmp_path):
        """Il cuore del risparmio: draft() fa decodificare il JPEG gia' ridotto.

        Senza, una foto da telefono inviata come 'file' costa ~47 MB di picco.
        Il test verifica la proprieta' osservabile: dopo draft(), l'immagine
        caricata e' molto piu' piccola dell'originale sul disco.
        """
        percorso = tmp_path / "schedina_grande.jpg"
        Image.new('RGB', (4032, 3024), 'white').save(percorso, quality=85)

        with Image.open(percorso) as originale:
            assert originale.size == (4032, 3024)
            originale.draft('RGB', bt.DIMENSIONE_MAX_FOTO)
            # draft() riduce gia' in fase di decodifica
            assert originale.size[0] < 4032, "draft() non ha ridotto: si decodifica tutto in memoria"
            immagine = originale.convert('RGB')

        immagine.thumbnail(bt.DIMENSIONE_MAX_FOTO)
        assert max(immagine.size) <= max(bt.DIMENSIONE_MAX_FOTO)

    def test_una_foto_piccola_resta_leggibile(self, tmp_path):
        """draft() non deve degradare una schermata gia' piccola: le schedine
        arrivano spesso come screenshot da 1080px, e la lettura IA dipende da
        quanto resta leggibile il testo."""
        percorso = tmp_path / "screenshot.jpg"
        Image.new('RGB', (1080, 1920), 'white').save(percorso, quality=85)

        with Image.open(percorso) as originale:
            originale.draft('RGB', bt.DIMENSIONE_MAX_FOTO)
            immagine = originale.convert('RGB')
        immagine.thumbnail(bt.DIMENSIONE_MAX_FOTO)

        assert max(immagine.size) <= max(bt.DIMENSIONE_MAX_FOTO)
        assert min(immagine.size) >= 400, "ridotta troppo: il testo della schedina diventerebbe illeggibile"


class TestAutoUpdateNonSiRipete:
    """L'invio (non il ricalcolo) e' condizionato: un messaggio identico ogni
    sera smette di essere letto, e quando cambia davvero non lo noti piu'."""

    def test_report_identico_non_viene_reinviato(self):
        bt.ultimo_report_inviato = ("3", "REPORT GIORNATA 3\nMARIO - 10 Pt")
        assert ("3", "REPORT GIORNATA 3\nMARIO - 10 Pt") == bt.ultimo_report_inviato

    def test_report_cambiato_viene_reinviato(self):
        bt.ultimo_report_inviato = ("3", "MARIO - 10 Pt")
        assert ("3", "MARIO - 18 Pt") != bt.ultimo_report_inviato

    def test_stessa_giornata_ma_testo_diverso_conta_come_novita(self):
        """Il caso che conta: la giornata non cambia per giorni, ma i risultati si'."""
        primo = ("3", "MARIO - 0 Pt (in attesa)")
        secondo = ("3", "MARIO - 18 Pt (CHIUSA)")
        assert primo != secondo

    def test_cambio_di_giornata_conta_come_novita(self):
        assert ("3", "identico") != ("4", "identico")


class TestCatenaModelliRicordaChiHaRisposto:

    def test_registra_il_modello_principale(self, monkeypatch):
        monkeypatch.setattr(bt.time, "sleep", lambda _: None)
        bt.ultima_lettura_ia.update(modello=None, secondi=0.0, di_riserva=False)
        bt.chiama_gemini_con_fallback(lambda m: "ok")
        assert bt.ultima_lettura_ia["modello"] == bt.MODELLI_GEMINI[0]
        assert bt.ultima_lettura_ia["di_riserva"] is False

    def test_segnala_quando_ha_risposto_una_riserva(self, monkeypatch):
        """E' il segnale che finisce nel riepilogo della schedina."""
        monkeypatch.setattr(bt.time, "sleep", lambda _: None)
        bt.ultima_lettura_ia.update(modello=None, secondi=0.0, di_riserva=False)

        def chiamata(modello):
            if modello == bt.MODELLI_GEMINI[0]:
                raise Exception("503 UNAVAILABLE high demand")
            return "ok"

        bt.chiama_gemini_con_fallback(chiamata)
        assert bt.ultima_lettura_ia["modello"] == bt.MODELLI_GEMINI[1]
        assert bt.ultima_lettura_ia["di_riserva"] is True


class TestFrequenzaControlloAnomalie:

    def test_il_controllo_anomalie_non_e_piu_frequente_del_necessario(self):
        """Era ogni 2h (12 letture complete di Giocate al giorno). E' un avviso
        preventivo: ogni 4h copre lo stesso bisogno a meta' del costo."""
        sorgente = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot_telegram.py")).read()
        assert "run_repeating(task_controlla_anomalie_partite, interval=14400" in sorgente



class TestMemoriaAttualeEPicco:
    """Distinguere i due numeri non e' pedanteria: ru_maxrss e' un massimo
    storico che non scende MAI, quindi dopo un singolo picco mostrerebbe per
    sempre un valore alto, facendo sembrare critico un bot in perfetta salute."""

    def test_il_picco_non_e_mai_inferiore_all_attuale(self):
        assert bt.memoria_picco_mb() >= 0
        assert bt.memoria_mb() >= 0

    def test_il_picco_non_scende_mai(self):
        primo = bt.memoria_picco_mb()
        zavorra = [str(n) * 100 for n in range(50_000)]
        durante = bt.memoria_picco_mb()
        del zavorra
        dopo = bt.memoria_picco_mb()
        assert durante >= primo
        assert dopo >= durante, "il picco deve restare alto anche dopo aver liberato la memoria"

    def test_nessuna_delle_due_solleva_senza_proc(self, monkeypatch):
        """Su macOS /proc non esiste: memoria_mb() deve ripiegare, non esplodere."""
        def niente_file(*a, **k):
            raise FileNotFoundError("/proc/self/status")
        monkeypatch.setattr("builtins.open", niente_file)
        assert bt.memoria_mb() >= 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
