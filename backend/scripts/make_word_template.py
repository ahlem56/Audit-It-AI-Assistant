from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

from lxml import etree as ET


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

def w_tag(name: str) -> str:
    return f"{{{NS['w']}}}{name}"


def ns_tag(namespace: str, name: str) -> str:
    return f"{{{NS[namespace]}}}{name}"


def paragraph(
    text: str = "",
    *,
    style: str | None = None,
    align: str | None = None,
    bold: bool = False,
    size: int | None = None,
    color: str | None = None,
    spacing_before: int | None = None,
    spacing_after: int | None = None,
    keep_with_next: bool = False,
    page_break_before: bool = False,
) -> ET.Element:
    p = ET.Element(w_tag("p"))
    if style or align or spacing_before is not None or spacing_after is not None or keep_with_next or page_break_before:
        p_pr = ET.SubElement(p, w_tag("pPr"))
        if style:
            ET.SubElement(p_pr, w_tag("pStyle"), {w_tag("val"): style})
        if align:
            ET.SubElement(p_pr, w_tag("jc"), {w_tag("val"): align})
        if spacing_before is not None or spacing_after is not None:
            attrs = {}
            if spacing_before is not None:
                attrs[w_tag("before")] = str(spacing_before)
            if spacing_after is not None:
                attrs[w_tag("after")] = str(spacing_after)
            ET.SubElement(p_pr, w_tag("spacing"), attrs)
        if keep_with_next:
            ET.SubElement(p_pr, w_tag("keepNext"))
        if page_break_before:
            ET.SubElement(p_pr, w_tag("pageBreakBefore"))
    if text:
        for index, line in enumerate(text.split("\n")):
            if index:
                r_break = ET.SubElement(p, w_tag("r"))
                ET.SubElement(r_break, w_tag("br"))
            r = ET.SubElement(p, w_tag("r"))
            if bold or size or color:
                r_pr = ET.SubElement(r, w_tag("rPr"))
                ET.SubElement(
                    r_pr,
                    w_tag("rFonts"),
                    {
                        w_tag("ascii"): "Arial",
                        w_tag("hAnsi"): "Arial",
                        w_tag("eastAsia"): "Arial",
                        w_tag("cs"): "Arial",
                    },
                )
                if bold:
                    ET.SubElement(r_pr, w_tag("b"))
                if size:
                    ET.SubElement(r_pr, w_tag("sz"), {w_tag("val"): str(size * 2)})
                    ET.SubElement(r_pr, w_tag("szCs"), {w_tag("val"): str(size * 2)})
                if color:
                    ET.SubElement(r_pr, w_tag("color"), {w_tag("val"): color})
            t = ET.SubElement(r, w_tag("t"))
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = line
    return p


def page_break() -> ET.Element:
    p = ET.Element(w_tag("p"))
    r = ET.SubElement(p, w_tag("r"))
    ET.SubElement(r, w_tag("br"), {w_tag("type"): "page"})
    return p


def logo_paragraph(relationship_id: str, *, width_emu: int = 1450000, height_emu: int = 470000) -> ET.Element:
    p = paragraph(align="right", spacing_after=1800)
    r = ET.SubElement(p, w_tag("r"))
    drawing = ET.SubElement(r, w_tag("drawing"))
    inline = ET.SubElement(drawing, ns_tag("wp", "inline"), {"distT": "0", "distB": "0", "distL": "0", "distR": "0"})
    ET.SubElement(inline, ns_tag("wp", "extent"), {"cx": str(width_emu), "cy": str(height_emu)})
    ET.SubElement(inline, ns_tag("wp", "effectExtent"), {"l": "0", "t": "0", "r": "0", "b": "0"})
    ET.SubElement(inline, ns_tag("wp", "docPr"), {"id": "1", "name": "PwC logo"})
    ET.SubElement(inline, ns_tag("wp", "cNvGraphicFramePr"))
    graphic = ET.SubElement(inline, ns_tag("a", "graphic"))
    graphic_data = ET.SubElement(graphic, ns_tag("a", "graphicData"), {"uri": NS["pic"]})
    pic = ET.SubElement(graphic_data, ns_tag("pic", "pic"))
    nv_pic_pr = ET.SubElement(pic, ns_tag("pic", "nvPicPr"))
    ET.SubElement(nv_pic_pr, ns_tag("pic", "cNvPr"), {"id": "0", "name": "pwc-logo.png"})
    ET.SubElement(nv_pic_pr, ns_tag("pic", "cNvPicPr"))
    blip_fill = ET.SubElement(pic, ns_tag("pic", "blipFill"))
    ET.SubElement(blip_fill, ns_tag("a", "blip"), {ns_tag("r", "embed"): relationship_id})
    stretch = ET.SubElement(blip_fill, ns_tag("a", "stretch"))
    ET.SubElement(stretch, ns_tag("a", "fillRect"))
    sp_pr = ET.SubElement(pic, ns_tag("pic", "spPr"))
    xfrm = ET.SubElement(sp_pr, ns_tag("a", "xfrm"))
    ET.SubElement(xfrm, ns_tag("a", "off"), {"x": "0", "y": "0"})
    ET.SubElement(xfrm, ns_tag("a", "ext"), {"cx": str(width_emu), "cy": str(height_emu)})
    prst_geom = ET.SubElement(sp_pr, ns_tag("a", "prstGeom"), {"prst": "rect"})
    ET.SubElement(prst_geom, ns_tag("a", "avLst"))
    return p


def cover_background_paragraph(
    relationship_id: str,
    *,
    width_emu: int = 7560000,
    height_emu: int = 10692000,
) -> ET.Element:
    """Place the reference artwork behind the first-page content."""
    p = paragraph(spacing_after=0)
    r = ET.SubElement(p, w_tag("r"))
    drawing = ET.SubElement(r, w_tag("drawing"))
    anchor = ET.SubElement(
        drawing,
        ns_tag("wp", "anchor"),
        {
            "distT": "0",
            "distB": "0",
            "distL": "0",
            "distR": "0",
            "simplePos": "0",
            "relativeHeight": "0",
            "behindDoc": "1",
            "locked": "0",
            "layoutInCell": "1",
            "allowOverlap": "1",
        },
    )
    ET.SubElement(anchor, ns_tag("wp", "simplePos"), {"x": "0", "y": "0"})
    position_h = ET.SubElement(anchor, ns_tag("wp", "positionH"), {"relativeFrom": "page"})
    ET.SubElement(position_h, ns_tag("wp", "posOffset")).text = "0"
    position_v = ET.SubElement(anchor, ns_tag("wp", "positionV"), {"relativeFrom": "page"})
    ET.SubElement(position_v, ns_tag("wp", "posOffset")).text = "0"
    ET.SubElement(anchor, ns_tag("wp", "extent"), {"cx": str(width_emu), "cy": str(height_emu)})
    ET.SubElement(anchor, ns_tag("wp", "effectExtent"), {"l": "0", "t": "0", "r": "0", "b": "0"})
    ET.SubElement(anchor, ns_tag("wp", "wrapNone"))
    ET.SubElement(anchor, ns_tag("wp", "docPr"), {"id": "900", "name": "PwC cover artwork"})
    ET.SubElement(anchor, ns_tag("wp", "cNvGraphicFramePr"))
    graphic = ET.SubElement(anchor, ns_tag("a", "graphic"))
    graphic_data = ET.SubElement(graphic, ns_tag("a", "graphicData"), {"uri": NS["pic"]})
    pic = ET.SubElement(graphic_data, ns_tag("pic", "pic"))
    nv_pic_pr = ET.SubElement(pic, ns_tag("pic", "nvPicPr"))
    ET.SubElement(nv_pic_pr, ns_tag("pic", "cNvPr"), {"id": "900", "name": "pwc-cover-artwork.png"})
    ET.SubElement(nv_pic_pr, ns_tag("pic", "cNvPicPr"))
    blip_fill = ET.SubElement(pic, ns_tag("pic", "blipFill"))
    ET.SubElement(blip_fill, ns_tag("a", "blip"), {ns_tag("r", "embed"): relationship_id})
    stretch = ET.SubElement(blip_fill, ns_tag("a", "stretch"))
    ET.SubElement(stretch, ns_tag("a", "fillRect"))
    sp_pr = ET.SubElement(pic, ns_tag("pic", "spPr"))
    xfrm = ET.SubElement(sp_pr, ns_tag("a", "xfrm"))
    ET.SubElement(xfrm, ns_tag("a", "off"), {"x": "0", "y": "0"})
    ET.SubElement(xfrm, ns_tag("a", "ext"), {"cx": str(width_emu), "cy": str(height_emu)})
    prst_geom = ET.SubElement(sp_pr, ns_tag("a", "prstGeom"), {"prst": "rect"})
    ET.SubElement(prst_geom, ns_tag("a", "avLst"))
    return p


def accent_rule() -> ET.Element:
    p = paragraph()
    p_pr = p.find("w:pPr", NS) or ET.SubElement(p, w_tag("pPr"))
    p_bdr = ET.SubElement(p_pr, w_tag("pBdr"))
    ET.SubElement(p_bdr, w_tag("bottom"), {w_tag("val"): "single", w_tag("sz"): "18", w_tag("space"): "1", w_tag("color"): "E0301E"})
    return p


def section_label(text: str) -> ET.Element:
    return paragraph(text, bold=True, size=8, color="E0301E", spacing_before=140, spacing_after=80)


def numbered_heading(number: str, title: str, *, page_break_before: bool = False) -> list[ET.Element]:
    return [
        paragraph(number, bold=True, size=26, color="D04A02", spacing_after=0, page_break_before=page_break_before),
        paragraph(title, bold=True, size=19, color="2D2D2D", spacing_after=260, keep_with_next=True),
        accent_rule(),
    ]


def find_cover_artwork_relationship(source_files: dict[str, bytes]) -> str | None:
    rels_path = "word/_rels/document.xml.rels"
    root = ET.fromstring(source_files[rels_path])
    candidates: list[tuple[int, str]] = []
    for relationship in root.findall(ns_tag("rel", "Relationship")):
        if not (relationship.get("Type") or "").endswith("/image"):
            continue
        target = relationship.get("Target") or ""
        package_path = f"word/{target}".replace("word/../", "")
        payload = source_files.get(package_path)
        if payload:
            candidates.append((len(payload), relationship.get("Id") or ""))
    return max(candidates, default=(0, ""))[1] or None


def table(headers: list[str], rows: list[list[str]], *, header_fill: str = "2D2D2D") -> ET.Element:
    tbl = ET.Element(w_tag("tbl"))
    tbl_pr = ET.SubElement(tbl, w_tag("tblPr"))
    ET.SubElement(tbl_pr, w_tag("tblStyle"), {w_tag("val"): "TableGrid"})
    ET.SubElement(tbl_pr, w_tag("tblW"), {w_tag("w"): "0", w_tag("type"): "auto"})
    ET.SubElement(tbl_pr, w_tag("tblLook"), {w_tag("val"): "04A0"})
    tbl_grid = ET.SubElement(tbl, w_tag("tblGrid"))
    column_count = max(len(headers), *(len(row) for row in rows))
    column_width = str(max(1200, int(9000 / max(1, column_count))))
    for _ in range(column_count):
        ET.SubElement(tbl_grid, w_tag("gridCol"), {w_tag("w"): column_width})

    def add_row(values: list[str], *, is_header: bool = False) -> None:
        tr = ET.SubElement(tbl, w_tag("tr"))
        for value in values:
            tc = ET.SubElement(tr, w_tag("tc"))
            tc_pr = ET.SubElement(tc, w_tag("tcPr"))
            ET.SubElement(tc_pr, w_tag("tcW"), {w_tag("w"): "2400", w_tag("type"): "dxa"})
            if is_header:
                ET.SubElement(tc_pr, w_tag("shd"), {w_tag("fill"): header_fill})
            tc.append(paragraph(value, bold=is_header, color="FFFFFF" if is_header else None, size=9 if is_header else None))

    add_row(headers, is_header=True)
    for row in rows:
        add_row(row)
    return tbl


def build_body_children(section_properties: ET.Element | None, *, cover_artwork_relationship_id: str | None = None) -> list[ET.Element]:
    children: list[ET.Element] = [
        *([cover_background_paragraph(cover_artwork_relationship_id)] if cover_artwork_relationship_id else []),
        paragraph("{{ confidentiality_notice }}", align="right", bold=True, size=8, color="5A5A5A", spacing_after=1900),
        section_label("RAPPORT D'AUDIT IT"),
        paragraph("{{ cover_title }}", bold=True, size=30, color="1F1F1F", spacing_after=300),
        paragraph("{{ cover_subtitle }}", size=15, color="5A5A5A", spacing_after=180),
        paragraph("{{ client_name }}", bold=True, size=18, color="2D2D2D", spacing_after=1700),
        accent_rule(),
        paragraph("Période couverte", bold=True, size=9, color="E0301E", spacing_before=2500, spacing_after=40),
        paragraph("{{ report_period }}", size=13, color="444444", spacing_after=240),
        paragraph("Date d'émission", bold=True, size=9, color="E0301E", spacing_after=40),
        paragraph("{{ report_date }}", size=12, color="444444"),
        page_break(),
        *numbered_heading("00", "Sommaire"),
        paragraph("{% for item in word_sections %}"),
        paragraph("{{ loop.index }}. {{ item }}", style="ListParagraph"),
        paragraph("{% endfor %}"),
        page_break(),
        *numbered_heading("01", "Préambule"),
        paragraph("{{ preamble }}"),
        *numbered_heading("02", "Modalité et intervenants"),
        paragraph("{{ modality }}"),
        paragraph("{% if stakeholders %}"),
        paragraph("Interlocuteurs", style="Heading2"),
    ]

    children.append(
        table(
            ["Interlocuteur", "Fonction"],
            [
                ["{%tr for stakeholder in stakeholders %}", ""],
                ["{{ stakeholder.name }}", "{{ stakeholder.role }}"],
                ["{%tr endfor %}", ""],
            ],
        )
    )

    children.extend(
        [
            paragraph("{% endif %}"),
            *numbered_heading("03", "Objectifs et approche"),
            paragraph("Objectifs de la mission", style="Heading2"),
            paragraph("{% for objective in objectives %}"),
            paragraph("{{ objective }}", style="ListParagraph"),
            paragraph("{% endfor %}"),
            paragraph("Approche de nos travaux d'audit informatique", style="Heading2"),
            paragraph("{% for step in audit_approach %}"),
            paragraph("{{ step }}", style="ListParagraph"),
            paragraph("{% endfor %}"),
            *numbered_heading("04", "Périmètre d'intervention"),
            paragraph("{{ scope_summary }}"),
            paragraph("Applications couvertes", style="Heading2"),
            paragraph("{% for application in applications %}"),
            paragraph("{{ application }}", style="ListParagraph"),
            paragraph("{% endfor %}"),
            paragraph("Périmètre applicatif détaillé", style="Heading2"),
        ]
    )

    children.append(
        table(
            ["Application", "Description", "Système d'exploitation", "Base de données", "Prestataire"],
            [
                ["{%tr for application in application_details %}", "", "", "", ""],
                [
                    "{{ application.name }}",
                    "{{ application.description }}",
                    "{{ application.operating_system }}",
                    "{{ application.database }}",
                    "{{ application.provider }}",
                ],
                ["{%tr endfor %}", "", "", "", ""],
            ],
        )
    )

    children.extend(
        [
            page_break(),
            *numbered_heading("05", "Synthèse générale"),
            paragraph("Vue d'ensemble", style="Heading2"),
        ]
    )

    children.append(
        table(
            ["Indicateur", "Valeur", "Lecture"],
            [
                ["Observations", "{{ metrics.total_findings }}", "Constats consolidés dans le rapport"],
                ["Priorités critiques", "{{ metrics.critical_count }}", "Points nécessitant une attention immédiate"],
                ["Priorités élevées", "{{ metrics.high_count }}", "Points à planifier à court terme"],
                ["Applications couvertes", "{{ metrics.applications_count }}", "Périmètre applicatif revu"],
                ["Maturité globale", "{{ metrics.maturity_level }}", "{{ metrics.maturity_assessment }}"],
            ],
        )
    )

    children.extend(
        [
            paragraph("Synthèse exécutive", style="Heading2"),
            paragraph("{{ general_synthesis }}"),
            paragraph("{% if executive_highlights %}"),
            paragraph("Faits marquants", style="Heading2"),
            paragraph("{% for highlight in executive_highlights %}"),
            paragraph("{{ highlight }}", style="ListParagraph"),
            paragraph("{% endfor %}"),
            paragraph("{% endif %}"),
            paragraph("Répartition des constats par priorité", style="Heading2"),
        ]
    )

    children.append(
        table(
            ["Priorité", "Nombre", "Pourcentage"],
            [
                ["{%tr for item in priority_summary %}", "", ""],
                ["{{ item.priority_label }}", "{{ item.count }}", "{{ item.percentage }}%"],
                ["{%tr endfor %}", "", ""],
            ],
        )
    )

    children.extend(
        [
            paragraph("Points d'attention", style="Heading2"),
            paragraph("{% for point in watch_points %}"),
            paragraph("{{ point }}", style="ListParagraph"),
            paragraph("{% endfor %}"),
            page_break(),
            *numbered_heading("06", "Points relevés"),
            paragraph("{% for finding in detailed_findings %}"),
            paragraph("{{ loop.index }}. {{ finding.title }}", style="Heading2"),
            paragraph("{{ finding.management_summary }}", style="IntenseQuote"),
        ]
    )

    children.append(
        table(
            ["Champ", "Détail"],
            [
                ["Référence", "{{ finding.reference }}"],
                ["Domaine", "{{ finding.domain }}"],
                ["Application", "{{ finding.application }}"],
                ["Priorité", "{{ finding.priority_label }}"],
                ["Responsable", "{{ finding.owners }}"],
                ["Contrôle attendu", "{{ finding.expected_control }}"],
                ["Constat", "{{ finding.finding }}"],
                ["Risque / impact", "{{ finding.risk_impact }}"],
                ["Cause racine", "{{ finding.root_cause }}"],
                ["Recommandation", "{{ finding.recommendation }}"],
                ["Commentaire auditeur", "{{ finding.auditor_comment }}"],
            ],
        )
    )

    children.extend(
        [
            paragraph("{% endfor %}"),
            page_break(),
            *numbered_heading("07", "Plan d'action et recommandations détaillées"),
        ]
    )

    children.append(
        table(
            ["Réf.", "Application", "Priorité", "Responsable", "Action recommandée"],
            [
                ["{%tr for recommendation in detailed_recommendations %}", "", "", "", ""],
                [
                    "{{ recommendation.reference }}",
                    "{{ recommendation.application }}",
                    "{{ recommendation.priority_label }}",
                    "{{ recommendation.owners }}",
                    "{{ recommendation.recommendation }}",
                ],
                ["{%tr endfor %}", "", "", "", ""],
            ],
        )
    )

    children.extend(
        [
            paragraph("{% if appendices %}"),
            *numbered_heading("08", "Annexes", page_break_before=True),
            paragraph("{% for appendix in appendices %}"),
            paragraph("{{ appendix }}", style="ListParagraph"),
            paragraph("{% endfor %}"),
            paragraph("{% endif %}"),
            *numbered_heading("09", "Conclusion", page_break_before=True),
            paragraph("{{ conclusion }}"),
        ]
    )

    if section_properties is not None:
        children.append(section_properties)
    return children


def paragraph_text(paragraph_element: ET.Element) -> str:
    return "".join(text_node.text or "" for text_node in paragraph_element.findall(".//w:t", NS))


def replace_paragraph_text(paragraph_element: ET.Element, new_text: str) -> None:
    runs = paragraph_element.findall(".//w:r", NS)
    if not runs:
        run = ET.SubElement(paragraph_element, w_tag("r"))
        text_node = ET.SubElement(run, w_tag("t"))
        text_node.text = new_text
        return

    first_text_written = False
    for run in runs:
        text_nodes = run.findall(".//w:t", NS)
        for text_node in text_nodes:
            if not first_text_written:
                text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                text_node.text = new_text
                first_text_written = True
            else:
                text_node.text = ""


def make_rebuilt_template(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source, "r") as zin:
        source_files = {item.filename: zin.read(item.filename) for item in zin.infolist()}
    cover_artwork_relationship_id = find_cover_artwork_relationship(source_files)

    document_root = ET.fromstring(source_files["word/document.xml"])
    body = document_root.find("w:body", NS)
    if body is None:
        raise RuntimeError("word/document.xml does not contain a document body.")

    section_properties = body.find("w:sectPr", NS)
    if section_properties is not None:
        body.remove(section_properties)

    for child in list(body):
        body.remove(child)

    for child in build_body_children(
        section_properties,
        cover_artwork_relationship_id=cover_artwork_relationship_id,
    ):
        body.append(child)

    updated_files = dict(source_files)
    updated_files["word/document.xml"] = ET.tostring(document_root, encoding="utf-8", xml_declaration=True)

    for header_footer in (
        "word/header1.xml",
        "word/header2.xml",
        "word/header3.xml",
        "word/footer1.xml",
        "word/footer2.xml",
        "word/footer3.xml",
    ):
        if header_footer not in updated_files:
            continue
        root = ET.fromstring(updated_files[header_footer])
        xml_changed = False
        dynamic_header_written = False
        for p in root.findall(".//w:p", NS):
            text = paragraph_text(p)
            if header_footer.startswith("word/header") and text.strip():
                updated = "Rapport d'audit IT — {{ client_name }} | {{ report_year }}" if not dynamic_header_written else ""
                dynamic_header_written = True
                replace_paragraph_text(p, updated)
                xml_changed = True
            elif "STE XYZ" in text or "2024" in text:
                updated = text.replace("STE XYZ", "{{ client_name }}").replace("2024", "{{ report_year }}")
                replace_paragraph_text(p, updated)
                xml_changed = True
        if xml_changed:
            updated_files[header_footer] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for filename, payload in updated_files.items():
            zout.writestr(filename, payload)


def _replace_text_nodes(container: ET.Element, new_text: str) -> None:
    text_nodes = container.findall(".//w:t", NS)
    if not text_nodes:
        paragraph_element = container.find(".//w:p", NS)
        if paragraph_element is None and container.tag == w_tag("p"):
            paragraph_element = container
        if paragraph_element is not None:
            replace_paragraph_text(paragraph_element, new_text)
        return
    for index, text_node in enumerate(text_nodes):
        text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        text_node.text = new_text if index == 0 else ""


def _populate_empty_textbox(textbox: ET.Element, text: str, *, size: int = 36) -> None:
    paragraph_element = textbox.find(".//w:p", NS)
    if paragraph_element is None:
        paragraph_element = ET.SubElement(textbox, w_tag("p"))
    run = ET.SubElement(paragraph_element, w_tag("r"))
    run_properties = ET.SubElement(run, w_tag("rPr"))
    ET.SubElement(
        run_properties,
        w_tag("rFonts"),
        {
            w_tag("ascii"): "Arial",
            w_tag("hAnsi"): "Arial",
            w_tag("eastAsia"): "Arial",
            w_tag("cs"): "Arial",
        },
    )
    ET.SubElement(run_properties, w_tag("color"), {w_tag("val"): "2D2D2D"})
    ET.SubElement(run_properties, w_tag("sz"), {w_tag("val"): str(size)})
    ET.SubElement(run_properties, w_tag("szCs"), {w_tag("val"): str(size)})
    text_node = ET.SubElement(run, w_tag("t"))
    text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = text


def make_layout_preserving_template(source: Path, destination: Path) -> None:
    """Turn the supplied PwC report into a dynamic template without removing artwork.

    The reference document builds its visual identity from anchored DrawingML and
    VML shapes. Rebuilding the body discards those shapes, so this path deliberately
    keeps the complete package and edits only text inside the existing containers.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source, "r") as zin:
        source_files = {item.filename: zin.read(item.filename) for item in zin.infolist()}

    root = ET.fromstring(source_files["word/document.xml"])

    textbox_replacements = {
        "Détection de Fraude Financiere": "{{ cover_client }}",
        "Taux de fraudes : {{taux_de_fraudes}}": "Constats prioritaires : {{ priority_findings_count }}",
        "Anomalies détectées : {{anomalies_détéctées}}": "Total des constats : {{ total_findings_count }}",
        "Transactions analysées : {{transactions_analysées}}": "Applications couvertes : {{ applications_count }}",
        "Montant exposé : {{montant_exposé}}": "Maturité globale : {{ maturity_level }}",
        "Faible : {{pourcentage_faible}}": "Faible : {{ low_percentage }}",
        "Elevé : {{pourcentage_elevé}}": "Élevée : {{ high_percentage }}",
        "Critique : {{pourcentage_critique}}": "Critique : {{ critical_percentage }}",
    }
    textboxes = root.findall(".//w:txbxContent", NS)
    for textbox_index, textbox in enumerate(textboxes):
        text = " ".join(paragraph_text(textbox).split())
        if text == "D’audit":
            _replace_text_nodes(textbox, "D’audit ITGC")
            continue
        if textbox_index in {3, 9} and not text:
            _populate_empty_textbox(textbox, "{{ cover_subject }}", size=36)
            continue
        replacement = textbox_replacements.get(text)
        if replacement is not None:
            _replace_text_nodes(textbox, replacement)

    paragraph_replacements = {
        "Résumé exécutif": "Synthèse générale",
        "Analyse visuelle des résultats": "Analyse des risques et du périmètre",
        "Transactions prioritaires à contrôler": "Points relevés",
        "Fiche de cas – Alertes Critiques": "Fiches de constats prioritaires",
        "Recommandations pour l’auditeur": "Plan d'action et recommandations",
        "Glossaire – Termes Techniques Expliqués": "Annexes et méthodologie",
        "01 Résumé exécutif": "01 Synthèse générale",
        "02 Analyse visuelle des résultats": "02 Analyse des risques et du périmètre",
        "03 Transactions prioritaires à contrôler": "03 Points relevés",
        "04 Fiche de cas – Alertes Critiques": "04 Fiches de constats prioritaires",
        "05 Recommandations pour l’auditeur": "05 Plan d'action et recommandations",
        "06 Glossaire – Termes Techniques Expliqués": "06 Annexes et méthodologie",
        "Réparation des transactions :": "Répartition des constats :",
        "Niveau de risque détecté :": "Niveau de priorité détecté :",
        "Exposition financière par type d’opération (kTND) :": "Exposition au risque par domaine :",
        "{{transaction_text}}": "{{r transaction_text }}",
        "{{reparation_transactions_graphes}}": "{{r priority_chart }}",
        "{{niveau_risque_graphes}}": "{{r risk_level_chart }}",
        "{{exposition_financière_graphes}}": "{{r domain_chart }}",
        "{{recommendations_text}}": "{{r recommendations_text }}",
        "{{glossaire_ text }}": "{{r glossary_text }}",
    }
    body_paragraphs = root.findall(".//w:body/w:p", NS)
    for body_paragraph in body_paragraphs:
        if body_paragraph.find(".//w:drawing", NS) is not None or body_paragraph.find(".//w:pict", NS) is not None:
            continue
        direct_text_nodes = body_paragraph.findall(".//w:t", NS)
        text = " ".join("".join(node.text or "" for node in direct_text_nodes).split())
        replacement = paragraph_replacements.get(text)
        if replacement is not None:
            _replace_text_nodes(body_paragraph, replacement)

    # The original critical-case page intentionally contains an empty content
    # area. Reuse its first empty paragraph for the dynamic priority case cards.
    for index, body_paragraph in enumerate(body_paragraphs):
        text = "".join(node.text or "" for node in body_paragraph.findall(".//w:t", NS)).strip()
        if text == "04 Fiches de constats prioritaires":
            for candidate in body_paragraphs[index + 1 :]:
                candidate_text = "".join(candidate.itertext()).strip()
                if not candidate_text:
                    replace_paragraph_text(candidate, "{{r critical_case_text }}")
                    break

    # The reference ends with a standalone legal artwork page. The generated
    # report already carries a compact legal/page footer, so retaining that page
    # creates two visually empty pages once dynamic content reflows.
    body = root.find("w:body", NS)
    glossary_paragraph = next(
        (
            paragraph_element
            for paragraph_element in body_paragraphs
            if "{{r glossary_text }}" in paragraph_text(paragraph_element)
        ),
        None,
    )
    if body is not None and glossary_paragraph is not None:
        glossary_index = list(body).index(glossary_paragraph)
        for trailing_element in list(body)[glossary_index + 1 :]:
            if trailing_element.tag != w_tag("sectPr"):
                body.remove(trailing_element)

    updated_files = dict(source_files)
    for header_path in ("word/header1.xml", "word/header2.xml", "word/header3.xml"):
        if header_path not in updated_files:
            continue
        header_root = ET.fromstring(updated_files[header_path])
        for header_paragraph in header_root.findall(".//w:p", NS):
            if paragraph_text(header_paragraph).strip():
                replace_paragraph_text(
                    header_paragraph,
                    "Rapport d'audit ITGC — {{ client_name }} | {{ report_year }}",
                )
                break
        updated_files[header_path] = ET.tostring(header_root, encoding="utf-8", xml_declaration=True)

    updated_files["word/document.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for filename, payload in updated_files.items():
            zout.writestr(filename, payload)


def make_simplified_template(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)

    with zipfile.ZipFile(source, "r") as zin:
        document_xml = zin.read("word/document.xml")
        source_files = {item.filename: zin.read(item.filename) for item in zin.infolist() if item.filename != "word/document.xml"}

    root = ET.fromstring(document_xml)
    body = root.find("w:body", NS)
    if body is None:
        raise RuntimeError("word/document.xml does not contain a document body.")

    section_properties = body.find("w:sectPr", NS)
    if section_properties is not None:
        body.remove(section_properties)

    for child in list(body):
        body.remove(child)

    for child in build_body_children(section_properties):
        body.append(child)

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for filename, payload in source_files.items():
            zout.writestr(filename, payload)
        zout.writestr("word/document.xml", ET.tostring(root, encoding="utf-8", xml_declaration=True))


def make_template(source: Path, destination: Path, *, simplified: bool = False) -> None:
    if simplified:
        make_simplified_template(source, destination)
    else:
        make_layout_preserving_template(source, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a docxtpl-compatible Word report template from the PwC static template.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument(
        "--simplified",
        action="store_true",
        help="Rebuild a compact generic template instead of preserving the original PwC layout.",
    )
    args = parser.parse_args()

    make_template(args.source, args.destination, simplified=args.simplified)
    print(f"Created dynamic Word template: {args.destination}")


if __name__ == "__main__":
    main()
