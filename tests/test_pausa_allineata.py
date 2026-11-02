"""La pausa notturna e' scritta in due posti: nel bot (PAUSA_NOTTURNA_*) e nella sveglia
del Worker Cloudflare (frontend/worker/sveglia.ts, INIZIO/FINE_PAUSA_MIN). Se divergono,
o il Worker chiama il bot che dovrebbe dormire (ore Render sprecate, come a ottobre 2026)
o non lo sveglia quando dovrebbe essere acceso (bot muto, 02/11/2026)."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot_telegram as bt

SVEGLIA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "worker", "sveglia.ts")


def _minuti_ts(nome):
    sorgente = open(SVEGLIA, encoding="utf-8").read()
    m = re.search(rf"const {nome} = (\d+) \* 60(?: \+ (\d+))?;", sorgente)
    assert m, f"{nome} non trovato in sveglia.ts"
    return int(m.group(1)) * 60 + int(m.group(2) or 0)


def test_la_pausa_del_worker_coincide_con_quella_del_bot():
    inizio_bot = bt.PAUSA_NOTTURNA_INIZIO.hour * 60 + bt.PAUSA_NOTTURNA_INIZIO.minute
    fine_bot = bt.PAUSA_NOTTURNA_FINE.hour * 60 + bt.PAUSA_NOTTURNA_FINE.minute
    assert _minuti_ts("INIZIO_PAUSA_MIN") == inizio_bot
    assert _minuti_ts("FINE_PAUSA_MIN") == fine_bot
