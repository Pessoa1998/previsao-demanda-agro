"""Figuras do case, em versão clara e escura (para o README do GitHub).

Paleta categórica validada (CVD e contraste) e cor fixa por entidade em todos os
gráficos: modelo = azul, média móvel = laranja, sazonal ingênuo = verde-água,
realizado = tinta principal.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

TEMAS = {
    "claro": dict(fundo="#ffffff", tinta="#0b0b0b", tinta2="#52514e", suave="#898781",
                  grade="#e1e0d9", eixo="#c3c2b7", outras="#c3c2b7",
                  modelo="#2a78d6", media_movel="#eb6834", sazonal="#1baf7a",
                  destaque="#6250d6"),
    "escuro": dict(fundo="#0d1117", tinta="#f0efec", tinta2="#c3c2b7", suave="#898781",
                   grade="#21262d", eixo="#30363d", outras="#4a4a46",
                   modelo="#3987e5", media_movel="#d95926", sazonal="#199e70",
                   destaque="#9085e9"),
}
ROTULOS = {
    "prev_modelo": ("Modelo", "modelo", "o"),
    "prev_sazonal_ingenuo": ("Sazonal ingênuo", "sazonal", "s"),
    "prev_media_movel": ("Média móvel", "media_movel", "^"),
}
MESES_SAFRA = [("jul", 0), ("ago", 4), ("set", 9), ("out", 13), ("nov", 17), ("dez", 22),
               ("jan", 26), ("fev", 30), ("mar", 35), ("abr", 39), ("mai", 43), ("jun", 48)]
MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
reais = FuncFormatter(lambda v, _: f"R$ {v:,.0f} mi".replace(",", "."))
mes_ano = FuncFormatter(lambda v, _: (lambda d: f"{MESES_PT[d.month - 1]}/{d:%y}")(
    matplotlib.dates.num2date(v)))


def _figura(t, largura=8.0, altura=4.4, ncols=1):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5,
                         "axes.titlesize": 10.5})
    fig, axes = plt.subplots(1, ncols, figsize=(largura, altura), dpi=200,
                             facecolor=t["fundo"], squeeze=False)
    for ax in axes.flat:
        ax.set_facecolor(t["fundo"])
        for lado in ("top", "right", "left"):
            ax.spines[lado].set_visible(False)
        ax.spines["bottom"].set_color(t["eixo"])
        ax.tick_params(colors=t["tinta2"], length=0, pad=6)
        ax.grid(axis="y", color=t["grade"], linewidth=0.6)
        ax.set_axisbelow(True)
    return fig, axes.flat


def _titulo(fig, t, titulo, subtitulo):
    fig.text(0.012, 0.975, titulo, color=t["tinta"], fontsize=12.5, fontweight="bold",
             va="top")
    fig.text(0.012, 0.905, subtitulo, color=t["tinta2"], fontsize=9.5, va="top")


def _salvar(fig, destino: Path, t):
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino, facecolor=t["fundo"])
    plt.close(fig)


SAFRA_DESTAQUE = "23/24"


def _safra(inicio: pd.Timestamp, k: int) -> str:
    """Rótulo da k-ésima safra contada a partir da semana inicial (julho)."""
    return f"{(inicio.year + k) % 100:02d}/{(inicio.year + k + 1) % 100:02d}"


# --------------------------------------------------------------------- figuras
def sazonalidade(demanda: pd.DataFrame, dim_material: pd.DataFrame, destino: Path, tema: str):
    """Demanda semanal por safra (sementes de soja e milho), com a safra 23/24 em destaque."""
    t = TEMAS[tema]
    d = demanda.merge(dim_material[["material", "familia"]], on="material")
    inicio = d["semana"].min()
    d["indice"] = (d["semana"] - inicio).dt.days // 7
    d["safra"], d["semana_safra"] = d["indice"] // 52, d["indice"] % 52
    fig, axes = _figura(t, altura=4.2, ncols=2)
    for ax, fam, un in zip(axes, ["SEMENTES DE SOJA", "SEMENTES DE MILHO"],
                           ["mil sacas", "mil sacas"]):
        g = (d[d["familia"] == fam].groupby(["safra", "semana_safra"])["quantidade"].sum()
             .unstack(0).rolling(3, center=True, min_periods=1).mean() / 1000)
        for s in g.columns:
            destaque = _safra(inicio, s) == SAFRA_DESTAQUE
            ax.plot(g.index, g[s], color=t["destaque"] if destaque else t["outras"],
                    linewidth=2.2 if destaque else 1.3, zorder=3 if destaque else 2,
                    solid_capstyle="round", gid="destaque" if destaque else None)
        ax.set_title(fam.capitalize(), color=t["tinta"], loc="left", pad=8)
        ax.set_xticks([p for _, p in MESES_SAFRA[::2]], [m for m, _ in MESES_SAFRA[::2]])
        ax.set_xlim(0, 51)
        ax.set_ylim(0, None)
        ax.set_ylabel(f"demanda semanal ({un})", color=t["tinta2"])
    pico = next(linha for linha in axes[0].lines if linha.get_gid() == "destaque")
    x, y = pico.get_xdata(), pico.get_ydata()
    i = int(np.nanargmax(y))
    axes[0].annotate("23/24: chuva atrasou\no plantio", xy=(x[i], y[i]),
                     xytext=(x[i] + 7, y[i] * 0.98), color=t["tinta"], fontsize=9,
                     arrowprops=dict(arrowstyle="-", color=t["suave"], lw=0.8))
    handles = [plt.Line2D([], [], color=t["destaque"], lw=2.2),
               plt.Line2D([], [], color=t["outras"], lw=1.3)]
    safras = [_safra(inicio, k) for k in sorted(d["safra"].unique())]
    fig.legend(handles, [f"Safra {SAFRA_DESTAQUE}",
                         f"Demais safras ({safras[0]} a {safras[-1]})"],
               loc="upper right", bbox_to_anchor=(0.99, 0.985), ncols=2, frameon=False,
               labelcolor=t["tinta2"])
    _titulo(fig, t, "A safra muda de data todo ano",
            "Demanda semanal somada das 6 filiais (média móvel de 3 semanas)")
    fig.subplots_adjust(left=0.07, right=0.985, top=0.76, bottom=0.1, wspace=0.18)
    _salvar(fig, destino, t)


def previsao_vs_real(teste: pd.DataFrame, destino: Path, tema: str):
    """Demanda das próximas 4 semanas (R$) somada de todas as séries, no ano de teste."""
    t = TEMAS[tema]
    cols = ["y", *ROTULOS]
    v = teste[cols].mul(teste["preco"], axis=0)
    v["semana"] = teste["semana_origem"]
    g = v.groupby("semana")[cols].sum() / 1e6
    fig, (ax,) = _figura(t, altura=4.4)
    for col, (nome, chave, _m) in reversed(list(ROTULOS.items())):
        ax.plot(g.index, g[col], color=t[chave], linewidth=1.7, label=nome,
                solid_capstyle="round")
    ax.plot(g.index, g["y"], color=t["tinta"], linewidth=2.3, label="Realizado",
            solid_capstyle="round")
    ax.yaxis.set_major_formatter(reais)
    ax.set_ylim(0, None)
    ax.margins(x=0.01)
    ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(bymonth=range(1, 13, 2)))
    ax.xaxis.set_major_formatter(mes_ano)
    leg = ax.legend(loc="upper right", ncols=4, frameon=False, labelcolor=t["tinta2"],
                    bbox_to_anchor=(1.0, 1.13), handlelength=1.6)
    leg.set_zorder(5)
    _titulo(fig, t, "Previsão × realizado na safra de teste (25/26)",
            "Valor da demanda das 4 semanas seguintes a cada semana, soma das 180 séries")
    fig.subplots_adjust(left=0.1, right=0.985, top=0.8, bottom=0.09)
    _salvar(fig, destino, t)


def erro_por_familia(metricas_familia: pd.DataFrame, destino: Path, tema: str):
    """WAPE em valor por família (gráfico de pontos)."""
    t = TEMAS[tema]
    nomes = {"prev_modelo": "Modelo (gradient boosting)",
             "prev_media_movel": "Média móvel 4 semanas",
             "prev_sazonal_ingenuo": "Sazonal ingênuo (ano anterior)"}
    w = pd.DataFrame({k: metricas_familia[(n, "WAPE")] for k, n in nomes.items()}) * 100
    w = w.sort_values("prev_modelo", ascending=False)
    fig, (ax,) = _figura(t, altura=4.6)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=t["grade"], linewidth=0.6)
    ypos = np.arange(len(w))
    for y in ypos:
        ax.plot([w.iloc[y].min(), w.iloc[y].max()], [y, y], color=t["grade"], lw=2.5,
                zorder=1, solid_capstyle="round")
    for col, (nome, chave, marcador) in ROTULOS.items():
        ax.scatter(w[col], ypos, s=46, marker=marcador, color=t[chave], label=nome,
                   zorder=3, edgecolors=t["fundo"], linewidths=1.2)
    ax.set_yticks(ypos, [f.capitalize() for f in w.index], color=t["tinta"])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.set_xlim(0, 100)
    ax.set_xticks(range(0, 101, 20))
    ax.spines["bottom"].set_visible(False)
    ax.legend(loc="upper right", ncols=3, frameon=False, labelcolor=t["tinta2"],
              bbox_to_anchor=(1.0, 1.12), handletextpad=0.3)
    _titulo(fig, t, "Erro por família na safra de teste (WAPE em R$, menor é melhor)",
            "O modelo erra menos em todas as famílias")
    fig.subplots_adjust(left=0.2, right=0.965, top=0.8, bottom=0.08)
    _salvar(fig, destino, t)


def tradeoff_estoque(curvas: dict[str, pd.DataFrame], alvo: float, destino: Path, tema: str):
    """Nível de atendimento × estoque médio: quanto capital cada método exige."""
    t = TEMAS[tema]
    chaves = {"Modelo (gradient boosting)": "prev_modelo",
              "Média móvel 4 semanas": "prev_media_movel",
              "Sazonal ingênuo (ano anterior)": "prev_sazonal_ingenuo"}
    fig, (ax,) = _figura(t, altura=4.6)
    ax.axvline(alvo * 100, color=t["suave"], lw=0.9, ls=(0, (3, 3)), zorder=1)
    ax.text(alvo * 100 - 0.25, 0.02, f"alvo {alvo:.0%}", transform=ax.get_xaxis_transform(),
            color=t["tinta2"], fontsize=8.5, ha="right")
    for nome, c in curvas.items():
        rot, chave, marcador = ROTULOS[chaves[nome]]
        c = c[(c["atendimento"] >= 0.80)]
        ax.plot(c["atendimento"] * 100, c["estoque_rs_mi"], color=t[chave], lw=1.9,
                label=rot, solid_capstyle="round")
        ordem = c.sort_values("atendimento").drop_duplicates("atendimento")
        y_alvo = float(np.interp(alvo, ordem["atendimento"], ordem["estoque_rs_mi"]))
        ax.scatter([alvo * 100], [y_alvo], s=52, marker=marcador, color=t[chave], zorder=4,
                   edgecolors=t["fundo"], linewidths=1.3)
        ax.annotate(f"R$ {y_alvo:,.1f} mi".replace(",", "X").replace(".", ",").replace("X", "."),
                    xy=(alvo * 100, y_alvo), xytext=(-10, 0), textcoords="offset points",
                    ha="right", va="center", color=t["tinta"], fontsize=9)
    ax.yaxis.set_major_formatter(reais)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.set_xlim(80, 100)
    ax.set_xticks(range(80, 101, 5))
    ax.set_ylim(0, 140)
    ax.set_xlabel("atendimento (% do valor demandado servido na hora)", color=t["tinta2"])
    h, l = ax.get_legend_handles_labels()
    ordem = [l.index(n) for n in ("Média móvel", "Sazonal ingênuo", "Modelo")]
    ax.legend([h[i] for i in ordem], [l[i] for i in ordem], loc="upper left",
              frameon=False, labelcolor=t["tinta2"])
    _titulo(fig, t, "Quanto estoque cada método exige para o mesmo atendimento",
            "Estoque-alvo médio por semana na safra de teste, variando a margem de segurança")
    fig.subplots_adjust(left=0.11, right=0.965, top=0.82, bottom=0.13)
    _salvar(fig, destino, t)
