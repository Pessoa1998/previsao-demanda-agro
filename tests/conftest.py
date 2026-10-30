import pytest

from demanda import camada_sql, gerar_dados


@pytest.fixture(scope="session")
def tabelas():
    """Extração pequena (2 safras) para os testes rodarem rápido."""
    return gerar_dados.gerar(semente=7, n_safras=2)


@pytest.fixture(scope="session")
def con(tabelas, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("raw")
    gerar_dados.salvar(tabelas, pasta)
    conexao = camada_sql.construir(":memory:", dados_brutos=pasta)
    yield conexao
    conexao.close()
