"""Métricas de previsão e avaliação da política de estoque.

Tudo é valorizado em R$ (quantidade x preço médio do material): somar sacas,
toneladas e litros não faz sentido, mas somar dinheiro faz.

Política avaliada (a mesma para todos os métodos): estoque para cobrir o lead time
S = previsão + z x incerteza. O que muda entre os métodos é a previsão e a
incerteza:

* baselines: incerteza = desvio-padrão histórico do erro de cada série (fixo o ano
  todo, como no estoque de segurança clássico);
* modelo: incerteza condicional, tirada do quantil P90 do próprio modelo; ela
  cresce no pico da safra e encolhe na entressafra.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from demanda.config import NIVEL_SERVICO, QUANTIL

METODOS = {
    "prev_modelo": "Modelo (gradient boosting)",
    "prev_media_movel": "Média móvel 4 semanas",
    "prev_sazonal_ingenuo": "Sazonal ingênuo (ano anterior)",
}
Z_QUANTIL = 1.2815515655446004          # quantil 0,90 da normal padrão
GRADE_Z = np.round(np.arange(0.0, 6.0001, 0.02), 2)


def wape(y, previsto, peso=None) -> float:
    """Erro absoluto ponderado: sum|y - ŷ| / sum y (ponderado por valor se houver peso)."""
    y, previsto = np.asarray(y, float), np.asarray(previsto, float)
    peso = np.ones_like(y) if peso is None else np.asarray(peso, float)
    return float(np.sum(np.abs(y - previsto) * peso) / np.sum(y * peso))


def vies(y, previsto, peso=None) -> float:
    """Viés relativo: > 0 superestima, < 0 subestima."""
    y, previsto = np.asarray(y, float), np.asarray(previsto, float)
    peso = np.ones_like(y) if peso is None else np.asarray(peso, float)
    return float(np.sum((previsto - y) * peso) / np.sum(y * peso))


def tabela_metricas(prev: pd.DataFrame, por: str | None = None) -> pd.DataFrame:
    """WAPE e viés em valor (R$) por método, opcionalmente por grupo."""
    def calc(g):
        return pd.Series({(METODOS[k], m): f(g["y"], g[k], g["preco"])
                          for k in METODOS for m, f in (("WAPE", wape), ("viés", vies))})
    if por is None:
        return calc(prev).to_frame("total").T
    return prev.groupby(por, observed=True)[["y", "preco", *METODOS]].apply(calc)


# ------------------------------------------------------------------ política
def sigma_historico(referencia: pd.DataFrame, coluna: str) -> pd.Series:
    """Desvio-padrão do erro por série (material x centro) num período de referência."""
    erro = referencia["y"] - referencia[coluna]
    sigma = erro.groupby([referencia["material"], referencia["centro"]],
                         observed=True).std()
    return sigma.fillna(sigma.median())


def incerteza(prev: pd.DataFrame, coluna: str, sigma: pd.Series | None) -> np.ndarray:
    if coluna == "prev_modelo":                       # condicional, vem do quantil
        return np.clip(prev["prev_modelo_p90"] - prev["prev_modelo"], 0, None).to_numpy() \
            / Z_QUANTIL
    chave = pd.MultiIndex.from_arrays([prev["material"], prev["centro"]])
    return sigma.reindex(chave).fillna(sigma.median()).to_numpy()


def estoque_alvo(prev: pd.DataFrame, coluna: str, z: float, sigma=None) -> np.ndarray:
    return np.clip(prev[coluna].to_numpy() + z * incerteza(prev, coluna, sigma), 0, None)


def atendimento(prev: pd.DataFrame, estoque: np.ndarray) -> float:
    """Fill rate em valor: fração do R$ demandado que o estoque atenderia na hora."""
    y, p = prev["y"].to_numpy(), prev["preco"].to_numpy()
    return float(np.sum(np.minimum(estoque, y) * p) / np.sum(y * p))


def estoque_medio(prev: pd.DataFrame, estoque: np.ndarray) -> float:
    """Estoque-alvo médio por semana, em R$ milhões."""
    return float(np.sum(estoque * prev["preco"].to_numpy()) / prev["origem"].nunique() / 1e6)


def calibrar_z(prev: pd.DataFrame, coluna: str, sigma=None,
               alvo: float = NIVEL_SERVICO) -> float:
    """Menor z que atinge o atendimento-alvo no período de calibração."""
    for z in GRADE_Z:
        if atendimento(prev, estoque_alvo(prev, coluna, z, sigma)) >= alvo:
            return float(z)
    return float(GRADE_Z[-1])


def curva_servico(prev: pd.DataFrame, coluna: str, sigma=None) -> pd.DataFrame:
    """Trade-off atendimento x estoque médio variando z."""
    linhas = []
    for z in GRADE_Z:
        est = estoque_alvo(prev, coluna, z, sigma)
        linhas.append((z, atendimento(prev, est), estoque_medio(prev, est)))
    return pd.DataFrame(linhas, columns=["z", "atendimento", "estoque_rs_mi"])


def estoque_no_alvo(curva: pd.DataFrame, alvo: float = NIVEL_SERVICO) -> float:
    """Estoque médio necessário para atingir exatamente o alvo (interpolado na curva)."""
    c = curva.sort_values("atendimento").drop_duplicates("atendimento")
    return float(np.interp(alvo, c["atendimento"], c["estoque_rs_mi"]))


def avaliar_politicas(calibracao: pd.DataFrame, teste: pd.DataFrame,
                      alvo: float = NIVEL_SERVICO) -> tuple[pd.DataFrame, dict]:
    """Calibra z na safra anterior e mede na safra de teste, com a mesma regra para todos."""
    linhas, curvas = [], {}
    for coluna, nome in METODOS.items():
        sigma = None if coluna == "prev_modelo" else sigma_historico(calibracao, coluna)
        z = calibrar_z(calibracao, coluna, sigma, alvo)
        est = estoque_alvo(teste, coluna, z, sigma)
        curvas[nome] = curva_servico(teste, coluna, sigma)
        linhas.append({
            "método": nome,
            "z calibrado": z,
            "atendimento no teste": atendimento(teste, est),
            "estoque médio (R$ mi)": estoque_medio(teste, est),
            f"estoque p/ {alvo:.0%} no teste (R$ mi)": estoque_no_alvo(curvas[nome], alvo),
        })
    res = pd.DataFrame(linhas).set_index("método")
    col = f"estoque p/ {alvo:.0%} no teste (R$ mi)"
    res["economia do modelo"] = 1 - res.loc[METODOS["prev_modelo"], col] / res[col]
    return res, curvas


__all__ = ["METODOS", "QUANTIL", "wape", "vies", "tabela_metricas", "avaliar_politicas",
           "curva_servico", "atendimento", "estoque_alvo", "calibrar_z", "estoque_no_alvo",
           "sigma_historico"]
