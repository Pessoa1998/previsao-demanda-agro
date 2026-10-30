"""Regras da camada semântica (as mesmas que iriam para as views do Datasphere)."""
import pandas as pd


def q(con, sql):
    return con.execute(sql).df()


def test_conversao_alpha_e_texto_em_portugues(con):
    dim = q(con, "SELECT * FROM dim_material")
    assert dim["material"].is_unique                       # MAKT filtrada por idioma
    assert not dim["material"].str.startswith("0").any()
    assert dim["descricao"].str.contains("SEMENTE|FERTILIZANTE|HERBICIDA").any()
    assert dim["familia"].notna().all()


def test_fato_sem_duplicidade(con):
    fato = q(con, "SELECT documento, item FROM fato_vendas")
    assert not fato.duplicated().any()
    brutas = q(con, "SELECT COUNT(DISTINCT VBELN || POSNR) AS n FROM stg_vbap")["n"][0]
    assert len(fato) == brutas


def test_demanda_exclui_devolucao_e_recusa(con):
    total = q(con, "SELECT SUM(quantidade) AS t FROM demanda_semanal")["t"][0]
    firme = q(con, """SELECT SUM(quantidade) AS t FROM fato_vendas
                      WHERE movimento IN ('VENDA', 'BONIFICACAO')""")["t"][0]
    tudo = q(con, "SELECT SUM(quantidade) AS t FROM fato_vendas")["t"][0]
    assert abs(total - float(firme)) < 1e-6
    assert float(tudo) > total


def test_demanda_semanal_densa(con):
    d = q(con, "SELECT * FROM demanda_semanal")
    n_series = d[["material", "centro"]].drop_duplicates().shape[0]
    semanas = pd.Series(sorted(d["semana"].unique()))
    assert len(d) == n_series * len(semanas)               # toda série em toda semana
    assert d["quantidade"].notna().all() and (d["quantidade"] >= 0).all()
    assert (semanas.diff().dropna() == pd.Timedelta(days=7)).all()
    assert (pd.to_datetime(semanas).dt.dayofweek == 0).all()   # semanas começam na segunda
