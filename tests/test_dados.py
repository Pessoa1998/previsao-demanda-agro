"""A extração sintética precisa ter a cara de uma extração SAP de verdade."""
import pandas as pd

from demanda import gerar_dados


def test_geracao_e_deterministica():
    a = gerar_dados.gerar(semente=3, n_safras=2)
    b = gerar_dados.gerar(semente=3, n_safras=2)
    for nome in a:
        pd.testing.assert_frame_equal(a[nome], b[nome])


def test_chaves_no_formato_sap(tabelas):
    vbak, vbap = tabelas["VBAK"], tabelas["VBAP"]
    assert vbap["MATNR"].str.fullmatch(r"0{12}\d{6}").all()      # MATNR com 18 posições
    assert vbak["KUNNR"].str.fullmatch(r"\d{10}").all()
    assert vbak["VBELN"].str.fullmatch(r"00\d{8}").all()
    assert vbap["POSNR"].str.fullmatch(r"\d{6}").all()
    assert vbak["ERDAT"].str.fullmatch(r"20\d{6}").all()           # DATS: AAAAMMDD
    assert pd.to_datetime(vbak["ERDAT"], format="%Y%m%d").notna().all()


def test_problemas_de_qualidade_foram_injetados(tabelas):
    vbap, vbak, makt = tabelas["VBAP"], tabelas["VBAK"], tabelas["MAKT"]
    assert vbap.duplicated(["VBELN", "POSNR"]).any()                 # carga delta duplicada
    assert (vbap["ABGRU"] != "").any()                               # itens recusados
    assert set(vbak["AUART"]) == {"ZVEN", "ZBON", "ZDEV"}
    assert set(makt["SPRAS"]) == {"P", "E"}                           # textos em 2 idiomas


def test_toda_venda_tem_cabecalho(tabelas):
    assert set(tabelas["VBAP"]["VBELN"]) <= set(tabelas["VBAK"]["VBELN"])
