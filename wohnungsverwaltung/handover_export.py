"""Immutable, private handover documents. No network resources are rendered."""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import reportlab
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import reverse
from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as PDFImage
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate

from .forms import ACCEPTANCE_STATUS_LABELS, HANDOVER_STATUS_LABELS, HANDOVER_TYPE_LABELS
from .models import Protokoll, ProtokollStatus, ProtokollTyp, ProtokollUnterschrift

SALT = "handover-final-content-v1"
DECLARATIONS = [
    "Die Schlüsselübergabe wurde einschließlich fehlender Schlüssel geprüft.",
    "Die Angaben entsprechen nach bestem Wissen dem tatsächlichen Zustand der Mieträume.",
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def display(value):
    if value is None or value == "":
        return "Nicht angegeben"
    if isinstance(value, bool):
        return "Ja" if value else "Nein"
    if isinstance(value, datetime):
        return value.astimezone(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y %H:%M:%S %Z")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, Decimal):
        return str(value).replace(".", ",")
    return str(value)


def employee_name(user):
    try:
        name = str(user.person_profile).strip()
    except AttributeError:
        name = ""
    return name or user.get_full_name().strip()


def load_protocol(pk):
    return (
        Protokoll.objects.select_related("wohnung", "person")
        .prefetch_related(
            "protokoll_schluessel", "raeume__raum_merkmale__merkmal", "raeume__raum_merkmale__fotos"
        )
        .get(pk=pk)
    )


def _section(title, values):
    return {"title": title, "rows": [[label, display(value)] for label, value in values]}


def _side(item, label):
    if item is None:
        return {"label": label, "text": "Kein Gegenstück erfasst", "details": [], "photos": []}
    value = item.wert if isinstance(item.wert, dict) else {}
    photos = []
    for photo in sorted(item.fotos.all(), key=lambda p: (p.created_at, str(p.pk))):
        with photo.datei.open("rb") as stream:
            checksum = digest(stream.read())
        photos.append(
            {
                "path": photo.datei.name,
                "sha256": checksum,
                "url": reverse(
                    "wohnungsverwaltung:handover_protocol_checklist_item_photo_view",
                    args=[
                        item.raumprotokoll.protokoll_id,
                        item.raumprotokoll_id,
                        item.pk,
                        photo.pk,
                    ],
                ),
            }
        )
    details = value.get("angaben", {})
    return {
        "label": label,
        "text": str(value.get("text", "")),
        "details": [[str(k), display(v)] for k, v in sorted(details.items())],
        "photos": photos,
    }


def build_snapshot(protocol, name=""):
    # Shared selection rule, including the explicitly documented chronological fallback.
    from .views import _move_in_reference_for_apartment

    reference = None
    if protocol.protokoll_typ == ProtokollTyp.MOVE_OUT:
        reference = _move_in_reference_for_apartment(
            protocol.wohnung_id, before=protocol.uebergabe_zeitpunkt, person_id=protocol.person_id
        )
    sections = [
        _section(
            "Zuordnung",
            [
                ("Protokoll", protocol.pk),
                (
                    "Wohnung",
                    f"Gebäude {protocol.wohnung.gebaeudenummer}, "
                    f"Wohnung {protocol.wohnung.wohnungsnummer}",
                ),
                ("Etage", protocol.wohnung.etage),
                ("Mieter", str(protocol.person)),
                ("Vertretung des Unternehmens", name or protocol.vermieter_name),
                ("Übergabetyp", HANDOVER_TYPE_LABELS[protocol.protokoll_typ]),
                ("Übergabezeitpunkt", protocol.uebergabe_zeitpunkt),
                ("Übergabezustand", HANDOVER_STATUS_LABELS[protocol.uebergabe_status]),
                ("Abnahme", ACCEPTANCE_STATUS_LABELS[protocol.abnahme_status]),
            ],
        )
    ]
    meter_values = []
    for suffix, label in [
        ("wasser_kalt", "Kaltwasser"),
        ("wasser_warm", "Warmwasser"),
        ("heizung", "Heizung"),
        ("strom", "Strom"),
    ]:
        current = getattr(protocol, f"zaehlerstand_{suffix}")
        meter_values.extend(
            [
                (f"{label}: Nummer", getattr(protocol, f"zaehlernummer_{suffix}")),
                (f"{label}: Stand", current),
            ]
        )
        if reference:
            old = getattr(reference, f"zaehlerstand_{suffix}")
            meter_values.extend(
                [
                    (f"{label}: Einzugsnummer", getattr(reference, f"zaehlernummer_{suffix}")),
                    (f"{label}: Einzugsstand", old),
                    (f"{label}: Differenz Auszug minus Einzug", current - old),
                ]
            )
    meter_values.append(("Heizungsablesungen", protocol.heizungsablesungen))
    if reference:
        meter_values.append(("Heizungsablesungen Einzug", reference.heizungsablesungen))
    sections.append(_section("Zähler", meter_values))
    if protocol.protokoll_typ == ProtokollTyp.MOVE_IN:
        sections.append(
            _section(
                "Nachweise",
                [
                    ("Kautionsbeleg vorhanden", protocol.kaution_nachweis_vorhanden),
                    ("Erste Miete: Beleg vorhanden", protocol.erste_miete_nachweis_vorhanden),
                ],
            )
        )
    else:
        sections.append(
            _section(
                "Auszug",
                [
                    ("Zukünftige Anschrift", protocol.mieter_zukuenftige_anschrift),
                    ("Nachbesserungen", protocol.nachbesserung_beschreibung),
                    ("Frist", protocol.nachbesserung_bis),
                    (
                        "Einzugsreferenz",
                        f"{reference.pk}, {display(reference.uebergabe_zeitpunkt)}"
                        if reference
                        else "Keine Einzugsreferenz vorhanden",
                    ),
                ],
            )
        )
    if protocol.anlagenblaetter_anzahl:
        sections.append(
            _section(
                "Historische Zusatzangabe",
                [
                    (
                        "Erfasste Anlagenblattanzahl (Dateien nicht hinterlegt)",
                        protocol.anlagenblaetter_anzahl,
                    )
                ],
            )
        )
    for index, key in enumerate(
        sorted(protocol.protokoll_schluessel.all(), key=lambda k: (k.raum_bezeichnung, str(k.pk))),
        1,
    ):
        sections.append(
            _section(
                f"Schlüsselposition {index}",
                [
                    ("Raum / Bezeichnung", key.raum_bezeichnung),
                    ("Anzahl", key.anzahl),
                    ("Aufschrift", key.aufschrift),
                    ("Nummer", key.schluesselnummer),
                    ("Fehlt", key.fehlt),
                    ("Fehlgrund", key.fehlgrund),
                    ("Nachlieferung", key.nachlieferung_am),
                ],
            )
        )
    rooms = {str(r.raum_id): r for r in protocol.raeume.all()}
    old_rooms = {str(r.raum_id): r for r in reference.raeume.all()} if reference else {}
    groups = []
    for room_id in sorted(
        rooms.keys() | old_rooms.keys(),
        key=lambda pk: ((rooms.get(pk) or old_rooms[pk]).name, pk),
    ):
        room, old_room = rooms.get(room_id), old_rooms.get(room_id)
        current = {str(i.merkmal_id): i for i in room.raum_merkmale.all()} if room else {}
        old = {str(i.merkmal_id): i for i in old_room.raum_merkmale.all()} if old_room else {}
        items = []
        for feature_id in sorted(
            current.keys() | old.keys(),
            key=lambda pk: (
                (current.get(pk) or old[pk]).merkmal.bereich,
                (current.get(pk) or old[pk]).merkmal.bezeichnung,
                pk,
            ),
        ):
            item = current.get(feature_id) or old[feature_id]
            sides = []
            if protocol.protokoll_typ == ProtokollTyp.MOVE_OUT:
                sides.append(_side(old.get(feature_id), "Einzug (Referenz)"))
            sides.append(
                _side(current.get(feature_id), HANDOVER_TYPE_LABELS[protocol.protokoll_typ])
            )
            items.append(
                {"title": f"{item.merkmal.bereich}: {item.merkmal.bezeichnung}", "sides": sides}
            )
        groups.append({"title": (room or old_room).name, "items": items})
    return {
        "version": 1,
        "protocol_id": str(protocol.pk),
        "employee": name,
        "tenant": str(protocol.person).strip(),
        "sections": sections,
        "rooms": groups,
        "declarations": DECLARATIONS,
        "reference_id": str(reference.pk) if reference else None,
    }


def fingerprint(snapshot):
    return digest(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode())


def content_token(snapshot, user):
    return signing.dumps({"hash": fingerprint(snapshot), "user": user.pk}, salt=SALT)


def token_matches(token, snapshot, user):
    try:
        data = signing.loads(token, salt=SALT)
    except signing.BadSignature:
        return False
    return data == {"hash": fingerprint(snapshot), "user": user.pk}


def clean_signature(upload):
    if not upload or upload.size > 512 * 1024:
        raise ValidationError("Bitte unterschreiben Sie im Zeichenfeld (maximal 512 KiB).")
    try:
        with Image.open(upload) as image:
            if image.format != "PNG" or image.size != (1200, 400):
                raise ValueError
            image.load()
            white = Image.new("RGBA", image.size, "white")
            white.alpha_composite(image.convert("RGBA"))
            rgb = white.convert("RGB")
            difference = ImageChops.difference(rgb, Image.new("RGB", image.size, "white"))
            # Reject an empty canvas and insignificant single-pixel payloads.
            visible = difference.convert("L").point(lambda p: 255 if p > 30 else 0)
            if sum(visible.histogram()[1:]) < 100:
                raise ValueError
            out = BytesIO()
            rgb.save(out, "PNG")
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise ValidationError(
            "Die Unterschrift fehlt oder ist kein gültiges PNG-Zeichenfeld."
        ) from error


def _image(data, max_width=170 * mm, max_height=85 * mm):
    with Image.open(BytesIO(data)) as original:
        original.load()
        normalized = ImageOps.exif_transpose(original).convert("RGB")
        normalized.thumbnail((2000, 1600))
        stream = BytesIO()
        normalized.save(stream, "PNG")
        width, height = normalized.size
    scale = min(max_width / width, max_height / height)
    stream.seek(0)
    return PDFImage(stream, width=width * scale, height=height * scale)


def render_pdf(snapshot, signatures):
    fonts = Path(reportlab.__file__).parent / "fonts"
    if "Handover" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Handover", str(fonts / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("HandoverBold", str(fonts / "VeraBd.ttf")))
        pdfmetrics.registerFontFamily("Handover", normal="Handover", bold="HandoverBold")
    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "HandoverText",
        parent=styles["Normal"],
        fontName="Handover",
        fontSize=10,
        leading=15,
        spaceAfter=6,
    )
    heading = ParagraphStyle(
        "HandoverHeading",
        parent=normal,
        fontName="HandoverBold",
        fontSize=14,
        leading=19,
        spaceBefore=12,
        keepWithNext=True,
    )
    title = ParagraphStyle("HandoverTitle", parent=heading, fontSize=20, leading=26)

    def paragraph(text, style=normal):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)

    story = [
        paragraph("Übergabeprotokoll", title),
        paragraph(f"STEImmo · {snapshot['protocol_id']}"),
    ]
    archive = snapshot["archive"]
    if archive["legacy"]:
        story.append(
            paragraph(
                "Nachträglich gesicherter Stand: Zwischenzeitliche Stammdatenänderungen "
                "sind nicht rekonstruierbar. Historische Unterschriften wurden nicht erfasst."
            )
        )
    for section in snapshot["sections"]:
        story.append(paragraph(section["title"], heading))
        story.extend(paragraph(f"{key}: {value}") for key, value in section["rows"])
    for room in snapshot["rooms"]:
        story.append(paragraph(f"Raum: {room['title']}", heading))
        for item in room["items"]:
            story.append(paragraph(item["title"], heading))
            for side in item["sides"]:
                story.append(paragraph(side["label"], heading))
                # Separate explicit lines so heading keep-with-next never moves an
                # entire multi-page finding onto a mostly empty following page.
                story.extend(paragraph(line) for line in side["text"].splitlines())
                story.extend(paragraph(f"{k}: {v}") for k, v in side["details"])
                for index, photo in enumerate(side["photos"], 1):
                    with default_storage.open(photo["path"], "rb") as source:
                        data = source.read()
                    if digest(data) != photo["sha256"]:
                        raise OSError("Foto wurde zwischenzeitlich verändert.")
                    story.append(
                        KeepTogether(
                            [
                                _image(data),
                                paragraph(
                                    f"{room['title']} / {item['title']} / "
                                    f"{side['label']} / Foto {index}"
                                ),
                            ]
                        )
                    )
    story.append(PageBreak())
    story.append(paragraph("Bestätigung und Unterschriften", heading))
    for label, key in [("Bestätigt am", "confirmed"), ("Gesichert am", "secured")]:
        story.append(paragraph(f"{label}: {archive[key]}"))
    for declaration, checked in zip(snapshot["declarations"], archive["checks"], strict=True):
        story.append(paragraph(f"{'Bestätigt' if checked else 'Nicht erfasst'}: {declaration}"))
    for role, label in [("mitarbeiter", "Mitarbeiter"), ("mieter", "Mieter")]:
        if role in signatures:
            value = signatures[role]
            story.append(
                KeepTogether(
                    [
                        paragraph(f"{label}: {value['name']}", heading),
                        _image(value["data"], max_width=140 * mm, max_height=47 * mm),
                        paragraph(f"Erfasst beim Abschluss: {archive['secured']}"),
                    ]
                )
            )
        elif role == "mieter" and not archive["legacy"]:
            story.extend(
                [
                    paragraph("Mieter hat nicht unterschrieben", heading),
                    paragraph(archive["reason"]),
                ]
            )
        else:
            story.append(paragraph(f"{label}: Keine historische Unterschrift erfasst"))
    output = BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Handover", 8)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(20 * mm, 12 * mm, f"STEImmo · {snapshot['protocol_id']}")
        canvas.drawRightString(190 * mm, 12 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(
        output,
        pagesize=(210 * mm, 297 * mm),
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title="Übergabeprotokoll",
        author="STEImmo",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def archive_protocol(
    protocol, snapshot, signatures, now, stored_paths, *, legacy=False, reason="", user=None
):
    snapshot["archive"] = {
        "legacy": legacy,
        "secured": display(now),
        "confirmed": display(protocol.bestaetigt_am if legacy else now),
        "reason": reason,
        "checks": [protocol.schluessel_ueberprueft, protocol.bestaetigung_erklaert]
        if legacy
        else [True, True],
    }
    pdf = render_pdf(snapshot, signatures)
    prefix = f"private/handovers/{protocol.pk}/{uuid4().hex}"
    for role, value in signatures.items():
        path = default_storage.save(f"{prefix}/{role}.png", ContentFile(value["data"]))
        stored_paths.append(path)
        ProtokollUnterschrift.objects.create(
            protokoll=protocol,
            rolle=role,
            name=value["name"],
            datei=path,
            hash_sha256=digest(value["data"]),
            erfasst_am=now,
        )
    path = default_storage.save(f"{prefix}/protokoll.pdf", ContentFile(pdf))
    stored_paths.append(path)
    protocol.export_snapshot = snapshot
    protocol.dokument_pfad = path
    protocol.dokument_hash_sha256 = digest(pdf)
    protocol.gesichert_am = now
    protocol.nachtraeglich_gesichert = legacy
    if not legacy:
        protocol.vermieter_name = snapshot["employee"]
        protocol.bestaetigt_am = now
        protocol.status = ProtokollStatus.SIGNED
        protocol.schluessel_ueberprueft = True
        protocol.bestaetigung_erklaert = True
        protocol.abgeschlossen_von = user
        protocol.mieter_unterschrift_fehlt_grund = reason
    protocol.save()
