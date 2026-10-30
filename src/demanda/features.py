"""Base supervisionada para previsão da demanda das próximas H semanas.

Para cada série (material x centro) e cada semana de origem t, o alvo é a demanda
acumulada em t+1..t+H (o lead time de reposição). As features usam apenas
informação disponível até o fim da semana t:

* nível recente da série (somas das últimas 4, 8, 13, 26 e 52 semanas);
* o mesmo período do ano anterior, inclusive deslocado em ±2 semanas, para o
  modelo perceber plantio adiantado ou atrasado;
* razão entre as últimas 4 semanas e as mesmas semanas do ano anterior, na série,
  na família da filial e na família em todas as filiais (sinal de calendário);
* semana da safra, família, filial e material.

As quantidades são normalizadas pela média semanal dos últimos 52 semanas da série
(`escala`), o que permite um único modelo global para itens vendidos em sacas,
toneladas, litros ou doses.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from demanda.config import HORIZONTE

SEMANAS_ANO = 52
ORIGEM_MINIMA = SEMANAS_ANO + 3          # precisa de 1 ano de histórico + 4 semanas

CATEGORICAS = ["familia", "centro", "material"]
FEATURES = [
    "ult_1", "ult_2", "soma_4", "soma_8", "soma_13", "soma_26",
    "aa_prox_4", "aa_prox_4_antes", "aa_prox_4_depois", "aa_prox_8",
    "razao_aa", "fc_soma_4", "fc_aa_prox_4", "fc_razao_aa", "ft_razao_aa",
    "ft_aa_prox_4", "participacao", "semana_safra", "sen_safra", "cos_safra",
] + CATEGORICAS


def matriz_demanda(demanda: pd.DataFrame):
    """Demanda longa (semana, material, centro, quantidade) -> matriz séries x semanas."""
    tab = demanda.pivot_table(index=["material", "centro"], columns="semana",
                              values="quantidade", aggfunc="sum", fill_value=0.0)
    series = tab.index.to_frame(index=False)
    return tab.to_numpy(dtype=float), series, pd.DatetimeIndex(tab.columns)


def _acumulada(m: np.ndarray) -> np.ndarray:
    return np.concatenate([np.zeros((m.shape[0], 1)), np.cumsum(m, axis=1)], axis=1)


def _janela(acum: np.ndarray, origens: np.ndarray, ini: int, fim: int) -> np.ndarray:
    """Soma das semanas [t+ini, t+fim] para cada origem t; NaN fora do histórico."""
    n_sem = acum.shape[1] - 1
    a, b = origens + ini, origens + fim
    valido = (a >= 0) & (b <= n_sem - 1)
    out = acum[:, np.clip(b + 1, 0, n_sem)] - acum[:, np.clip(a, 0, n_sem)]
    out[:, ~valido] = np.nan
    return out


def _razao(atual, anterior, escala):
    suav = 0.5 * escala
    return (atual + suav) / (anterior + suav)


def montar_base(demanda: pd.DataFrame, dim_material: pd.DataFrame,
                horizonte: int = HORIZONTE) -> pd.DataFrame:
    """Uma linha por série x semana de origem, com features, alvo e baselines."""
    mat, series, semanas = matriz_demanda(demanda)
    familia = series["material"].map(dim_material.set_index("material")["familia"])
    series = series.assign(familia=familia.to_numpy())
    n_series, n_sem = mat.shape
    origens = np.arange(ORIGEM_MINIMA, n_sem)

    # agregados por família x centro e por família (todas as filiais)
    chave_fc = series["familia"] + "|" + series["centro"]
    fc_ids, fc_idx = np.unique(chave_fc, return_inverse=True)
    ft_ids, ft_idx = np.unique(series["familia"], return_inverse=True)
    mat_fc = np.zeros((len(fc_ids), n_sem))
    np.add.at(mat_fc, fc_idx, mat)
    mat_ft = np.zeros((len(ft_ids), n_sem))
    np.add.at(mat_ft, ft_idx, mat)
    ac, ac_fc, ac_ft = _acumulada(mat), _acumulada(mat_fc), _acumulada(mat_ft)

    def j(acum, ini, fim):
        return _janela(acum, origens, ini, fim)

    a = SEMANAS_ANO
    soma_52 = j(ac, -51, 0)
    escala = np.where(soma_52 > 0, soma_52 / a, 1.0)
    fc_escala = np.maximum(j(ac_fc, -51, 0) / a, 1e-9)[fc_idx]
    ft_escala = np.maximum(j(ac_ft, -51, 0) / a, 1e-9)[ft_idx]

    bruto = {
        "ult_1": j(ac, 0, 0), "ult_2": j(ac, -1, -1),
        "soma_4": j(ac, -3, 0), "soma_8": j(ac, -7, 0),
        "soma_13": j(ac, -12, 0), "soma_26": j(ac, -25, 0),
        "aa_prox_4": j(ac, 1 - a, horizonte - a),
        "aa_prox_4_antes": j(ac, -1 - a, horizonte - 2 - a),
        "aa_prox_4_depois": j(ac, 3 - a, horizonte + 2 - a),
        "aa_prox_8": j(ac, 1 - a, 8 - a),
    }
    aa_ult_4 = j(ac, -3 - a, -a)
    fc_soma_4, fc_aa_ult_4 = j(ac_fc, -3, 0)[fc_idx], j(ac_fc, -3 - a, -a)[fc_idx]
    ft_soma_4, ft_aa_ult_4 = j(ac_ft, -3, 0)[ft_idx], j(ac_ft, -3 - a, -a)[ft_idx]

    cols = {k: v / escala for k, v in bruto.items()}
    cols.update({
        "razao_aa": _razao(bruto["soma_4"], aa_ult_4, escala),
        "fc_soma_4": fc_soma_4 / fc_escala,
        "fc_aa_prox_4": j(ac_fc, 1 - a, horizonte - a)[fc_idx] / fc_escala,
        "fc_razao_aa": _razao(fc_soma_4, fc_aa_ult_4, fc_escala),
        "ft_razao_aa": _razao(ft_soma_4, ft_aa_ult_4, ft_escala),
        "ft_aa_prox_4": j(ac_ft, 1 - a, horizonte - a)[ft_idx] / ft_escala,
        "participacao": (soma_52 / a) / fc_escala,
    })
    alvo = j(ac, 1, horizonte)

    def longo(m):
        return m.reshape(-1)

    rep = np.repeat(np.arange(n_series), len(origens))
    base = pd.DataFrame({
        "material": series["material"].to_numpy()[rep],
        "centro": series["centro"].to_numpy()[rep],
        "familia": series["familia"].to_numpy()[rep],
        "origem": np.tile(origens, n_series),
    })
    base["semana_origem"] = semanas[base["origem"].to_numpy()]
    for nome, m in cols.items():
        base[nome] = longo(m)
    base["semana_safra"] = (base["origem"] + 1) % a
    ang = 2 * np.pi * base["semana_safra"] / a
    base["sen_safra"], base["cos_safra"] = np.sin(ang), np.cos(ang)
    base["escala"] = longo(escala)
    base["soma_52"] = longo(soma_52)
    base["y"] = longo(alvo)
    base["y_norm"] = base["y"] / base["escala"]
    # baselines em unidades: média móvel (nível recente) e sazonal ingênuo
    base["prev_media_movel"] = longo(bruto["soma_4"]) * horizonte / 4
    base["prev_sazonal_ingenuo"] = longo(bruto["aa_prox_4"])
    for c in CATEGORICAS:
        base[c] = base[c].astype("category")
    return base
