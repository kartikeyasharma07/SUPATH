"""PDF briefs — redesigned around one rule: a panicked reader should be able
to stop after page 1 and already know the call, the number, and what to do.

Structure (the inverted pyramid a SITREP or a BLUF document follows):

  Page 1   BLUF — freshness banner, the call, a risk gauge, six hero numbers,
           the lead action, a pointer to the rest.
  Page 2+  Analyst layer — full corridor table, score derivation as a
           waterfall, every recommendation (bucketed: moves barrels vs.
           prepares only), the scenario cascade if one is running.
  Last     Audit layer — tripwires with proximity bars, deduplicated
           evidence, assumptions. Everything above is reconstructible from
           what's on this page.

Two documents get asked for:
  Situation Brief  — the full picture, as above.
  Last 24 Hours    — page 1 only, condensed to a single page.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.graphics.shapes import Drawing, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from ..reference import INDIA, RISK_BANDS

# ---------------------------------------------------------------------------
# Palette — the same restrained, low-contrast, three-status language as the
# website. Colour is reserved for meaning: a red thing on this page is a
# risk, never decoration.
# ---------------------------------------------------------------------------

INK = colors.HexColor("#12281F")
INK_2 = colors.HexColor("#2B3A32")
MUTED = colors.HexColor("#5B6B61")
FAINT = colors.HexColor("#8B9A91")
GREEN = colors.HexColor("#1F6F43")
GREEN_DEEP = colors.HexColor("#123F27")
MOSS = colors.HexColor("#4C7C5C")
LINE = colors.HexColor("#D8E2DA")
LINE_2 = colors.HexColor("#C7D6CB")
WASH = colors.HexColor("#F2F6F2")
AMBER = colors.HexColor("#B07819")
AMBER_WASH = colors.HexColor("#FBF1DD")
RUST = colors.HexColor("#A6432B")
RUST_WASH = colors.HexColor("#FBEDE9")
SEVERE = colors.HexColor("#7E2418")
TEAL = colors.HexColor("#2E7A8C")

BAND_COLOUR = {"low": MOSS, "moderate": GREEN, "elevated": AMBER,
               "high": RUST, "severe": SEVERE}

# Distinguishable, still-muted hues for the five risk-derivation terms —
# these signal "which factor", not "how bad", so they get their own small
# palette rather than reusing the band colours.
TERM_COLOUR = {
    "Conflict & Security": RUST, "Sanctions Exposure": AMBER,
    "Port Congestion": MOSS, "Weather & Sea State": TEAL,
    "Market Stress": GREEN_DEEP,
}
TERM_FALLBACK = [RUST, AMBER, MOSS, TEAL, GREEN_DEEP]

CATEGORY = {
    "REROUTE_SUPPLY": ("SOURCE", GREEN),
    "SPR_DRAW": ("RESERVE", TEAL),
    "PORT_CLEARANCE": ("PORT OPS", AMBER),
    "DEMAND_MGMT": ("DEMAND", MUTED),
}


def _category(rec_id: str) -> tuple[str, colors.Color]:
    if rec_id.startswith("REROUTE_") and rec_id != "REROUTE_SUPPLY":
        return ("CORRIDOR", GREEN)
    return CATEGORY.get(rec_id, ("ACTION", MOSS))


# ---------------------------------------------------------------------------
# Typography — a real scale, on purpose. The hero tier (page-1 numbers) did
# not exist before; it is the single biggest legibility fix available.
# ---------------------------------------------------------------------------

def _styles():
    ss = getSampleStyleSheet()
    return {
        "masthead": ParagraphStyle("mh", fontName="Helvetica-Bold", fontSize=8.5,
                                   leading=11, textColor=MOSS),
        "title": ParagraphStyle("t", fontName="Times-Bold", fontSize=21, leading=25,
                                textColor=INK, alignment=TA_LEFT),
        "thesis": ParagraphStyle("th", fontName="Times-Italic", fontSize=10, leading=14,
                                 textColor=GREEN_DEEP),
        "eyebrow": ParagraphStyle("e", fontName="Helvetica-Bold", fontSize=8,
                                  leading=10.5, textColor=MOSS),
        "h2": ParagraphStyle("h2", fontName="Times-Bold", fontSize=13, leading=16,
                             textColor=INK, spaceBefore=13, spaceAfter=5),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.5, leading=13,
                             textColor=INK),
        "body": ParagraphStyle("b", fontName="Helvetica", fontSize=9.7, leading=13.8,
                               textColor=INK_2),
        "small": ParagraphStyle("s", fontName="Helvetica", fontSize=8, leading=11,
                                textColor=MUTED),
        "lead": ParagraphStyle("l", fontName="Times-Roman", fontSize=12, leading=16.5,
                               textColor=INK),
        "cell": ParagraphStyle("c", fontName="Helvetica", fontSize=8, leading=10.5,
                               textColor=INK_2),
        "cell_b": ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=8, leading=10.5,
                                 textColor=INK),
        "hero_v": ParagraphStyle("hv", fontName="Helvetica-Bold", fontSize=25, leading=27,
                                 textColor=INK),
        "hero_l": ParagraphStyle("hl", fontName="Helvetica-Bold", fontSize=7, leading=9,
                                 textColor=MOSS),
        "hero_s": ParagraphStyle("hs", fontName="Helvetica", fontSize=7.3, leading=9,
                                 textColor=MUTED),
        "posture": ParagraphStyle("p", fontName="Times-Bold", fontSize=25, leading=28,
                                  textColor=GREEN_DEEP),
    }


def _table(data, widths, header=True, body_pad=5):
    t = Table(data, colWidths=widths, hAlign="LEFT")
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK_2),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), body_pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), body_pad),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        style += [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, 0), MOSS),
            ("FONTSIZE", (0, 0), (-1, 0), 7.2),
            ("BACKGROUND", (0, 0), (-1, 0), WASH),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, GREEN),
        ]
    t.setStyle(TableStyle(style))
    return t


# ---------------------------------------------------------------------------
# Custom visual components — a gauge, hero cards, a waterfall, proximity bars
# and per-row colour badges. This is the part a plain lined table cannot do.
# ---------------------------------------------------------------------------

def _gauge(score: float, width=172, height=15) -> Drawing:
    """Horizontal segmented risk gauge: five band zones, a needle at `score`,
    boundary ticks. Reads the whole 0-100 scale at a glance."""
    d = Drawing(width, height + 13)
    zones = [(lo, hi, BAND_COLOUR[key]) for lo, hi, key, _ in RISK_BANDS]
    for lo, hi, col in zones:
        x0 = width * (lo / 100.0)
        w = width * ((hi - lo) / 100.0)
        d.add(Rect(x0, 10, max(0, w - 1), height, fillColor=col, strokeColor=None))
    for bpt in (25, 50, 70, 85):
        x = width * (bpt / 100.0)
        d.add(String(x, 0, str(bpt), fontName="Helvetica", fontSize=5.5, fillColor=FAINT,
                     textAnchor="middle"))
    nx = width * (max(0, min(100, score)) / 100.0)
    d.add(Polygon(points=[nx - 4, height + 13, nx + 4, height + 13, nx, 10 + height - 1],
                  fillColor=INK, strokeColor=colors.white, strokeWidth=0.6))
    return d


def _mini_bar(pct: float, colour, width=26, height=3.4) -> Drawing:
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=WASH, strokeColor=None))
    w = max(0, min(100, pct)) / 100.0 * width
    d.add(Rect(0, 0, w, height, fillColor=colour, strokeColor=None))
    return d


def _proximity_bar(progress: float, width=26, height=3.4) -> Drawing:
    p = max(0.0, min(1.0, progress or 0))
    colour = RUST if p >= 0.85 else AMBER if p >= 0.5 else MOSS
    return _mini_bar(p * 100, colour, width, height)


def _band_badge(band: str, width=42, height=12) -> Drawing:
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=BAND_COLOUR.get(band, MOSS),
              strokeColor=None, rx=2, ry=2))
    d.add(String(width / 2, height / 2 - 3, band.upper(), fontName="Helvetica-Bold",
                fontSize=6.6, fillColor=colors.white, textAnchor="middle"))
    return d


def _waterfall(terms: list, total: float, width=172, height=16) -> Drawing:
    """Stacked horizontal bar: each risk-derivation term as a segment,
    building left-to-right to the total score. Reads faster than the
    Sigma-notation equation underneath it, which stays for anyone who wants it."""
    d = Drawing(width, height + 11)
    scale = 100.0  # the score is always out of 100
    x = 0.0
    for i, t in enumerate(terms):
        colour = TERM_COLOUR.get(t["label"], TERM_FALLBACK[i % len(TERM_FALLBACK)])
        w = max(0.0, (t["contribution"] / scale) * width)
        d.add(Rect(x, 8, max(0, w - 0.6), height, fillColor=colour, strokeColor=None))
        if w > 13:
            d.add(String(x + w / 2, 8 + height / 2 - 2.6, f"{t['contribution']:.0f}",
                         fontName="Helvetica-Bold", fontSize=6.4, fillColor=colors.white,
                         textAnchor="middle"))
        x += w
    d.add(String(min(x + 4, width - 14), 8 + height / 2 - 3, f"{total:.0f}",
                fontName="Helvetica-Bold", fontSize=8.5, fillColor=INK))
    return d


def _hero_row(cards: list, S) -> Table:
    """cards: (value, label, sub, accent_colour). A row of big-number tiles —
    the thing a rushed reader looks at first, on purpose."""
    cells = []
    col_w = 172.0 / len(cards)
    for value, label, sub, accent in cards:
        lbl_style = ParagraphStyle("l", parent=S["hero_l"], textColor=accent)
        inner = Table(
            [[Paragraph(label.upper(), lbl_style)],
             [Paragraph(value, S["hero_v"])],
             [Paragraph(sub, S["hero_s"])]],
            colWidths=[col_w * mm - 3 * mm])
        inner.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
            ("TOPPADDING", (0, 1), (-1, 1), 1), ("BOTTOMPADDING", (0, 1), (-1, 1), 2),
            ("BOTTOMPADDING", (0, 2), (-1, 2), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBEFORE", (0, 0), (0, -1), 2, accent),
            ("BACKGROUND", (0, 0), (-1, -1), WASH),
        ]))
        cells.append(inner)
    outer = Table([cells], colWidths=[col_w * mm] * len(cards))
    outer.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return outer


def _status_icon(colour, warn: bool, size=8) -> Drawing:
    """A small drawn icon instead of a unicode glyph — ⚠ and ● are outside
    Helvetica's base WinAnsi encoding and render as missing-glyph boxes."""
    d = Drawing(size, size)
    if warn:
        d.add(Polygon(points=[size / 2, size, 0, 0, size, 0], fillColor=colour, strokeColor=None))
        d.add(String(size / 2, 1.2, "!", fontName="Helvetica-Bold", fontSize=5.6,
                     fillColor=colors.white, textAnchor="middle"))
    else:
        d.add(Rect(0, size / 2 - 3.2, size, 6.4, fillColor=colour, strokeColor=None, rx=3.2, ry=3.2))
    return d


def _freshness_banner(confidence: dict, S) -> Table:
    degraded = confidence.get("degraded") or []
    live = not degraded
    bg = colors.HexColor("#E7F1EA") if live else AMBER_WASH
    border = GREEN if live else AMBER
    if live:
        text = "<b>All streams live</b> - every number below reflects a fetch from this run."
    else:
        verb = "is" if len(degraded) == 1 else "are"
        text = (f"<b>Reference-data mode</b> - {', '.join(degraded)} {verb} not live in "
                f"this run. Directional guidance only; the note under Confidence on the last "
                f"page names exactly what to re-check before this brief is acted on.")
    icon = _status_icon(border, warn=not live)
    t = Table([[icon, Paragraph(text, ParagraphStyle("fb", fontName="Helvetica", fontSize=8.6,
                                                      leading=11.5, textColor=INK))]],
              colWidths=[12 * mm, 160 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.8, border),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def _dedupe_evidence(items: list) -> list:
    """Wire-service syndication means the same story often shows up from two
    domains with two URLs but one canonical link path - collapse exact-URL
    duplicates so the same story isn't cited twice."""
    seen, out = set(), []
    for it in items:
        key = (it.get("url") or "").split("?")[0].rstrip("/")
        if key and key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(FAINT)
    canvas.drawString(18 * mm, 10 * mm, "SUPATH \u00b7 Strategic Energy Transit Unit")
    canvas.drawCentredString(105 * mm, 10 * mm,
                             datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"))
    canvas.drawRightString(192 * mm, 10 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Document assembly
# ---------------------------------------------------------------------------

def build_pdf(assessment: dict, recs: dict, brief: dict, scenario, kind: str = "full") -> bytes:
    S = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=20 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            title="SUPATH Situation Brief", author="SUPATH")
    story = []
    b = brief["value"]
    nat = assessment["national"]
    conf = b["confidence"]
    all_recs = recs["value"]["recommendations"]
    # The critique's re-bucketing: an action that covers zero barrels and
    # moves zero risk points is preparedness, not impact - it must not carry
    # the same visual weight as one that does.
    impact_recs = [r for r in all_recs if r.get("covers_kbd") or r.get("risk_points")]
    prep_recs = [r for r in all_recs if r not in impact_recs]
    stamp_date = datetime.now(timezone.utc).strftime("%d %B %Y")

    # ======================================================================
    # PAGE 1 - BLUF
    # ======================================================================
    story += [
        Paragraph("SUPATH \u00b7 STRATEGIC ENERGY TRANSIT UNIT", S["masthead"]),
        Paragraph("Situation Brief" if kind == "full" else "Last 24 Hours", S["title"]),
        Paragraph(f"India-bound crude corridors &nbsp;\u00b7&nbsp; {stamp_date}", S["small"]),
        Spacer(1, 3),
        Paragraph("The reasoning, not the output, is what gets judged. Every figure in this "
                 "brief is reconstructible from the sources listed on its last page.", S["thesis"]),
        Spacer(1, 8),
        _freshness_banner(conf, S),
        Spacer(1, 12),
    ]

    # --- The call: posture, gauge, band badge -------------------------------
    call_row = Table(
        [[Paragraph(b["posture"].upper(), S["posture"]), _band_badge(nat["band"])]],
        colWidths=[130 * mm, 42 * mm])
    call_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    gauge_row = Table(
        [[_gauge(nat["score"]),
          Paragraph(f"<b>{nat['score']}</b> / 100 &nbsp;\u00b7&nbsp; {nat['band']} &nbsp;\u00b7&nbsp; "
                   f"confidence {conf['score']}% ({conf['label']})", S["small"])]],
        colWidths=[70 * mm, 100 * mm])
    gauge_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [
        Paragraph("THE CALL", S["eyebrow"]),
        Spacer(1, 3),
        call_row,
        Spacer(1, 6),
        gauge_row,
        Spacer(1, 8),
        Paragraph(b["narrative"], S["lead"]),
        Spacer(1, 5),
        Paragraph(f"<b>Standing playbook:</b> {b['playbook']}", S["body"]),
        Spacer(1, 14),
    ]

    # --- Six hero numbers ----------------------------------------------------
    story += [Paragraph("AT A GLANCE", S["eyebrow"]), Spacer(1, 5)]
    if scenario:
        h = scenario["headline"]
        story.append(_hero_row([
            (f"${h['peak_brent']:.0f}", "Peak Brent", f"{h['peak_brent_chg_pct']:+.0f}% vs. base", RUST),
            (f"{h['peak_gap_kbd']:,}", "Peak supply gap", "kb/d unmet", AMBER),
            (f"{h['final_pump_pct']:+.1f}%", "Retail fuel", "at horizon", RUST),
            (f"{h['final_cpi_pp']:+.2f}", "CPI, pp", "inflation add", AMBER),
            (f"{h['final_gdp_drag_pct']:.2f}%", "GDP drag", "at horizon", MOSS),
            (f"{h['min_refinery_util']:.0f}%", "Min refinery run", "worst day", TEAL),
        ], S))
    else:
        elevated = sum(1 for c in assessment["corridors"] if c["score"] >= 50)
        brent_chg = assessment["prices"]["brent"]["value"].get("chg_1d_pct", 0)
        story.append(_hero_row([
            (str(nat["score"]), "National risk", nat["band"], BAND_COLOUR.get(nat["band"], MOSS)),
            (f"{nat['exposed_kbd']:,}", "Exposed", "kb/d on elevated+", AMBER),
            (f"{nat['spr_cover_days']}", "Strategic cover", "days", TEAL),
            (f"{conf['score']}%", "Confidence", conf["label"], GREEN),
            (str(elevated), "Corridors elevated+", "of 5 watched", RUST if elevated else MOSS),
            (f"{brent_chg:+.1f}%", "Brent today", "session move", RUST if abs(brent_chg) > 2 else MOSS),
        ], S))
    story.append(Spacer(1, 15))

    # --- Lead action(s) only - the rest is a page turn away -----------------
    story.append(Paragraph("LEAD ACTION" + ("S" if len(impact_recs) > 1 else ""), S["eyebrow"]))
    story.append(Spacer(1, 5))
    for r in impact_recs[:2]:
        cat_label, cat_colour = _category(r["id"])
        sub_bits = []
        if r.get("covers_kbd"):
            sub_bits.append(f"{r['covers_kbd']:,} kb/d covered")
        sub_bits.append(f"{r['lead_days']} day lead")
        if r.get("cost_usd_m_day"):
            sub_bits.append(f"${r['cost_usd_m_day']:.1f}m/day")
        sub_line = " \u00b7 ".join(sub_bits)
        tag_style = ParagraphStyle("cl", fontName="Helvetica-Bold", fontSize=6.6,
                                   textColor=colors.white, alignment=1)
        tag = Table([[Paragraph(cat_label, tag_style)]], colWidths=[18 * mm], rowHeights=[5.5 * mm])
        tag.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), cat_colour),
                                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        row = Table([[tag, Paragraph(f"<b>{r['title']}</b><br/>"
                                     f"<font size=8 color='#5B6B61'>{sub_line}</font>", S["body"])]],
                    colWidths=[20 * mm, 152 * mm])
        row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        story.append(row)
    remaining = len(impact_recs) - 2 + len(prep_recs)
    if remaining > 0:
        story.append(Paragraph(
            f"+ {remaining} more recommended action{'s' if remaining != 1 else ''}, "
            f"ranked and costed on page 2 ->", S["small"]))
    if not impact_recs:
        story.append(Paragraph(
            "No corridor is scored elevated or worse and no scenario is running - holding "
            "position is the recommendation, and it is a deliberate one.", S["body"]))

    if kind == "24h":
        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
        return buf.getvalue()

    # ======================================================================
    # PAGE 2+ - ANALYST LAYER
    # ======================================================================
    story += [PageBreak(), Paragraph("CORRIDOR RISK", S["eyebrow"]), Spacer(1, 3),
             Paragraph(nat["method"], S["small"]), Spacer(1, 6)]

    rows = [["Corridor", "Share", "Barrel-weighted", "Risk", "Band", "Top driver"]]
    for c in assessment["corridors"]:
        rows.append([
            Paragraph(f"<b>{c['short']}</b><br/><font size=6.5 color='#7A8A80'>{c['name']}</font>",
                     S["cell"]),
            f"{c['share_pct']:.0f}%",
            _mini_bar(c["share_pct"] / 44 * 100, MOSS),
            Paragraph(f"<b>{c['score']}</b>", S["cell_b"]),
            _band_badge(c["band"], width=40, height=11),
            Paragraph(f"{c['top_driver']['label']} ({c['top_driver']['contribution']:.1f} pts)",
                     S["cell"]),
        ])
    story += [_table(rows, [38 * mm, 12 * mm, 20 * mm, 12 * mm, 22 * mm, 62 * mm]), Spacer(1, 10)]

    top = assessment["corridors"][0]
    story += [
        Paragraph(f"How {top['short']} scored {top['score']}", S["h2"]),
        _waterfall(top["breakdown"], top["score"]),
        Spacer(1, 4),
    ]
    term_rows = [["Term", "Weight", "Sub-score", "Points", "Source"]]
    for x in top["breakdown"]:
        term_rows.append([
            Paragraph(x["label"], S["cell"]),
            f"{x['weight']:.2f}", f"{x['subscore']:.2f}", f"{x['contribution']:.1f}",
            Paragraph(x["source"], S["cell"]),
        ])
    story += [_table(term_rows, [38 * mm, 16 * mm, 20 * mm, 16 * mm, 78 * mm], body_pad=4),
             Spacer(1, 3), Paragraph(top["equation"], S["small"]), Spacer(1, 12)]

    # --- Full recommendations, bucketed --------------------------------------
    story.append(Paragraph("RECOMMENDED ACTIONS", S["eyebrow"]))
    story.append(Spacer(1, 3))
    story.append(Paragraph("Ranked by barrels covered per rupee and per day of lead time.",
                           S["small"]))
    story.append(Spacer(1, 8))

    def _rec_block(r, i):
        cat_label, cat_colour = _category(r["id"])
        tag_style = ParagraphStyle("cl2", fontName="Helvetica-Bold", fontSize=6.4,
                                   textColor=colors.white, alignment=1)
        tag = Table([[Paragraph(cat_label, tag_style)]], colWidths=[17 * mm], rowHeights=[5 * mm])
        tag.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), cat_colour),
                                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        head = Table([[tag, Paragraph(f"<b>{i}. {r['title']}</b>", S["h3"])]],
                     colWidths=[19 * mm, 150 * mm])
        head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        block = [head, Spacer(1, 4), Paragraph(r["action"], S["body"]), Spacer(1, 3)]
        stats = f"{r['lead_days']} days lead"
        if r.get("covers_kbd"):
            stats = f"{r['covers_kbd']:,} kb/d covered ({r.get('covers_pct', 0)}%) \u00b7 " + stats
        if r.get("risk_points"):
            stats += f" \u00b7 -{r['risk_points']:.1f} risk points"
        stats += (f" \u00b7 ${r.get('cost_usd_m_day', 0):.2f}m/day" if r.get("cost_usd_m_day")
                 else " \u00b7 no incremental cost")
        block += [Paragraph(stats, ParagraphStyle("st", fontName="Helvetica-Bold", fontSize=8,
                                                   textColor=GREEN_DEEP)),
                 Spacer(1, 3), Paragraph(f"<i>Why:</i> {r['why']}", S["small"])]
        if r.get("tradeoff"):
            block.append(Paragraph(f"<i>Trade-off:</i> {r['tradeoff']}", S["small"]))
        block.append(Spacer(1, 9))
        return block

    for i, r in enumerate(impact_recs, 1):
        for flow in _rec_block(r, i):
            story.append(flow)

    if prep_recs:
        header_style = ParagraphStyle("pp", fontName="Helvetica-Bold", fontSize=7.5,
                                      textColor=MUTED)
        header_tbl = Table([[Paragraph("PREPARE - NO IMMEDIATE BARREL IMPACT", header_style)]],
                           colWidths=[172 * mm])
        header_tbl.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.6, LINE_2),
                                        ("TOPPADDING", (0, 0), (-1, -1), 8)]))
        story += [
            Spacer(1, 2), header_tbl,
            Paragraph("These stand ready but do not move barrels, cost, or risk points today - "
                     "listed for completeness, not because they carry the same weight as the "
                     "actions above.", S["small"]),
            Spacer(1, 8),
        ]
        for i, r in enumerate(prep_recs, len(impact_recs) + 1):
            for flow in _rec_block(r, i):
                story.append(flow)

    # --- Scenario -------------------------------------------------------------
    if scenario:
        h = scenario["headline"]
        story += [
            PageBreak(),
            Paragraph("SCENARIO", S["eyebrow"]),
            Paragraph(scenario["name"], S["title"]),
            Paragraph(f"{scenario['subtitle']} \u00b7 severity {int(scenario['severity']*100)}% \u00b7 "
                     f"{scenario['days']}-day horizon \u00b7 {scenario['engine']}", S["small"]),
            HRFlowable(width="100%", thickness=1.1, color=GREEN, spaceBefore=6, spaceAfter=10),
            _hero_row([
                (f"${h['peak_brent']:.0f}", "Peak Brent", f"{h['peak_brent_chg_pct']:+.0f}%", RUST),
                (f"{h['peak_gap_kbd']:,}", "Peak supply gap", "kb/d", AMBER),
                (f"{h['final_pump_pct']:+.1f}%", "Retail fuel", "at horizon", RUST),
                (f"{h['final_cpi_pp']:+.2f}", "CPI, pp", "add", AMBER),
                (f"{h['final_gdp_drag_pct']:.2f}%", "GDP drag", "at horizon", MOSS),
                (f"{h['min_refinery_util']:.0f}%", "Min refinery run", "worst day", TEAL),
            ], S),
            Spacer(1, 12),
            Paragraph("The cascade, in the order it reaches India", S["h2"]),
        ]
        for step in scenario["explanation"]["chain"]:
            story.append(Paragraph(f"<b>{step['step']}.</b> {step['text']}", S["body"]))
            story.append(Spacer(1, 3))
        story += [
            Spacer(1, 5),
            Paragraph(scenario["explanation"]["caveat"], S["small"]),
            Spacer(1, 10),
            Paragraph("Industries to brace", S["h2"]),
            _table([["Sector", "Input cost", "Lands on", "Note"]] +
                  [[Paragraph(s["name"], S["cell"]), f"+{s['cost_increase_pct']:.1f}%",
                    f"day {s['impact_day']}", Paragraph(s["note"], S["cell"])]
                   for s in scenario["sector_impact"][:6]],
                  [36 * mm, 20 * mm, 18 * mm, 98 * mm]),
        ]

    # ======================================================================
    # LAST PAGE - AUDIT LAYER: tripwires, evidence, assumptions
    # ======================================================================
    story += [PageBreak(), Paragraph("WHAT WOULD CHANGE THIS CALL", S["eyebrow"]), Spacer(1, 3)]
    tw_rows = [["Tripwire", "Now", "Proximity", "What it would mean"]]
    for t in b["tripwires"]:
        tw_rows.append([
            Paragraph(t["trigger"], S["cell"]),
            Paragraph(f"<b>{t['current']}</b>", S["cell"]),
            _proximity_bar(t.get("progress", 0)),
            Paragraph(t["means"], S["cell"]),
        ])
    story += [_table(tw_rows, [46 * mm, 26 * mm, 20 * mm, 83 * mm]), Spacer(1, 12)]

    story += [Paragraph("EVIDENCE", S["eyebrow"]), Spacer(1, 3)]
    deduped = _dedupe_evidence(b["citations"])
    ev_rows = [["Type", "Source", "Used for"]]
    for c in deduped[:14]:
        ev_rows.append([
            Paragraph(c["type"], S["cell"]),
            Paragraph(f"{c['title']} "
                     f"<link href='{c['url']}' color='#1F6F43'>(source)</link>", S["cell"]),
            Paragraph(c["used_for"], S["cell"]),
        ])
    story += [_table(ev_rows, [24 * mm, 108 * mm, 43 * mm])]
    if len(b["citations"]) != len(deduped):
        n_dupe = len(b["citations"]) - len(deduped)
        story.append(Paragraph(
            f"{n_dupe} duplicate wire-service link{'s' if n_dupe != 1 else ''} collapsed to a "
            f"single citation.", S["small"]))
    story.append(Spacer(1, 12))

    story += [
        Paragraph("ASSUMPTIONS", S["eyebrow"]),
        Paragraph(
            f"India imports {INDIA['crude_imports_kbd']:,} kb/d "
            f"({INDIA['crude_import_dependency_pct']:.0f}% of consumption) against "
            f"{INDIA['spr_days_cover']} days of strategic cover. Risk weights: conflict 0.32, "
            f"sanctions 0.22, congestion 0.18, weather 0.16, market 0.12. Retail pass-through "
            f"62%; fuel weight in CPI 9%. Scenario price formation: a saturating exponential "
            f"curve in the net world supply loss share, after pipeline bypass, OPEC spare, IEA "
            f"stock release and demand response. Confidence: {conf['note']}",
            S["small"]),
    ]

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
