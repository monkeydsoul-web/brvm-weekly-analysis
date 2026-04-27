"""
Générateur de rapport PDF — Analyse Hebdomadaire BRVM
Produit un rapport complet avec classements, graphiques et fiches détaillées
"""

import os
import io
import math
import logging
from datetime import datetime

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, HRFlowable, KeepTogether
)
from reportlab.platypus.flowables import BalancedColumns

from valuation import tier_label

logger = logging.getLogger(__name__)

# ── Palette de couleurs ───────────────────────────────────────────────────────
GREEN_DARK  = colors.HexColor("#1A5C2A")
GREEN_MID   = colors.HexColor("#2E8B3F")
GREEN_LIGHT = colors.HexColor("#D4EDDA")
AMBER       = colors.HexColor("#B7791F")
AMBER_LIGHT = colors.HexColor("#FEF3C7")
RED_DARK    = colors.HexColor("#9B1C1C")
RED_LIGHT   = colors.HexColor("#FDE8E8")
GOLD        = colors.HexColor("#D4AF37")
GRAY_DARK   = colors.HexColor("#1F2937")
GRAY_MID    = colors.HexColor("#6B7280")
GRAY_LIGHT  = colors.HexColor("#F3F4F6")
WHITE       = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 1.8 * cm


def score_color(score: float, max_score: float = 70) -> colors.HexColor:
    pct = score / max_score
    if pct >= 0.70: return GREEN_MID
    if pct >= 0.50: return AMBER
    return RED_DARK


def bar_chart_scores(df: pd.DataFrame, top_n: int = 20) -> io.BytesIO:
    """Graphique barres horizontales — Top N scores composites"""
    top = df.head(top_n).copy()
    top = top.iloc[::-1]  # inverser pour afficher le meilleur en haut

    fig, ax = plt.subplots(figsize=(10, top_n * 0.45 + 1.2))
    fig.patch.set_facecolor("#F8FAFC")
    ax.set_facecolor("#F8FAFC")

    cols_map = {
        "Graham": "#2E8B3F", "DCF/FCF": "#0369A1", "DDM": "#7C3AED",
        "EPV": "#B45309", "Buffett": "#DC2626", "Rev.DCF": "#0891B2",
        "Relatif": "#15803D",
    }
    model_cols = ["score_graham", "score_dcf", "score_ddm", "score_epv",
                  "score_buffett", "score_rev_dcf", "score_relatif"]
    model_names = list(cols_map.keys())
    model_colors = list(cols_map.values())

    bottoms = [0] * len(top)
    for i, (col, name, color) in enumerate(zip(model_cols, model_names, model_colors)):
        vals = top[col].fillna(0).tolist()
        bars = ax.barh(top["ticker"].tolist(), vals, left=bottoms,
                       color=color, label=name, height=0.65, alpha=0.88)
        bottoms = [b + v for b, v in zip(bottoms, vals)]

    # Score total à droite
    for idx, (_, row) in enumerate(top.iterrows()):
        ax.text(row["composite_adj"] + 0.3, idx, f"{row['composite_adj']:.0f}",
                va="center", ha="left", fontsize=8, fontweight="bold", color="#1F2937")

    ax.set_xlabel("Score composite /70", fontsize=9, color="#374151")
    ax.set_xlim(0, 75)
    ax.axvline(50, color="#2E8B3F", linestyle="--", linewidth=0.8, alpha=0.6, label="Seuil Fort (50)")
    ax.axvline(35, color="#B7791F", linestyle="--", linewidth=0.8, alpha=0.6, label="Seuil Modéré (35)")
    ax.legend(loc="lower right", fontsize=7, ncol=2, framealpha=0.8)
    ax.tick_params(axis="y", labelsize=8)
    ax.tick_params(axis="x", labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_title(f"Top {top_n} BRVM — Scores multi-modèles", fontsize=11, fontweight="bold",
                 color="#1F2937", pad=10)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf


def heatmap_chart(df: pd.DataFrame, top_n: int = 25) -> io.BytesIO:
    """Heatmap des scores par modèle"""
    top = df.head(top_n).copy()
    score_cols = ["score_graham", "score_dcf", "score_ddm", "score_epv",
                  "score_buffett", "score_rev_dcf", "score_relatif"]
    col_labels = ["Graham", "DCF", "DDM", "EPV", "Buffett", "Rev.DCF", "Relatif"]

    matrix = top[score_cols].values.astype(float)
    tickers = top["ticker"].tolist()

    fig, ax = plt.subplots(figsize=(10, top_n * 0.38 + 1.5))
    fig.patch.set_facecolor("#F8FAFC")

    cmap = plt.cm.RdYlGn
    im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=10)

    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, fontsize=8, fontweight="bold")
    ax.set_yticks(range(len(tickers)))
    ax.set_yticklabels(tickers, fontsize=8)

    for i in range(len(tickers)):
        for j in range(len(col_labels)):
            val = matrix[i, j]
            txt_color = "white" if val < 3.5 or val > 7.5 else "black"
            ax.text(j, i, f"{val:.0f}", ha="center", va="center",
                    fontsize=7.5, color=txt_color, fontweight="bold")

    plt.colorbar(im, ax=ax, shrink=0.6, label="Score /10")
    ax.set_title(f"Heatmap — Scores par modèle (Top {top_n})",
                 fontsize=11, fontweight="bold", pad=10)
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf


def sector_pie(df: pd.DataFrame) -> io.BytesIO:
    """Camembert — répartition sectorielle du marché"""
    sector_counts = df["sector"].value_counts()
    colors_pie = ["#2E8B3F", "#0369A1", "#7C3AED", "#B45309",
                  "#DC2626", "#0891B2", "#15803D", "#92400E"]

    fig, ax = plt.subplots(figsize=(6, 4))
    fig.patch.set_facecolor("#F8FAFC")
    wedges, texts, autotexts = ax.pie(
        sector_counts.values, labels=sector_counts.index,
        autopct="%1.0f%%", colors=colors_pie[:len(sector_counts)],
        startangle=140, pctdistance=0.82
    )
    for t in texts: t.set_fontsize(8)
    for a in autotexts: a.set_fontsize(7); a.set_color("white")
    ax.set_title("Répartition sectorielle BRVM", fontsize=10, fontweight="bold")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf


def make_styles():
    styles = getSampleStyleSheet()
    custom = {
        "Cover": ParagraphStyle("Cover", parent=styles["Title"],
            fontSize=28, textColor=WHITE, alignment=TA_CENTER,
            spaceAfter=8, leading=34),
        "CoverSub": ParagraphStyle("CoverSub", parent=styles["Normal"],
            fontSize=13, textColor=colors.HexColor("#D1FAE5"),
            alignment=TA_CENTER, spaceAfter=4),
        "CoverDate": ParagraphStyle("CoverDate", parent=styles["Normal"],
            fontSize=10, textColor=colors.HexColor("#A7F3D0"),
            alignment=TA_CENTER),
        "SectionTitle": ParagraphStyle("SectionTitle", parent=styles["Heading1"],
            fontSize=14, textColor=GREEN_DARK, spaceBefore=14, spaceAfter=6,
            borderPad=4),
        "SubTitle": ParagraphStyle("SubTitle", parent=styles["Heading2"],
            fontSize=11, textColor=GREEN_DARK, spaceBefore=8, spaceAfter=4),
        "Body": ParagraphStyle("Body", parent=styles["Normal"],
            fontSize=8.5, textColor=GRAY_DARK, spaceAfter=3, leading=12),
        "SmallBody": ParagraphStyle("SmallBody", parent=styles["Normal"],
            fontSize=7.5, textColor=GRAY_MID, spaceAfter=2, leading=10),
        "TableHeader": ParagraphStyle("TableHeader", parent=styles["Normal"],
            fontSize=8, textColor=WHITE, fontName="Helvetica-Bold",
            alignment=TA_CENTER),
        "Detail": ParagraphStyle("Detail", parent=styles["Normal"],
            fontSize=7, textColor=GRAY_MID, leading=9.5, spaceAfter=1),
        "Ticker": ParagraphStyle("Ticker", parent=styles["Normal"],
            fontSize=14, fontName="Helvetica-Bold", textColor=GREEN_DARK),
        "Disclaimer": ParagraphStyle("Disclaimer", parent=styles["Normal"],
            fontSize=7, textColor=GRAY_MID, alignment=TA_CENTER, leading=9),
    }
    for k, v in custom.items():
        styles.add(v)
    return styles


def score_badge_color(score: float) -> colors.HexColor:
    if score >= 7: return GREEN_LIGHT
    if score >= 4: return AMBER_LIGHT
    return RED_LIGHT


def score_text_color(score: float) -> colors.HexColor:
    if score >= 7: return GREEN_DARK
    if score >= 4: return AMBER
    return RED_DARK


def generate_report(
    df_scores: pd.DataFrame,
    output_path: str,
    week_label: str = None,
    prev_df: pd.DataFrame = None,
) -> str:
    """Génère le rapport PDF complet"""
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    week_label = week_label or datetime.now().strftime("Semaine du %d %B %Y")
    styles = make_styles()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=f"Analyse BRVM — {week_label}",
        author="BRVM Analyzer",
    )

    story = []

    # ── PAGE DE COUVERTURE ────────────────────────────────────────────────────
    story.append(Spacer(1, 3 * cm))

    # Fond vert simulé avec rectangle
    cover_table = Table([[
        Paragraph("📈 ANALYSE HEBDOMADAIRE BRVM", styles["Cover"]),
    ]], colWidths=[PAGE_W - 2 * MARGIN])
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GREEN_DARK),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [GREEN_DARK]),
        ("TOPPADDING", (0, 0), (-1, -1), 20),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
        ("ROUNDEDCORNERS", [8]),
    ]))
    story.append(cover_table)
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(week_label, styles["CoverSub"]))
    story.append(Paragraph(
        f"Rapport généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
        styles["CoverDate"]
    ))
    story.append(Spacer(1, 1.5 * cm))

    # Statistiques de couverture
    n_stocks = len(df_scores)
    n_strong = len(df_scores[df_scores["composite_adj"] >= 50])
    n_moderate = len(df_scores[(df_scores["composite_adj"] >= 35) & (df_scores["composite_adj"] < 50)])
    n_weak = n_stocks - n_strong - n_moderate

    stats_data = [
        ["Actions analysées", "Fort (≥50/70)", "Modéré (35–50)", "Faible (<35)"],
        [str(n_stocks), str(n_strong), str(n_moderate), str(n_weak)],
    ]
    stats_table = Table(stats_data, colWidths=[(PAGE_W - 2 * MARGIN) / 4] * 4)
    stats_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 1), (-1, 1), GREEN_LIGHT),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 16),
        ("TEXTCOLOR", (0, 1), (-1, 1), GREEN_DARK),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9CA3AF")),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 1 * cm))

    # Top 3 podium
    top3 = df_scores.head(3)
    medals = ["🥇", "🥈", "🥉"]
    story.append(Paragraph("🏆 Podium de la semaine", styles["SectionTitle"]))
    podium_data = [["", "Ticker", "Société", "Pays", "Score /70", "Tier", "P/E", "Div."]]
    for i, (_, row) in enumerate(top3.iterrows()):
        div_str = f"{row['div_yield']:.1f}%" if row.get("div_yield") else "—"
        price_str = f"{row['price']:,.0f}" if row.get("price") else "—"
        podium_data.append([
            medals[i],
            row["ticker"],
            row["name"][:28],
            row["country"],
            f"{row['composite_adj']:.0f}",
            tier_label(row["composite_adj"]),
            f"{row['pe_ref']}×",
            div_str,
        ])

    podium_table = Table(podium_data, colWidths=[0.6*cm, 1.4*cm, 5.2*cm, 2.8*cm, 1.6*cm, 2.2*cm, 1.2*cm, 1.2*cm])
    podium_style = [
        ("BACKGROUND", (0, 0), (-1, 0), GREEN_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FEF9C3")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#F1F5F9")),
        ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#FEF3E2")),
    ]
    podium_table.setStyle(TableStyle(podium_style))
    story.append(podium_table)
    story.append(PageBreak())

    # ── GRAPHIQUES ────────────────────────────────────────────────────────────
    story.append(Paragraph("1. Vue d'ensemble — Scores composites", styles["SectionTitle"]))
    story.append(Paragraph(
        "Chaque barre représente le score composite /70 d'une action, décomposé par modèle de valorisation. "
        "Les lignes en pointillés indiquent les seuils Fort (50) et Modéré (35).",
        styles["Body"]
    ))

    bar_buf = bar_chart_scores(df_scores, top_n=min(25, len(df_scores)))
    story.append(Image(bar_buf, width=PAGE_W - 2 * MARGIN, height=11 * cm))
    story.append(Spacer(1, 0.5 * cm))

    # Camembert sectoriel
    story.append(Paragraph("Répartition sectorielle du marché BRVM", styles["SubTitle"]))
    pie_buf = sector_pie(df_scores)
    story.append(Image(pie_buf, width=10 * cm, height=6.5 * cm))
    story.append(PageBreak())

    # ── HEATMAP ───────────────────────────────────────────────────────────────
    story.append(Paragraph("2. Heatmap multi-modèles", styles["SectionTitle"]))
    story.append(Paragraph(
        "Vert = score élevé (7–10/10), Jaune = modéré (4–6), Rouge = faible (0–3). "
        "Une ligne majoritairement verte signale une action bon marché selon tous les angles.",
        styles["Body"]
    ))
    heat_buf = heatmap_chart(df_scores, top_n=min(30, len(df_scores)))
    story.append(Image(heat_buf, width=PAGE_W - 2 * MARGIN, height=12 * cm))
    story.append(PageBreak())

    # ── CLASSEMENT COMPLET ────────────────────────────────────────────────────
    story.append(Paragraph("3. Classement complet — Toutes les actions BRVM", styles["SectionTitle"]))

    header = ["#", "Ticker", "Société", "Pays", "Cours XOF", "Var%",
              "P/E", "P/B", "ROE", "Div%", "/70", "Graham", "DCF",
              "DDM", "EPV", "Buffett", "RevDCF", "Relatif", "Tier"]
    col_widths = [0.5,1.2,4.0,2.3,1.5,1.0,0.9,0.8,0.9,0.9,1.0,1.0,0.9,0.9,0.9,1.1,1.1,1.1,1.8]
    col_widths = [w * cm for w in col_widths]

    table_data = [header]
    for _, row in df_scores.iterrows():
        price_str = f"{row['price']:,.0f}" if row.get("price") else "N/D"
        chg = row.get("change_pct", 0) or 0
        chg_str = f"{chg:+.1f}%" if chg else "—"
        div_str = f"{row['div_yield']:.1f}" if row.get("div_yield") else "—"
        mcap_str = f"{row['market_cap_xof']/1e9:.0f}G" if row.get("market_cap_xof") else ""

        table_data.append([
            str(int(row["rank"])),
            row["ticker"],
            row["name"][:22],
            row["country"][:12],
            price_str,
            chg_str,
            f"{row['pe_ref']}×",
            f"{row['pb_ref']}×",
            f"{row['roe']}%",
            div_str,
            f"{row['composite_adj']:.0f}",
            f"{row['score_graham']:.0f}",
            f"{row['score_dcf']:.0f}",
            f"{row['score_ddm']:.0f}",
            f"{row['score_epv']:.0f}",
            f"{row['score_buffett']:.0f}",
            f"{row['score_rev_dcf']:.0f}",
            f"{row['score_relatif']:.0f}",
            tier_label(row["composite_adj"])[:10],
        ])

    full_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), GREEN_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#D1D5DB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GRAY_LIGHT]),
    ]

    # Coloriser le score composite
    for i in range(1, len(table_data)):
        try:
            s = float(table_data[i][10])
            bg = GREEN_LIGHT if s >= 50 else (AMBER_LIGHT if s >= 35 else RED_LIGHT)
            ts.append(("BACKGROUND", (10, i), (10, i), bg))
        except:
            pass

    full_table.setStyle(TableStyle(ts))
    story.append(full_table)
    story.append(PageBreak())

    # ── FICHES DÉTAILLÉES — TOP 15 ────────────────────────────────────────────
    story.append(Paragraph("4. Fiches détaillées — Top 15 actions", styles["SectionTitle"]))
    story.append(Paragraph(
        "Analyse complète avec détail de chacun des 7 modèles de valorisation.",
        styles["Body"]
    ))

    top15 = df_scores.head(15)
    for _, row in top15.iterrows():
        price_str = f"{row['price']:,.0f} XOF" if row.get("price") else "N/D"
        chg = row.get("change_pct", 0) or 0
        chg_str = f"{chg:+.2f}%"
        div_str = f"{row['div_yield']:.2f}%" if row.get("div_yield") else "N/D"
        tier = tier_label(row["composite_adj"])
        tier_col = GREEN_LIGHT if "FORT" in tier else (AMBER_LIGHT if "MODÉRÉ" in tier else RED_LIGHT)
        tier_txt_col = GREEN_DARK if "FORT" in tier else (AMBER if "MODÉRÉ" in tier else RED_DARK)

        # En-tête de fiche
        header_data = [[
            Paragraph(f"#{int(row['rank'])}  {row['ticker']}", styles["Ticker"]),
            Paragraph(row["name"], styles["Body"]),
            Paragraph(f"{row['composite_adj']:.0f}/70  {tier}", styles["Body"]),
        ]]
        header_t = Table(header_data, colWidths=[3*cm, 8*cm, 5.2*cm])
        header_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), GREEN_LIGHT),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -1), 1.5, GREEN_DARK),
        ]))
        story.append(header_t)

        # Métriques rapides
        metrics = [
            ["Cours", price_str, "Variation", chg_str, "P/E", f"{row['pe_ref']}×", "P/B", f"{row['pb_ref']}×"],
            ["ROE", f"{row['roe']}%", "Div. yield", div_str, "Secteur", row["sector"], "Pays", row["country"]],
        ]
        m_table = Table(metrics, colWidths=[1.8*cm, 2.2*cm, 1.8*cm, 1.8*cm, 1.4*cm, 2.6*cm, 1.4*cm, 3.2*cm])
        m_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTNAME", (4, 0), (4, -1), "Helvetica-Bold"),
            ("FONTNAME", (6, 0), (6, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BACKGROUND", (0, 0), (-1, -1), WHITE),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
            ("TEXTCOLOR", (0, 0), (0, -1), GRAY_MID),
            ("TEXTCOLOR", (2, 0), (2, -1), GRAY_MID),
            ("TEXTCOLOR", (4, 0), (4, -1), GRAY_MID),
            ("TEXTCOLOR", (6, 0), (6, -1), GRAY_MID),
        ]))
        story.append(m_table)

        # Scores par modèle avec barres
        model_details = [
            ("Graham",   row["score_graham"],  row["detail_graham"]),
            ("DCF/FCF",  row["score_dcf"],     row["detail_dcf"]),
            ("DDM",      row["score_ddm"],      row["detail_ddm"]),
            ("EPV",      row["score_epv"],      row["detail_epv"]),
            ("Buffett",  row["score_buffett"],  row["detail_buffett"]),
            ("Rev. DCF", row["score_rev_dcf"],  row["detail_rev_dcf"]),
            ("Relatif",  row["score_relatif"],  row["detail_relatif"]),
        ]

        model_data = [["Modèle", "Score", "Détail"]]
        for label, score, detail in model_details:
            score_str = f"{score:.1f}/10"
            detail_short = detail[:110] + "…" if len(detail) > 110 else detail
            model_data.append([label, score_str, detail_short])

        model_t = Table(model_data, colWidths=[1.8*cm, 1.5*cm, 12.9*cm])
        model_ts = [
            ("BACKGROUND", (0, 0), (-1, 0), GRAY_DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#E5E7EB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GRAY_LIGHT]),
        ]
        for i, (_, score, _) in enumerate(model_details, 1):
            bg = score_badge_color(score)
            tc = score_text_color(score)
            model_ts.append(("BACKGROUND", (1, i), (1, i), bg))
            model_ts.append(("TEXTCOLOR", (1, i), (1, i), tc))
            model_ts.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))

        model_t.setStyle(TableStyle(model_ts))
        story.append(model_t)
        story.append(Spacer(1, 0.4 * cm))

    story.append(PageBreak())

    # ── ANALYSE PAR SECTEUR ───────────────────────────────────────────────────
    story.append(Paragraph("5. Analyse sectorielle", styles["SectionTitle"]))
    for sector in df_scores["sector"].unique():
        sector_df = df_scores[df_scores["sector"] == sector].head(5)
        if sector_df.empty:
            continue
        story.append(Paragraph(f"Secteur : {sector}", styles["SubTitle"]))
        sec_data = [["Rang", "Ticker", "Société", "Cours", "Div%", "Score/70", "Tier"]]
        for _, row in sector_df.iterrows():
            p = f"{row['price']:,.0f}" if row.get("price") else "N/D"
            d = f"{row['div_yield']:.1f}" if row.get("div_yield") else "—"
            sec_data.append([
                str(int(row["rank"])), row["ticker"], row["name"][:30],
                p, d, f"{row['composite_adj']:.0f}", tier_label(row["composite_adj"])[:10]
            ])
        sec_t = Table(sec_data, colWidths=[1.0*cm,1.4*cm,6.0*cm,2.2*cm,1.4*cm,1.8*cm,2.4*cm])
        sec_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GREEN_MID),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREEN_LIGHT]),
        ]))
        story.append(sec_t)
        story.append(Spacer(1, 0.3 * cm))

    story.append(PageBreak())

    # ── DISCLAIMER ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 2 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GRAY_MID))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "⚠️ AVERTISSEMENT — Ce rapport est produit automatiquement à des fins d'information et d'analyse uniquement. "
        "Il ne constitue pas un conseil en investissement. Les scores sont calculés à partir de données publiques "
        "et de paramètres de valorisation standardisés. Les marchés frontières comme la BRVM comportent des risques "
        "spécifiques : liquidité limitée, risque politique, risque de change. Consultez un conseiller financier "
        "agréé avant toute décision d'investissement. Données BRVM © BRVM — Bourse Régionale des Valeurs Mobilières.",
        styles["Disclaimer"]
    ))

    doc.build(story)
    logger.info(f"Rapport PDF généré: {output_path}")
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test avec données fictives
    import sys
    sys.path.insert(0, ".")
    from scraper import STOCK_FUNDAMENTALS
    from valuation import compute_all_scores

    rows = []
    for ticker, f in list(STOCK_FUNDAMENTALS.items())[:10]:
        rows.append({
            "ticker": ticker, "name": f["name"], "sector": f["sector"],
            "country": f["country"], "price": 10000, "change_pct": 1.2,
            "pe_ref": f["pe_hist"], "pb_ref": f["pb_hist"], "roe": f["roe"],
            "div_per_share": f["div_hist"], "div_yield": (f["div_hist"]/10000)*100,
            "debt_level": f["debt"], "earnings_stable": f["stable"],
            "market_cap_xof": 10000 * f["shares"], "eps_est": 10000/f["pe_hist"],
        })
    df = pd.DataFrame(rows)
    scored = compute_all_scores(df)
    out = generate_report(scored, "reports/test_report.pdf")
    print(f"✅ PDF généré: {out}")
