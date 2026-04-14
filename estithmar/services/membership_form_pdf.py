"""Membership application PDF — same HTML as the print page, rendered via Playwright; FPDF fallback."""
from __future__ import annotations

import base64
import logging
import os
import time

from fpdf import FPDF

from estithmar.config import resolve_static_folder
from estithmar.models import Member, get_or_create_settings

logger = logging.getLogger(__name__)

_NAVY = (30, 68, 113)
_BLUE = (0, 74, 153)
_GREEN = (59, 181, 74)
_TEXT = (51, 51, 51)


def _safe_pdf_text(s: str | None) -> str:
    if s is None:
        return ""
    return "".join(c if 32 <= ord(c) < 127 or c in "\t\n" else "?" for c in str(s))


def _logo_relative_static_path() -> str:
    ex = get_or_create_settings().get_extra()
    lt = ex.get("logo_light")
    if isinstance(lt, str) and lt.strip() and ".." not in lt and "://" not in lt:
        return lt.replace("\\", "/").strip().lstrip("/")
    return "assets/images/logo-light.png"


def _logo_path() -> str | None:
    ex = get_or_create_settings().get_extra()
    lt = ex.get("logo_light")
    base = resolve_static_folder()
    candidates: list[str] = []
    if isinstance(lt, str) and lt.strip() and ".." not in lt and "://" not in lt:
        rel = lt.replace("\\", "/").strip().lstrip("/")
        candidates.append(os.path.join(base, rel.replace("/", os.sep)))
    candidates.append(os.path.join(base, "assets", "images", "logo-light.png"))
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def _logo_data_uri() -> str | None:
    """Embed logo in HTML so PDF render does not depend on HTTP to this app."""
    p = _logo_path()
    if not p or not os.path.isfile(p):
        return None
    ext = os.path.splitext(p)[1].lower().lstrip(".")
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(ext, "image/png")
    with open(p, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _gender_label(member: Member) -> str:
    g = (member.gender or "").strip().lower()
    if g == "male":
        return "Male"
    if g == "female":
        return "Female"
    return ""


def _dob(member: Member) -> str:
    if not member.date_of_birth:
        return ""
    return member.date_of_birth.strftime("%d %B %Y")


def _field_block(pdf: FPDF, x: float, y: float, usable_w: float, label: str, val: str | None) -> float:
    pdf.set_font("Helvetica", "B", 9.5)
    lab = label + ": "
    w_lab = pdf.get_string_width(lab)
    pdf.set_xy(x, y)
    pdf.cell(w_lab, 5, _safe_pdf_text(lab), ln=0)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*_TEXT)
    vx = x + w_lab
    vw = usable_w - w_lab
    pdf.set_xy(vx, y)
    pdf.multi_cell(vw, 5.2, _safe_pdf_text(val or ""), border="B")
    pdf.set_text_color(0, 0, 0)
    return pdf.get_y() + 2.5


def _section_title(pdf: FPDF, x: float, y: float, usable_w: float, title: str) -> float:
    pdf.set_fill_color(*_GREEN)
    pdf.rect(x, y + 0.8, 1.4, 5.5, "F")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*_NAVY)
    pdf.set_xy(x + 4, y)
    pdf.cell(usable_w - 4, 6.5, _safe_pdf_text(title), ln=1)
    pdf.set_text_color(0, 0, 0)
    return pdf.get_y() + 4


def _row_dob_gender(pdf: FPDF, x: float, y: float, uw: float, member: Member) -> float:
    gap = 5
    col_w = (uw - gap) / 2
    pdf.set_font("Helvetica", "B", 9.5)
    lab = "Date of Birth: "
    w_l = pdf.get_string_width(lab)
    pdf.set_xy(x, y)
    pdf.cell(w_l, 5, lab, ln=0)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*_TEXT)
    pdf.set_xy(x + w_l, y)
    pdf.multi_cell(col_w - w_l, 5.2, _dob(member), border="B")
    y_left = pdf.get_y()
    pdf.set_text_color(0, 0, 0)

    x2 = x + col_w + gap
    pdf.set_font("Helvetica", "B", 9.5)
    lab2 = "Gender: "
    w2 = pdf.get_string_width(lab2)
    pdf.set_xy(x2, y)
    pdf.cell(w2, 5, lab2, ln=0)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*_TEXT)
    pdf.set_xy(x2 + w2, y)
    pdf.multi_cell(col_w - w2, 5.2, _gender_label(member), border="B")
    y_right = pdf.get_y()
    pdf.set_text_color(0, 0, 0)
    return max(y_left, y_right) + 2.5


def _build_membership_form_pdf_fpdf(member: Member) -> bytes:
    """Legacy layout-only PDF if HTML pipeline is unavailable."""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(True, margin=22)
    pdf.add_page()
    W, H = 210, 297
    m = 18
    uw = W - 2 * m
    y = 14

    pdf.set_draw_color(*_BLUE)
    pdf.set_line_width(1.1)
    pdf.line(m - 2, 12, m + 32, 12)
    pdf.line(m - 2, 12, m - 2, 44)
    pdf.set_draw_color(*_GREEN)
    pdf.set_line_width(0.5)
    pdf.line(m + 1, 15, m + 28, 15)
    pdf.line(m + 1, 15, m + 1, 40)

    pdf.set_draw_color(*_BLUE)
    pdf.set_line_width(1.1)
    pdf.line(W - m + 2, H - 12, W - m - 32, H - 12)
    pdf.line(W - m + 2, H - 12, W - m + 2, H - 44)
    pdf.set_draw_color(*_GREEN)
    pdf.set_line_width(0.5)
    pdf.line(W - m - 1, H - 15, W - m - 28, H - 15)
    pdf.line(W - m - 1, H - 15, W - m - 1, H - 40)

    logo = _logo_path()
    if logo:
        try:
            if hasattr(pdf, "set_alpha"):
                pdf.set_alpha(0.09)
            pdf.image(logo, x=W / 2 - 45, y=H / 2 - 35, w=90)
            if hasattr(pdf, "set_alpha"):
                pdf.set_alpha(1)
        except OSError:
            pass

    if logo:
        try:
            img_w = 55
            pdf.image(logo, x=(W - img_w) / 2, y=y, w=img_w)
            y = y + 20
        except OSError:
            y += 6
    else:
        y += 4

    pdf.set_draw_color(*_GREEN)
    pdf.set_line_width(0.35)
    seg = uw * 0.55
    x0 = (W - seg) / 2
    pdf.line(x0, y, x0 + seg, y)
    y += 10

    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*_NAVY)
    pdf.set_x(m)
    pdf.cell(uw, 7, "ESTITHMAR MEMBERSHIP APPLICATION FORM", align="C", ln=1)
    pdf.set_text_color(0, 0, 0)
    y = pdf.get_y() + 2
    pdf.set_draw_color(*_NAVY)
    pdf.set_line_width(0.5)
    pdf.line(m, y, m + uw, y)
    y += 10

    y = _field_block(pdf, m, y, uw, "Member Name", member.full_name)
    y = _field_block(pdf, m, y, uw, "Address", member.address)

    y = _section_title(pdf, m, y, uw, "1. Personal Information")
    y = _field_block(pdf, m, y, uw, "Full Name", member.full_name)
    y = _row_dob_gender(pdf, m, y, uw, member)

    y = _field_block(pdf, m, y, uw, "National ID / Passport No", member.national_id)
    y = _field_block(pdf, m, y, uw, "Phone Number", member.phone)
    y = _field_block(pdf, m, y, uw, "Email Address", member.email)
    y = _field_block(pdf, m, y, uw, "Residential Address", member.address)
    y = _field_block(pdf, m, y, uw, "Occupation / Employer", member.occupation_employer)

    y = _section_title(pdf, m, y, uw, "2. Next of Kin (Emergency Contact)")
    y = _field_block(pdf, m, y, uw, "Name", member.next_of_kin_name)
    y = _field_block(pdf, m, y, uw, "Relationship", member.next_of_kin_relationship)
    y = _field_block(pdf, m, y, uw, "Phone Number", member.next_of_kin_phone)
    y = _field_block(pdf, m, y, uw, "Physical Address", member.next_of_kin_address)

    fy = y + 10
    if fy + 18 > H - 12:
        pdf.add_page()
        fy = 22
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_NAVY)
    pdf.set_fill_color(*_GREEN)
    pdf.ellipse(48, fy, 9, 9, "F")
    pdf.set_xy(60, fy + 2)
    pdf.cell(75, 6, "+252772233330", ln=0)
    pdf.ellipse(128, fy, 9, 9, "F")
    pdf.set_xy(140, fy + 2)
    pdf.cell(60, 6, "Mogadisho-Somalia", ln=1)
    pdf.set_text_color(0, 0, 0)

    raw = pdf.output(dest="S")
    if isinstance(raw, str):
        return raw.encode("latin-1", errors="replace")
    return bytes(raw)


def _build_membership_form_pdf_playwright(member: Member) -> bytes:
    """Render ``membership_form_print.html`` with Chromium so layout matches the browser."""
    from flask import render_template, request, url_for

    logo_data_uri = _logo_data_uri()
    rel = _logo_relative_static_path()
    brand_abs = url_for("static", filename=rel, _external=True)
    html = render_template(
        "members/membership_form_print.html",
        member=member,
        membership_pdf_mode=True,
        logo_data_uri=logo_data_uri,
        brand_logo_light_lg=brand_abs,
        brand_logo_light_sm=brand_abs,
        brand_logo_dark_lg=brand_abs,
        brand_logo_dark_sm=brand_abs,
    )
    base = (request.url_root if request else None) or "http://127.0.0.1/"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is required for template-accurate PDFs. "
            "Install: pip install playwright && playwright install chromium"
        ) from e

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = None
        try:
            # Match template width (794px ≈ A4 at 96dpi); screen media matches the browser preview URL.
            context = browser.new_context(
                viewport={"width": 794, "height": 1400},
                device_scale_factor=1,
                base_url=base,
            )
            page = context.new_page()
            page.emulate_media(media="screen")
            page.set_content(html, wait_until="load", timeout=120_000)
            time.sleep(0.75)
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "0mm", "right": "0mm", "bottom": "0mm", "left": "0mm"},
                prefer_css_page_size=True,
            )
        finally:
            if context is not None:
                context.close()
            browser.close()
    return pdf_bytes


def build_membership_form_pdf(member: Member) -> bytes:
    """PDF bytes for membership form — HTML template first, FPDF if Playwright fails."""
    try:
        return _build_membership_form_pdf_playwright(member)
    except Exception as e:
        logger.warning("Membership HTML→PDF failed (%s); using FPDF fallback.", e)
        return _build_membership_form_pdf_fpdf(member)
