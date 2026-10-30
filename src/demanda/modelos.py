"""Modelo global de gradient boosting (ponto e quantil) e backtest por origem móvel."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from demanda.config import HORIZONTE, PASSO_RETREINO, QUANTIL, SEMENTE
from demanda.features import FEATURES


def novo_modelo(perda: str = "poisson", quantil: float | None = None):
    params = dict(loss=perda, learning_rate=0.08, max_iter=200, max_leaf_nodes=31,
                  min_samples_leaf=40, l2_regularization=1.0, early_stopping=False,
                  categorical_features="from_dtype", random_state=SEMENTE)
    if quantil is not None:
        params["quantile"] = quantil
    return HistGradientBoostingRegressor(**params)


def _peso(df: pd.DataFrame, preco: pd.Series) -> np.ndarray:
    """Peso pelo valor da série (R$/semana): erra-se menos onde o dinheiro está."""
    p = df["escala"].to_numpy() * df["material"].map(preco).astype(float).to_numpy()
    return p / p.mean()


def treinar(treino: pd.DataFrame, preco: pd.Series, quantil: float = QUANTIL):
    treino = treino.dropna(subset=["y_norm"])
    X, y, w = treino[FEATURES], treino["y_norm"], _peso(treino, preco)
    ponto = novo_modelo("poisson").fit(X, y, sample_weight=w)
    modelo_q = novo_modelo("quantile", quantil).fit(X, y, sample_weight=w)
    return ponto, modelo_q


def prever(modelos, df: pd.DataFrame) -> pd.DataFrame:
    ponto, quantil = modelos
    X, escala = df[FEATURES], df["escala"].to_numpy()
    p50 = np.clip(ponto.predict(X), 0, None) * escala
    p90 = np.clip(quantil.predict(X), 0, None) * escala
    return pd.DataFrame({"prev_modelo": p50, "prev_modelo_p90": np.maximum(p90, p50)},
                        index=df.index)


def backtest(base: pd.DataFrame, preco: pd.Series, inicio: int, fim: int,
             passo: int = PASSO_RETREINO, horizonte: int = HORIZONTE) -> pd.DataFrame:
    """Simula a operação: a cada `passo` semanas retreina só com o que já era conhecido.

    Uma linha de treino com origem t usa o alvo t+1..t+H, então só pode entrar no
    modelo treinado na semana f se t + H <= f (sem vazamento do futuro).
    """
    partes = []
    for f in range(inicio, fim + 1, passo):
        treino = base[base["origem"] + horizonte <= f]
        alvo = base[(base["origem"] >= f) & (base["origem"] < min(f + passo, fim + 1))]
        modelos = treinar(treino, preco)
        partes.append(alvo.join(prever(modelos, alvo)).assign(retreino=f))
    return pd.concat(partes)
