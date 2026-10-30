"""Camada semântica em DuckDB, no estilo das views do SAP Datasphere.

A extração bruta (CSV, tudo texto, como chega do SAP) vira views de staging
`stg_*`. Depois os arquivos `sql/*.sql` rodam em ordem e criam dimensões, fato,
a demanda semanal e a camada de consumo de BI.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from demanda.config import DADOS_BRUTOS, SQL_DIR

TABELAS_SAP = ["VBAK", "VBAP", "KNA1", "MARA", "MAKT", "T023T", "T001W"]


def construir(banco: str | Path = ":memory:", dados_brutos: Path = DADOS_BRUTOS,
              sql_dir: Path = SQL_DIR) -> duckdb.DuckDBPyConnection:
    """Cria (ou recria) o warehouse e devolve a conexão aberta."""
    con = duckdb.connect(str(banco))
    for tabela in TABELAS_SAP:
        arquivo = (Path(dados_brutos) / f"{tabela}.csv").as_posix().replace("'", "''")
        con.execute(
            f"CREATE OR REPLACE VIEW stg_{tabela.lower()} AS "
            f"SELECT * FROM read_csv('{arquivo}', header = true, all_varchar = true)"
        )
    for script in sorted(Path(sql_dir).glob("*.sql")):
        con.execute(script.read_text(encoding="utf-8"))
    return con


def tabela(con: duckdb.DuckDBPyConnection, nome: str) -> pd.DataFrame:
    return con.execute(f"SELECT * FROM {nome}").df()


def relatorio_qualidade(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """O que a camada semântica tratou na extração bruta."""
    consultas = {
        "linhas de item na extração (VBAP)": "SELECT COUNT(*) FROM stg_vbap",
        "linhas duplicadas pela carga delta": (
            "SELECT COUNT(*) - COUNT(DISTINCT VBELN || POSNR) FROM stg_vbap"),
        "itens recusados (ABGRU preenchido)": (
            "SELECT COUNT(*) FROM fato_vendas WHERE movimento = 'RECUSADO'"),
        "itens de devolução (ZDEV)": (
            "SELECT COUNT(*) FROM fato_vendas WHERE movimento = 'DEVOLUCAO'"),
        "itens de bonificação (ZBON)": (
            "SELECT COUNT(*) FROM fato_vendas WHERE movimento = 'BONIFICACAO'"),
        "descrições em outros idiomas (MAKT)": (
            "SELECT COUNT(*) FROM stg_makt WHERE SPRAS <> 'P'"),
        "materiais marcados para eliminação (MARA-LVORM)": (
            "SELECT COUNT(*) FROM dim_material WHERE marcado_eliminacao"),
    }
    linhas = [(nome, con.execute(sql).fetchone()[0]) for nome, sql in consultas.items()]
    return pd.DataFrame(linhas, columns=["verificação", "quantidade"])
