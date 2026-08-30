"""
Test della logica pura di bot_telegram.py (nessuna chiamata a Sheets o Football-Data).

Perché esiste questo file: in due giorni il progetto ha subito quattro regressioni
sui dati reali del torneo (pronostico "SI" letto come vinto, "2X" idem, vincite
sopra i 1.000€ lette come 0, partite con squadre in ordine invertito mai valutate).
Tre di queste quattro sarebbero state intercettate qui in due secondi.

Esecuzione:  python3 -m pytest tests/ -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt


# =========================================================
# normalizza_pronostico — pulizia dei formati dei bookmaker
# =========================================================
class TestNormalizzaPronostico:

    @pytest.mark.parametrize("grezzo, atteso", [
        ("1", "1"), ("X", "X"), ("2", "2"),
        ("1X", "1X"), ("X2", "X2"), ("12", "12"),
        ("GOAL", "GOAL"), ("NOGOAL", "NOGOAL"),
        ("OVER_2.5", "OVER_2.5"), ("UNDER_2.5", "UNDER_2.5"),
    ])
    def test_formati_gia_corretti_restano_invariati(self, grezzo, atteso):
        assert bt.normalizza_pronostico(grezzo) == atteso

    @pytest.mark.parametrize("grezzo", ["GG", "G/G", "G", "GOL", "goal/goal"])
    def test_alias_goal(self, grezzo):
        assert bt.normalizza_pronostico(grezzo) == "GOAL"

    @pytest.mark.parametrize("grezzo", ["NG", "NO GOAL", "N/G", "no/goal"])
    def test_alias_nogoal(self, grezzo):
        assert bt.normalizza_pronostico(grezzo) == "NOGOAL"

    @pytest.mark.parametrize("grezzo", ["O2.5", "OVER 2.5", "over 2,5", "PIU DI 2.5", "+2.5"])
    def test_alias_over(self, grezzo):
        assert bt.normalizza_pronostico(grezzo) == "OVER_2.5"

    @pytest.mark.parametrize("grezzo", ["U2.5", "UNDER 2.5", "under 2,5", "MENO DI 2.5"])
    def test_alias_under(self, grezzo):
        assert bt.normalizza_pronostico(grezzo) == "UNDER_2.5"

    def test_regola_buona_fede_over_1_5_diventa_over_2_5(self):
        # Regolamento: "Over 1.5 vale solo se la partita finisce Over 2.5"
        assert bt.normalizza_pronostico("OVER 1.5") == "OVER_2.5"

    def test_regola_buona_fede_under_3_5_diventa_under_2_5(self):
        assert bt.normalizza_pronostico("UNDER 3.5") == "UNDER_2.5"

    @pytest.mark.parametrize("grezzo, atteso", [
        ("1+O2.5", "1+OVER_2.5"),
        ("2+GG", "2+GOAL"),
        ("X2+NG", "X2+NOGOAL"),
        ("1 E GG", "1+GOAL"),
        ("1&GG", "1+GOAL"),
    ])
    def test_combo(self, grezzo, atteso):
        assert bt.normalizza_pronostico(grezzo) == atteso

    # --- REGRESSIONE: incidente del 30/08/2026 (schedina Michele, Lazio-Genoa) ---
    @pytest.mark.parametrize("grezzo", ["SI", "si", "Sì", "SÌ"])
    def test_regressione_si_del_mercato_entrambe_segnano(self, grezzo):
        assert bt.normalizza_pronostico(grezzo) == "GOAL"

    @pytest.mark.parametrize("grezzo", ["NO", "no"])
    def test_regressione_no_del_mercato_entrambe_segnano(self, grezzo):
        assert bt.normalizza_pronostico(grezzo) == "NOGOAL"

    # --- REGRESSIONE: incidente del 30/08/2026 (schedina Michele, Sassuolo-Torino) ---
    @pytest.mark.parametrize("grezzo, atteso", [("2X", "X2"), ("X1", "1X"), ("21", "12")])
    def test_regressione_doppia_chance_in_ordine_invertito(self, grezzo, atteso):
        assert bt.normalizza_pronostico(grezzo) == atteso

    def test_regressione_doppia_chance_invertita_dentro_una_combo(self):
        assert bt.normalizza_pronostico("2X+GG") == "X2+GOAL"


# =========================================================
# valuta_singolo_segno / controlla_esito
# =========================================================
class TestValutaSingoloSegno:
    """Partita di riferimento: 0-3 (vince l'ospite, 3 gol totali, non entrambe a segno)."""
    CASA, OSPITE = 0, 3

    @pytest.mark.parametrize("segno, atteso", [
        ("1", False), ("X", False), ("2", True),
        ("1X", False), ("X2", True), ("12", True),
        ("GOAL", False), ("NOGOAL", True),
        ("PARI", False), ("DISPARI", True),
        ("OVER_2.5", True), ("UNDER_2.5", False),
    ])
    def test_segni_riconosciuti(self, segno, atteso):
        assert bt.valuta_singolo_segno(segno, self.CASA, self.OSPITE) is atteso

    @pytest.mark.parametrize("segno", ["SI", "2X", "X1", "1 X", "MULTIGOL_1-3", "TESTO A CASO", ""])
    def test_segni_non_riconosciuti_ritornano_none(self, segno):
        """None = "non lo so": mai indovinare, il chiamante deve segnalarlo."""
        assert bt.valuta_singolo_segno(segno, self.CASA, self.OSPITE) is None

    def test_pareggio_e_segno_x(self):
        assert bt.valuta_singolo_segno("X", 1, 1) is True
        assert bt.valuta_singolo_segno("1X", 1, 1) is True
        assert bt.valuta_singolo_segno("X2", 1, 1) is True
        assert bt.valuta_singolo_segno("12", 1, 1) is False

    def test_zero_a_zero(self):
        assert bt.valuta_singolo_segno("NOGOAL", 0, 0) is True
        assert bt.valuta_singolo_segno("GOAL", 0, 0) is False
        assert bt.valuta_singolo_segno("UNDER_2.5", 0, 0) is True
        assert bt.valuta_singolo_segno("PARI", 0, 0) is True


class TestControllaEsito:

    def test_vinta_semplice(self):
        assert "VINTA" in bt.controlla_esito("2", 0, 3)

    def test_persa_semplice(self):
        assert "PERSA" in bt.controlla_esito("1", 0, 3)

    def test_combo_vinta_solo_se_entrambi_i_segni_vincono(self):
        assert "VINTA" in bt.controlla_esito("2+OVER_2.5", 0, 3)

    def test_combo_persa_se_anche_un_solo_segno_perde(self):
        assert "PERSA" in bt.controlla_esito("2+UNDER_2.5", 0, 3)
        assert "PERSA" in bt.controlla_esito("1+OVER_2.5", 0, 3)

    def test_annullata_resta_annullata(self):
        assert "ANNULLATA" in bt.controlla_esito("1 (ANNULLATA ECCESSO)", 0, 3)

    # --- Il cuore della correzione: mai vincere per default ---
    @pytest.mark.parametrize("pronostico", [
        "SI", "2X", "X1", "MULTIGOL_1-3", "OVER 2.5", "1 X", "TESTO A CASO", "", "   ",
    ])
    def test_pronostico_non_riconosciuto_non_vince_mai(self, pronostico):
        """Prima della correzione questi restituivano tutti VINTA, regalando punti
        in silenzio. Ora devono fermarsi e chiedere una verifica umana."""
        esito = bt.controlla_esito(pronostico, 0, 3)
        assert esito == bt.ESITO_DA_VERIFICARE
        assert "VINTA" not in esito

    def test_combo_con_un_segno_ignoto_va_in_verifica_anche_se_l_altro_vince(self):
        assert bt.controlla_esito("2+QUALCOSA_DI_STRANO", 0, 3) == bt.ESITO_DA_VERIFICARE


# =========================================================
# calcola_punteggio_partita — tabella punti del regolamento
# =========================================================
class TestCalcolaPunteggio:

    @pytest.mark.parametrize("pronostico, punti_attesi", [
        ("1+OVER_2.5", 6),   # Combo
        ("1", 4), ("X", 4), ("2", 4),   # Fisse
        ("1X", 1), ("X2", 1), ("12", 1),   # Doppie chance
        ("GOAL", 2), ("NOGOAL", 2), ("OVER_2.5", 2), ("PARI", 2),   # Variabili
    ])
    def test_punti_base_con_quota_bassa(self, pronostico, punti_attesi):
        assert bt.calcola_punteggio_partita(pronostico, 1.50) == punti_attesi

    @pytest.mark.parametrize("pronostico, punti_attesi", [
        ("1+OVER_2.5", 12), ("1", 8), ("1X", 2), ("GOAL", 4),
    ])
    def test_punti_raddoppiati_da_quota_3_50(self, pronostico, punti_attesi):
        assert bt.calcola_punteggio_partita(pronostico, 3.50) == punti_attesi

    def test_soglia_raddoppio_esatta(self):
        assert bt.calcola_punteggio_partita("1", 3.49) == 4
        assert bt.calcola_punteggio_partita("1", 3.50) == 8

    def test_annullata_non_vale_punti(self):
        assert bt.calcola_punteggio_partita("1 (ANNULLATA ECCESSO)", 5.00) == 0


# =========================================================
# estrai_numero — parsing importi/quote in formato italiano
# =========================================================
class TestEstraiNumero:

    @pytest.mark.parametrize("testo, atteso", [
        ("1,5", 1.5), ("2.5", 2.5), ("3", 3.0), ("", 0.0), ("abc", 0.0),
    ])
    def test_valori_base(self, testo, atteso):
        assert bt.estrai_numero(testo) == atteso

    def test_estrae_da_stringa_con_valuta(self):
        assert bt.estrai_numero("430,00€") == 430.0

    @pytest.mark.parametrize("quota", ["1,45", "3,5", "2,05", "1,2"])
    def test_le_quote_restano_lette_correttamente(self, quota):
        assert bt.estrai_numero(quota) == float(quota.replace(',', '.'))

    # --- REGRESSIONE: vincite a quattro cifre finite in Cassa ---
    @pytest.mark.parametrize("testo, atteso", [
        ("855,70", 855.70),      # sotto i mille: funzionava gia'
        ("1.008,29", 1008.29),   # Villari, Giornata 2
        ("1.674,56", 1674.56),   # Nico, Giornata 2
        ("2.414,56", 2414.56),   # Michele, Giornata 2
        ("12.345,67", 12345.67),
    ])
    def test_regressione_separatore_delle_migliaia(self, testo, atteso):
        """Prima "1.674,56" veniva letto come 1.674: in Cassa sarebbero finiti
        0,84 EUR invece di 837,28 EUR."""
        assert bt.estrai_numero(testo) == pytest.approx(atteso)

    def test_meta_vincita_versata_in_cassa_e_corretta(self):
        # Regolamento: 50% al giocatore, 50% al Fondo Cassa
        assert bt.estrai_numero("1.008,29") / 2 == pytest.approx(504.145)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
