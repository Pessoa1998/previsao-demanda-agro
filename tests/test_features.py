"""A base supervisionada não pode olhar para o futuro."""
import numpy as np
import pandas as pd
import pytest

from demanda import camada_sql, features
from demanda.config import HORIZONTE


@pytest.fixture(scope="module")
def demanda_e_dim(con):
    return camada_sql.tabela(con, "demanda_semanal"), camada_sql.tabela(con, "dim_material")


def test_sem_vazamento_do_futuro(demanda_e_dim):
    demanda, dim = demanda_e_dim
    base = features.montar_base(demanda, dim)
    corte = 80                                             # semana de origem de referência
    semanas = sorted(demanda["semana"].unique())
    futuro = demanda["semana"] > semanas[corte]
    alterada = demanda.copy()
    rng = np.random.default_rng(0)
    alterada.loc[futuro, "quantidade"] = rng.uniform(0, 5_000, futuro.sum())
    base_alt = features.montar_base(alterada, dim)

    cols = [c for c in features.FEATURES if c not in features.CATEGORICAS] + ["escala"]
    a = base[base["origem"] <= corte].sort_values(["material", "centro", "origem"])
    b = base_alt[base_alt["origem"] <= corte].sort_values(["material", "centro", "origem"])
    np.testing.assert_allclose(a[cols].to_numpy(float), b[cols].to_numpy(float),
                               equal_nan=True)
    # o alvo, por definição, muda quando o futuro muda
    assert not np.allclose(a["y"].fillna(0), b["y"].fillna(0))


def test_alvo_e_baselines(demanda_e_dim):
    demanda, dim = demanda_e_dim
    base = features.montar_base(demanda, dim)
    mat, series, _ = features.matriz_demanda(demanda)
    linha = base[(base["material"] == series.loc[0, "material"])
                 & (base["centro"] == series.loc[0, "centro"])].set_index("origem")
    t = 70
    assert linha.loc[t, "y"] == pytest.approx(mat[0, t + 1:t + 1 + HORIZONTE].sum())
    assert linha.loc[t, "prev_media_movel"] == pytest.approx(mat[0, t - 3:t + 1].sum())
    assert linha.loc[t, "prev_sazonal_ingenuo"] == pytest.approx(
        mat[0, t + 1 - 52:t + 1 - 52 + HORIZONTE].sum())
    ultimas = base[base["origem"] > base["origem"].max() - HORIZONTE]
    assert ultimas["y"].isna().all()                      # alvo ainda desconhecido


def test_features_existem_e_categoricas(demanda_e_dim):
    base = features.montar_base(*demanda_e_dim)
    assert set(features.FEATURES) <= set(base.columns)
    for c in features.CATEGORICAS:
        assert isinstance(base[c].dtype, pd.CategoricalDtype)
