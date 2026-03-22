from __future__ import annotations

import base64
from io import BytesIO

import qrcode
from qrcode.constants import ERROR_CORRECT_M
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer


def build_styled_qr_data_url(content: str, size: int) -> str:
    normalized = str(content or "").strip()
    if not normalized:
        return ""

    image = build_styled_qr_image(normalized, size)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_styled_qr_image(content: str, size: int):
    target_size = max(96, int(size))

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(content)
    qr.make(fit=True)

    image = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(radius_ratio=0.4),
    ).convert("RGBA")

    return image.resize((target_size, target_size))
