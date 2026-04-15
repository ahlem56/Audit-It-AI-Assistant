from __future__ import annotations

import re
import tempfile
import time
import textwrap
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional, NamedTuple

import pythoncom
import win32com.client

from app.models.export_models import ExportReportRequest

PP_SAVE_AS_OPEN_XML_PRESENTATION = 24
PP_LAYOUT_BLANK = 12
MSO_SHAPE_RECTANGLE = 1
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "data" / "Template PWC Universal v2.pptx"

SLIDE_WIDTH = 13.333 * 72
SLIDE_HEIGHT = 7.5 * 72
MARGIN_X = 0.55 * 72
TITLE_TOP = 0.28 * 72
BODY_TOP = 1.15 * 72
FOOTER_Y = 7.08 * 72
TABLE_ROW_LIMIT = 6
TABLE_LEFT = 0.52 * 72
TABLE_TOP = 1.02 * 72
TABLE_WIDTH = 8.90 * 72
TABLE_HEADER_HEIGHT = 0.42 * 72
TABLE_ROW_HEIGHT = 0.44 * 72
CARD_GAP = 0.08 * 72
TABLE_BOTTOM = 6.65 * 72


def _bgr(r: int, g: int, b: int) -> int:
    # PowerPoint COM uses BGR integer in .RGB fields (0x00BBGGRR).
    return (b << 16) | (g << 8) | r


# Strict PwC palette (no blue).
PWC_RED = _bgr(192, 0, 0)
PWC_ORANGE = _bgr(209, 122, 0)
PWC_YELLOW = _bgr(243, 175, 34)
PWC_GREEN = _bgr(46, 125, 50)
PWC_LIGHT_GREY = _bgr(245, 245, 245)
PWC_LINE_GREY = _bgr(210, 210, 210)
PWC_TEXT_GREY = _bgr(102, 102, 102)
PWC_TEXT_DARK = _bgr(0, 0, 0)
PWC_WHITE = _bgr(255, 255, 255)


def _page_size(presentation) -> tuple[float, float]:
    try:
        return float(presentation.PageSetup.SlideWidth), float(presentation.PageSetup.SlideHeight)
    except Exception:
        return SLIDE_WIDTH, SLIDE_HEIGHT


def _content_bottom(presentation) -> float:
    # Bottom edge for content area (keeps space for footer).
    _, page_h = _page_size(presentation)
    return page_h - (0.85 * 72)


def _safe(value: object) -> str:
    return "" if value is None else str(value)


def _join_lines(values: Iterable[str]) -> str:
    return "\r".join(item.strip() for item in values if item and item.strip())


def _chunked(items: list, size: int) -> list[list]:
    if not items:
        return [[]]
    return [items[index : index + size] for index in range(0, len(items), size)]


def _wrap_cell_text(text: str, *, width: int, max_lines: int) -> str:
    value = " ".join(_safe(text).replace("\r", " ").replace("\n", " ").split())
    if not value:
        return ""

    wrapped = textwrap.wrap(
        value,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if not wrapped:
        return value

    if len(wrapped) > max_lines:
        wrapped = wrapped[:max_lines]
        if len(wrapped[-1]) > max(3, width - 3):
            wrapped[-1] = wrapped[-1][: max(0, width - 3)].rstrip()
        wrapped[-1] = wrapped[-1].rstrip(" .,;:") + "..."

    return "\r".join(wrapped)


def _wrap_preserving_lines(text: str, *, width: int, max_lines: int) -> str:
    # Similar to _wrap_cell_text, but keeps explicit line breaks (useful for bullets).
    raw = _safe(text).replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = [line.strip() for line in raw.split("\n")]
    wrapped_lines: list[str] = []

    for line in raw_lines:
        if not line:
            continue
        pieces = textwrap.wrap(
            " ".join(line.split()),
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        wrapped_lines.extend(pieces if pieces else [line])

    if not wrapped_lines:
        return ""

    if len(wrapped_lines) > max_lines:
        wrapped_lines = wrapped_lines[:max_lines]
        last = wrapped_lines[-1]
        if len(last) > max(3, width - 3):
            last = last[: max(0, width - 3)].rstrip()
        wrapped_lines[-1] = last.rstrip(" .,;:") + "..."

    return "\r".join(wrapped_lines)


def _wrap_text(text: str, *, width: int) -> str:
    value = " ".join(_safe(text).replace("\r", " ").replace("\n", " ").split())
    if not value:
        return ""
    wrapped = textwrap.wrap(
        value,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return "\r".join(wrapped) if wrapped else value


def _line_count(text: str, *, width: int) -> int:
    value = " ".join(_safe(text).replace("\r", " ").replace("\n", " ").split())
    if not value:
        return 1
    wrapped = textwrap.wrap(
        value,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return max(1, len(wrapped))


def _normalize_table_rows(
    rows: list[tuple[str, ...]],
    specs: list[tuple[int, int]],
) -> list[tuple[str, ...]]:
    normalized: list[tuple[str, ...]] = []
    for row in rows:
        cells: list[str] = []
        for index, value in enumerate(row):
            width, max_lines = specs[index] if index < len(specs) else (24, 2)
            cells.append(_wrap_cell_text(value, width=width, max_lines=max_lines))
        normalized.append(tuple(cells))
    return normalized


def _display_priority(priority: str) -> str:
    return {
        "Critical": "Critique",
        "High": "Elevee",
        "Medium": "Moyenne",
        "Low": "Faible",
    }.get(priority, priority or "")


def _replace_text(text: str, mapping: dict[str, str]) -> str:
    updated = text
    for source, target in mapping.items():
        updated = updated.replace(source, target)
    return updated


def _replace_placeholders_in_shape(shape, mapping: dict[str, str]) -> None:
    try:
        if shape.HasTextFrame and shape.TextFrame.HasText:
            shape.TextFrame.TextRange.Text = _replace_text(shape.TextFrame.TextRange.Text, mapping)
    except Exception:
        pass


def _replace_placeholders_in_slide(slide, mapping: dict[str, str]) -> None:
    for index in range(1, slide.Shapes.Count + 1):
        _replace_placeholders_in_shape(slide.Shapes(index), mapping)


def _extract_report_year(data) -> str:
    title = _safe(getattr(data, "cover_title", ""))
    match = re.search(r"FY\s*([0-9]{2,4})", title, flags=re.IGNORECASE)
    if match:
        year = match.group(1)
        return f"20{year}" if len(year) == 2 else year

    report_date = _safe(data.report_date)
    digits = "".join(char for char in report_date if char.isdigit())
    if len(digits) >= 4:
        return digits[-4:]
    period = _safe(data.report_period)
    tokens = [token for token in period.replace("-", " ").split() if token.isdigit() and len(token) == 4]
    return tokens[-1] if tokens else ""


def _build_footer_label(data) -> str:
    client = _safe(data.client_name) or "Client"
    period = _safe(data.report_period)
    return f"PwC | {client} {period}".strip()


def _build_cover_date_label(data) -> str:
    report_date = _safe(getattr(data, "report_date", "")).strip()
    if report_date:
        return f"{report_date} | Version projet"
    return "Version projet"


def _build_fiscal_exercise_label(data) -> str:
    year = _extract_report_year(data)
    return f"Exercice {year}" if year else "Exercice en cours"


def _decorate_cover_slide(slide, data) -> None:
    page_w, page_h = _page_size(slide.Parent)
    exercise_label = _build_fiscal_exercise_label(data)
    confidentiality = _safe(getattr(data, "confidentiality_notice", "")).strip() or "Strictement privé et confidentiel"

    _add_textbox(
        slide,
        MARGIN_X,
        page_h - 1.05 * 72,
        page_w - 2 * MARGIN_X,
        0.50 * 72,
        exercise_label,
        font_size=10,
        bold=True,
        color=PWC_TEXT_DARK,
    )
    _add_textbox(
        slide,
        MARGIN_X,
        1.62 * 72,
        page_w - 2 * MARGIN_X,
        0.50 * 72,
        confidentiality,
        font_size=9,
        color=PWC_TEXT_GREY,
    )


def _shape_text(shape) -> str:
    try:
        if shape.HasTextFrame and shape.TextFrame.HasText:
            return shape.TextFrame.TextRange.Text or ""
    except Exception:
        pass
    return ""


def _apply_font(text_range, *, size: int = 12, bold: bool = False, color: int = 0x000000, name: str = "Arial") -> None:
    try:
        text_range.Font.Name = name
        text_range.Font.Size = size
        text_range.Font.Bold = -1 if bold else 0
        text_range.Font.Color.RGB = color
    except Exception:
        pass


def _add_textbox(
    slide,
    left: float,
    top: float,
    width: float,
    height: float,
    text: str,
    *,
    font_size: int = 12,
    bold: bool = False,
    color: int = 0x000000,
    name: str = "Arial",
) -> None:
    box = slide.Shapes.AddTextbox(1, left, top, width, height)
    text_range = box.TextFrame.TextRange
    text_range.Text = text
    _apply_font(text_range, size=font_size, bold=bold, color=color, name=name)
    try:
        box.TextFrame.MarginTop = 3
        box.TextFrame.MarginBottom = 3
        box.TextFrame.MarginLeft = 4
        box.TextFrame.MarginRight = 4
        box.TextFrame.WordWrap = True
        box.TextFrame.AutoSize = 0
    except Exception:
        pass


def _add_rect(slide, left: float, top: float, width: float, height: float, *, fill_rgb: int = 0xFFFFFF, line_rgb: int = 0xBFBFBF, weight: float = 0.75):
    shape = slide.Shapes.AddShape(MSO_SHAPE_RECTANGLE, left, top, width, height)
    try:
        shape.Fill.Visible = True
        shape.Fill.Solid()
        shape.Fill.ForeColor.RGB = fill_rgb
        shape.Line.Visible = True
        shape.Line.ForeColor.RGB = line_rgb
        shape.Line.Weight = weight
    except Exception:
        pass
    return shape


def _add_footer(slide, footer_label: str, slide_number: int) -> None:
    try:
        page_w, page_h = _page_size(slide.Parent)
    except Exception:
        page_w, page_h = SLIDE_WIDTH, SLIDE_HEIGHT

    footer_y = page_h - (0.42 * 72)
    number_w = 0.4 * 72
    label_w = max(1.0, page_w - 2 * MARGIN_X - number_w - 0.20 * 72)

    _add_textbox(slide, MARGIN_X, footer_y, label_w, 0.25 * 72, footer_label, font_size=8, color=PWC_TEXT_GREY)
    _add_textbox(slide, page_w - MARGIN_X - number_w, footer_y, number_w, 0.25 * 72, str(slide_number), font_size=8, color=PWC_TEXT_GREY)


def _add_blank_slide(presentation):
    slide = presentation.Slides.Add(presentation.Slides.Count + 1, PP_LAYOUT_BLANK)
    # Prevent any master graphics (often blue) from showing through.
    try:
        slide.DisplayMasterShapes = 0
    except Exception:
        pass
    try:
        slide.FollowMasterBackground = 0
    except Exception:
        pass
    try:
        slide.Background.Fill.Visible = True
        slide.Background.Fill.Solid()
        slide.Background.Fill.ForeColor.RGB = PWC_WHITE
    except Exception:
        pass
    return slide


def _add_title(slide, title: str) -> None:
    try:
        page_w, _ = _page_size(slide.Parent)
    except Exception:
        page_w = SLIDE_WIDTH

    _add_textbox(slide, MARGIN_X, TITLE_TOP, page_w - 2 * MARGIN_X, 0.5 * 72, title, font_size=24, bold=True, name="Georgia", color=PWC_TEXT_DARK)
    _add_rect(slide, MARGIN_X, TITLE_TOP + 0.55 * 72, page_w - 2 * MARGIN_X, 0.03 * 72, fill_rgb=PWC_ORANGE, line_rgb=PWC_ORANGE, weight=0)


def _priority_color(priority: str) -> int:
    return {
        "Critical": PWC_RED,
        "High": PWC_ORANGE,
        "Medium": PWC_YELLOW,
        "Low": PWC_GREEN,
    }.get(priority, PWC_TEXT_DARK)


def _priority_fill_and_font(priority_label: str) -> tuple[int, int]:
    lowered = _safe(priority_label).strip().lower()
    if "critique" in lowered or "critical" in lowered:
        return PWC_RED, PWC_WHITE
    if "elevee" in lowered or "élevée" in lowered or "high" in lowered:
        return PWC_ORANGE, PWC_WHITE
    if "moyenne" in lowered or "medium" in lowered:
        return PWC_YELLOW, PWC_TEXT_DARK
    if "faible" in lowered or "low" in lowered:
        return PWC_GREEN, PWC_WHITE
    return PWC_LIGHT_GREY, PWC_TEXT_DARK


def _is_blue_like(bgr: int) -> bool:
    # Office RGB is BGR (0x00BBGGRR)
    r = bgr & 0xFF
    g = (bgr >> 8) & 0xFF
    b = (bgr >> 16) & 0xFF
    return b > 110 and b > (r + 35) and b > (g + 35)


def _sanitize_fill(fill) -> None:
    try:
        if not fill.Visible:
            return
    except Exception:
        return

    try:
        color = fill.ForeColor.RGB
        if isinstance(color, int) and _is_blue_like(color):
            try:
                fill.Solid()
            except Exception:
                pass
            fill.ForeColor.RGB = PWC_ORANGE
    except Exception:
        pass


def _sanitize_line(line) -> None:
    try:
        if not line.Visible:
            return
    except Exception:
        return

    try:
        color = line.ForeColor.RGB
        if isinstance(color, int) and _is_blue_like(color):
            line.ForeColor.RGB = PWC_LINE_GREY
    except Exception:
        pass


def _sanitize_text_range(rng) -> None:
    try:
        color = rng.Font.Color.RGB
        if isinstance(color, int) and _is_blue_like(color):
            rng.Font.Color.RGB = PWC_TEXT_DARK
    except Exception:
        pass


def _sanitize_shape_palette(shape) -> None:
    # Replace any blue-ish fills/lines/fonts with PwC orange/grey/black.
    try:
        _sanitize_fill(shape.Fill)
    except Exception:
        pass

    try:
        _sanitize_line(shape.Line)
    except Exception:
        pass

    try:
        if shape.HasTextFrame and shape.TextFrame.HasText:
            rng = shape.TextFrame.TextRange
            # Also sanitize any run-level colors by applying at TextRange level.
            _sanitize_text_range(rng)
    except Exception:
        pass


def _sanitize_slide_palette(slide) -> None:
    try:
        for index in range(1, slide.Shapes.Count + 1):
            _sanitize_shape_palette(slide.Shapes(index))
    except Exception:
        pass


def _sanitize_master_palette(presentation) -> None:
    # Covers cases where blue comes from master/layout shapes or theme styling.
    try:
        master = presentation.SlideMaster
        for index in range(1, master.Shapes.Count + 1):
            _sanitize_shape_palette(master.Shapes(index))

        # Custom layouts (if any)
        try:
            layouts = master.CustomLayouts
            for li in range(1, layouts.Count + 1):
                layout = layouts(li)
                for si in range(1, layout.Shapes.Count + 1):
                    _sanitize_shape_palette(layout.Shapes(si))
        except Exception:
            pass
    except Exception:
        pass


class _TableColumn(NamedTuple):
    header: str
    width: float  # points
    wrap_width: int  # approximate characters per line
    max_lines: int  # cap to avoid overflow


def _add_text_slide_v3(presentation, title: str, body_lines: list[str], footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    _add_title(slide, title)
    # Defensive wrapping/truncation to ensure text never overflows outside the slide.
    body = _wrap_preserving_lines(_join_lines(body_lines), width=120, max_lines=24)
    page_w, _ = _page_size(presentation)
    content_bottom = _content_bottom(presentation)
    box_top = BODY_TOP + 0.10 * 72
    _add_textbox(
        slide,
        MARGIN_X,
        box_top,
        page_w - 2 * MARGIN_X,
        max(1.0, content_bottom - box_top),
        body,
        font_size=13,
        name="Arial",
        color=PWC_TEXT_DARK,
    )
    _sanitize_slide_palette(slide)
    _add_footer(slide, footer_label, presentation.Slides.Count)


def _add_synthese_slide_v3(presentation, data, footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    _add_title(slide, "Synthèse générale")
    page_w, _ = _page_size(presentation)
    content_bottom = _content_bottom(presentation)

    counts = {item.priority: item.count for item in data.priority_summary}
    kpis = [
        ("Critique", counts.get("Critical", 0), PWC_RED),
        ("Élevée", counts.get("High", 0), PWC_ORANGE),
        ("Moyenne", counts.get("Medium", 0), PWC_YELLOW),
        ("Faible", counts.get("Low", 0), PWC_GREEN),
    ]

    kpi_top = BODY_TOP + 0.05 * 72
    gap = 0.10 * 72
    card_w = (page_w - 2 * MARGIN_X - 3 * gap) / 4
    for idx, (label, value, color) in enumerate(kpis):
        left = MARGIN_X + idx * (card_w + gap)
        _add_rect(slide, left, kpi_top, card_w, 0.72 * 72, fill_rgb=PWC_WHITE, line_rgb=PWC_LINE_GREY, weight=0.75)
        _add_rect(slide, left, kpi_top, 0.10 * 72, 0.72 * 72, fill_rgb=color, line_rgb=color, weight=0)
        _add_textbox(slide, left + 0.16 * 72, kpi_top + 0.10 * 72, card_w - 0.20 * 72, 0.20 * 72, label, font_size=10, bold=True, color=PWC_TEXT_DARK)
        _add_textbox(slide, left + 0.16 * 72, kpi_top + 0.34 * 72, card_w - 0.20 * 72, 0.28 * 72, str(value), font_size=18, bold=True, color=PWC_TEXT_DARK, name="Georgia")

    # 2x2 grid: Niveau global / Principaux constats / Principaux risques / Actions recommandées
    grid_top = kpi_top + 0.92 * 72
    grid_gap_x = 0.22 * 72
    grid_gap_y = 0.20 * 72
    grid_w = page_w - 2 * MARGIN_X
    grid_h = content_bottom - grid_top
    card_w = (grid_w - grid_gap_x) / 2
    card_h = (grid_h - grid_gap_y) / 2

    def card(x: float, y: float, title: str, body_lines: list[str], *, max_lines: int) -> None:
        _add_rect(slide, x, y, card_w, card_h, fill_rgb=PWC_WHITE, line_rgb=PWC_LINE_GREY, weight=0.75)
        _add_textbox(slide, x + 0.12 * 72, y + 0.10 * 72, card_w - 0.24 * 72, 0.22 * 72, title, font_size=12, bold=True, color=PWC_ORANGE, name="Georgia")
        body = _wrap_preserving_lines(_join_lines(body_lines), width=58, max_lines=max_lines)
        _add_textbox(slide, x + 0.12 * 72, y + 0.42 * 72, card_w - 0.24 * 72, card_h - 0.52 * 72, body, font_size=11, color=PWC_TEXT_DARK)

    maturity = _safe(getattr(data, "maturity_level", "")).strip()
    maturity_assessment = _safe(getattr(data, "maturity_assessment", "")).strip()
    total = len(getattr(data, "detailed_findings", []) or [])
    counts_line = f"{counts.get('Critical', 0)} critique(s), {counts.get('High', 0)} élevée(s), {counts.get('Medium', 0)} moyenne(s), {counts.get('Low', 0)} faible(s)."
    niveau_lines = [
        f"- La revue a mis en évidence {total} observation(s), dont {counts_line}",
        f"- Le niveau de maturité est estimé {maturity}." if maturity else "",
        f"- {maturity_assessment}" if maturity_assessment else "",
    ]
    niveau_lines = [line for line in niveau_lines if line]

    constats_lines: list[str] = []
    for item in (getattr(data, "watch_points", []) or [])[:4]:
        constats_lines.append(f"- {item}")
    if not constats_lines:
        synth = _safe(getattr(data, "general_synthesis", "")).strip()
        if synth:
            constats_lines.append(f"- {synth}")

    risks: list[str] = []
    for finding in getattr(data, "detailed_findings", []) or []:
        risk = _safe(getattr(finding, "risk_impact", "")).strip()
        if risk and risk not in risks:
            risks.append(risk)
        if len(risks) == 3:
            break
    risques_lines = [f"- {risk}" for risk in risks] or ["- Risques non précisés dans l'output."]

    actions_lines: list[str] = []
    initiatives = getattr(data, "transversal_initiatives", []) or []
    for item in initiatives[:3]:
        actions_lines.append(f"- {item}")
    if not actions_lines and getattr(data, "strategic_priorities", None):
        for item in (data.strategic_priorities or [])[:3]:
            actions_lines.append(f"- {item}")
    if not actions_lines:
        actions_lines = ["- Mettre en œuvre un plan d'action priorisé et suivi par le management."]

    x1 = MARGIN_X
    x2 = MARGIN_X + card_w + grid_gap_x
    y1 = grid_top
    y2 = grid_top + card_h + grid_gap_y
    card(x1, y1, "1. Niveau global", niveau_lines, max_lines=6)
    card(x2, y1, "2. Principaux constats", constats_lines or ["- Aucun constat synthétisé."], max_lines=7)
    card(x1, y2, "3. Principaux risques", risques_lines, max_lines=7)
    card(x2, y2, "4. Actions recommandées", actions_lines, max_lines=7)

    _sanitize_slide_palette(slide)
    _add_footer(slide, footer_label, presentation.Slides.Count)


def _add_priorities_slide_v3(presentation, data, footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    _add_title(slide, "Synthèse des priorités")
    page_w, _ = _page_size(presentation)
    content_bottom = _content_bottom(presentation)

    # Left: visual breakdown (bars). Right: management-ready action boxes (short).
    left = MARGIN_X
    top = BODY_TOP + 0.10 * 72
    width = page_w - 2 * MARGIN_X

    gap_x = 0.25 * 72
    left_w = width * 0.60
    right_w = width - left_w - gap_x
    right_left = left + left_w + gap_x

    counts = {item.priority: int(getattr(item, "count", 0) or 0) for item in getattr(data, "priority_summary", []) or []}
    total = max(1, sum(counts.values()))
    rows = [
        ("Critical", "Critique", PWC_RED),
        ("High", "Élevée", PWC_ORANGE),
        ("Medium", "Moyenne", PWC_YELLOW),
        ("Low", "Faible", PWC_GREEN),
    ]

    # Bars
    label_w = 1.55 * 72
    metric_w = 1.05 * 72
    bar_left = left + label_w + metric_w + 0.10 * 72
    bar_w = max(1.0, left + left_w - bar_left)
    bar_h = 0.18 * 72
    row_h = 0.60 * 72

    _add_textbox(slide, left, top - 0.20 * 72, left_w, 0.18 * 72, "Répartition des observations", font_size=12, bold=True, color=PWC_TEXT_DARK, name="Georgia")

    y = top
    for key, label, color in rows:
        value = counts.get(key, 0)
        if value <= 0:
            continue
        pct = round((value / total) * 100, 1)
        _add_textbox(slide, left, y, label_w, 0.24 * 72, label, font_size=11, bold=True, color=PWC_TEXT_DARK)
        _add_textbox(slide, left + label_w, y, metric_w, 0.24 * 72, f"{value} ({pct}%)", font_size=10, color=PWC_TEXT_GREY)

        # Background bar
        _add_rect(slide, bar_left, y + 0.04 * 72, bar_w, bar_h, fill_rgb=PWC_LIGHT_GREY, line_rgb=PWC_LINE_GREY, weight=0.5)
        fill_w = max(0.0, min(bar_w, bar_w * (value / total)))
        _add_rect(slide, bar_left, y + 0.04 * 72, fill_w, bar_h, fill_rgb=color, line_rgb=color, weight=0)
        y += row_h

    # Right-side action cards (keep short to avoid text-heavy slides).
    card_gap = 0.18 * 72
    card_h = max(1.0, (content_bottom - top - card_gap) / 2)

    def card(x: float, y: float, title: str, body_lines: list[str], *, max_lines: int) -> None:
        _add_rect(slide, x, y, right_w, card_h, fill_rgb=PWC_WHITE, line_rgb=PWC_LINE_GREY, weight=0.75)
        _add_textbox(slide, x + 0.12 * 72, y + 0.10 * 72, right_w - 0.24 * 72, 0.22 * 72, title, font_size=12, bold=True, color=PWC_ORANGE, name="Georgia")
        body = _wrap_preserving_lines(_join_lines(body_lines), width=48, max_lines=max_lines)
        _add_textbox(slide, x + 0.12 * 72, y + 0.42 * 72, right_w - 0.24 * 72, card_h - 0.52 * 72, body, font_size=11, color=PWC_TEXT_DARK)

    actions = [f"- {_safe(item)}" for item in (getattr(data, "strategic_priorities", []) or [])[:4] if _safe(item).strip()]
    if not actions:
        actions = ["- Prioriser la remédiation des faiblesses critiques et élevées."]

    initiatives_raw = getattr(data, "transversal_initiatives", []) or []
    initiatives = []
    for item in initiatives_raw:
        value = _safe(item).strip()
        if value and value not in initiatives:
            initiatives.append(value)
        if len(initiatives) == 4:
            break
    initiatives_lines = [f"- {item}" for item in initiatives] or ["- Définir 3 à 5 chantiers transverses (IAM, changements, exploitation)."]

    card(right_left, top, "Actions prioritaires", actions, max_lines=7)
    card(right_left, top + card_h + card_gap, "Chantiers transverses", initiatives_lines, max_lines=7)

    _sanitize_slide_palette(slide)
    _add_footer(slide, footer_label, presentation.Slides.Count)


def _add_observation_slide_v3(presentation, finding, footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    page_w, _ = _page_size(presentation)
    content_bottom = _content_bottom(presentation)

    ref = _safe(getattr(finding, "reference", ""))
    app = _safe(getattr(finding, "application", ""))
    layer = _safe(getattr(finding, "layer", ""))
    owners = _safe(getattr(finding, "owners", ""))
    prio = _safe(getattr(finding, "priority", ""))
    prio_label = _display_priority(prio)

    header_left = " | ".join(part for part in [ref, app, layer] if part).strip(" |")
    _add_textbox(slide, MARGIN_X, TITLE_TOP, 10.0 * 72, 0.35 * 72, header_left, font_size=18, bold=True, name="Georgia", color=PWC_TEXT_DARK)

    pill_w = 2.10 * 72
    pill_h = 0.30 * 72
    pill_left = page_w - MARGIN_X - pill_w
    pill_top = TITLE_TOP + 0.02 * 72
    pill_color = _priority_color(prio)
    _add_rect(slide, pill_left, pill_top, pill_w, pill_h, fill_rgb=pill_color, line_rgb=pill_color, weight=0)
    _add_textbox(slide, pill_left + 0.10 * 72, pill_top + 0.03 * 72, pill_w - 0.20 * 72, pill_h - 0.06 * 72, f"Priorité {prio_label}", font_size=10, bold=True, color=PWC_WHITE)

    _add_rect(slide, MARGIN_X, TITLE_TOP + 0.45 * 72, page_w - 2 * MARGIN_X, 0.03 * 72, fill_rgb=PWC_ORANGE, line_rgb=PWC_ORANGE, weight=0)

    title = _sharpen_title(_safe(getattr(finding, "title", "")), reference=ref)
    if title:
        _add_textbox(slide, MARGIN_X, BODY_TOP - 0.15 * 72, page_w - 2 * MARGIN_X, 0.30 * 72, title, font_size=14, bold=True, color=PWC_TEXT_DARK)

    meta_parts = []
    if owners:
        meta_parts.append(f"Acteurs / responsables : {owners}")
    if meta_parts:
        _add_textbox(
            slide,
            MARGIN_X,
            BODY_TOP + 0.06 * 72,
            page_w - 2 * MARGIN_X,
            0.18 * 72,
            " | ".join(meta_parts),
            font_size=9,
            color=PWC_TEXT_GREY,
        )

    constat = _safe(getattr(finding, "finding", ""))
    compensating = _safe(getattr(finding, "compensating_procedure", "")).strip()
    auditor_comment = _safe(getattr(finding, "auditor_comment", "")).strip()
    risk = _safe(getattr(finding, "risk_impact", ""))
    impact = _safe(getattr(finding, "impact_detail", ""))
    reco = _safe(getattr(finding, "recommendation", ""))
    reco_obj = _safe(getattr(finding, "recommendation_objective", ""))
    reco_steps = getattr(finding, "recommendation_steps", None)
    root_cause = _safe(getattr(finding, "root_cause", "")).strip()

    top = BODY_TOP + 0.38 * 72
    grid_gap_x = 0.18 * 72
    grid_gap_y = 0.16 * 72
    width = page_w - 2 * MARGIN_X
    card_w = (width - grid_gap_x) / 2
    card_h = (content_bottom - top - grid_gap_y) / 2

    def section(x: float, y: float, label: str, body: str, *, max_lines: int) -> None:
        _add_rect(slide, x, y, card_w, card_h, fill_rgb=PWC_WHITE, line_rgb=PWC_LINE_GREY, weight=0.75)
        _add_textbox(slide, x + 0.10 * 72, y + 0.10 * 72, card_w - 0.20 * 72, 0.20 * 72, label, font_size=12, bold=True, color=PWC_ORANGE, name="Georgia")
        wrapped = _wrap_preserving_lines(body, width=56, max_lines=max_lines)
        _add_textbox(
            slide,
            x + 0.10 * 72,
            y + 0.38 * 72,
            card_w - 0.20 * 72,
            card_h - 0.48 * 72,
            wrapped or "Information non fournie.",
            font_size=10,
            color=PWC_TEXT_DARK,
        )

    control_context_lines = []
    if compensating:
        control_context_lines.append(f"Procédure compensatoire : {compensating}")
    if auditor_comment:
        control_context_lines.append(f"Commentaire d'audit : {auditor_comment}")
    if not control_context_lines:
        control_context_lines.append("Aucune procédure compensatoire ni commentaire complémentaire renseigné.")

    seed = f"{ref}|{app}|{prio}"
    risk_lines = []
    if risk:
        if impact:
            risk_lines.append(_risk_impact_sentence(risk, impact, seed=seed))
        else:
            risk_lines.append(_risk_sentence(risk, seed=seed))
    if root_cause:
        risk_lines.append(f"Cause racine : {root_cause}.")

    reco_text = _pwc_recommendation(reco, objective=reco_obj, steps=reco_steps) if reco else ""
    left_x = MARGIN_X
    right_x = MARGIN_X + card_w + grid_gap_x
    top_y = top
    bottom_y = top + card_h + grid_gap_y

    section(left_x, top_y, "Constat", constat, max_lines=9)
    section(right_x, top_y, "Procédure compensatoire / commentaire", _join_lines(control_context_lines), max_lines=9)
    section(left_x, bottom_y, "Risque et impact", _join_lines(risk_lines) if risk_lines else "Non déterminé.", max_lines=9)
    section(right_x, bottom_y, "Recommandation", reco_text or "Recommandation non fournie.", max_lines=10)

    _sanitize_slide_palette(slide)
    _add_footer(slide, footer_label, presentation.Slides.Count)


def _add_table_slides_v3(
    presentation,
    title: str,
    columns: list[_TableColumn],
    rows: list[tuple[str, ...]],
    footer_label: str,
) -> None:
    # Clean table layout: light lines, no heavy containers, no overflow.
    page_w, _ = _page_size(presentation)
    table_left = MARGIN_X
    table_top = BODY_TOP + 0.10 * 72
    table_width = page_w - 2 * MARGIN_X
    table_bottom = _content_bottom(presentation)

    header_h = 0.34 * 72
    min_row_h = 0.38 * 72
    line_h = 0.16 * 72

    def normalize_row(row: tuple[str, ...]) -> list[str]:
        values = list(row) + [""] * max(0, len(columns) - len(row))
        return [_safe(values[i]) for i in range(len(columns))]

    def wrap_row(values: list[str]) -> list[str]:
        wrapped: list[str] = []
        for col, value in zip(columns, values):
            wrapped.append(_wrap_preserving_lines(value, width=col.wrap_width, max_lines=col.max_lines))
        return wrapped

    def row_height(wrapped: list[str]) -> float:
        lines = 1
        for col, value in zip(columns, wrapped):
            lines = max(lines, _line_count(value, width=col.wrap_width))
        return max(min_row_h, (0.18 * 72) + lines * line_h)

    # Build pages
    pages: list[list[tuple[str, ...]]] = []
    current: list[tuple[str, ...]] = []
    y = table_top + header_h
    for row in rows or [tuple("" for _ in columns)]:
        wrapped = wrap_row(normalize_row(row))
        h = row_height(wrapped)
        if current and (y + h) > table_bottom:
            pages.append(current)
            current = []
            y = table_top + header_h
        current.append(row)
        y += h
    if current:
        pages.append(current)

    for page_rows in pages:
        slide = _add_blank_slide(presentation)
        _add_title(slide, title)

        # Header row
        x = table_left
        for col in columns:
            _add_rect(slide, x, table_top, col.width, header_h, fill_rgb=PWC_LIGHT_GREY, line_rgb=PWC_LINE_GREY, weight=0.75)
            _add_textbox(slide, x + 0.06 * 72, table_top + 0.08 * 72, col.width - 0.12 * 72, header_h - 0.12 * 72, col.header, font_size=10, bold=True, color=PWC_TEXT_DARK)
            x += col.width

        # Body rows
        y = table_top + header_h
        for row in page_rows:
            values = normalize_row(row)
            wrapped = wrap_row(values)
            h = row_height(wrapped)

            x = table_left
            for index, (col, value) in enumerate(zip(columns, wrapped)):
                fill_rgb = PWC_WHITE
                font_color = PWC_TEXT_DARK
                bold = False
                if title == "Recommandations détaillées" and index == 2:
                    fill_rgb, font_color = _priority_fill_and_font(values[index])
                    bold = True

                _add_rect(slide, x, y, col.width, h, fill_rgb=fill_rgb, line_rgb=PWC_LINE_GREY, weight=0.5)
                _add_textbox(
                    slide,
                    x + 0.06 * 72,
                    y + 0.06 * 72,
                    col.width - 0.12 * 72,
                    h - 0.12 * 72,
                    value,
                    font_size=10,
                    bold=bold,
                    color=font_color,
                )
                x += col.width
            y += h

        _sanitize_slide_palette(slide)
        _add_footer(slide, footer_label, presentation.Slides.Count)


def _add_content_slide(presentation, title: str, body_lines: list[str], footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    _add_title(slide, title)
    _add_textbox(slide, MARGIN_X, BODY_TOP, 11.9 * 72, 5.6 * 72, _join_lines(body_lines), font_size=12)
    _add_footer(slide, footer_label, presentation.Slides.Count)


def _set_cell_text(table, row: int, col: int, value: str, *, bold: bool = False, font_size: int = 10, align: int = 1) -> None:
    cell = table.Cell(row, col).Shape.TextFrame.TextRange
    cell.Text = value
    _apply_font(cell, size=font_size, bold=bold)
    try:
        cell.ParagraphFormat.Alignment = align
    except Exception:
        pass
    try:
        cell.ParagraphFormat.SpaceBefore = 0
        cell.ParagraphFormat.SpaceAfter = 0
    except Exception:
        pass
    try:
        shape = table.Cell(row, col).Shape
        shape.TextFrame.MarginTop = 2
        shape.TextFrame.MarginBottom = 2
        shape.TextFrame.MarginLeft = 4
        shape.TextFrame.MarginRight = 4
        shape.TextFrame.WordWrap = True
        shape.TextFrame.AutoSize = 0
    except Exception:
        pass


def _set_cell_fill(table, row: int, col: int, rgb: int) -> None:
    try:
        fill = table.Cell(row, col).Shape.Fill
        fill.Visible = True
        fill.ForeColor.RGB = rgb
        fill.Solid()
    except Exception:
        pass


def _paginate_by_height(items: list, height_fn) -> list[list]:
    pages: list[list] = []
    current: list = []
    current_height = TABLE_TOP
    for item in items:
        item_height = height_fn(item)
        projected = current_height + item_height + (CARD_GAP if current else 0)
        if current and projected > TABLE_BOTTOM:
            pages.append(current)
            current = [item]
            current_height = TABLE_TOP + item_height
        else:
            if current:
                current_height += CARD_GAP
            current.append(item)
            current_height += item_height
    return pages or [[]]


def _control_card_height(row: tuple[str, ...]) -> float:
    _, description, procedure = row
    desc_lines = _line_count(description, width=78)
    proc_lines = _line_count(procedure, width=78)
    return (0.70 + 0.14 * desc_lines + 0.14 * proc_lines) * 72


def _recommendation_card_height(row: tuple[str, ...]) -> float:
    _, _, _, recommendation = row
    recommendation_lines = _line_count(recommendation, width=92)
    return (0.54 + 0.14 * recommendation_lines) * 72


def _matrix_card_height(row: tuple[str, ...]) -> float:
    # Dynamic height based on wrapped content to avoid overflow outside slide.
    values = list(row) + ["", "", "", ""]
    wrapped = [
        _wrap_text(_safe(values[0]), width=18),
        _wrap_text(_safe(values[1]), width=26),
        _wrap_text(_safe(values[2]), width=18),
        _wrap_text(_safe(values[3]), width=22),
    ]
    line_counts = [
        _line_count(wrapped[0], width=18),
        _line_count(wrapped[1], width=26),
        _line_count(wrapped[2], width=18),
        _line_count(wrapped[3], width=22),
    ]
    max_lines = max(1, max(line_counts))
    return max(0.72 * 72, (0.32 + 0.16 * max_lines) * 72)


def _draw_control_cards(slide, rows: list[tuple[str, ...]]) -> None:
    left = TABLE_LEFT
    top = TABLE_TOP
    width = TABLE_WIDTH

    for ref, description, procedure in rows:
        desc_text = _wrap_text(description, width=78)
        proc_text = _wrap_text(procedure, width=78)
        desc_lines = desc_text.count("\r") + 1 if desc_text else 1
        proc_lines = proc_text.count("\r") + 1 if proc_text else 1
        card_height = _control_card_height((ref, description, procedure))

        _add_rect(slide, left, top, width, card_height, fill_rgb=0xFFFFFF, line_rgb=PWC_LINE_GREY)
        _add_rect(slide, left, top, width, 0.24 * 72, fill_rgb=PWC_ORANGE, line_rgb=PWC_ORANGE)
        _add_textbox(slide, left + 0.10 * 72, top + 0.02 * 72, 1.10 * 72, 0.16 * 72, ref, font_size=10, bold=True, color=0xFFFFFF)

        body_top = top + 0.32 * 72
        _add_textbox(slide, left + 0.12 * 72, body_top, 1.75 * 72, 0.16 * 72, "Description du controle", font_size=8, bold=True)
        _add_textbox(slide, left + 1.95 * 72, body_top - 0.02 * 72, width - 2.10 * 72, max(0.30 * 72, desc_lines * 0.15 * 72), desc_text, font_size=9)

        proc_top = body_top + max(0.30 * 72, desc_lines * 0.15 * 72) + 0.08 * 72
        _add_textbox(slide, left + 0.12 * 72, proc_top, 1.75 * 72, 0.16 * 72, "Procedure de test", font_size=8, bold=True)
        _add_textbox(slide, left + 1.95 * 72, proc_top - 0.02 * 72, width - 2.10 * 72, max(0.30 * 72, proc_lines * 0.15 * 72), proc_text, font_size=9)

        top += card_height + CARD_GAP


def _draw_matrix_cards(slide, rows: list[tuple[str, ...]]) -> None:
    left = TABLE_LEFT
    top = TABLE_TOP
    width = TABLE_WIDTH
    headers = ["Controle", "Application", "Nb obs", "Priorite dominante"]
    col_widths = [1.35 * 72, 2.15 * 72, 1.35 * 72, width - (1.35 + 2.15 + 1.35) * 72]

    _add_rect(slide, left, top, width, 0.24 * 72, fill_rgb=PWC_ORANGE, line_rgb=PWC_ORANGE)
    cursor = left
    for header, col_width in zip(headers, col_widths):
        _add_textbox(slide, cursor + 0.04 * 72, top + 0.02 * 72, col_width - 0.08 * 72, 0.14 * 72, header, font_size=8, bold=True, color=0xFFFFFF)
        cursor += col_width
    top += 0.30 * 72

    for row in rows:
        row_height = _matrix_card_height(row)
        _add_rect(slide, left, top, width, row_height, fill_rgb=0xFFFFFF, line_rgb=PWC_LINE_GREY)
        cursor = left
        values = list(row) + ["", "", "", ""]
        wrapped_values = [
            _wrap_text(_safe(values[0]), width=18),
            _wrap_text(_safe(values[1]), width=26),
            _wrap_text(_safe(values[2]), width=18),
            _wrap_text(_safe(values[3]), width=22),
        ]
        for wrapped_value, col_width in zip(wrapped_values, col_widths):
            _add_rect(slide, cursor, top, col_width, row_height, fill_rgb=0xFFFFFF, line_rgb=PWC_LINE_GREY)
            _add_textbox(
                slide,
                cursor + 0.05 * 72,
                top + 0.08 * 72,
                col_width - 0.10 * 72,
                row_height - 0.16 * 72,
                wrapped_value,
                font_size=9,
            )
            cursor += col_width
        top += row_height + CARD_GAP


def _draw_recommendation_cards(slide, rows: list[tuple[str, ...]]) -> None:
    left = TABLE_LEFT
    top = TABLE_TOP
    width = TABLE_WIDTH
    meta_widths = [1.10 * 72, 1.65 * 72, 1.10 * 72]
    recommendation_left = left + sum(meta_widths)
    recommendation_width = width - sum(meta_widths)
    meta_headers = ["ID", "Application", "Priorite"]

    for ref, application, priority, recommendation in rows:
        recommendation_text = _wrap_text(recommendation, width=92)
        recommendation_lines = recommendation_text.count("\r") + 1 if recommendation_text else 1
        card_height = _recommendation_card_height((ref, application, priority, recommendation))

        _add_rect(slide, left, top, width, card_height, fill_rgb=0xFFFFFF, line_rgb=PWC_LINE_GREY)
        cursor = left
        for header, value, col_width in zip(meta_headers, [ref, application, priority], meta_widths):
            _add_rect(slide, cursor, top, col_width, card_height, fill_rgb=PWC_LIGHT_GREY, line_rgb=PWC_LINE_GREY)
            _add_textbox(slide, cursor + 0.04 * 72, top + 0.05 * 72, col_width - 0.08 * 72, 0.14 * 72, header, font_size=8, bold=True)
            _add_textbox(slide, cursor + 0.04 * 72, top + 0.30 * 72, col_width - 0.08 * 72, 0.26 * 72, value, font_size=9)
            cursor += col_width

        _add_rect(slide, recommendation_left, top, recommendation_width, 0.24 * 72, fill_rgb=PWC_ORANGE, line_rgb=PWC_ORANGE)
        _add_textbox(slide, recommendation_left + 0.05 * 72, top + 0.03 * 72, recommendation_width - 0.10 * 72, 0.14 * 72, "Recommandation", font_size=8, bold=True, color=0xFFFFFF)
        _add_textbox(
            slide,
            recommendation_left + 0.06 * 72,
            top + 0.30 * 72,
            recommendation_width - 0.12 * 72,
            max(0.28 * 72, recommendation_lines * 0.15 * 72),
            recommendation_text,
            font_size=9,
        )
        top += card_height + CARD_GAP


def _add_table_slide(
    presentation,
    title: str,
    headers: list[str],
    rows: list[tuple[str, ...]],
    footer_label: str,
    *,
    row_limit: int = TABLE_ROW_LIMIT,
) -> None:
    if title == "Liste des controles couverts":
        pages = _paginate_by_height(rows, _control_card_height)
    elif title == "Synthese controle x application":
        pages = _paginate_by_height(rows, _matrix_card_height)
    elif title == "Recommandations detaillees":
        pages = _paginate_by_height(rows, _recommendation_card_height)
    else:
        pages = _chunked(rows, row_limit)

    for page_rows in pages:
        slide = _add_blank_slide(presentation)
        _add_title(slide, title)
        if title == "Liste des controles couverts":
            _draw_control_cards(slide, page_rows)
        elif title == "Synthese controle x application":
            _draw_matrix_cards(slide, page_rows)
        elif title == "Recommandations detaillees":
            _draw_recommendation_cards(slide, page_rows)
        else:
            _draw_matrix_cards(slide, page_rows)
        _add_footer(slide, footer_label, presentation.Slides.Count)


def _build_scope_rows(data) -> list[str]:
    applications = data.applications or ["Perimetre non precise"]
    return [
        f"- Applications couvertes : {', '.join(applications)}",
        f"- Processus couverts : {', '.join(data.covered_processes)}",
        f"- Resume du perimetre : {_safe(data.scope_summary)}",
    ]


def _add_scope_slide(presentation, data, footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    _add_title(slide, "Périmètre")
    page_w, _ = _page_size(presentation)
    content_bottom = _content_bottom(presentation)

    process_lines = [f"- {item}" for item in (getattr(data, "covered_processes", []) or [])]
    if not process_lines:
        process_lines = ["- Aucun processus renseigné"]

    _add_textbox(slide, MARGIN_X, BODY_TOP - 0.02 * 72, page_w - 2 * MARGIN_X, 0.18 * 72, "Processus couverts", font_size=12, bold=True, color=PWC_ORANGE, name="Georgia")
    process_body = _wrap_preserving_lines(_join_lines(process_lines), width=120, max_lines=4)
    _add_textbox(slide, MARGIN_X, BODY_TOP + 0.18 * 72, page_w - 2 * MARGIN_X, 0.58 * 72, process_body, font_size=11, color=PWC_TEXT_DARK)

    rows = []
    for app in getattr(data, "application_details", []) or []:
        description = _safe(getattr(app, "description", "")).strip() or "Non renseigné"
        operating_system = _safe(getattr(app, "operating_system", "")).strip() or "Non renseigné"
        database = _safe(getattr(app, "database", "")).strip() or "Non renseigné"
        rows.append(
            (
                _safe(getattr(app, "name", "")),
                description,
                operating_system,
                database,
            )
        )

    if not rows:
        fallback_applications = getattr(data, "applications", []) or []
        rows = [(_safe(application), "Non renseigné", "Non renseigné", "Non renseigné") for application in fallback_applications if _safe(application)]

    if not rows:
        rows = [("Périmètre à compléter", "", "", "")]

    table_top = BODY_TOP + 0.98 * 72
    table_bottom = content_bottom
    headers = [
        ("Application", 2.10 * 72, 20, 2),
        ("Description", 4.00 * 72, 42, 3),
        ("Système d'exploitation", 2.10 * 72, 20, 2),
        ("Base de données", page_w - 2 * MARGIN_X - (2.10 + 4.00 + 2.10) * 72, 20, 2),
    ]
    header_h = 0.36 * 72
    row_h = 0.52 * 72

    x = MARGIN_X
    for label, width, _, _ in headers:
        _add_rect(slide, x, table_top, width, header_h, fill_rgb=PWC_LIGHT_GREY, line_rgb=PWC_LINE_GREY, weight=0.75)
        _add_textbox(slide, x + 0.05 * 72, table_top + 0.08 * 72, width - 0.10 * 72, header_h - 0.12 * 72, label, font_size=9, bold=True, color=PWC_TEXT_DARK)
        x += width

    y = table_top + header_h
    for row in rows:
        if y + row_h > table_bottom:
            break
        x = MARGIN_X
        for (value, (__, width, wrap_width, max_lines)) in zip(row, headers):
            wrapped = _wrap_preserving_lines(value, width=wrap_width, max_lines=max_lines)
            _add_rect(slide, x, y, width, row_h, fill_rgb=PWC_WHITE, line_rgb=PWC_LINE_GREY, weight=0.5)
            _add_textbox(slide, x + 0.05 * 72, y + 0.06 * 72, width - 0.10 * 72, row_h - 0.12 * 72, wrapped, font_size=9, color=PWC_TEXT_DARK)
            x += width
        y += row_h

    _sanitize_slide_palette(slide)
    _add_footer(slide, footer_label, presentation.Slides.Count)


def _build_intervenant_rows(data) -> list[str]:
    rows: list[str] = []
    for item in data.stakeholders:
        if " - " in item:
            left, right = item.split(" - ", 1)
            rows.append(f"- {right.strip()} : {left.strip()}")
        else:
            rows.append(f"- {item}")
    return rows or ["- Aucun intervenant renseigne"]


def _build_general_synthesis_rows(data) -> list[str]:
    counts = {item.priority: item.count for item in data.priority_summary}
    top_risks = []
    for finding in data.detailed_findings:
        risk = _safe(finding.risk_impact)
        if risk and risk not in top_risks:
            top_risks.append(risk)
        if len(top_risks) == 3:
            break
    rows = [
        f"- {len(data.detailed_findings)} observations identifiees",
        f"- Critique : {counts.get('Critical', 0)}",
        f"- Elevee : {counts.get('High', 0)}",
        f"- Moyenne : {counts.get('Medium', 0)}",
        f"- Faible : {counts.get('Low', 0)}",
        "",
        f"- Niveau de maturite : {_safe(getattr(data, 'maturity_level', '')).strip() or 'N/A'}",
        f"- Appreciation : {_safe(getattr(data, 'maturity_assessment', '')).strip() or 'N/A'}",
        "",
        "- Principaux risques :",
    ]
    for risk in top_risks:
        rows.append(f"- {risk}")
    rows.extend(["", "- Actions correctives requises a court terme."])
    return rows


def _build_priority_rows(data) -> list[str]:
    rows = [f"- {_display_priority(item.priority)} : {item.count} ({item.percentage}%)" for item in data.priority_summary]
    if data.strategic_priorities:
        rows.extend(["", "- Actions prioritaires :"])
        rows.extend(f"- {item}" for item in data.strategic_priorities[:3])
    initiatives = getattr(data, "transversal_initiatives", []) or []
    if initiatives:
        rows.extend(["", "- Chantiers transverses :"])
        rows.extend(f"- {_safe(item)}" for item in initiatives[:5])
    return rows or ["- Aucune priorite calculee"]


def _build_control_rows(data) -> list[tuple[str, str, str]]:
    rows = [
        (_safe(control.reference), _safe(control.description), _safe(control.test_procedure))
        for control in data.covered_controls
    ]
    return rows or [("N/A", "Aucun controle catalogue sur le perimetre.", "Aucun test defini.")]


def _matrix_status_fill(status: str) -> int:
    lowered = _safe(status).strip().lower()
    if lowered == "satisfaisant":
        return _bgr(226, 239, 218)
    if lowered == "recommandation mineure":
        return _bgr(255, 242, 204)
    if lowered == "non applicable":
        return _bgr(230, 230, 230)
    if lowered == "non testé":
        return _bgr(242, 242, 242)
    if lowered.startswith("non satisfaisant") and "critique" in lowered:
        return PWC_RED
    if lowered.startswith("non satisfaisant") and "élevée" in lowered:
        return PWC_ORANGE
    if lowered.startswith("non satisfaisant") and "moyenne" in lowered:
        return PWC_YELLOW
    if lowered.startswith("non satisfaisant") and "faible" in lowered:
        return _bgr(255, 230, 153)
    if lowered.startswith("non satisfaisant"):
        return _bgr(255, 242, 204)
    return PWC_WHITE


def _matrix_status_font_color(status: str) -> int:
    lowered = _safe(status).strip().lower()
    if lowered.startswith("non satisfaisant") and ("critique" in lowered or "élevée" in lowered):
        return PWC_WHITE
    if lowered == "faible":
        return PWC_WHITE
    return PWC_TEXT_DARK


def _matrix_display_status(status: str) -> str:
    value = _safe(status).strip()
    if value.startswith("Non satisfaisant (") and value.endswith(")"):
        priority = value[len("Non satisfaisant (") : -1].strip()
        return f"Non satisf. - {priority}"
    return value


def _matrix_row_risk_label(entry) -> str:
    priority = _safe(getattr(entry, "overall_priority", "")).strip()
    if priority:
        return _display_priority(priority)

    statuses = list((getattr(entry, "application_statuses", {}) or {}).values())
    lowered = [_safe(status).strip().lower() for status in statuses]
    if any(status.startswith("non satisfaisant") for status in lowered):
        return "Élevée"
    if any(status == "recommandation mineure" for status in lowered):
        return "Faible"
    if statuses and all(status == "non testé" for status in lowered):
        return "Non testé"
    if statuses and all(status == "non applicable" for status in lowered):
        return "Non applicable"
    return "Satisfaisant"


def _paginate_control_matrix_rows(data, applications: list[str], page_capacity: int = 12) -> list[list]:
    rows = list(getattr(data, "control_matrix", []) or [])
    if not rows:
        return [[]]

    pages: list[list] = []
    current: list = []
    current_process = ""
    logical_rows = 0
    for entry in rows:
        entry_process = _safe(getattr(entry, "process", ""))
        additional_rows = 1
        if entry_process != current_process:
            additional_rows += 1

        if current and logical_rows + additional_rows > page_capacity:
            pages.append(current)
            current = []
            logical_rows = 0
            current_process = ""

        if entry_process != current_process:
            current.append(("__PROCESS__", entry_process))
            logical_rows += 1
            current_process = entry_process

        current.append(("__ENTRY__", entry))
        logical_rows += 1

    if current:
        pages.append(current)
    return pages


def _add_control_matrix_slides(presentation, data, footer_label: str) -> None:
    applications = list(getattr(data, "applications", []) or [])
    pages = _paginate_control_matrix_rows(data, applications)
    page_w, _ = _page_size(presentation)
    table_left = MARGIN_X
    table_top = BODY_TOP + 0.10 * 72
    table_bottom = _content_bottom(presentation)
    table_width = page_w - 2 * MARGIN_X
    header_h = 0.38 * 72
    process_h = 0.28 * 72
    row_h = 0.58 * 72
    ref_w = 0.95 * 72
    control_w = 3.55 * 72
    risk_w = 1.05 * 72
    remaining_w = max(1.0, table_width - ref_w - control_w - risk_w)
    app_w = remaining_w / max(1, len(applications))

    for page_rows in pages:
        slide = _add_blank_slide(presentation)
        _add_title(slide, "Synthèse contrôle × application")

        x = table_left
        headers = [("Réf.", ref_w), ("Contrôle", control_w)] + [(application, app_w) for application in applications] + [("Risque", risk_w)]
        for label, width in headers:
            _add_rect(slide, x, table_top, width, header_h, fill_rgb=PWC_LIGHT_GREY, line_rgb=PWC_LINE_GREY, weight=0.75)
            _add_textbox(slide, x + 0.05 * 72, table_top + 0.08 * 72, width - 0.10 * 72, header_h - 0.12 * 72, label, font_size=9, bold=True, color=PWC_TEXT_DARK)
            x += width

        y = table_top + header_h
        for row_type, payload in page_rows:
            if row_type == "__PROCESS__":
                _add_rect(slide, table_left, y, table_width, process_h, fill_rgb=PWC_ORANGE, line_rgb=PWC_ORANGE, weight=0)
                _add_textbox(slide, table_left + 0.08 * 72, y + 0.04 * 72, table_width - 0.16 * 72, process_h - 0.08 * 72, _safe(payload), font_size=10, bold=True, color=PWC_WHITE, name="Georgia")
                y += process_h
                continue

            entry = payload
            x = table_left
            cells = [
                (_safe(getattr(entry, "reference", "")), ref_w, PWC_WHITE, PWC_TEXT_DARK, True),
                (_wrap_preserving_lines(_safe(getattr(entry, "control_description", "")), width=34, max_lines=2), control_w, PWC_WHITE, PWC_TEXT_DARK, False),
            ]
            statuses = getattr(entry, "application_statuses", {}) or {}
            for application in applications:
                status = _safe(statuses.get(application, "Non testé")) or "Non testé"
                display_status = _matrix_display_status(status)
                cells.append((display_status, app_w, _matrix_status_fill(status), _matrix_status_font_color(status), False))

            row_risk = _matrix_row_risk_label(entry)
            risk_fill, risk_font = _priority_fill_and_font(row_risk)
            if row_risk in {"Satisfaisant", "Non testé", "Non applicable"}:
                risk_fill = _matrix_status_fill(row_risk)
                risk_font = _matrix_status_font_color(row_risk)
            cells.append((row_risk, risk_w, risk_fill, risk_font, True))

            for text, width, fill_rgb, color, bold in cells:
                _add_rect(slide, x, y, width, row_h, fill_rgb=fill_rgb, line_rgb=PWC_LINE_GREY, weight=0.5)
                _add_textbox(slide, x + 0.04 * 72, y + 0.05 * 72, width - 0.08 * 72, row_h - 0.10 * 72, text, font_size=9, bold=bold, color=color)
                x += width
            y += row_h

            if y + row_h > table_bottom:
                break

        _sanitize_slide_palette(slide)
        _add_footer(slide, footer_label, presentation.Slides.Count)


def _truncate(text: str, max_len: int = 220) -> str:
    value = _safe(text)
    return value if len(value) <= max_len else value[: max_len - 3].rstrip() + "..."


def _pwc_constat(text: str) -> str:
    value = _truncate(text, 260).rstrip(".")
    return f"Nos travaux ont mis en évidence que {value}."


def _pwc_risk(text: str) -> str:
    value = _truncate(text, 200).rstrip(".")
    return f"Risque principal : {value}."


def _pwc_impact(text: str) -> str:
    value = _truncate(text, 200).rstrip(".")
    return f"Impact métier potentiel : {value}."


def _variant_index(seed: str, modulo: int) -> int:
    if modulo <= 1:
        return 0
    value = 0
    for ch in (seed or ""):
        value = (value * 31 + ord(ch)) % 1_000_000
    return value % modulo


def _risk_sentence(risk: str, *, seed: str = "") -> str:
    value = _truncate(risk, 200).rstrip(".")
    variants = [
        f"Risque principal : {value}.",
        f"Risque identifié : {value}.",
        f"Exposition principale : {value}.",
    ]
    return variants[_variant_index(seed, len(variants))]


def _impact_sentence(impact: str, *, seed: str = "") -> str:
    value = _truncate(impact, 200).rstrip(".")
    variants = [
        f"Impact métier potentiel : {value}.",
        f"Impact potentiel : {value}.",
        f"Conséquence métier possible : {value}.",
    ]
    return variants[_variant_index(seed, len(variants))]


def _risk_impact_sentence(risk: str, impact: str, *, seed: str = "") -> str:
    risk_value = _truncate(risk, 170).rstrip(".")
    impact_value = _truncate(impact, 170).rstrip(".")
    variants = [
        f"Risque principal : {risk_value}.\rImpact métier potentiel : {impact_value}.",
        f"Risque identifié : {risk_value}.\rImpact potentiel : {impact_value}.",
        f"Exposition principale : {risk_value}.\rConséquence métier possible : {impact_value}.",
    ]
    return variants[_variant_index(seed, len(variants))]


def _de_prefix(phrase: str) -> str:
    candidate = (phrase or "").strip()
    if not candidate:
        return "de "
    first = candidate[0].lower()
    if first in "aeiouhàâäéèêëîïôöùûüÿœæ":
        return "d'"
    return "de "


def _pwc_recommendation(recommendation: str, *, objective: str = "", steps: Optional[list[str]] = None) -> str:
    steps = steps or []
    objective_value = _truncate(objective, 170).strip().rstrip(".")

    if steps:
        lines = ["Nous recommandons de:"]
        lines.extend(f"- {_truncate(step, 140)}" for step in steps if step and str(step).strip())
        if objective_value:
            lines.append(f"Afin de: {objective_value}.")
        return "\r".join(lines)

    base = _truncate(recommendation, 240).strip().rstrip(".")
    if not base:
        return ""

    # Most recommendations are imperative infinitives ("Mettre en place...", "Formaliser...").
    lowered = base[0].lower() + base[1:] if len(base) > 1 else base.lower()
    prefix = _de_prefix(lowered)
    intro_variants = [
        "Nous recommandons ",
        "Nous préconisons ",
        "Il est recommandé ",
    ]
    intro = intro_variants[_variant_index(lowered, len(intro_variants))]

    if objective_value:
        return f"{intro}{prefix}{lowered}, afin de {objective_value}."
    return f"{intro}{prefix}{lowered}."


def _sharpen_title(title: str, reference: str = "") -> str:
    value = " ".join((title or "").split()).strip()
    if not value:
        return ""

    lowered = value.lower()
    ref = (reference or "").upper().strip()

    if ref == "APD-01" and "validation" in lowered and "absence" in lowered:
        return "Validation des accès non formalisée"
    if ref == "APD-02" and ("apres depart" in lowered or "après départ" in lowered or "post-depart" in lowered or "post-départ" in lowered):
        return "Comptes actifs post-départ"
    if ref == "APD-03" and ("recertification" in lowered or "recertification" in lowered) and ("absence" in lowered or "aucune" in lowered):
        return "Recertification des droits sensibles non réalisée"
    if ref == "PC-01" and ("recette" in lowered or "tests" in lowered) and ("absence" in lowered or "preuve" in lowered):
        return "Recette des changements non documentée"
    if ref == "PC-02" and ("production" in lowered and "developpement" in lowered) or ("accès" in lowered and "cumul" in lowered):
        return "Accès cumulés développement / production"

    # Generic shortening: remove leading "Absence de ..." when possible.
    if lowered.startswith("absence de "):
        trimmed = value[len("Absence de ") :].strip()
        if trimmed:
            # Capitalize first character.
            return trimmed[0].upper() + trimmed[1:]

    return value


def _add_finding_slide(presentation, finding, footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    header = f"{_safe(finding.reference)} | {_safe(finding.application)} | Priorite {_display_priority(_safe(finding.priority))}"
    _add_textbox(
        slide,
        MARGIN_X,
        TITLE_TOP,
        11.5 * 72,
        0.45 * 72,
        header,
        font_size=22,
        bold=True,
        color=_priority_color(_safe(finding.priority)),
        name="Georgia",
    )

    # Manager-friendly layout: 3 blocks (Constat / Risque+Impact / Recommandation)
    left = MARGIN_X
    right = SLIDE_WIDTH - MARGIN_X
    content_width = right - left

    block_gap = 0.14 * 72
    available = TABLE_BOTTOM - BODY_TOP
    block_height = (available - 2 * block_gap) / 3

    constat_value = _safe(getattr(finding, "finding", ""))
    risk_value = _safe(getattr(finding, "risk_impact", ""))
    impact_value = _safe(getattr(finding, "impact_detail", "")) or risk_value
    root_cause = _safe(getattr(finding, "root_cause", "")).strip()
    justification = _safe(getattr(finding, "priority_justification", "")).strip()
    reco_value = _safe(getattr(finding, "recommendation", ""))
    reco_obj = _safe(getattr(finding, "recommendation_objective", ""))
    reco_steps = getattr(finding, "recommendation_steps", None)

    def add_block(top: float, title: str, body: str) -> None:
        _add_rect(slide, left, top, content_width, block_height, fill_rgb=0xFFFFFF, line_rgb=PWC_LINE_GREY)
        _add_rect(slide, left, top, content_width, 0.24 * 72, fill_rgb=PWC_ORANGE, line_rgb=PWC_ORANGE)
        _add_textbox(slide, left + 0.10 * 72, top + 0.02 * 72, content_width - 0.20 * 72, 0.18 * 72, title, font_size=10, bold=True, color=0xFFFFFF)
        _add_textbox(slide, left + 0.12 * 72, top + 0.32 * 72, content_width - 0.24 * 72, block_height - 0.38 * 72, body, font_size=10)

    top = BODY_TOP
    add_block(top, "Constat (extrait)", _pwc_constat(constat_value) if constat_value else "Information non fournie.")
    top += block_height + block_gap

    risk_lines: list[str] = []
    if risk_value:
        risk_lines.append(_pwc_risk(risk_value))
    if impact_value:
        risk_lines.append(_pwc_impact(impact_value))
    if root_cause:
        risk_lines.append(f"Cause racine probable: {_truncate(root_cause, 170)}.")
    if justification:
        risk_lines.append(f"Justification de la priorite: {_truncate(justification, 170)}.")
    add_block(top, "Risque, impact et priorite", _join_lines(risk_lines) if risk_lines else "Non determine.")
    top += block_height + block_gap

    reco_text = _pwc_recommendation(reco_value, objective=reco_obj, steps=reco_steps) if reco_value else "Recommandation non fournie."
    add_block(top, "Recommandation", reco_text)

    _add_footer(slide, footer_label, presentation.Slides.Count)


def _build_recommendation_rows(data) -> list[tuple[str, str, str, str]]:
    rows = [
        (
            _safe(item.reference),
            " - ".join(part for part in [_safe(item.application), _safe(getattr(item, "layer", ""))] if part),
            _display_priority(_safe(item.priority)),
            _safe(item.recommendation),
        )
        for item in data.detailed_recommendations
    ]
    return rows


def _prepare_presentation(powerpoint, data):
    presentation = powerpoint.Presentations.Open(str(TEMPLATE_PATH), WithWindow=False)
    _sanitize_master_palette(presentation)
    cover_placeholders = {
        "{{REPORT_DATE}}": _build_cover_date_label(data),
        "{{CLIENT_NAME}}": _safe(data.client_name),
        "{{REPORT_TITLE}}": _safe(data.cover_title),
        "{{FOOTER_LABEL}}": _build_footer_label(data),
        "{{YEAR}}": _extract_report_year(data),
        "{{REPORT_YEAR}}": _extract_report_year(data),
    }
    _replace_placeholders_in_slide(presentation.Slides(1), cover_placeholders)
    _decorate_cover_slide(presentation.Slides(1), data)
    _sanitize_slide_palette(presentation.Slides(1))
    while presentation.Slides.Count > 1:
        presentation.Slides(presentation.Slides.Count).Delete()
    return presentation


def build_report_pptx(result: ExportReportRequest) -> BytesIO:
    data = result.structured_output
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"PowerPoint template not found: {TEMPLATE_PATH}")

    footer_label = _build_footer_label(data)
    pythoncom.CoInitialize()
    powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
    powerpoint.Visible = 1
    presentation = None
    temp_path: Optional[Path] = None

    try:
        presentation = _prepare_presentation(powerpoint, data)

        _add_text_slide_v3(presentation, "Sommaire", [f"{index}. {item}" for index, item in enumerate(data.table_of_contents, start=1)], footer_label)
        _add_text_slide_v3(presentation, "Préambule", [data.preamble], footer_label)
        _add_text_slide_v3(presentation, "Objectifs", [f"- {item}" for item in data.objectives] or [f"- {_safe(data.executive_summary)}"], footer_label)
        _add_scope_slide(presentation, data, footer_label)
        _add_text_slide_v3(presentation, "Intervenants", _build_intervenant_rows(data), footer_label)
        _add_text_slide_v3(presentation, "Approche d'audit", [f"- {item}" for item in data.audit_approach], footer_label)

        page_w, _ = _page_size(presentation)
        table_width = page_w - 2 * MARGIN_X

        _add_table_slides_v3(
            presentation,
            "Liste des contrôles",
            [
                _TableColumn("Réf.", 1.10 * 72, 14, 2),
                _TableColumn("Description du contrôle", table_width - (1.10 + 3.90) * 72, 68, 4),
                _TableColumn("Procédure de test", 3.90 * 72, 52, 4),
            ],
            _build_control_rows(data),
            footer_label,
        )

        _add_control_matrix_slides(presentation, data, footer_label)

        _add_synthese_slide_v3(presentation, data, footer_label)
        _add_priorities_slide_v3(presentation, data, footer_label)

        for finding in data.detailed_findings:
            _add_observation_slide_v3(presentation, finding, footer_label)

        _add_table_slides_v3(
            presentation,
            "Recommandations détaillées",
            [
                _TableColumn("ID", 1.20 * 72, 14, 1),
                _TableColumn("Application", 3.20 * 72, 26, 2),
                _TableColumn("Priorité", 1.30 * 72, 12, 1),
                _TableColumn("Recommandation", table_width - (1.20 + 3.20 + 1.30) * 72, 68, 5),
            ],
            _build_recommendation_rows(data),
            footer_label,
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pptx") as temp_file:
            temp_path = Path(temp_file.name)

        presentation.SaveAs(str(temp_path), PP_SAVE_AS_OPEN_XML_PRESENTATION)
        presentation.Close()
        presentation = None
        time.sleep(1)

        payload = temp_path.read_bytes()
        try:
            temp_path.unlink()
        except PermissionError:
            pass

        output = BytesIO(payload)
        output.seek(0)
        return output
    finally:
        if presentation is not None:
            try:
                presentation.Close()
            except Exception:
                pass
        try:
            powerpoint.Application.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()
