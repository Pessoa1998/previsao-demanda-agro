"""Gera uma extração sintética no formato das tabelas do SAP SD/MM.

Tabelas geradas (CSV, todos os campos como texto, como numa extração real):

    VBAK  cabeçalho da ordem de venda     VBAP  item da ordem de venda
    KNA1  mestre de clientes              MARA  mestre de materiais
    MAKT  descrições de materiais         T023T descrições dos grupos de mercadoria
    T001W centros (filiais)

Cenário fictício: uma distribuidora de insumos agrícolas com seis filiais em Mato
Grosso. A demanda segue o calendário da safra (soja no 2º semestre, milho safrinha
no 1º), cresce ano a ano e tem o plantio deslocado conforme a chuva de cada safra.
Também são injetados problemas típicos de dados SAP: zeros à esquerda (conversão
ALPHA), datas DATS (AAAAMMDD), descrições em mais de um idioma, itens recusados
(ABGRU), devoluções, bonificações e linhas duplicadas pela extração.

Uso:  python -m demanda.gerar_dados [--saida data/raw] [--semente 42]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from demanda.config import DADOS_BRUTOS, SEMENTE

INICIO = pd.Timestamp("2020-07-06")  # segunda-feira: início da safra 20/21
SEMANAS_SAFRA = 52
N_SAFRAS = 6

# Deslocamento do calendário de plantio em cada safra (semanas; + = atraso).
# Na 23/24 as chuvas atrasaram (El Niño) e o plantio foi empurrado para frente.
DESLOCAMENTO_SAFRA = [-0.5, 0.5, 0.0, 2.5, -1.0, 1.0]
CRESCIMENTO_ANUAL = 0.05

# WERKS, NAME1, ORT01, porte relativo, deslocamento regional (semanas), cidades
CENTROS = [
    ("1101", "FILIAL CUIABA", "CUIABA", 0.6, 0.0,
     ["CUIABA", "VARZEA GRANDE", "CHAPADA DOS GUIMARAES", "JACIARA"]),
    ("1102", "FILIAL RONDONOPOLIS", "RONDONOPOLIS", 0.9, 0.5,
     ["RONDONOPOLIS", "ITIQUIRA", "PEDRA PRETA", "ALTO GARCAS"]),
    ("1103", "FILIAL PRIMAVERA DO LESTE", "PRIMAVERA DO LESTE", 1.0, 0.5,
     ["PRIMAVERA DO LESTE", "CAMPO VERDE", "PARANATINGA", "POXOREU"]),
    ("1104", "FILIAL LUCAS DO RIO VERDE", "LUCAS DO RIO VERDE", 1.2, -0.5,
     ["LUCAS DO RIO VERDE", "NOVA MUTUM", "TAPURAH", "SAO JOSE DO RIO CLARO"]),
    ("1105", "FILIAL SORRISO", "SORRISO", 1.4, -0.5,
     ["SORRISO", "IPIRANGA DO NORTE", "VERA", "NOVA UBIRATA"]),
    ("1106", "FILIAL SINOP", "SINOP", 1.1, -1.0,
     ["SINOP", "CLAUDIA", "SANTA CARMEM", "ITAUBA"]),
]

# Picos sazonais em "semana da safra" (0 = 1ª semana de julho): (centro, largura, peso)
FAMILIAS = {
    "SEMSOJA": dict(nome="SEMENTES DE SOJA", en="SOYBEAN SEEDS", volume=30_000,
                    pedido=120, preco=310.0, picos=[(2, 2.5, .15), (11, 3.0, 1.0)]),
    "SEMMILHO": dict(nome="SEMENTES DE MILHO", en="CORN SEEDS", volume=9_000,
                     pedido=60, preco=880.0, picos=[(25, 2.5, 1.0), (29, 2.0, .35)]),
    "INOCUL": dict(nome="INOCULANTES", en="INOCULANTS", volume=120_000,
                   pedido=400, preco=4.5, picos=[(13, 2.5, 1.0)]),
    "FERTIL": dict(nome="FERTILIZANTES", en="FERTILIZERS", volume=6_000,
                   pedido=25, preco=2_900.0, picos=[(9, 4.0, 1.0), (25, 3.0, .55)]),
    "HERBIC": dict(nome="HERBICIDAS", en="HERBICIDES", volume=60_000, pedido=360,
                   preco=28.0, picos=[(10, 2.5, 1.0), (19, 3.0, .7), (29, 3.0, .6)]),
    "FUNGIC": dict(nome="FUNGICIDAS", en="FUNGICIDES", volume=30_000, pedido=180,
                   preco=125.0, picos=[(22, 4.0, 1.0), (38, 3.0, .5)]),
    "INSETI": dict(nome="INSETICIDAS", en="INSECTICIDES", volume=20_000, pedido=140,
                   preco=95.0, picos=[(18, 4.0, 1.0), (35, 4.0, .6)]),
    "ADJUV": dict(nome="ADJUVANTES", en="ADJUVANTS", volume=25_000, pedido=240,
                  preco=16.0, picos=[(10, 2.5, .8), (19, 3.0, .6), (22, 4.0, .8),
                                     (35, 4.0, .4)]),
}
# choques de mercado por (família, safra): margem apertada, expansão do milho...
CHOQUES = {("FERTIL", 3): 0.88, ("SEMMILHO", 4): 1.12, ("FUNGIC", 5): 1.08}
# índice de preço por safra (fertilizantes caíram forte depois do pico de 2022)
INDICE_PRECO = {"FERTIL": [0.70, 0.85, 1.00, 0.72, 0.75, 0.80]}
INDICE_PRECO_PADRAO = [0.94, 0.97, 1.00, 1.03, 1.06, 1.09]

# número, grupo, descrição PT, descrição EN, unidade, embalagem, peso na família,
# fator de preço, picos próprios (None = os da família), ciclo de vida
MATERIAIS = [
    ("100101", "SEMSOJA", "SEMENTE SOJA CULTIVAR SJ-01 40KG", "SOYBEAN SEED SJ-01 40KG", "SC", 1, 1.0, 1.00, None, None),
    ("100102", "SEMSOJA", "SEMENTE SOJA CULTIVAR SJ-02 40KG", "SOYBEAN SEED SJ-02 40KG", "SC", 1, 0.8, 1.05, None, None),
    ("100103", "SEMSOJA", "SEMENTE SOJA CULTIVAR SJ-03 40KG", "SOYBEAN SEED SJ-03 40KG", "SC", 1, 0.6, 0.90, None, ("saida", 208)),
    ("100104", "SEMSOJA", "SEMENTE SOJA CULTIVAR SJ-04 40KG", "SOYBEAN SEED SJ-04 40KG", "SC", 1, 0.5, 1.00, None, None),
    ("100105", "SEMSOJA", "SEMENTE SOJA CULTIVAR SJ-05 40KG", "SOYBEAN SEED SJ-05 40KG", "SC", 1, 0.9, 1.15, None, ("entrada", 208)),
    ("100201", "SEMMILHO", "SEMENTE MILHO HIBRIDO MH-01 60M", "CORN SEED HYBRID MH-01 60K", "SC", 1, 1.0, 1.00, None, None),
    ("100202", "SEMMILHO", "SEMENTE MILHO HIBRIDO MH-02 60M", "CORN SEED HYBRID MH-02 60K", "SC", 1, 0.8, 1.10, None, None),
    ("100203", "SEMMILHO", "SEMENTE MILHO HIBRIDO MH-03 60M", "CORN SEED HYBRID MH-03 60K", "SC", 1, 0.6, 0.95, None, None),
    ("100204", "SEMMILHO", "SEMENTE MILHO HIBRIDO MH-04 60M", "CORN SEED HYBRID MH-04 60K", "SC", 1, 0.4, 1.05, None, None),
    ("100301", "INOCUL", "INOCULANTE SOJA LIQUIDO 50 DOSES", "SOY INOCULANT LIQUID 50 DOSES", "DS", 50, 1.0, 1.00, None, None),
    ("100302", "INOCUL", "INOCULANTE SOJA TURFOSO 50 DOSES", "SOY INOCULANT PEAT 50 DOSES", "DS", 50, 0.5, 0.85, None, None),
    ("100401", "FERTIL", "FERTILIZANTE MAP 11-52-00 BIG BAG", "FERTILIZER MAP 11-52-00 BIG BAG", "TO", 1, 1.0, 1.10, None, None),
    ("100402", "FERTIL", "FERTILIZANTE KCL 00-00-60 BIG BAG", "FERTILIZER KCL 00-00-60 BIG BAG", "TO", 1, 0.9, 0.85, None, None),
    ("100403", "FERTIL", "FERTILIZANTE NPK 02-20-18 BIG BAG", "FERTILIZER NPK 02-20-18 BIG BAG", "TO", 1, 0.8, 1.00, [(9, 4.0, 1.0)], None),
    ("100404", "FERTIL", "FERTILIZANTE UREIA 45-00-00 BIG BAG", "FERTILIZER UREA 45-00-00 BIG BAG", "TO", 1, 0.6, 0.95, [(27, 3.0, 1.0)], None),
    ("100405", "FERTIL", "FERTILIZANTE NPK 00-20-20 BIG BAG", "FERTILIZER NPK 00-20-20 BIG BAG", "TO", 1, 0.5, 0.95, None, None),
    ("100406", "FERTIL", "FERTILIZANTE SSP 00-18-00 BIG BAG", "FERTILIZER SSP 00-18-00 BIG BAG", "TO", 1, 0.3, 0.70, [(8, 4.0, 1.0)], None),
    ("100501", "HERBIC", "HERBICIDA GLIFOSATO 480 SL GL 20L", "HERBICIDE GLYPHOSATE 480 SL 20L", "L", 20, 1.0, 0.70, None, None),
    ("100502", "HERBIC", "HERBICIDA 2,4-D 806 SL GL 20L", "HERBICIDE 2,4-D 806 SL 20L", "L", 20, 0.6, 0.80, [(10, 2.5, 1.0), (29, 3.0, .4)], None),
    ("100503", "HERBIC", "HERBICIDA CLETODIM 240 EC GL 5L", "HERBICIDE CLETHODIM 240 EC 5L", "L", 5, 0.4, 1.60, [(19, 3.0, 1.0)], None),
    ("100504", "HERBIC", "HERBICIDA DIQUAT 200 SL GL 20L", "HERBICIDE DIQUAT 200 SL 20L", "L", 20, 0.4, 1.20, [(10, 2.0, 1.0), (40, 2.5, .6)], None),
    ("100505", "HERBIC", "HERBICIDA ATRAZINA 500 SC GL 20L", "HERBICIDE ATRAZINE 500 SC 20L", "L", 20, 0.5, 0.60, [(29, 3.0, 1.0)], None),
    ("100601", "FUNGIC", "FUNGICIDA AZOXISTROBINA+CIPROCONAZOL GL 5L", "FUNGICIDE AZOXYSTROBIN+CYPROCONAZOLE 5L", "L", 5, 1.0, 1.00, None, None),
    ("100602", "FUNGIC", "FUNGICIDA PROTIOCONAZOL+TRIFLOXISTROBINA GL 5L", "FUNGICIDE PROTHIOCONAZOLE+TRIFLOXYSTROBIN 5L", "L", 5, 0.8, 1.30, None, None),
    ("100603", "FUNGIC", "FUNGICIDA MANCOZEBE 750 WG SC 25KG", "FUNGICIDE MANCOZEB 750 WG 25KG", "KG", 25, 0.7, 0.30, None, None),
    ("100701", "INSETI", "INSETICIDA LAMBDA-CIALOTRINA 50 EC GL 5L", "INSECTICIDE LAMBDA-CYHALOTHRIN 50 EC 5L", "L", 5, 1.0, 0.70, None, None),
    ("100702", "INSETI", "INSETICIDA CLORANTRANILIPROLE 200 SC GL 1L", "INSECTICIDE CHLORANTRANILIPROLE 200 SC 1L", "L", 1, 0.4, 4.50, None, None),
    ("100703", "INSETI", "INSETICIDA ACEFATO 750 SP SC 25KG", "INSECTICIDE ACEPHATE 750 SP 25KG", "KG", 25, 0.7, 0.45, None, None),
    ("100801", "ADJUV", "OLEO MINERAL ADJUVANTE GL 20L", "MINERAL OIL ADJUVANT 20L", "L", 20, 1.0, 1.00, None, None),
    ("100802", "ADJUV", "ESPALHANTE ADESIVO GL 5L", "SPREADER STICKER 5L", "L", 5, 0.5, 1.40, None, None),
]

NOMES_FAZENDA = [
    "SANTA MARIA", "BOA ESPERANCA", "SAO JOSE", "TRES IRMAOS", "PRIMAVERA", "BOM JESUS",
    "AGUA LIMPA", "RIO VERDE", "SANTA LUZIA", "PLANALTO", "SERRA AZUL", "VALE DO SOL",
    "SAO FRANCISCO", "NOVA ALIANCA", "ESTRELA", "PARAISO", "SANTA RITA", "BELA VISTA",
    "CAMPO VERDE", "SAO PEDRO", "ITAMARATI", "TAQUARAL", "BURITI", "CACHOEIRA",
    "AGUA BOA", "SANTO ANTONIO", "MORRO ALTO", "TRES LAGOAS", "PORTEIRA", "CERRADAO",
]
PREFIXOS = ["FAZENDA", "AGROPECUARIA", "SITIO", "GRUPO", "AGRO"]


def _perfil(picos, x):
    """Curva sazonal (soma de gaussianas circulares no ano-safra) avaliada em x."""
    y = np.full_like(np.asarray(x, dtype=float), 0.04)
    for centro, largura, peso in picos:
        d = (np.asarray(x) - centro + SEMANAS_SAFRA / 2) % SEMANAS_SAFRA - SEMANAS_SAFRA / 2
        y = y + peso * np.exp(-0.5 * (d / largura) ** 2)
    return y


def _ciclo_de_vida(ciclo, semanas):
    if ciclo is None:
        return np.ones(len(semanas))
    tipo, semana = ciclo
    s = np.asarray(semanas)
    if tipo == "saida":       # última safra já em queda; depois descontinuado
        return np.where(s >= semana, 0.0, np.where(s >= semana - SEMANAS_SAFRA, 0.6, 1.0))
    return np.where(s < semana, 0.0, np.where(s < semana + SEMANAS_SAFRA, 0.6, 1.0))


def _clientes(rng):
    linhas, por_centro, numero = [], {}, 100001
    for werks, _, _, porte, _, cidades in CENTROS:
        n = int(40 + 50 * porte)
        ids = []
        for _ in range(n):
            nome = f"{rng.choice(PREFIXOS)} {rng.choice(NOMES_FAZENDA)}"
            if rng.random() < 0.35:
                nome += f" {rng.choice(['I', 'II', 'III', 'LTDA', 'S/A'])}"
            kunnr = f"{numero:010d}"
            linhas.append(dict(KUNNR=kunnr, NAME1=nome, ORT01=rng.choice(cidades),
                               REGIO="MT", LAND1="BR", KTOKD="0001"))
            ids.append(kunnr)
            numero += 1
        peso = rng.pareto(1.3, n) + 0.2            # poucos clientes grandes
        por_centro[werks] = (np.array(ids), peso / peso.sum())
    return pd.DataFrame(linhas), por_centro


def gerar(semente: int = SEMENTE, n_safras: int = N_SAFRAS) -> dict[str, pd.DataFrame]:
    """Gera todas as tabelas. Determinístico para uma mesma semente."""
    rng = np.random.default_rng(semente)
    n_sem = n_safras * SEMANAS_SAFRA
    semanas = np.arange(n_sem)
    safra = semanas // SEMANAS_SAFRA
    sem_safra = semanas % SEMANAS_SAFRA

    kna1, clientes_centro = _clientes(rng)
    pesos_familia = {}
    for m in MATERIAIS:
        pesos_familia[m[1]] = pesos_familia.get(m[1], 0.0) + m[6]

    afinidade = {(c[0], f): rng.lognormal(0, 0.2) for c in CENTROS for f in FAMILIAS}
    for werks in ("1104", "1105", "1106"):          # milho safrinha forte no médio-norte
        afinidade[(werks, "SEMMILHO")] *= 1.3
    ruido_ano = {(f, c[0], s): rng.normal(1, 0.04)
                 for f in FAMILIAS for c in CENTROS for s in range(n_safras)}

    blocos = []
    for i_mat, (_num, grupo, _pt, _en, _un, emb, peso, _fp, picos_mat, ciclo) in \
            enumerate(MATERIAIS):
        fam = FAMILIAS[grupo]
        picos = picos_mat or fam["picos"]
        norma = _perfil(picos, np.arange(SEMANAS_SAFRA)).mean()
        base = fam["volume"] * peso / pesos_familia[grupo] / SEMANAS_SAFRA
        pedido = max(fam["pedido"] * (0.6 + 0.4 * peso), 2 * emb)
        for werks, _, _, porte, desl_reg, _ in CENTROS:
            x = sem_safra - np.array(DESLOCAMENTO_SAFRA)[safra] - desl_reg
            mu = (base * porte * afinidade[(werks, grupo)] * _perfil(picos, x) / norma
                  * (1 + CRESCIMENTO_ANUAL) ** (semanas / SEMANAS_SAFRA)
                  * np.array([CHOQUES.get((grupo, s), 1.0) for s in safra])
                  * np.array([ruido_ano[(grupo, werks, s)] for s in safra])
                  * _ciclo_de_vida(ciclo, semanas)
                  * rng.lognormal(-0.02, 0.2, n_sem))
            n_ped = rng.poisson(mu / pedido)
            total = int(n_ped.sum())
            if total == 0:
                continue
            qtd = rng.gamma(2.0, pedido / 2.0, total)
            qtd = np.maximum(emb, np.round(qtd / emb) * emb)
            blocos.append(pd.DataFrame({
                "i_mat": i_mat, "WERKS": werks,
                "semana": np.repeat(semanas, n_ped), "qtd": qtd,
            }))
    itens = pd.concat(blocos, ignore_index=True)

    # cliente de cada pedido (ponderado pelo porte do cliente na filial)
    itens["KUNNR"] = ""
    for werks, (ids, p) in clientes_centro.items():
        idx = itens.index[itens["WERKS"] == werks]
        itens.loc[idx, "KUNNR"] = rng.choice(ids, size=len(idx), p=p)

    # um documento por cliente, filial e semana (itens de famílias diferentes juntos)
    itens = itens.sort_values(["semana", "WERKS", "KUNNR", "i_mat"], kind="stable")
    itens["doc"] = itens.groupby(["semana", "WERKS", "KUNNR"], sort=False).ngroup()
    docs = itens.groupby("doc", sort=True).agg(semana=("semana", "first"),
                                               WERKS=("WERKS", "first"),
                                               KUNNR=("KUNNR", "first")).reset_index()
    dia = rng.choice(6, size=len(docs), p=[.2, .2, .2, .18, .15, .07])
    docs["data"] = INICIO + pd.to_timedelta(docs["semana"] * 7 + dia, unit="D")
    docs["AUART"] = np.where(rng.random(len(docs)) < 0.04, "ZBON", "ZVEN")
    itens["ABGRU"] = ""

    # itens recusados (não viram demanda firme): ~3% dos documentos
    recusa = docs.sample(frac=0.03, random_state=semente)["doc"].to_numpy()
    extra = itens[itens["doc"].isin(recusa)].groupby("doc").head(1).copy()
    extra["i_mat"] = rng.integers(0, len(MATERIAIS), len(extra))
    extra["ABGRU"] = rng.choice(["01", "02", "03", "05"], len(extra))
    itens = pd.concat([itens, extra], ignore_index=True)
    itens["POSNR"] = (itens.groupby("doc").cumcount() + 1) * 10

    # devoluções: documentos ZDEV de 1 a 6 semanas depois da venda (~1,5% dos itens)
    vendas = itens[(itens["ABGRU"] == "") & itens["doc"].isin(
        docs.loc[docs["AUART"] == "ZVEN", "doc"])]
    dev = vendas.sample(frac=0.015, random_state=semente + 1).copy()
    dev = dev.merge(docs[["doc", "data"]], on="doc")
    dev["data"] = dev["data"] + pd.to_timedelta(rng.integers(7, 43, len(dev)), unit="D")
    dev = dev[dev["data"] < INICIO + pd.Timedelta(weeks=n_sem)].copy()
    emb_dev = np.array([MATERIAIS[i][5] for i in dev["i_mat"]])
    dev["qtd"] = np.maximum(emb_dev, np.round(dev["qtd"] * rng.uniform(.1, .5, len(dev))
                                              / emb_dev) * emb_dev)
    dev["doc"] = np.arange(len(dev)) + docs["doc"].max() + 1
    dev["POSNR"] = 10
    docs_dev = dev[["doc", "WERKS", "KUNNR", "data"]].copy()
    docs_dev["semana"] = ((docs_dev["data"] - INICIO).dt.days // 7).astype(int)
    docs_dev["AUART"] = "ZDEV"
    docs = pd.concat([docs, docs_dev], ignore_index=True)
    itens = pd.concat([itens, dev.drop(columns="data")], ignore_index=True)

    # numeração SAP crescente no tempo
    docs = docs.sort_values(["data", "doc"]).reset_index(drop=True)
    docs["VBELN"] = [f"{10_000_001 + i:010d}" for i in range(len(docs))]
    itens = itens.merge(docs[["doc", "VBELN", "AUART", "data"]], on="doc")

    # valores
    mat = pd.DataFrame(MATERIAIS, columns=["num", "grupo", "pt", "en", "un", "emb", "peso",
                                           "fpreco", "picos", "ciclo"])
    itens = itens.merge(mat[["num", "grupo", "un", "fpreco"]], left_on="i_mat",
                        right_index=True)
    safra_item = ((itens["data"] - INICIO).dt.days // 7 // SEMANAS_SAFRA).clip(0, n_safras - 1)
    indice = np.array([INDICE_PRECO.get(g, INDICE_PRECO_PADRAO)[s]
                       for g, s in zip(itens["grupo"], safra_item)])
    preco = np.array([FAMILIAS[g]["preco"] for g in itens["grupo"]]) * itens["fpreco"] * indice
    valor = itens["qtd"] * preco * rng.uniform(0.92, 1.0, len(itens))
    itens["NETWR"] = np.where(itens["AUART"] == "ZBON", 0.0, valor)
    itens["PSTYV"] = np.where(itens["AUART"] == "ZBON", "TANN",
                              np.where(itens["AUART"] == "ZDEV", "REN", "TAN"))

    vbap = pd.DataFrame({
        "VBELN": itens["VBELN"],
        "POSNR": itens["POSNR"].map(lambda p: f"{p:06d}"),
        "MATNR": itens["num"].map(lambda n: n.zfill(18)),
        "WERKS": itens["WERKS"],
        "KWMENG": itens["qtd"].map(lambda q: f"{q:.3f}"),
        "VRKME": itens["un"],
        "NETWR": itens["NETWR"].map(lambda v: f"{v:.2f}"),
        "WAERK": "BRL",
        "ABGRU": itens["ABGRU"],
        "PSTYV": itens["PSTYV"],
    }).sort_values(["VBELN", "POSNR"])
    # sobreposição de cargas delta: ~0,4% das linhas chegam duplicadas
    vbap = pd.concat([vbap, vbap.sample(frac=0.004, random_state=semente + 2)],
                     ignore_index=True)

    vbak = pd.DataFrame({
        "VBELN": docs["VBELN"], "ERDAT": docs["data"].dt.strftime("%Y%m%d"),
        "AUART": docs["AUART"], "VKORG": "1000", "VTWEG": "10", "SPART": "00",
        "KUNNR": docs["KUNNR"], "WAERK": "BRL",
    })

    mara = pd.DataFrame({
        "MATNR": mat["num"].map(lambda n: n.zfill(18)),
        "ERSDA": [("20240510" if c and c[0] == "entrada" else "20190301") for c in mat["ciclo"]],
        "MTART": "HAWA", "MATKL": mat["grupo"], "MEINS": mat["un"],
        "LVORM": [("X" if c and c[0] == "saida" else "") for c in mat["ciclo"]],
    })
    makt = pd.concat([
        pd.DataFrame({"MATNR": mara["MATNR"], "SPRAS": "P", "MAKTX": mat["pt"]}),
        pd.DataFrame({"MATNR": mara["MATNR"], "SPRAS": "E", "MAKTX": mat["en"]}),
    ], ignore_index=True)
    t023t = pd.DataFrame(
        [(g, "P", f["nome"]) for g, f in FAMILIAS.items()]
        + [(g, "E", f["en"]) for g, f in FAMILIAS.items()],
        columns=["MATKL", "SPRAS", "WGBEZ"])
    t001w = pd.DataFrame([(c[0], c[1], c[2], "MT", "BR") for c in CENTROS],
                         columns=["WERKS", "NAME1", "ORT01", "REGIO", "LAND1"])

    return {"VBAK": vbak, "VBAP": vbap, "KNA1": kna1, "MARA": mara, "MAKT": makt,
            "T023T": t023t, "T001W": t001w}


def salvar(tabelas: dict[str, pd.DataFrame], destino: Path = DADOS_BRUTOS) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for nome, df in tabelas.items():
        df.to_csv(destino / f"{nome}.csv", index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--saida", type=Path, default=DADOS_BRUTOS)
    ap.add_argument("--semente", type=int, default=SEMENTE)
    args = ap.parse_args()
    tabelas = gerar(args.semente)
    salvar(tabelas, args.saida)
    for nome, df in tabelas.items():
        print(f"{nome:<6} {len(df):>8,} linhas")


if __name__ == "__main__":
    main()
