from __future__ import annotations

import collections
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from xml.etree import ElementTree as ET


_NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


@dataclass(frozen=True)
class PptxAnalysis:
    path: str
    slide_size_emu: tuple[int, int]
    slide_count: int
    colors_srgb: dict[str, int]
    scheme_colors: dict[str, int]
    fonts: dict[str, int]
    font_sizes_pt: dict[str, int]
    shape_lefts_pt_bucketed: dict[str, int]
    shape_tops_pt_bucketed: dict[str, int]


def _read_xml(z: zipfile.ZipFile, name: str) -> Optional[ET.Element]:
    try:
        data = z.read(name)
    except KeyError:
        return None
    return ET.fromstring(data)


def _emu_to_pt(emu: int) -> float:
    # 1 point = 12700 EMU
    return float(emu) / 12700.0


def _bucket(value: float, step: float = 6.0) -> str:
    # Bucket positions to reduce noise (6pt buckets).
    b = round(value / step) * step
    return f"{b:.0f}"


def _bgr_int_to_rgb_hex(bgr: int) -> str:
    r = bgr & 0xFF
    g = (bgr >> 8) & 0xFF
    b = (bgr >> 16) & 0xFF
    return f"#{r:02X}{g:02X}{b:02X}"


_SRGB_RE = re.compile(r"^[0-9A-Fa-f]{6}$")


def _collect_from_slide(root: ET.Element, *, colors: collections.Counter, scheme: collections.Counter, fonts: collections.Counter, sizes: collections.Counter, lefts: collections.Counter, tops: collections.Counter) -> None:
    # Colors
    for node in root.findall(".//a:srgbClr", _NS):
        val = node.attrib.get("val")
        if val and _SRGB_RE.match(val):
            colors[val.upper()] += 1

    for node in root.findall(".//a:schemeClr", _NS):
        val = node.attrib.get("val")
        if val:
            scheme[val] += 1

    # Fonts + sizes
    for node in root.findall(".//a:rPr", _NS):
        sz = node.attrib.get("sz")  # hundredths of a point
        if sz and sz.isdigit():
            sizes[str(round(int(sz) / 100))] += 1

        latin = node.find("a:latin", _NS)
        if latin is not None:
            face = latin.attrib.get("typeface")
            if face:
                fonts[face] += 1

    # Positions (shape transforms)
    for xfrm in root.findall(".//a:xfrm", _NS):
        off = xfrm.find("a:off", _NS)
        if off is not None:
            x = off.attrib.get("x")
            y = off.attrib.get("y")
            if x and x.isdigit():
                lefts[_bucket(_emu_to_pt(int(x)))] += 1
            if y and y.isdigit():
                tops[_bucket(_emu_to_pt(int(y)))] += 1


def analyze_pptx(path: str) -> PptxAnalysis:
    pptx_path = Path(path)
    if not pptx_path.exists():
        raise FileNotFoundError(path)

    colors = collections.Counter()
    scheme = collections.Counter()
    fonts = collections.Counter()
    sizes = collections.Counter()
    lefts = collections.Counter()
    tops = collections.Counter()

    with zipfile.ZipFile(pptx_path, "r") as z:
        pres = _read_xml(z, "ppt/presentation.xml")
        if pres is None:
            raise ValueError("Invalid PPTX: missing ppt/presentation.xml")

        sldsz = pres.find("p:sldSz", _NS)
        cx = int(sldsz.attrib.get("cx", "0")) if sldsz is not None else 0
        cy = int(sldsz.attrib.get("cy", "0")) if sldsz is not None else 0

        slide_ids = pres.findall(".//p:sldId", _NS)
        slide_count = len(slide_ids)

        # Theme colors (best-effort)
        theme = _read_xml(z, "ppt/theme/theme1.xml")
        scheme_colors: dict[str, int] = {}
        if theme is not None:
            for key in ("dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6"):
                node = theme.find(f".//a:clrScheme/a:{key}", _NS)
                if node is None:
                    continue
                srgb = node.find(".//a:srgbClr", _NS)
                if srgb is not None:
                    val = srgb.attrib.get("val")
                    if val and _SRGB_RE.match(val):
                        scheme_colors[key] = int(val, 16)

        # Slides
        for i in range(1, slide_count + 1):
            slide = _read_xml(z, f"ppt/slides/slide{i}.xml")
            if slide is None:
                continue
            _collect_from_slide(slide, colors=colors, scheme=scheme, fonts=fonts, sizes=sizes, lefts=lefts, tops=tops)

    top_colors = dict(colors.most_common(30))
    top_scheme = dict(scheme.most_common(20))
    top_fonts = dict(fonts.most_common(20))
    top_sizes = dict(sizes.most_common(15))
    top_lefts = dict(lefts.most_common(15))
    top_tops = dict(tops.most_common(15))

    return PptxAnalysis(
        path=str(pptx_path),
        slide_size_emu=(cx, cy),
        slide_count=slide_count,
        colors_srgb=top_colors,
        scheme_colors={k: int(v) for k, v in scheme_colors.items()},
        fonts=top_fonts,
        font_sizes_pt=top_sizes,
        shape_lefts_pt_bucketed=top_lefts,
        shape_tops_pt_bucketed=top_tops,
    )


def to_json(analysis: PptxAnalysis) -> str:
    payload: dict[str, Any] = {
        "path": analysis.path,
        "slide_count": analysis.slide_count,
        "slide_size_emu": analysis.slide_size_emu,
        "slide_size_pt": (
            round(_emu_to_pt(analysis.slide_size_emu[0]), 2),
            round(_emu_to_pt(analysis.slide_size_emu[1]), 2),
        ),
        "colors_srgb_top": analysis.colors_srgb,
        "scheme_colors_rgb": {k: _bgr_int_to_rgb_hex(v) for k, v in analysis.scheme_colors.items()},
        "fonts_top": analysis.fonts,
        "font_sizes_pt_top": analysis.font_sizes_pt,
        "shape_lefts_pt_bucketed_top": analysis.shape_lefts_pt_bucketed,
        "shape_tops_pt_bucketed_top": analysis.shape_tops_pt_bucketed,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)

