"""/start deve funzionare anche a meta' di un'operazione.

Il 16/10/2026 due letture lasciate senza "Salva" ne' "Annulla" hanno tenuto la
conversazione ferma in CONFERMA_LETTURA_IA: /start, unico entry point, veniva
ignorato in silenzio e il bot sembrava spento. Il test legge il sorgente, come
quelli di test_multi_admin.py: e' una regressione che non da' errori a runtime.
"""
import os
import re

SORGENTE = open(os.path.join(os.path.dirname(__file__), "..", "bot_telegram.py"), encoding="utf-8").read()


def test_conversation_handler_permette_di_rientrare_con_start():
    blocco = SORGENTE[SORGENTE.index("conv_handler = ConversationHandler("):]
    blocco = blocco[: blocco.index("app.add_handler(conv_handler")] if "app.add_handler(conv_handler" in blocco else blocco[:6000]
    assert 'CommandHandler("start", start)' in blocco
    assert re.search(r"allow_reentry\s*=\s*True", blocco), "senza allow_reentry /start viene ignorato a meta' di un'operazione"
