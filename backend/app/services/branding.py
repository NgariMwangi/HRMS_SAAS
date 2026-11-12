"""Company-owned branding; uploaded raster logos are decoded and normalised."""
import base64
import re
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

DEFAULT_COLOR = "#4F46E5"
NEXGEN_COLOR = "#005EEB"
NEXGEN_LOGO = "data:image/svg+xml;base64," + base64.b64encode((Path(__file__).parents[1] / "assets" / "nexgen.svg").read_bytes().replace(b"\r\n", b"\n")).decode()


def normalise_logo(value):
    if value is None or value == "":
        return None
    if value == NEXGEN_LOGO:
        return value
    if not re.match(r"^data:image/(png|jpeg);base64,", value):
        raise ValueError("Use a PNG or JPEG logo")
    try:
        raw = base64.b64decode(value.split(",", 1)[1], validate=True)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Logo must be smaller than 2 MB")
        with Image.open(BytesIO(raw)) as image:
            if image.format not in {"PNG", "JPEG"} or image.width * image.height > 4_000_000:
                raise ValueError("Use a PNG or JPEG logo up to 4 million pixels")
            image.load()
            image = image.convert("RGBA")
            image.thumbnail((1024, 1024))
            result = BytesIO()
            image.save(result, format="PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(result.getvalue()).decode()
    except (UnidentifiedImageError, OSError, base64.binascii.Error, Image.DecompressionBombError) as exc:
        raise ValueError("The logo image is not valid") from exc


def company_branding(company):
    return {"theme_color": company.theme_color or DEFAULT_COLOR, "logo_data_url": company.logo_data_url}


def logo_flowable(value, max_width=150, max_height=40):
    if not value:
        return None
    if value == NEXGEN_LOGO:
        # Only the bundled, trusted SVG is parsed. User uploads are raster images.
        from xml.etree import ElementTree
        from reportlab.graphics.shapes import Drawing, Group
        from reportlab.graphics.svgpath import SvgPath
        from reportlab.lib.colors import HexColor
        drawing = Drawing(272, 55)
        group = Group()
        group.translate(0, 55)
        group.scale(1, -1)
        for element in ElementTree.fromstring(base64.b64decode(value.split(",", 1)[1])):
            group.add(SvgPath(element.attrib["d"], fillColor=HexColor(element.attrib["fill"]),
                strokeColor=HexColor(element.attrib["stroke"]) if "stroke" in element.attrib else None))
        drawing.add(group)
        scale = min(max_width / 272, max_height / 55)
        drawing.scale(scale, scale)
        drawing.width, drawing.height = 272 * scale, 55 * scale
        return drawing
    from reportlab.platypus import Image as PDFImage
    image = PDFImage(BytesIO(base64.b64decode(value.split(",", 1)[1])))
    scale = min(max_width / image.imageWidth, max_height / image.imageHeight)
    image.drawWidth, image.drawHeight = image.imageWidth * scale, image.imageHeight * scale
    return image
