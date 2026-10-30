"""Métricas e política de estoque."""
import numpy as np
import pandas as pd
import pytest

from demanda import avaliacao as av


def test_wape_e_vies():
    y, prev, peso = [10, 0, 30], [12, 1, 24], [1, 1, 2]
    assert av.wape(y, prev) == pytest.approx((2 + 1 + 6) / 40)
    assert av.vies(y, prev) == pytest.approx((2 + 1 - 6) / 40)
    assert av.wape(y, prev, peso) == pytest.approx((2 + 1 + 12) / 70)


def _prev():
    return pd.DataFrame({
        "material": ["1", "1", "2", "2"], "centro": ["A"] * 4, "origem": [0, 1, 0, 1],
        "y": [10.0, 20.0, 5.0, 0.0], "preco": [2.0, 2.0, 10.0, 10.0],
        "prev_media_movel": [8.0, 15.0, 4.0, 1.0],
        "prev_modelo": [9.0, 18.0, 5.0, 0.5], "prev_modelo_p90": [12.0, 24.0, 6.0, 1.0],
    })


def test_atendimento_em_valor():
    p = _prev()
    estoque = np.array([10.0, 10.0, 5.0, 0.0])
    # atende 10*2 + 10*2 + 5*10 de (10+20)*2 + 5*10
    assert av.atendimento(p, estoque) == pytest.approx(90 / 110)


def test_calibracao_atinge_o_alvo():
    p = _prev()
    sigma = av.sigma_historico(p, "prev_media_movel")
    z = av.calibrar_z(p, "prev_media_movel", sigma, alvo=0.95)
    est = av.estoque_alvo(p, "prev_media_movel", z, sigma)
    assert av.atendimento(p, est) >= 0.95
    menor = av.estoque_alvo(p, "prev_media_movel", max(z - 0.02, 0), sigma)
    assert z == 0 or av.atendimento(p, menor) < 0.95


def test_incerteza_do_modelo_vem_do_quantil():
    p = _prev()
    sig = av.incerteza(p, "prev_modelo", None)
    np.testing.assert_allclose(sig * av.Z_QUANTIL, p["prev_modelo_p90"] - p["prev_modelo"])


def test_curva_e_monotona():
    p = _prev()
    curva = av.curva_servico(p, "prev_modelo")
    assert curva["estoque_rs_mi"].is_monotonic_increasing
    assert curva["atendimento"].is_monotonic_increasing
