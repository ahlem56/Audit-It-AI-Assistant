from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

ET.register_namespace("w", NS["w"])
ET.register_namespace("r", NS["r"])
ET.register_namespace("wp", NS["wp"])
ET.register_namespace("a", NS["a"])
ET.register_namespace("pic", NS["pic"])
ET.register_namespace("", NS["rel"])


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
) -> ET.Element:
    p = ET.Element(w_tag("p"))
    if style or align or spacing_before is not None or spacing_after is not None:
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
    if text:
        for index, line in enumerate(text.split("\n")):
            if index:
                r_break = ET.SubElement(p, w_tag("r"))
                ET.SubElement(r_break, w_tag("br"))
            r = ET.SubElement(p, w_tag("r"))
            if bold or size or color:
                r_pr = ET.SubElement(r, w_tag("rPr"))
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


def accent_rule() -> ET.Element:
    p = paragraph()
    p_pr = p.find("w:pPr", NS) or ET.SubElement(p, w_tag("pPr"))
    p_bdr = ET.SubElement(p_pr, w_tag("pBdr"))
    ET.SubElement(p_bdr, w_tag("bottom"), {w_tag("val"): "single", w_tag("sz"): "18", w_tag("space"): "1", w_tag("color"): "E0301E"})
    return p


def section_label(text: str) -> ET.Element:
    return paragraph(text, bold=True, size=8, color="E0301E", spacing_before=140, spacing_after=80)


def ensure_document_logo_relationship(source_files: dict[str, bytes]) -> str:
    rels_path = "word/_rels/document.xml.rels"
    relationship_id = "rIdPwcLogo"
    root = ET.fromstring(source_files[rels_path])

    for relationship in root.findall(ns_tag("rel", "Relationship")):
        if relationship.get("Target") == "media/image1.png":
            return relationship.get("Id") or relationship_id

    ET.SubElement(
        root,
        ns_tag("rel", "Relationship"),
        {
            "Id": relationship_id,
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
            "Target": "media/image1.png",
        },
    )
    source_files[rels_path] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return relationship_id


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


def build_body_children(section_properties: ET.Element | None, *, logo_relationship_id: str = "rIdPwcLogo") -> list[ET.Element]:
    children: list[ET.Element] = [
        logo_paragraph(logo_relationship_id),
        paragraph("{{ confidentiality_notice }}", align="right", size=9, color="666666", spacing_after=2600),
        section_label("RAPPORT D'AUDIT IT"),
        paragraph("{{ cover_title }}", style="Title", bold=True, size=30, color="1F1F1F", spacing_after=360),
        paragraph("{{ client_name }}", style="Subtitle", size=18, color="666666", spacing_after=2200),
        accent_rule(),
        paragraph("Période couverte", bold=True, size=9, color="E0301E", spacing_before=2500, spacing_after=40),
        paragraph("{{ report_period }}", size=13, color="444444", spacing_after=240),
        paragraph("Date d'émission", bold=True, size=9, color="E0301E", spacing_after=40),
        paragraph("{{ report_date }}", size=12, color="444444"),
        page_break(),
        paragraph("Sommaire", style="Heading1"),
        paragraph("{% for item in word_sections %}"),
        paragraph("{{ loop.index }}. {{ item }}", style="ListParagraph"),
        paragraph("{% endfor %}"),
        page_break(),
        paragraph("1. Préambule", style="Heading1"),
        paragraph("{{ preamble }}"),
        paragraph("2. Modalité et intervenants", style="Heading1"),
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
            paragraph("3. Objectifs et approche", style="Heading1"),
            paragraph("Objectifs de la mission", style="Heading2"),
            paragraph("{% for objective in objectives %}"),
            paragraph("{{ objective }}", style="ListParagraph"),
            paragraph("{% endfor %}"),
            paragraph("Approche de nos travaux d'audit informatique", style="Heading2"),
            paragraph("{% for step in audit_approach %}"),
            paragraph("{{ step }}", style="ListParagraph"),
            paragraph("{% endfor %}"),
            paragraph("4. Périmètre d'intervention", style="Heading1"),
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
            paragraph("5. Synthèse générale", style="Heading1"),
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
            paragraph("6. Points relevés", style="Heading1"),
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
            paragraph("7. Plan d'action et recommandations détaillées", style="Heading1"),
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
            paragraph("8. Annexes", style="Heading1"),
            paragraph("{% for appendix in appendices %}"),
            paragraph("{{ appendix }}", style="ListParagraph"),
            paragraph("{% endfor %}"),
            paragraph("{% endif %}"),
            paragraph("9. Conclusion", style="Heading1"),
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


def make_layout_preserving_template(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source, "r") as zin:
        source_files = {item.filename: zin.read(item.filename) for item in zin.infolist()}
    logo_relationship_id = ensure_document_logo_relationship(source_files)

    document_root = ET.fromstring(source_files["word/document.xml"])
    body = document_root.find("w:body", NS)
    if body is None:
        raise RuntimeError("word/document.xml does not contain a document body.")

    section_properties = body.find("w:sectPr", NS)
    if section_properties is not None:
        body.remove(section_properties)

    for child in list(body):
        body.remove(child)

    for child in build_body_children(section_properties, logo_relationship_id=logo_relationship_id):
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
        for p in root.findall(".//w:p", NS):
            text = paragraph_text(p)
            if "STE XYZ" in text or "2024" in text:
                updated = text.replace("STE XYZ", "{{ client_name }}").replace("2024", "{{ report_year }}")
                replace_paragraph_text(p, updated)
                xml_changed = True
        if xml_changed:
            updated_files[header_footer] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

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
