"""Pipeline completo: extração SAP -> camada SQL -> features -> backtest -> decisão.

Uso:  python -m demanda.pipeline [--sem-figuras]
"""
from __future__ import annotations

import argparse
import json
import time

import pandas as pd

from demanda import avaliacao, camada_sql, features, gerar_dados, graficos, modelos
from demanda.config import (CALIBRACAO, DADOS_BRUTOS, DADOS_PROC, FIGURAS, HORIZONTE,
                            NIVEL_SERVICO, RELATORIOS, TESTE)


def carregar(con):
    demanda = camada_sql.tabela(con, "demanda_semanal")
    dim_material = camada_sql.tabela(con, "dim_material")
    preco = (camada_sql.tabela(con, "preco_material")
             .set_index("material")["preco_medio"].astype(float))
    return demanda, dim_material, preco


def recomendacao_compra(base, preco, dim_material, z: float) -> pd.DataFrame:
    """Treina com todo o histórico e recomenda o estoque para as próximas 4 semanas."""
    ultima = base["origem"].max()
    modelos_finais = modelos.treinar(base[base["origem"] + HORIZONTE <= ultima], preco)
    agora = base[base["origem"] == ultima]
    prev = agora.join(modelos.prever(modelos_finais, agora))
    incerteza = avaliacao.incerteza(prev, "prev_modelo", None)
    rec = prev[["material", "centro", "familia"]].astype(str).assign(
        previsao_4_semanas=prev["prev_modelo"].round(0),
        p90=prev["prev_modelo_p90"].round(0),
        estoque_alvo=(prev["prev_modelo"] + z * incerteza).clip(lower=0).round(0),
    )
    rec = rec.merge(dim_material[["material", "descricao", "unidade"]], on="material")
    rec["valor_estoque_alvo"] = (rec["estoque_alvo"] * rec["material"].map(preco)).round(2)
    semana = (base["semana_origem"].max() + pd.Timedelta(days=7)).date()
    return (rec.assign(a_partir_de=semana)
            .sort_values("valor_estoque_alvo", ascending=False)
            [["a_partir_de", "centro", "material", "descricao", "familia", "unidade",
              "previsao_4_semanas", "p90", "estoque_alvo", "valor_estoque_alvo"]])


def executar(figuras: bool = True) -> dict:
    t0 = time.time()
    if not (DADOS_BRUTOS / "VBAP.csv").exists():
        gerar_dados.salvar(gerar_dados.gerar())
    DADOS_PROC.mkdir(parents=True, exist_ok=True)
    banco = DADOS_PROC / "warehouse.duckdb"
    banco.unlink(missing_ok=True)
    con = camada_sql.construir(banco)
    demanda, dim_material, preco = carregar(con)
    qualidade = camada_sql.relatorio_qualidade(con)

    base = features.montar_base(demanda, dim_material)
    prev = modelos.backtest(base, preco, inicio=CALIBRACAO[0], fim=TESTE[1])
    prev["preco"] = prev["material"].map(preco).astype(float)
    prev = prev[(prev["soma_52"] > 0) | (prev["y"] > 0)]       # séries ativas
    prev.to_parquet(DADOS_PROC / "previsoes_backtest.parquet")
    calibracao = prev[prev["origem"].between(*CALIBRACAO)]
    teste = prev[prev["origem"].between(*TESTE)]

    geral = pd.concat({"calibração (safra 24/25)": avaliacao.tabela_metricas(calibracao),
                       "teste (safra 25/26)": avaliacao.tabela_metricas(teste)})
    geral.index = geral.index.droplevel(1)
    por_familia = avaliacao.tabela_metricas(teste, por="familia")
    politica, curvas = avaliacao.avaliar_politicas(calibracao, teste)
    z_atual = avaliacao.calibrar_z(teste, "prev_modelo")
    compra = recomendacao_compra(base, preco, dim_material, z_atual)

    RELATORIOS.mkdir(parents=True, exist_ok=True)
    qualidade.to_csv(RELATORIOS / "qualidade_extracao.csv", index=False)
    geral.to_csv(RELATORIOS / "metricas_gerais.csv")
    por_familia.to_csv(RELATORIOS / "metricas_por_familia.csv")
    politica.to_csv(RELATORIOS / "politica_estoque.csv")
    compra.to_csv(RELATORIOS / "recomendacao_estoque.csv", index=False)

    m = avaliacao.METODOS
    col_alvo = f"estoque p/ {NIVEL_SERVICO:.0%} no teste (R$ mi)"
    resumo = {
        "wape_teste": {m[k]: round(float(geral.loc["teste (safra 25/26)", (m[k], "WAPE")]), 4)
                       for k in m},
        "wape_calibracao": {m[k]: round(float(geral.loc["calibração (safra 24/25)",
                                                         (m[k], "WAPE")]), 4) for k in m},
        "estoque_no_alvo_rs_mi": {n: round(float(v), 2)
                                  for n, v in politica[col_alvo].items()},
        "economia_do_modelo": {n: round(float(v), 4)
                               for n, v in politica["economia do modelo"].items()},
        "atendimento_alvo": NIVEL_SERVICO,
        "series": int(base[["material", "centro"]].drop_duplicates().shape[0]),
        "linhas_vbap": int(qualidade.iloc[0, 1]),
        "segundos": round(time.time() - t0, 1),
    }
    (RELATORIOS / "resultados.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")

    if figuras:
        for tema in graficos.TEMAS:
            graficos.sazonalidade(demanda, dim_material,
                                  FIGURAS / f"sazonalidade-{tema}.png", tema)
            graficos.previsao_vs_real(teste, FIGURAS / f"previsao-vs-real-{tema}.png", tema)
            graficos.erro_por_familia(por_familia, FIGURAS / f"erro-por-familia-{tema}.png",
                                      tema)
            graficos.tradeoff_estoque(curvas, NIVEL_SERVICO,
                                      FIGURAS / f"tradeoff-estoque-{tema}.png", tema)
    con.close()
    return resumo


def main() -> None:
    ap = argparse.ArgumentParser(description="Roda o case de ponta a ponta.")
    ap.add_argument("--sem-figuras", action="store_true")
    args = ap.parse_args()
    resumo = executar(figuras=not args.sem_figuras)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
