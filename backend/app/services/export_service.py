from __future__ import annotations

import re
import tempfile
import time
import textwrap
import logging
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional, NamedTuple

import pythoncom
import win32com.client

from app.models.export_models import ExportReportRequest
from app.domain.itgc_control_catalog import CONTROL_CATALOG
from app.utils.french_normalizer import normalize_french

PP_SAVE_AS_OPEN_XML_PRESENTATION = 24
PP_SAVE_AS_PDF = 32
PP_LAYOUT_BLANK = 12
MSO_SHAPE_RECTANGLE = 1
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "data" / "Template PWC Universal v2.pptx"
logger = logging.getLogger(__name__)

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
PWC_ORANGE = _bgr(252, 82, 7)
PWC_DARK_ORANGE = _bgr(196, 65, 0)
PWC_LEGACY_ORANGE = _bgr(209, 122, 0)
PWC_YELLOW = _bgr(243, 175, 34)
PWC_GREEN = _bgr(46, 125, 50)
PWC_DIVIDER_PEACH = _bgr(252, 228, 214)
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


CONTROL_SHORT_LABELS = {
    "APD-01": "Révocation des accès",
    "APD-02": "Révocation des accès",
    "APD-03": "Comptes à droits étendus et génériques",
    "APD-04": "Recertification des droits d'accès",
    "APD-05": "Politique de sécurité des mots de passe",
    "APD-06": "Politique de sécurité des mots de passe",
    "APD-07": "Validation des demandes d'accès",
    "APD-08": "Accès aux données sensibles",
    "APD-09": "Accès prestataires externes",
    "PC-01": "Tests et validation avant mise en production",
    "PC-02": "Séparation des environnements",
    "PC-03": "Tests et validation avant mise en production",
    "PC-04": "Traçabilité des transports et déploiements",
    "PC-05": "Dossiers de changement",
    "PC-06": "Accès privilégiés en production",
    "PC-07": "Changements d'urgence",
    "CO-01": "Sauvegardes et plan de reprise",
    "CO-02": "Gestion des incidents de production",
    "CO-03": "Supervision des prestations externalisées",
    "CO-04": "Gestion des correctifs de sécurité",
    "CO-05": "Sauvegardes et plan de reprise",
    "CO-06": "Gestion des comptes techniques",
    "CO-07": "Procédures de restauration",
    "CO-08": "Gestion des correctifs de sécurité",
    "CO-09": "Gestion de la capacité",
}


def _control_label(reference: str, finding: object | None = None) -> str:
    category = _safe(getattr(finding, "category", "") if finding is not None else "").strip()
    if category and category.lower() not in {"n/a", "na", "none"}:
        return category

    ref = _safe(reference).upper().strip()
    if ref in CONTROL_SHORT_LABELS:
        return CONTROL_SHORT_LABELS[ref]

    item = CONTROL_CATALOG.get(ref, {})
    description = _safe(item.get("description", "")).strip()
    if description:
        return _first_complete_clause(description, 80)
    return ref or "Contrôle non précisé"


def _control_application_label(finding: object, *, include_reference: bool = True) -> str:
    reference = _safe(getattr(finding, "reference", "")).upper().strip()
    application = _clean_export_text(getattr(finding, "application", "")).strip()
    label = _control_label(reference, finding)
    first_line = f"{label} - {application}" if application else label
    if include_reference and reference:
        return f"{first_line}\nRef. {reference}"
    return first_line


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
        wrapped[-1] = wrapped[-1].rstrip(" .,;:")

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
        wrapped_lines[-1] = _remove_dangling_tail(last.rstrip(" .,;:"))

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


def _wrapped_line_count(text: str, *, width: int) -> int:
    raw = _safe(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = 0
    for line in raw.split("\n"):
        value = " ".join(line.split()).strip()
        if not value:
            continue
        lines += max(1, len(textwrap.wrap(value, width=width, break_long_words=False, break_on_hyphens=False)))
    return max(1, lines)


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
        "High": "Élevée",
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


def _build_export_toc(data) -> list[str]:
    has_findings = bool(getattr(data, "detailed_findings", []) or [])
    items = [
        "Cadre de notre intervention et démarche",
        "Synthèse générale",
    ]
    if has_findings:
        items.append("Recommandations détaillées")
    items.append("Annexes")
    return items


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
        page_w - MARGIN_X - 3.35 * 72,
        0.48 * 72,
        3.35 * 72,
        0.22 * 72,
        confidentiality,
        font_size=8,
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


def _safe_geometry(slide, left: float, top: float, width: float, height: float) -> tuple[float, float, float, float]:
    try:
        page_w, page_h = _page_size(slide.Parent)
    except Exception:
        page_w, page_h = SLIDE_WIDTH, SLIDE_HEIGHT

    min_size = 1.0
    page_w = max(min_size, float(page_w))
    page_h = max(min_size, float(page_h))
    left = max(0.0, min(float(left), page_w - min_size))
    top = max(0.0, min(float(top), page_h - min_size))
    width = max(min_size, float(width))
    height = max(min_size, float(height))

    if left + width > page_w:
        width = max(min_size, page_w - left)
    if top + height > page_h:
        height = max(min_size, page_h - top)

    return left, top, width, height


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
    text = normalize_french(_safe(text))
    left, top, width, height = _safe_geometry(slide, left, top, width, height)
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
    try:
        min_size = min(font_size, 7)
        current_size = font_size
        available_h = max(1.0, height - box.TextFrame.MarginTop - box.TextFrame.MarginBottom)
        available_w = max(1.0, width - box.TextFrame.MarginLeft - box.TextFrame.MarginRight)
        while current_size > min_size:
            bound_h = float(text_range.BoundHeight)
            bound_w = float(text_range.BoundWidth)
            if bound_h <= available_h and bound_w <= available_w:
                break
            current_size -= 1
            text_range.Font.Size = current_size
    except Exception:
        pass


def _add_rect(slide, left: float, top: float, width: float, height: float, *, fill_rgb: int = 0xFFFFFF, line_rgb: int = 0xBFBFBF, weight: float = 0.75):
    left, top, width, height = _safe_geometry(slide, left, top, width, height)
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
        try:
            page_w, page_h = _page_size(slide.Parent)
        except Exception:
            page_w, page_h = SLIDE_WIDTH, SLIDE_HEIGHT

        footer_y = page_h - (0.42 * 72)
        number_w = 0.4 * 72
        label_w = max(1.0, page_w - 2 * MARGIN_X - number_w - 0.20 * 72)

        _add_textbox(slide, MARGIN_X, footer_y, label_w, 0.25 * 72, footer_label, font_size=8, color=PWC_TEXT_GREY)
        _add_textbox(slide, page_w - MARGIN_X - number_w, footer_y, number_w, 0.25 * 72, str(slide_number), font_size=8, color=PWC_TEXT_GREY)
    except Exception:
        # PowerPoint COM can occasionally invalidate a slide reference while
        # running headless from the web server. Footer rendering is cosmetic,
        # so export should continue rather than failing the whole report.
        return


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


def _is_legacy_orange(bgr: int) -> bool:
    return bgr == PWC_LEGACY_ORANGE


def _sanitize_fill(fill) -> None:
    try:
        if not fill.Visible:
            return
    except Exception:
        return

    try:
        color = fill.ForeColor.RGB
        if isinstance(color, int) and (_is_blue_like(color) or _is_legacy_orange(color)):
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
        if isinstance(color, int) and _is_legacy_orange(color):
            line.ForeColor.RGB = PWC_ORANGE
        elif isinstance(color, int) and _is_blue_like(color):
            line.ForeColor.RGB = PWC_LINE_GREY
    except Exception:
        pass


def _sanitize_text_range(rng) -> None:
    try:
        color = rng.Font.Color.RGB
        if isinstance(color, int) and _is_legacy_orange(color):
            rng.Font.Color.RGB = PWC_ORANGE
        elif isinstance(color, int) and _is_blue_like(color):
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


def _add_toc_slide_v3(presentation, items: list[str], footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    _add_title(slide, "Sommaire")
    page_w, _ = _page_size(presentation)
    left = MARGIN_X
    top = BODY_TOP + 0.20 * 72
    width = page_w - 2 * MARGIN_X
    row_h = 0.50 * 72
    gap = 0.10 * 72

    for index, item in enumerate(items, start=1):
        y = top + (index - 1) * (row_h + gap)
        _add_rect(slide, left, y, width, row_h, fill_rgb=PWC_WHITE, line_rgb=PWC_LINE_GREY, weight=0.5)
        _add_textbox(
            slide,
            left + 0.18 * 72,
            y + 0.10 * 72,
            0.38 * 72,
            row_h - 0.14 * 72,
            str(index),
            font_size=15,
            bold=True,
            color=PWC_ORANGE,
            name="Georgia",
        )
        _add_textbox(
            slide,
            left + 0.70 * 72,
            y + 0.11 * 72,
            width - 0.90 * 72,
            row_h - 0.14 * 72,
            _clean_export_text(item),
            font_size=16,
            bold=True,
            color=PWC_TEXT_DARK,
            name="Arial",
        )

    _sanitize_slide_palette(slide)
    _add_footer(slide, footer_label, presentation.Slides.Count)


def _parse_intervenant(item: str) -> tuple[str, str]:
    value = _clean_export_text(item)
    match = re.match(r"^(?P<name>.+?)\s*\((?P<role>[^)]+)\)\s*$", value)
    if match:
        return match.group("name").strip(), match.group("role").strip()
    if " - " in value:
        left, right = value.split(" - ", 1)
        return right.strip(), left.strip()
    return value, "Intervenant mission"


def _intervenant_organization(role: str) -> str:
    lowered = _safe(role).lower()
    if any(token in lowered for token in ("rssi", "dsi", "responsable", "direction")):
        return "Banque Zitouna / DGSI"
    return "PwC Audit IT"


def _intervenant_responsibility(role: str) -> str:
    lowered = _safe(role).lower()
    if "manager" in lowered:
        return "Pilotage de la mission, arbitrage des constats et validation du livrable."
    if "senior" in lowered:
        return "Coordination des travaux, revue des tests et consolidation des recommandations."
    if "auditeur" in lowered or "audit" in lowered:
        return "Exécution des tests, collecte des preuves et documentation des observations."
    if "rssi" in lowered or "responsable" in lowered:
        return "Point de contact sécurité, coordination DSI et suivi des plans d'action."
    return "Contribution aux entretiens, validation des informations et suivi des actions."


def _build_intervenant_table_rows(data) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for item in getattr(data, "stakeholders", []) or []:
        name, role = _parse_intervenant(str(item))
        rows.append(
            (
                name,
                role,
                _intervenant_organization(role),
                _intervenant_responsibility(role),
            )
        )
    return rows or [("À compléter", "À compléter", "À compléter", "Responsabilité à préciser.")]


def _add_intervenants_slide_v3(presentation, data, footer_label: str) -> None:
    page_w, _ = _page_size(presentation)
    table_width = page_w - 2 * MARGIN_X
    _add_table_slides_v3(
        presentation,
        "Intervenants",
        [
            _TableColumn("Nom", 2.05 * 72, 24, 2),
            _TableColumn("Rôle", 2.00 * 72, 24, 2),
            _TableColumn("Organisation / équipe", 2.20 * 72, 28, 2),
            _TableColumn("Responsabilité dans la mission", table_width - (2.05 + 2.00 + 2.20) * 72, 58, 3),
        ],
        _build_intervenant_table_rows(data),
        footer_label,
    )


def _add_section_divider_slide(presentation, title: str, section_number: int, footer_label: str, subtitle: str = "") -> None:
    slide = _add_blank_slide(presentation)
    page_w, page_h = _page_size(presentation)
    _add_rect(slide, 0, 0, page_w, page_h, fill_rgb=PWC_DIVIDER_PEACH, line_rgb=PWC_DIVIDER_PEACH, weight=0)

    # Match the divider slides from the PAREF reference deck.
    _add_textbox(slide, 0.44 * 72, 3.78 * 72, 6.17 * 72, 2.84 * 72, title, font_size=28, color=PWC_TEXT_DARK, name="Georgia")
    _add_textbox(slide, 8.96 * 72, 0.63 * 72, 3.79 * 72, 4.71 * 72, str(section_number), font_size=150, color=PWC_ORANGE, name="Georgia")

    _add_textbox(slide, 0.44 * 72, 7.11 * 72, 0.55 * 72, 0.18 * 72, "PwC", font_size=6, color=PWC_TEXT_DARK, bold=True)
    _add_textbox(slide, 1.17 * 72, 7.11 * 72, 9.64 * 72, 0.18 * 72, footer_label, font_size=6, color=PWC_TEXT_DARK)
    _add_textbox(slide, 12.58 * 72, 7.11 * 72, 0.33 * 72, 0.18 * 72, str(presentation.Slides.Count), font_size=6, color=PWC_TEXT_DARK)
    _sanitize_slide_palette(slide)


def _add_priority_methodology_slide(presentation, footer_label: str) -> None:
    columns = [
        _TableColumn("Priorité", 1.20 * 72, 14, 2),
        _TableColumn("Description", 4.45 * 72, 58, 4),
        _TableColumn("Risque", 3.60 * 72, 48, 4),
        _TableColumn("Délai cible", 1.45 * 72, 16, 2),
    ]
    rows = [
        (
            "Critique",
            "Faiblesse significative pouvant affecter une application ou un processus clé, avec exposition avérée ou forte probabilité d'exploitation.",
            "Impact potentiel élevé sur la confidentialité, l'intégrité, la disponibilité, la traçabilité ou la fiabilité des traitements.",
            "30 jours",
        ),
        (
            "Élevée",
            "Déficience importante nécessitant une remédiation priorisée et un suivi formel par le management.",
            "Risque notable de contournement de contrôle, d'erreur non détectée, de non-conformité ou d'interruption opérationnelle.",
            "60 jours",
        ),
        (
            "Moyenne",
            "Amélioration attendue sur un contrôle existant, sans exposition critique immédiate identifiée.",
            "Risque modéré pouvant réduire l'efficacité du dispositif de contrôle interne.",
            "90 jours",
        ),
        (
            "Faible",
            "Point d'amélioration ou formalisation complémentaire sans incidence significative à court terme.",
            "Risque limité, principalement lié à la documentation, à l'harmonisation ou à l'efficience du contrôle.",
            "À planifier",
        ),
    ]
    _add_table_slides_v3(
        presentation,
        "Niveaux de priorité et critères de classification",
        columns,
        rows,
        footer_label,
    )


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


def _priority_sort_value(priority: str) -> int:
    return {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}.get(_safe(priority), 99)


def _priority_due_label(priority: str) -> str:
    value = _safe(priority)
    if value == "Critical":
        return "30 jours"
    if value == "High":
        return "60 jours"
    if value == "Medium":
        return "90 jours"
    if value == "Low":
        return "À planifier"
    return "À confirmer"


def _add_synthese_slide_v3(presentation, data, footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    _add_title(slide, "Synthèse générale")
    page_w, _ = _page_size(presentation)
    content_bottom = _content_bottom(presentation)
    findings = list(getattr(data, "detailed_findings", []) or [])
    counts = {item.priority: int(getattr(item, "count", 0) or 0) for item in getattr(data, "priority_summary", []) or []}
    maturity = _safe(getattr(data, "maturity_level", "")).strip()
    maturity_assessment = _safe(getattr(data, "maturity_assessment", "")).strip()

    apps_impacted: list[str] = []
    for finding in findings:
        app = _safe(getattr(finding, "application", "")).strip()
        if app and app not in apps_impacted:
            apps_impacted.append(app)

    header_top = BODY_TOP + 0.04 * 72
    header_h = 0.76 * 72
    _add_rect(slide, MARGIN_X, header_top, page_w - 2 * MARGIN_X, header_h, fill_rgb=PWC_WHITE, line_rgb=PWC_LINE_GREY, weight=0.75)
    counts_line = (
        f"{counts.get('Critical', 0)} critique(s), {counts.get('High', 0)} élevée(s), "
        f"{counts.get('Medium', 0)} moyenne(s), {counts.get('Low', 0)} faible(s)"
    )
    headline = f"{len(findings)} observation(s) relevée(s), dont {counts_line}."
    if maturity:
        headline += f" Niveau de maturité estimé : {maturity}."
    _add_textbox(slide, MARGIN_X + 0.14 * 72, header_top + 0.10 * 72, page_w - 2 * MARGIN_X - 0.28 * 72, 0.22 * 72, "Message de synthèse", font_size=12, bold=True, color=PWC_ORANGE, name="Georgia")
    _add_textbox(slide, MARGIN_X + 0.14 * 72, header_top + 0.38 * 72, page_w - 2 * MARGIN_X - 0.28 * 72, 0.30 * 72, _wrap_text(headline, width=150), font_size=10, color=PWC_TEXT_DARK)

    main_top = header_top + header_h + 0.14 * 72
    gap = 0.22 * 72
    left_w = (page_w - 2 * MARGIN_X) * 0.46
    right_w = page_w - 2 * MARGIN_X - left_w - gap
    left = MARGIN_X
    right = MARGIN_X + left_w + gap
    main_h = content_bottom - main_top

    _add_rect(slide, left, main_top, left_w, main_h, fill_rgb=PWC_WHITE, line_rgb=PWC_LINE_GREY, weight=0.75)
    _add_textbox(slide, left + 0.12 * 72, main_top + 0.10 * 72, left_w - 0.24 * 72, 0.22 * 72, "Diagnostic par processus", font_size=12, bold=True, color=PWC_ORANGE, name="Georgia")
    y = main_top + 0.46 * 72
    col_w = [1.05 * 72, 0.55 * 72, 0.95 * 72, left_w - 2.55 * 72]
    headers = ["Processus", "Obs.", "Niveau", "Applications touchées"]
    x = left + 0.10 * 72
    for header, width in zip(headers, col_w):
        _add_rect(slide, x, y, width, 0.30 * 72, fill_rgb=PWC_LIGHT_GREY, line_rgb=PWC_LINE_GREY, weight=0.5)
        _add_textbox(slide, x + 0.04 * 72, y + 0.06 * 72, width - 0.08 * 72, 0.18 * 72, header, font_size=8, bold=True, color=PWC_TEXT_DARK)
        x += width
    y += 0.30 * 72

    for code, label in [("APD", "Accès"), ("PC", "Changements"), ("CO", "Exploitation")]:
        scoped = [item for item in findings if _safe(getattr(item, "reference", "")).upper().startswith(f"{code}-")]
        if not scoped:
            continue
        top_priority = sorted(scoped, key=lambda item: _priority_sort_value(getattr(item, "priority", "")))[0].priority
        scoped_apps: list[str] = []
        for item in scoped:
            app = _safe(getattr(item, "application", ""))
            if app and app not in scoped_apps:
                scoped_apps.append(app)
        row_h = 0.50 * 72
        values = [label, str(len(scoped)), _display_priority(top_priority), _wrap_text(", ".join(scoped_apps[:4]) or "-", width=30)]
        x = left + 0.10 * 72
        for value, width in zip(values, col_w):
            fill, font = _priority_fill_and_font(value) if value == values[2] else (PWC_WHITE, PWC_TEXT_DARK)
            _add_rect(slide, x, y, width, row_h, fill_rgb=fill, line_rgb=PWC_LINE_GREY, weight=0.5)
            _add_textbox(slide, x + 0.04 * 72, y + 0.06 * 72, width - 0.08 * 72, row_h - 0.10 * 72, value, font_size=8, bold=value == values[2], color=font)
            x += width
        y += row_h

    if maturity_assessment:
        remaining_h = max(0.58 * 72, main_top + main_h - y - 0.20 * 72)
        assessment = _wrap_preserving_lines(_clean_export_text(maturity_assessment), width=56, max_lines=5)
        _add_textbox(slide, left + 0.12 * 72, y + 0.12 * 72, left_w - 0.24 * 72, remaining_h, assessment, font_size=8, color=PWC_TEXT_DARK)

    card_gap = 0.20 * 72
    card_h = (main_h - card_gap) / 2

    def right_card(ypos: float, title: str, lines: list[str], *, max_lines: int) -> None:
        _add_rect(slide, right, ypos, right_w, card_h, fill_rgb=PWC_WHITE, line_rgb=PWC_LINE_GREY, weight=0.75)
        _add_textbox(slide, right + 0.12 * 72, ypos + 0.10 * 72, right_w - 0.24 * 72, 0.20 * 72, title, font_size=11, bold=True, color=PWC_ORANGE, name="Georgia")
        body = _wrap_preserving_lines(_join_lines(lines), width=62, max_lines=max_lines)
        _add_textbox(slide, right + 0.12 * 72, ypos + 0.38 * 72, right_w - 0.24 * 72, card_h - 0.46 * 72, body, font_size=9, color=PWC_TEXT_DARK)

    def synthesis_risk(finding) -> str:
        ref = _safe(getattr(finding, "reference", "")).upper()
        app = _safe(getattr(finding, "application", ""))
        if ref == "APD-01":
            return "Accès non autorisés via comptes actifs post-départ, avec risque de fraude, fuite de données et perte de traçabilité."
        if ref == "APD-03":
            return "Maintien de droits incompatibles ou excessifs, pouvant contourner la séparation des fonctions sur les processus sensibles."
        if ref == "CO-01":
            return "Indisponibilité prolongée en cas de sinistre faute de tests PRA/RTO/RPO complets et documentés."
        if ref == "CO-04":
            return "Exposition de services clients à des vulnérabilités critiques connues en raison de correctifs non appliqués dans les délais."
        risk = _first_complete_clause(_safe(getattr(finding, "risk_impact", "")), 150)
        return risk or f"Risque significatif identifié sur {app}."

    risks: list[str] = []
    for finding in findings:
        risk = synthesis_risk(finding).strip()
        if risk and risk not in risks:
            risks.append(risk)
        if len(risks) == 4:
            break
    risk_lines = [f"- {risk}" for risk in risks] or ["- Risques non précisés dans l'output."]
    management_lines = [
        f"- Périmètre impacté : {', '.join(apps_impacted[:5])}." if apps_impacted else "",
        "- Les faiblesses critiques/élevées appellent un suivi formalisé par le management.",
        "- La slide suivante présente l'ordre de traitement et les échéances cibles.",
    ]
    management_lines = [line for line in management_lines if line]
    right_card(main_top, "Risques métier clés", risk_lines, max_lines=7)
    right_card(main_top + card_h + card_gap, "Lecture management", management_lines, max_lines=5)

    _sanitize_slide_palette(slide)
    _add_footer(slide, footer_label, presentation.Slides.Count)


def _add_priorities_slide_v3(presentation, data, footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    _add_title(slide, "Synthèse des priorités")
    page_w, _ = _page_size(presentation)
    content_bottom = _content_bottom(presentation)
    findings = sorted(
        list(getattr(data, "detailed_findings", []) or []),
        key=lambda item: (_priority_sort_value(getattr(item, "priority", "")), _safe(getattr(item, "reference", "")), _safe(getattr(item, "application", ""))),
    )
    top = BODY_TOP + 0.08 * 72
    left = MARGIN_X
    width = page_w - 2 * MARGIN_X

    intro = "Ordre de traitement proposé : traiter d'abord les points critiques, puis les points élevés structurants. Les échéances suivent les critères de classification du rapport."
    _add_textbox(slide, left, top - 0.08 * 72, width, 0.34 * 72, _wrap_text(intro, width=140), font_size=11, color=PWC_TEXT_DARK)

    table_top = top + 0.42 * 72
    header_h = 0.34 * 72
    row_h = 0.64 * 72
    deadline_w = 0.95 * 72
    rank_w = 0.48 * 72
    priority_w = 0.95 * 72
    control_w = 2.25 * 72
    action_w = max(2.50 * 72, width - rank_w - priority_w - control_w - deadline_w)
    columns = [
        ("Rang", rank_w, 6),
        ("Priorité", priority_w, 10),
        ("Contrôle concerné / application", control_w, 30),
        ("Action immédiate attendue", action_w, 48),
        ("Échéance", deadline_w, 14),
    ]

    x = left
    for label, col_w, _ in columns:
        _add_rect(slide, x, table_top, col_w, header_h, fill_rgb=PWC_LIGHT_GREY, line_rgb=PWC_LINE_GREY, weight=0.75)
        _add_textbox(slide, x + 0.04 * 72, table_top + 0.07 * 72, col_w - 0.08 * 72, header_h - 0.10 * 72, label, font_size=8, bold=True, color=PWC_TEXT_DARK)
        x += col_w

    y = table_top + header_h
    for index, finding in enumerate(findings[:6], start=1):
        priority = _safe(getattr(finding, "priority", ""))
        priority_label = _display_priority(priority)
        control_application = _control_application_label(finding)
        action = _safe(getattr(finding, "immediate_action", "")).strip() or _safe(getattr(finding, "recommendation", "")).strip()
        values = [
            str(index),
            priority_label,
            _wrap_text(control_application, width=30),
            _wrap_text(action, width=48),
            _priority_due_label(priority),
        ]
        x = left
        for col_index, ((_, col_w, _), value) in enumerate(zip(columns, values)):
            fill_rgb, font_color = (_priority_fill_and_font(priority_label) if col_index == 1 else (PWC_WHITE, PWC_TEXT_DARK))
            _add_rect(slide, x, y, col_w, row_h, fill_rgb=fill_rgb, line_rgb=PWC_LINE_GREY, weight=0.5)
            _add_textbox(slide, x + 0.04 * 72, y + 0.06 * 72, col_w - 0.08 * 72, row_h - 0.10 * 72, value, font_size=9, bold=col_index in {0, 1}, color=font_color)
            x += col_w
        y += row_h

    bottom_top = y + 0.18 * 72
    bottom_h = max(0.75 * 72, content_bottom - bottom_top)
    _add_rect(slide, left, bottom_top, width, bottom_h, fill_rgb=PWC_WHITE, line_rgb=PWC_LINE_GREY, weight=0.75)
    _add_textbox(slide, left + 0.12 * 72, bottom_top + 0.08 * 72, width - 0.24 * 72, 0.20 * 72, "Chantiers transverses à piloter", font_size=12, bold=True, color=PWC_ORANGE, name="Georgia")
    initiatives: list[str] = []
    for item in getattr(data, "transversal_initiatives", []) or []:
        value = _safe(item).strip()
        if value and value not in initiatives:
            initiatives.append(value)
        if len(initiatives) == 3:
            break
    body = _wrap_preserving_lines(
        _join_lines([f"- {item}" for item in initiatives] or ["- Formaliser un pilotage transverse des remédiations avec responsables, échéances et preuves attendues."]),
        width=130,
        max_lines=5,
    )
    _add_textbox(slide, left + 0.12 * 72, bottom_top + 0.36 * 72, width - 0.24 * 72, bottom_h - 0.44 * 72, body, font_size=10, color=PWC_TEXT_DARK)

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

    control_label = _control_label(ref, finding)
    header_left = " | ".join(part for part in [control_label, app, layer] if part).strip(" |")
    _add_textbox(slide, MARGIN_X, TITLE_TOP, 10.0 * 72, 0.30 * 72, header_left, font_size=17, bold=True, name="Georgia", color=PWC_TEXT_DARK)
    if ref:
        _add_textbox(slide, MARGIN_X, TITLE_TOP + 0.30 * 72, 10.0 * 72, 0.16 * 72, f"Réf. contrôle : {ref}", font_size=8, color=PWC_TEXT_GREY)

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
    risk_scenario = _safe(getattr(finding, "risk_scenario", "")).strip()
    impact = _safe(getattr(finding, "impact_detail", ""))
    business_impact = _safe(getattr(finding, "business_impact", "")).strip()
    control_impact = _safe(getattr(finding, "control_impact", "")).strip()
    compliance_impact = _safe(getattr(finding, "compliance_impact", "")).strip()
    aggravating_factors = getattr(finding, "aggravating_factors", []) or []
    reco = _safe(getattr(finding, "recommendation", ""))
    reco_obj = _safe(getattr(finding, "recommendation_objective", ""))
    reco_steps = getattr(finding, "recommendation_steps", None)
    root_cause = _safe(getattr(finding, "root_cause", "")).strip()
    immediate_action = _safe(getattr(finding, "immediate_action", "")).strip()
    structural_action = _safe(getattr(finding, "structural_action", "")).strip()
    owner = _safe(getattr(finding, "owner", "")).strip()
    evidence_expected = _safe(getattr(finding, "evidence_expected", "")).strip()
    follow_up = _safe(getattr(finding, "follow_up_mechanism", "")).strip()

    top = BODY_TOP + 0.38 * 72
    grid_gap_x = 0.18 * 72
    grid_gap_y = 0.16 * 72
    width = page_w - 2 * MARGIN_X
    card_w = (width - grid_gap_x) / 2
    card_h = (content_bottom - top - grid_gap_y) / 2

    def section(x: float, y: float, label: str, body: str, *, max_lines: int, font_size: int = 10) -> None:
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
            font_size=font_size,
            color=PWC_TEXT_DARK,
        )

    control_context_lines = []
    if compensating:
        control_context_lines.append(f"Procédure compensatoire : {compensating}")
    if auditor_comment:
        control_context_lines.append(f"Commentaire d'audit : {auditor_comment}")
    if not control_context_lines:
        control_context_lines.append("Aucune procédure compensatoire ni commentaire complémentaire renseigné.")

    risk_lines = []
    if risk_scenario:
        risk_lines.append(_compact_bullet("Scenario", risk_scenario, max_len=118))
    elif risk:
        risk_lines.append(_compact_bullet("Risque", risk, max_len=118))
    if aggravating_factors:
        factors = "; ".join(str(item).strip().rstrip(".") for item in aggravating_factors[:2] if str(item).strip())
        if factors:
            risk_lines.append(_compact_bullet("Exposition", factors, max_len=112))
    if business_impact or impact:
        risk_lines.append(_compact_bullet("Impact metier", business_impact or impact, max_len=118))
    if control_impact:
        risk_lines.append(_compact_bullet("Controle interne", control_impact, max_len=112))
    if root_cause:
        risk_lines.append(_compact_bullet("Cause", root_cause, max_len=110))

    reco_lines = [
        _compact_bullet("Immediat", immediate_action, max_len=115),
        _compact_bullet("Structurel", structural_action, max_len=115),
        _compact_bullet("Owner", owner, max_len=90),
        _compact_bullet("Preuves", evidence_expected, max_len=112),
        _compact_bullet("Suivi", follow_up, max_len=112),
    ]
    reco_lines = [line for line in reco_lines if line]
    if not reco_lines and reco_steps:
        reco_lines = [f"- {_truncate(_compact_step_text(str(step)), 120)}" for step in reco_steps[:5] if str(step).strip()]
    if not reco_lines and reco:
        reco_lines = [_compact_bullet("Action", reco, max_len=130)]
    left_x = MARGIN_X
    right_x = MARGIN_X + card_w + grid_gap_x
    top_y = top
    bottom_y = top + card_h + grid_gap_y

    section(left_x, top_y, "Constat", constat, max_lines=9)
    section(right_x, top_y, "Procédure compensatoire / commentaire", _join_lines(control_context_lines), max_lines=9)
    section(left_x, bottom_y, "Risque, impact et exposition", _join_lines(risk_lines[:5]) if risk_lines else "Non déterminé.", max_lines=10, font_size=9)
    section(right_x, bottom_y, "Recommandation", _join_lines(reco_lines[:5]) if reco_lines else "Recommandation non fournie.", max_lines=10, font_size=9)

    _sanitize_slide_palette(slide)
    _add_footer(slide, footer_label, presentation.Slides.Count)


def _observation_header(slide, finding) -> tuple[str, str, str, str, str]:
    page_w, _ = _page_size(slide.Parent)
    ref = _safe(getattr(finding, "reference", ""))
    app = _safe(getattr(finding, "application", ""))
    layer = _safe(getattr(finding, "layer", ""))
    prio = _safe(getattr(finding, "priority", ""))
    prio_label = _display_priority(prio)
    title = _sharpen_title(_safe(getattr(finding, "title", "")), reference=ref)

    control_label = _control_label(ref, finding)
    header_left = " | ".join(part for part in [control_label, app, layer] if part).strip(" |")
    _add_textbox(slide, MARGIN_X, TITLE_TOP, 10.0 * 72, 0.30 * 72, header_left, font_size=17, bold=True, name="Georgia", color=PWC_TEXT_DARK)
    if ref:
        _add_textbox(slide, MARGIN_X, TITLE_TOP + 0.30 * 72, 10.0 * 72, 0.16 * 72, f"Réf. contrôle : {ref}", font_size=8, color=PWC_TEXT_GREY)

    pill_w = 2.10 * 72
    pill_h = 0.30 * 72
    pill_left = page_w - MARGIN_X - pill_w
    pill_top = TITLE_TOP + 0.02 * 72
    pill_color = _priority_color(prio)
    _add_rect(slide, pill_left, pill_top, pill_w, pill_h, fill_rgb=pill_color, line_rgb=pill_color, weight=0)
    _add_textbox(slide, pill_left + 0.10 * 72, pill_top + 0.03 * 72, pill_w - 0.20 * 72, pill_h - 0.06 * 72, f"Priorité {prio_label}", font_size=10, bold=True, color=PWC_WHITE)
    _add_rect(slide, MARGIN_X, TITLE_TOP + 0.45 * 72, page_w - 2 * MARGIN_X, 0.03 * 72, fill_rgb=PWC_ORANGE, line_rgb=PWC_ORANGE, weight=0)

    if title:
        _add_textbox(slide, MARGIN_X, BODY_TOP - 0.15 * 72, page_w - 2 * MARGIN_X, 0.30 * 72, title, font_size=14, bold=True, color=PWC_TEXT_DARK)

    return ref, app, layer, prio, title


def _extract_finding_numbers(text: str) -> list[str]:
    values = re.findall(r"\b\d+(?:[.,]\d+)?\s*%?|\b\d{1,2}/\d{1,2}/\d{4}\b", _safe(text))
    ordered: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in ordered:
            ordered.append(cleaned)
    return ordered[:5]


def _extract_key_evidence_points(text: str) -> list[str]:
    value = _clean_export_text(text)
    lowered = value.lower()
    points: list[str] = []

    patterns = [
        (r"(\d+)\s+comptes?\s+(?:utilisateurs?\s+)?(?:\w+\s+)?(?:toujours\s+)?actifs?.{0,45}?(?:post[- ]?départ|post[- ]?depart|départ|depart)", "{} comptes actifs post-départ"),
        (r"(\d+)\s+connexions?\s+(?:post[- ]?départ|post[- ]?depart)", "{} connexions post-départ confirmées"),
        (r"dont\s+(\d+).{0,45}?(?:fort\s+encours|comptes?\s+clients?)", "{} cas sur comptes clients à fort encours"),
        (r"(\d+)\s+cas\s+de\s+cumul", "{} cas de cumul de fonctions incompatibles"),
        (r"(\d+)\s+comptes?\s+(?:génériques|generiques|privilégiés|privilegies)", "{} comptes génériques ou privilégiés"),
        (r"(\d+)\s+rfc.{0,45}?(?:sans|ne comportent pas)", "{} RFC sans validation documentée"),
        (r"(\d+)\s+incidents?\s+majeurs?", "{} incidents majeurs"),
        (r"rpo\s*:\s*([0-9]+h)", "RPO {} non vérifié par test"),
        (r"rto\s*:\s*([0-9]+h)", "RTO {} non vérifié par test"),
        (r"cvss\s*(?:≥|>=|superieur|supérieur)?\s*([0-9]+(?:[.,][0-9]+)?)", "Vulnérabilités critiques CVSS {}"),
    ]

    for pattern, template in patterns:
        for match in re.finditer(pattern, lowered, flags=re.IGNORECASE):
            point = template.format(match.group(1))
            if point not in points:
                points.append(point)
            if len(points) >= 4:
                return points

    if not points:
        numbers = _extract_finding_numbers(value)
        if numbers:
            points.append("Exposition quantifiée dans le constat: " + ", ".join(numbers[:3]))
    return points[:4]


def _build_constat_evidence_lines(finding) -> list[str]:
    constat = _clean_export_text(getattr(finding, "finding", ""))
    compensating = _clean_export_text(getattr(finding, "compensating_procedure", ""))
    auditor_comment = _clean_export_text(getattr(finding, "auditor_comment", ""))
    owners = _tidy_owner_text(getattr(finding, "owners", ""), max_len=150)

    lines = [
        _compact_bullet("Travaux", constat, max_len=330),
    ]
    key_points = _extract_key_evidence_points(f"{constat} {auditor_comment}")
    if key_points:
        lines.append(_compact_bullet("Éléments clés", "; ".join(key_points), max_len=170))
    if auditor_comment:
        lines.append(_compact_bullet("Preuves", auditor_comment, max_len=300))
    if compensating:
        lines.append(_compact_bullet("Contrôle compensatoire", compensating, max_len=220))
    if owners:
        lines.append(_compact_bullet("Responsables", owners, max_len=130))
    return [line for line in lines if line][:5]


def _build_risk_action_lines(finding) -> tuple[list[str], list[str]]:
    risk = _safe(getattr(finding, "risk_impact", ""))
    risk_scenario = _safe(getattr(finding, "risk_scenario", "")).strip()
    impact = _safe(getattr(finding, "impact_detail", ""))
    business_impact = _safe(getattr(finding, "business_impact", "")).strip()
    control_impact = _safe(getattr(finding, "control_impact", "")).strip()
    aggravating_factors = getattr(finding, "aggravating_factors", []) or []
    root_cause = _safe(getattr(finding, "root_cause", "")).strip()
    immediate_action = _safe(getattr(finding, "immediate_action", "")).strip()
    structural_action = _safe(getattr(finding, "structural_action", "")).strip()
    owner = _tidy_owner_text(getattr(finding, "owner", ""), max_len=140)
    evidence_expected = _safe(getattr(finding, "evidence_expected", "")).strip()
    follow_up = _safe(getattr(finding, "follow_up_mechanism", "")).strip()
    reco = _safe(getattr(finding, "recommendation", ""))
    reco_steps = getattr(finding, "recommendation_steps", None)

    risk_lines = []
    if risk_scenario:
        risk_lines.append(_compact_bullet("Scénario", risk_scenario, max_len=190))
    elif risk:
        risk_lines.append(_compact_bullet("Risque", risk, max_len=220))
    if aggravating_factors:
        factors = "; ".join(str(item).strip().rstrip(".") for item in aggravating_factors[:2] if str(item).strip())
        risk_lines.append(_compact_bullet("Exposition", factors, max_len=190))
    risk_lines.append(_compact_bullet("Impact métier", business_impact or impact, max_len=190))
    risk_lines.append(_compact_bullet("Contrôle interne", control_impact, max_len=180))
    risk_lines.append(_compact_bullet("Cause", root_cause, max_len=240))
    risk_lines = [line for line in risk_lines if line][:5]

    reco_lines = [
        _compact_bullet("Immédiat", immediate_action, max_len=180),
        _compact_bullet("Structurel", structural_action, max_len=260),
        _compact_bullet("Owner", owner, max_len=140),
        _compact_bullet("Preuves", evidence_expected, max_len=220),
        _compact_bullet("Suivi", follow_up, max_len=220),
    ]
    reco_lines = [line for line in reco_lines if line]
    if not reco_lines and reco_steps:
        reco_lines = [f"- {_truncate(_compact_step_text(str(step)), 150)}" for step in reco_steps[:5] if str(step).strip()]
    if not reco_lines and reco:
        reco_lines = [_compact_bullet("Action", reco, max_len=150)]
    return risk_lines, reco_lines[:5]


def _add_observation_evidence_slide(presentation, finding, footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    page_w, _ = _page_size(presentation)
    content_bottom = _content_bottom(presentation)
    _observation_header(slide, finding)

    top = BODY_TOP + 0.38 * 72
    width = page_w - 2 * MARGIN_X
    height = content_bottom - top
    _add_rect(slide, MARGIN_X, top, width, height, fill_rgb=PWC_WHITE, line_rgb=PWC_LINE_GREY, weight=0.75)
    _add_textbox(slide, MARGIN_X + 0.16 * 72, top + 0.12 * 72, width - 0.32 * 72, 0.24 * 72, "Constat et éléments probants", font_size=13, bold=True, color=PWC_ORANGE, name="Georgia")
    body = _wrap_preserving_lines(_join_lines(_build_constat_evidence_lines(finding)), width=132, max_lines=20)
    _add_textbox(slide, MARGIN_X + 0.16 * 72, top + 0.50 * 72, width - 0.32 * 72, height - 0.64 * 72, body, font_size=10, color=PWC_TEXT_DARK)
    _sanitize_slide_palette(slide)
    _add_footer(slide, footer_label, presentation.Slides.Count)


def _add_observation_risk_action_slide(presentation, finding, footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    page_w, _ = _page_size(presentation)
    content_bottom = _content_bottom(presentation)
    _observation_header(slide, finding)

    top = BODY_TOP + 0.38 * 72
    gap = 0.22 * 72
    width = page_w - 2 * MARGIN_X
    card_w = (width - gap) / 2
    height = content_bottom - top
    risk_lines, reco_lines = _build_risk_action_lines(finding)

    def card(x: float, title: str, lines: list[str]) -> None:
        _add_rect(slide, x, top, card_w, height, fill_rgb=PWC_WHITE, line_rgb=PWC_LINE_GREY, weight=0.75)
        _add_textbox(slide, x + 0.14 * 72, top + 0.12 * 72, card_w - 0.28 * 72, 0.24 * 72, title, font_size=13, bold=True, color=PWC_ORANGE, name="Georgia")
        body = _wrap_preserving_lines(_join_lines(lines), width=62, max_lines=20)
        _add_textbox(slide, x + 0.14 * 72, top + 0.50 * 72, card_w - 0.28 * 72, height - 0.64 * 72, body, font_size=9, color=PWC_TEXT_DARK)

    card(MARGIN_X, "Risque, impact et cause", risk_lines)
    card(MARGIN_X + card_w + gap, "Plan d'action recommandé", reco_lines)
    _sanitize_slide_palette(slide)
    _add_footer(slide, footer_label, presentation.Slides.Count)


def _add_finding_slides(presentation, finding, footer_label: str) -> None:
    priority = _safe(getattr(finding, "priority", "")).strip().lower()
    if priority == "critical":
        _add_observation_evidence_slide(presentation, finding, footer_label)
        _add_observation_risk_action_slide(presentation, finding, footer_label)
        return
    # High/Medium/Low observations are covered in the consolidated action plan
    # to keep the report close to the compact style of the reference decks.
    return


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

    def protect_deadline_column(current: list[_TableColumn]) -> list[_TableColumn]:
        if not current:
            return current
        last = current[-1]
        if "chéance" not in normalize_french(last.header).lower():
            return current
        min_deadline_w = 0.98 * 72
        if last.width >= min_deadline_w:
            return current
        delta = min_deadline_w - last.width
        adjusted = list(current)
        for index in sorted(range(len(adjusted) - 1), key=lambda idx: adjusted[idx].width, reverse=True):
            col = adjusted[index]
            min_w = 0.75 * 72 if index == 0 else 1.15 * 72
            take = min(delta, max(0.0, col.width - min_w))
            if take <= 0:
                continue
            adjusted[index] = _TableColumn(col.header, col.width - take, col.wrap_width, col.max_lines)
            delta -= take
            if delta <= 0:
                break
        adjusted[-1] = _TableColumn(last.header, min_deadline_w - max(0.0, delta), max(last.wrap_width, 14), last.max_lines)
        return adjusted

    columns = protect_deadline_column(list(columns))
    total_column_width = sum(max(1.0, col.width) for col in columns)
    if total_column_width > table_width:
        scale = table_width / total_column_width
        columns = [
            _TableColumn(
                col.header,
                max(0.45 * 72, col.width * scale),
                col.wrap_width,
                col.max_lines,
            )
            for col in columns
        ]
        columns = protect_deadline_column(columns)
        # If minimum widths pushed the total over the page, compress the last
        # non-deadline columns first. Deadline columns must stay readable.
        overflow = sum(col.width for col in columns) - table_width
        if overflow > 0 and columns:
            adjusted = list(columns)
            protected_last = "chéance" in normalize_french(adjusted[-1].header).lower()
            candidates = range(len(adjusted) - (1 if protected_last else 0))
            for index in sorted(candidates, key=lambda idx: adjusted[idx].width, reverse=True):
                col = adjusted[index]
                min_w = 0.65 * 72 if index == 0 else 1.05 * 72
                take = min(overflow, max(0.0, col.width - min_w))
                if take <= 0:
                    continue
                adjusted[index] = _TableColumn(col.header, col.width - take, col.wrap_width, col.max_lines)
                overflow -= take
                if overflow <= 0:
                    break
            if overflow > 0:
                last = adjusted[-1]
                adjusted[-1] = _TableColumn(last.header, max(0.72 * 72, last.width - overflow), last.wrap_width, last.max_lines)
            columns = adjusted

    header_h = 0.34 * 72
    min_row_h = 0.38 * 72
    line_h = 0.16 * 72
    if title == "Plan d'action consolidé":
        line_h = 0.145 * 72

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
            lines = max(lines, _wrapped_line_count(value, width=col.wrap_width))
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
                if title.startswith("Mapping observations") and index == 2:
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
                    font_size=8 if title == "Plan d'action consolidé" else 10,
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

    _add_textbox(slide, MARGIN_X, BODY_TOP - 0.02 * 72, page_w - 2 * MARGIN_X, 0.22 * 72, "Processus couverts", font_size=14, bold=True, color=PWC_ORANGE, name="Georgia")
    process_body = _wrap_preserving_lines(_join_lines(process_lines), width=120, max_lines=4)
    _add_textbox(slide, MARGIN_X, BODY_TOP + 0.24 * 72, page_w - 2 * MARGIN_X, 0.62 * 72, process_body, font_size=12, color=PWC_TEXT_DARK)

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

    table_top = BODY_TOP + 1.05 * 72
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
    page_w, _ = _page_size(presentation)
    table_left = MARGIN_X
    table_top = BODY_TOP + 0.10 * 72
    table_bottom = _content_bottom(presentation)
    table_width = page_w - 2 * MARGIN_X
    header_h = 0.38 * 72
    process_h = 0.28 * 72
    min_row_h = 0.58 * 72
    ref_w = 0.95 * 72
    control_w = 3.55 * 72
    risk_w = 1.05 * 72
    remaining_w = max(1.0, table_width - ref_w - control_w - risk_w)
    app_w = remaining_w / max(1, len(applications))
    control_wrap_width = 42
    status_wrap_width = 11
    row_vertical_padding = 0.16 * 72
    row_line_h = 0.17 * 72

    def entry_height(entry) -> float:
        control_description = _safe(getattr(entry, "control_description", ""))
        lines = _line_count(control_description, width=control_wrap_width)
        statuses = getattr(entry, "application_statuses", {}) or {}
        for application in applications:
            status = _safe(statuses.get(application, "Non testé")) or "Non testé"
            lines = max(lines, _line_count(_matrix_display_status(status), width=status_wrap_width))
        lines = max(lines, _line_count(_matrix_row_risk_label(entry), width=status_wrap_width))
        return max(min_row_h, row_vertical_padding + lines * row_line_h)

    def paginate_rows() -> list[list]:
        rows = list(getattr(data, "control_matrix", []) or [])
        if not rows:
            return [[]]

        pages: list[list] = []
        current: list = []
        current_process = ""
        used_h = header_h

        for entry in rows:
            entry_process = _safe(getattr(entry, "process", ""))
            needs_process = entry_process != current_process
            required_h = entry_height(entry) + (process_h if needs_process else 0)

            if current and used_h + required_h > table_bottom - table_top:
                pages.append(current)
                current = []
                current_process = ""
                used_h = header_h
                needs_process = True
                required_h = entry_height(entry) + process_h

            if needs_process:
                current.append(("__PROCESS__", entry_process))
                used_h += process_h
                current_process = entry_process

            current.append(("__ENTRY__", entry))
            used_h += entry_height(entry)

        if current:
            pages.append(current)
        return pages

    pages = paginate_rows()

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
                _add_rect(slide, table_left, y, table_width, process_h, fill_rgb=PWC_DARK_ORANGE, line_rgb=PWC_DARK_ORANGE, weight=0)
                _add_textbox(slide, table_left + 0.08 * 72, y + 0.04 * 72, table_width - 0.16 * 72, process_h - 0.08 * 72, _safe(payload), font_size=10, bold=True, color=PWC_WHITE, name="Georgia")
                y += process_h
                continue

            entry = payload
            current_row_h = entry_height(entry)
            x = table_left
            cells = [
                (_safe(getattr(entry, "reference", "")), ref_w, PWC_WHITE, PWC_TEXT_DARK, True, 9),
                (_wrap_text(_safe(getattr(entry, "control_description", "")), width=control_wrap_width), control_w, PWC_WHITE, PWC_TEXT_DARK, False, 8),
            ]
            statuses = getattr(entry, "application_statuses", {}) or {}
            for application in applications:
                status = _safe(statuses.get(application, "Non testé")) or "Non testé"
                display_status = _matrix_display_status(status)
                cells.append((display_status, app_w, _matrix_status_fill(status), _matrix_status_font_color(status), False, 7))

            row_risk = _matrix_row_risk_label(entry)
            risk_fill, risk_font = _priority_fill_and_font(row_risk)
            if row_risk in {"Satisfaisant", "Non testé", "Non applicable"}:
                risk_fill = _matrix_status_fill(row_risk)
                risk_font = _matrix_status_font_color(row_risk)
            cells.append((row_risk, risk_w, risk_fill, risk_font, True, 8))

            for text, width, fill_rgb, color, bold, font_size in cells:
                _add_rect(slide, x, y, width, current_row_h, fill_rgb=fill_rgb, line_rgb=PWC_LINE_GREY, weight=0.5)
                _add_textbox(slide, x + 0.04 * 72, y + 0.05 * 72, width - 0.08 * 72, current_row_h - 0.10 * 72, text, font_size=font_size, bold=bold, color=color)
                x += width
            y += current_row_h

        _sanitize_slide_palette(slide)
        _add_footer(slide, footer_label, presentation.Slides.Count)


def _truncate(text: str, max_len: int = 220) -> str:
    value = " ".join(_safe(text).replace("\r", " ").replace("\n", " ").split()).strip()
    value = value.replace("..", ".").replace(" .", ".").replace(" ,", ",")
    if len(value) <= max_len:
        return value
    cut = value[:max_len]
    last_space = cut.rfind(" ")
    if last_space > max(20, max_len // 2):
        cut = cut[:last_space]
    return cut.rstrip(" .,;:")


def _first_complete_clause(text: str, max_len: int) -> str:
    value = _clean_export_text(text)
    if len(value) <= max_len:
        return value.rstrip(" .")

    sentence_end = max(value.rfind(". ", 0, max_len + 1), value.rfind("; ", 0, max_len + 1))
    if sentence_end >= max(45, max_len // 2):
        return value[:sentence_end].strip().rstrip(" .")

    separators = [". ", "; ", " : ", " - ", ", ce qui ", ", dont ", " avec ", " afin de ", " permettant "]
    candidates: list[str] = []
    for separator in separators:
        if separator in value:
            head = value.split(separator, 1)[0].strip()
            if 35 <= len(head) <= max_len:
                candidates.append(head)

    if candidates:
        return max(candidates, key=len).rstrip(" .")
    shortened = _truncate(value, max_len).rstrip(" .")
    return _remove_dangling_tail(shortened)


def _remove_dangling_tail(text: str) -> str:
    value = _safe(text).strip().rstrip(" ,;:")
    if not value:
        return value
    dangling_patterns = [
        r"\b(?:a|à|de|des|du|d'|l'|la|le|les|un|une|et|ou|avec|sans|pour|par|sur|dans|entre|dont|leur|leurs|non)$",
        r"\b(?:mouvements de|cycle de vie des|justification des|identifiants appartenant a|identifiants appartenant à|dans le delai de|dans le délai de|en cas|tickets de fin|notamment|profils incompatibles)$",
    ]
    changed = True
    while changed:
        changed = False
        for pattern in dangling_patterns:
            match = re.search(pattern, value, flags=re.IGNORECASE)
            if match and match.end() == len(value):
                value = value[: match.start()].strip().rstrip(" ,;:")
                changed = True
    return value


def _tidy_owner_text(text: str, max_len: int = 96) -> str:
    value = _clean_export_text(text)
    if not value:
        return ""
    if len(value) <= max_len:
        return value.rstrip(" .")
    separators = [" / ", "; ", ", "]
    parts: list[str] = []
    for separator in separators:
        if separator in value:
            for part in value.split(separator):
                cleaned = part.strip()
                if cleaned and len(" / ".join(parts + [cleaned])) <= max_len:
                    parts.append(cleaned)
            if parts:
                return " / ".join(parts).rstrip(" .")
    shortened = _remove_dangling_tail(_truncate(value, max_len).rstrip(" ."))
    dangling = ("responsable", "responsables", "responsables de", "les responsable", "les responsables de", "la dsi et les responsables de")
    if shortened.lower() in dangling:
        return "Responsable a confirmer"
    return shortened


def _clean_export_text(text: str) -> str:
    value = " ".join(_safe(text).replace("\r", " ").replace("\n", " ").split()).strip()
    while ".." in value:
        value = value.replace("..", ".")
    value = value.replace(" .", ".").replace(" ,", ",")
    return normalize_french(value).strip()


def _compact_bullet(label: str, value: str, *, max_len: int) -> str:
    cleaned = _first_complete_clause(value, max_len).rstrip(".")
    if not cleaned:
        return ""
    return f"- {label}: {cleaned}"


def _compact_step_text(step: str) -> str:
    value = _clean_export_text(step)
    replacements = {
        "Action corrective immediate:": "Immediat:",
        "Action structurelle:": "Structurel:",
        "Responsable:": "Owner:",
        "Preuves attendues:": "Preuves:",
        "Mecanisme de suivi:": "Suivi:",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


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
    header = f"{_control_label(_safe(finding.reference), finding)} | {_safe(finding.application)} | Priorite {_display_priority(_safe(finding.priority))}"
    _add_textbox(
        slide,
        MARGIN_X,
        TITLE_TOP,
        11.5 * 72,
        0.34 * 72,
        header,
        font_size=20,
        bold=True,
        color=_priority_color(_safe(finding.priority)),
        name="Georgia",
    )
    if _safe(finding.reference):
        _add_textbox(slide, MARGIN_X, TITLE_TOP + 0.34 * 72, 11.5 * 72, 0.16 * 72, f"Réf. contrôle : {_safe(finding.reference)}", font_size=8, color=PWC_TEXT_GREY)

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


def _target_deadline(priority: str) -> str:
    normalized = _safe(priority).strip().lower()
    if normalized == "critical":
        return "30 jours"
    if normalized == "high":
        return "60 jours"
    if normalized == "medium":
        return "90 jours"
    return "À planifier"


def _action_plan_value(item, action_getter) -> str:
    immediate = _brief_action(action_getter(item, "immediate_action", 0), 118)
    structural = _brief_action(action_getter(item, "structural_action", 1), 128)
    if immediate and structural and immediate.lower() != structural.lower():
        return f"Immédiat: {immediate}.\nStructurel: {structural}."
    return immediate or structural or _first_complete_clause(getattr(item, "recommendation", ""), 110)


def _brief_action(text: str, max_len: int) -> str:
    value = _clean_export_text(text).rstrip(".")
    if not value:
        return ""
    rules = [
        (("désactiver", "comptes prestataires"), "Désactiver les comptes prestataires résiduels et documenter les exceptions strictement nécessaires"),
        (("désactiver", "comptes"), "Désactiver les comptes résiduels identifiés et documenter les exceptions maintenues temporairement"),
        (("rapprochement", "contrats prestataires"), "Rapprocher contrats prestataires, tickets de fin de mission et comptes actifs, avec revue des droits d'administration"),
        (("rapprochement", "rh/it"), "Formaliser un rapprochement RH/IT récurrent des comptes actifs avec délai cible et preuve de traitement"),
        (("comptes génériques",), "Revoir les comptes génériques ou privilégiés, supprimer les droits non justifiés et documenter les usages maintenus"),
        (("pam",), "Basculer vers des comptes nominatifs ou un dispositif PAM"),
        (("recertification",), "Instaurer une campagne périodique de recertification des droits sensibles avec validation métier"),
        (("mfa",), "Corriger les paramètres d'authentification et activer le MFA sur les opérations sensibles"),
        (("mots de passe",), "Aligner mots de passe, MFA, historique et verrouillage sur les exigences BCT/NIST"),
        (("restauration",), "Planifier un test de restauration ou de reprise sur le périmètre concerné et documenter les résultats"),
        (("calendrier de tests",), "Formaliser un calendrier de tests de reprise et de restauration"),
        (("correctifs",), "Prioriser les correctifs critiques en retard et formaliser les exceptions avec acceptation du risque"),
        (("patch management",), "Mettre en place un patch management fondé sur la criticité CVSS avec circuit accéléré pour les CVE critiques"),
        (("incidents",), "Centraliser les incidents ouverts, qualifier leur criticité et documenter les RCA des incidents majeurs"),
        (("itsm",), "Formaliser l'usage d'un outil ITSM pour le suivi des incidents"),
        (("sla/kpi",), "Obtenir les preuves fournisseur manquantes: SLA/KPI, comités, rapports de contrôle ou contrôles de second niveau"),
        (("preuves de contrôle fournisseur",), "Obtenir les preuves fournisseur manquantes: SLA/KPI, comités, rapports de contrôle ou contrôles de second niveau"),
        (("prestations externalisées",), "Formaliser le pilotage fournisseur avec exigences contractuelles, reporting périodique et revue documentée"),
        (("changements",), "Revoir les changements non conformes et documenter les validations, tests et risques résiduels"),
        (("mises en production",), "Bloquer les mises en production sans demande approuvée et preuve de recette"),
        (("environnements",), "Renforcer la séparation dev/recette/production, les profils incompatibles et les contrôles de dérogation"),
        (("contrôle attendu",), "Formaliser le contrôle attendu avec rôles, fréquence et critères d'exécution"),
    ]
    lowered = value.lower()
    for markers, summary in rules:
        if all(marker in lowered for marker in markers):
            return summary
    return _first_complete_clause(value, max_len)


def _build_recommendation_rows(data) -> list[tuple[str, str, str, str, str]]:
    def action_value(item, attr: str, fallback_index: int | None = None) -> str:
        value = _clean_export_text(getattr(item, attr, ""))
        if value:
            return value
        steps = [_compact_step_text(str(step)) for step in (getattr(item, "recommendation_steps", []) or []) if str(step).strip()]
        if fallback_index is not None and len(steps) > fallback_index:
            return steps[fallback_index]
        return _safe(getattr(item, "recommendation", ""))

    rows = [
        (
            _control_application_label(item),
            _tidy_owner_text(_clean_export_text(getattr(item, "owner", "")) or _clean_export_text(getattr(item, "owners", "")), 72),
            _action_plan_value(item, action_value),
            _first_complete_clause(action_value(item, "evidence_expected", 3), 92),
            _target_deadline(_safe(item.priority)),
        )
        for item in data.detailed_recommendations
    ]
    return rows


def _build_observation_action_mapping_rows(data) -> list[tuple[str, str, str, str, str, str]]:
    recommendations = {}
    for item in getattr(data, "detailed_recommendations", []) or []:
        key = (_safe(getattr(item, "reference", "")), _safe(getattr(item, "application", "")))
        recommendations[key] = item
        recommendations.setdefault((_safe(getattr(item, "reference", "")), ""), item)

    rows: list[tuple[str, str, str, str, str, str]] = []
    findings = sorted(
        list(getattr(data, "detailed_findings", []) or []),
        key=lambda item: (
            _priority_sort_value(getattr(item, "priority", "")),
            _safe(getattr(item, "reference", "")),
            _safe(getattr(item, "application", "")),
        ),
    )
    for finding in findings:
        reference = _safe(getattr(finding, "reference", ""))
        application = _clean_export_text(getattr(finding, "application", ""))
        recommendation = recommendations.get((reference, application)) or recommendations.get((reference, ""))
        owner = ""
        action = ""
        if recommendation is not None:
            owner = _tidy_owner_text(_clean_export_text(getattr(recommendation, "owner", "")) or _clean_export_text(getattr(recommendation, "owners", "")), 64)
            action = _first_complete_clause(_action_plan_value(recommendation, lambda obj, attr, _: _clean_export_text(getattr(obj, attr, ""))), 112)
        if not owner:
            owner = _tidy_owner_text(_clean_export_text(getattr(finding, "owner", "")) or _clean_export_text(getattr(finding, "owners", "")), 64)
        if not action:
            action = _first_complete_clause(_clean_export_text(getattr(finding, "recommendation", "")), 112)
        rows.append(
            (
                _safe(getattr(finding, "observation_id", "")) or reference,
                _wrap_text(_control_application_label(finding), width=48),
                _display_priority(_safe(getattr(finding, "priority", ""))),
                owner or "À confirmer",
                action or "Action à préciser",
                _target_deadline(_safe(getattr(finding, "priority", ""))),
            )
        )
    return rows or [("N/A", "Aucune observation", "-", "-", "-", "-")]


def _add_closing_slide(presentation, data, footer_label: str) -> None:
    slide = _add_blank_slide(presentation)
    page_w, page_h = _page_size(presentation)
    client = _safe(getattr(data, "client_name", "")).strip()
    year = _extract_report_year(data)

    _add_rect(slide, 0, 0, page_w, page_h, fill_rgb=PWC_DIVIDER_PEACH, line_rgb=PWC_DIVIDER_PEACH, weight=0)
    _add_textbox(slide, MARGIN_X, 1.70 * 72, page_w - 2 * MARGIN_X, 0.70 * 72, "Merci", font_size=42, bold=True, color=PWC_TEXT_DARK, name="Georgia")
    _add_rect(slide, MARGIN_X, 2.58 * 72, 2.70 * 72, 0.06 * 72, fill_rgb=PWC_ORANGE, line_rgb=PWC_ORANGE, weight=0)
    closing = "Fin du rapport"
    if client:
        closing = f"Fin du rapport - {client}"
    _add_textbox(slide, MARGIN_X, 2.90 * 72, page_w - 2 * MARGIN_X, 0.35 * 72, closing, font_size=16, color=PWC_TEXT_DARK)

    legal_year = year or "2026"
    legal = (
        f"© {legal_year} PwC. Tous droits réservés. PwC désigne le réseau PwC et/ou une ou plusieurs de ses entités membres, "
        "chacune constituant une entité juridique distincte. Ce document est strictement privé et confidentiel."
    )
    _add_textbox(slide, MARGIN_X, page_h - 1.15 * 72, page_w - 2 * MARGIN_X, 0.48 * 72, legal, font_size=8, color=PWC_TEXT_GREY)
    _sanitize_slide_palette(slide)
    _add_footer(slide, footer_label, presentation.Slides.Count)


def _prepare_presentation(powerpoint, data):
    started = time.perf_counter()
    logger.info("Opening PowerPoint template: %s", TEMPLATE_PATH)
    presentation = powerpoint.Presentations.Open(str(TEMPLATE_PATH), WithWindow=False)
    _sanitize_master_palette(presentation)
    try:
        slide_count = int(presentation.Slides.Count)
    except Exception:
        try:
            presentation.Close()
        except Exception:
            pass
        presentation = powerpoint.Presentations.Add(WithWindow=False)
        slide_count = 0

    if slide_count < 1:
        logger.warning("PowerPoint template opened with no accessible slides; creating fallback cover slide.")
        presentation.Slides.Add(1, PP_LAYOUT_BLANK)
    logger.info("PowerPoint template ready with %s slide(s) in %.1fs", slide_count, time.perf_counter() - started)

    cover_placeholders = {
        "{{REPORT_DATE}}": _build_cover_date_label(data),
        "{{CLIENT_NAME}}": _safe(data.client_name),
        "{{REPORT_TITLE}}": _safe(data.cover_title),
        "{{FOOTER_LABEL}}": _build_footer_label(data),
        "{{YEAR}}": _extract_report_year(data),
        "{{REPORT_YEAR}}": _extract_report_year(data),
    }
    cover_slide = presentation.Slides(1)
    _replace_placeholders_in_slide(cover_slide, cover_placeholders)
    _decorate_cover_slide(cover_slide, data)
    _sanitize_slide_palette(cover_slide)
    while presentation.Slides.Count > 1:
        presentation.Slides(presentation.Slides.Count).Delete()
    return presentation


def _run_export_step(label: str, operation) -> None:
    try:
        operation()
    except Exception as exc:
        raise RuntimeError(f"PowerPoint export failed while rendering '{label}': {exc}") from exc


def _generate_report_file(result: ExportReportRequest, *, output_format: str) -> BytesIO:
    data = result.structured_output
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"PowerPoint template not found: {TEMPLATE_PATH}")

    normalized_format = output_format.strip().lower()
    if normalized_format not in {"pptx", "pdf"}:
        raise ValueError(f"Unsupported export format: {output_format}")

    save_as_type = PP_SAVE_AS_OPEN_XML_PRESENTATION if normalized_format == "pptx" else PP_SAVE_AS_PDF
    temp_suffix = ".pptx" if normalized_format == "pptx" else ".pdf"

    footer_label = _build_footer_label(data)
    pythoncom.CoInitialize()
    powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
    powerpoint.Visible = 1
    presentation = None
    temp_path: Optional[Path] = None

    try:
        render_started = time.perf_counter()
        presentation = _prepare_presentation(powerpoint, data)
        logger.info("PowerPoint report rendering started")

        _add_toc_slide_v3(presentation, _build_export_toc(data), footer_label)
        _add_section_divider_slide(
            presentation,
            "Cadre de notre intervention et démarche",
            1,
            footer_label,
            "Périmètre, objectifs, intervenants et approche d'audit",
        )
        _add_text_slide_v3(presentation, "Préambule", [data.preamble], footer_label)
        _add_text_slide_v3(presentation, "Objectifs", [f"- {item}" for item in data.objectives] or [f"- {_safe(data.executive_summary)}"], footer_label)
        _add_scope_slide(presentation, data, footer_label)
        _add_intervenants_slide_v3(presentation, data, footer_label)
        _add_text_slide_v3(presentation, "Approche d'audit", [f"- {item}" for item in data.audit_approach], footer_label)
        _add_priority_methodology_slide(presentation, footer_label)

        page_w, _ = _page_size(presentation)
        table_width = page_w - 2 * MARGIN_X

        _add_control_matrix_slides(presentation, data, footer_label)
        _add_synthese_slide_v3(presentation, data, footer_label)
        _add_priorities_slide_v3(presentation, data, footer_label)
        logger.info("PowerPoint synthesis slides rendered in %.1fs", time.perf_counter() - render_started)

        _add_section_divider_slide(
            presentation,
            "Recommandations détaillées",
            3,
            footer_label,
            "Points critiques et plan d'action consolidé",
        )
        for finding in data.detailed_findings:
            _add_finding_slides(presentation, finding, footer_label)
        logger.info("PowerPoint detailed finding slides rendered in %.1fs", time.perf_counter() - render_started)

        _add_table_slides_v3(
            presentation,
            "Plan d'action consolidé",
            [
                _TableColumn("Contrôle concerné / application", 1.85 * 72, 26, 3),
                _TableColumn("Owner", 1.55 * 72, 20, 3),
                _TableColumn("Action prioritaire", 3.85 * 72, 50, 8),
                _TableColumn("Preuve attendue", 1.95 * 72, 25, 4),
                _TableColumn("Échéance", table_width - (1.85 + 1.55 + 3.85 + 1.95) * 72, 18, 1),
            ],
            _build_recommendation_rows(data),
            footer_label,
        )

        _add_section_divider_slide(
            presentation,
            "Annexes",
            4,
            footer_label,
            "Référentiel des contrôles couverts",
        )
        _add_table_slides_v3(
            presentation,
            "Liste des contrôles couverts",
            [
                _TableColumn("Réf.", 1.10 * 72, 14, 2),
                _TableColumn("Description du contrôle", table_width - (1.10 + 3.90) * 72, 68, 4),
                _TableColumn("Procédure de test", 3.90 * 72, 52, 4),
            ],
            _build_control_rows(data),
            footer_label,
        )
        _add_closing_slide(presentation, data, footer_label)
        logger.info("PowerPoint all slides rendered (%s slides) in %.1fs", presentation.Slides.Count, time.perf_counter() - render_started)

        with tempfile.NamedTemporaryFile(delete=False, suffix=temp_suffix) as temp_file:
            temp_path = Path(temp_file.name)

        logger.info("Saving PowerPoint report as %s to %s", normalized_format, temp_path)
        save_started = time.perf_counter()
        presentation.SaveAs(str(temp_path), save_as_type)
        logger.info("PowerPoint SaveAs completed in %.1fs", time.perf_counter() - save_started)
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


def build_report_pptx(result: ExportReportRequest) -> BytesIO:
    return _generate_report_file(result, output_format="pptx")


def build_report_pdf(result: ExportReportRequest) -> BytesIO:
    return _generate_report_file(result, output_format="pdf")
