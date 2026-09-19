"""Configurazione comune dei test.

I test girano senza variabili d'ambiente: senza questo file ADMIN_ID vale 0,
la lista ADMIN_IDS resta vuota e il bot — correttamente — non autorizza
nessuno e non manda niente a nessuno. Tutti i test che simulano un admin
fallirebbero per il motivo sbagliato.

Qui si configura un bot a UN SOLO admin, che e' la situazione storica e quella
che i test esistenti danno per scontata. I test del multi-admin
(test_multi_admin.py) si costruiscono la loro lista da soli.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import bot_telegram as bt

ADMIN_DI_TEST = 424242


@pytest.fixture(autouse=True)
def bot_con_un_admin():
    originali = (bt.ADMIN_ID, bt.OWNER_ID, list(bt.ADMIN_IDS))
    bt.ADMIN_ID = ADMIN_DI_TEST
    bt.OWNER_ID = ADMIN_DI_TEST
    bt.ADMIN_IDS = [ADMIN_DI_TEST]
    yield
    bt.ADMIN_ID, bt.OWNER_ID, bt.ADMIN_IDS = originali[0], originali[1], originali[2]
