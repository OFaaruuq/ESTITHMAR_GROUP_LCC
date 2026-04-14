"""Share certificate PDF — visual and content parity with ``templates/certificates/print.html``."""
from __future__ import annotations

import logging
import math
import os
import time
from datetime import date

# Set to 0/false/no to raise if Playwright/Chromium fails instead of using FPDF (layout differs).
_CERT_PDF_FPDF_FALLBACK_ENV = "ESTITHMAR_CERTIFICATE_PDF_FPDF_FALLBACK"
# Optional path to chromium/chrome executable (Playwright bundled or system Chrome).
_CHROMIUM_EXECUTABLE_ENV = "ESTITHMAR_CHROMIUM_EXECUTABLE"
# 1 (default) or 2 — higher DPI scaling for sharper PDF text (larger buffer).
_CERT_PDF_DEVICE_SCALE_ENV = "ESTITHMAR_CERTIFICATE_PDF_DEVICE_SCALE"

from fpdf import FPDF

from estithmar.models import ShareCertificate, format_member_public_id, get_or_create_settings
from estithmar.services.certificates import (
    certificate_share_position_detail,
    certificate_stock_of_name,
    format_certificate_share_quantity,
)

logger = logging.getLogger(__name__)


def share_certificate_print_context(
    cert: ShareCertificate,
    *,
    settings=None,
    extra: dict | None = None,
) -> dict:
    """Template context for ``print.html`` and ``certificate_document.html`` (single source of truth)."""
    s = settings or get_or_create_settings()
    ex: dict = dict(extra) if extra is not None else dict(s.get_extra())
    sub = cert.subscription
    cur = s.currency_code or "USD"
    company_nm = (ex.get("company_name") or "Estithmar Investment Management").strip()
    cert_share_qty = format_certificate_share_quantity(sub, cur)
    cert_stock_of = certificate_stock_of_name(sub, company_nm)
    sym = s.currency_symbol or "$"
    cert_share_detail = certificate_share_position_detail(sub, sym, cur)
    idate = cert.issued_date or date.today()
    dnum = idate.day
    if 11 <= (dnum % 100) <= 13:
        day_ord = f"{dnum}th"
    else:
        day_ord = f"{dnum}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(dnum % 10, 'th') }"
    cert_issued_by_label = None
    if cert.issued_by:
        cert_issued_by_label = (cert.issued_by.full_name or cert.issued_by.username or "").strip() or None
    return {
        "cert": cert,
        "settings": s,
        "extra": ex,
        "currency_code": cur,
        "cert_share_qty": cert_share_qty,
        "cert_stock_of": cert_stock_of,
        "cert_share_detail": cert_share_detail,
        "cert_issued_day": idate.day,
        "cert_issued_day_ordinal": day_ord,
        "cert_issued_month": idate.strftime("%B"),
        "cert_issued_year": idate.year,
        "company_display_name": company_nm,
        "cert_issued_by_label": cert_issued_by_label,
    }

# Optional blackletter title (same family as print template). Drop TTF next to this file:
# ``estithmar/fonts/UnifrakturMaguntia-Regular.ttf`` (from Google Fonts OFL).
_TITLE_FONT_TTF = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "fonts", "UnifrakturMaguntia-Regular.ttf")
)

# Formal certificate palette (aligned with HTML stock certificate CSS)
_CERT_BLUE = (21, 44, 72)
_CERT_BLUE_DEEP = (15, 36, 62)
_CERT_BLUE_SOFT = (232, 236, 244)
_CREAM = (255, 254, 251)
_TEXT_MUTED = (100, 100, 100)


def _safe_pdf_text(s: str | None) -> str:
    if s is None:
        return ""
    return "".join(c if 32 <= ord(c) < 127 or c in "\t\n" else "?" for c in str(s))


def _ordinal_day(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _try_load_title_font(pdf: FPDF) -> bool:
    if not os.path.isfile(_TITLE_FONT_TTF):
        return False
    try:
        pdf.add_font("CertTitle", "", _TITLE_FONT_TTF, uni=True)
        return True
    except Exception:
        return False


def _draw_star_ornament(pdf: FPDF, cx: float, cy: float, outer: float, inner: float) -> None:
    """Eight-point star (matches template corner SVG roughly)."""
    r, g, b = _CERT_BLUE
    pdf.set_fill_color(r, g, b)
    pts: list[tuple[float, float]] = []
    for k in range(16):
        ang = (math.pi / 8) * k - math.pi / 2
        rad = outer if k % 2 == 0 else inner
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    pdf.polygon(pts, style="F")
    pdf.set_fill_color(r, g, b)
    pdf.ellipse(cx - 0.9, cy - 0.9, 1.8, 1.8, style="F")


def _draw_inner_stripes(pdf: FPDF, x: float, y: float, w: float, h: float) -> None:
    """Subtle diagonal hatch like ``.stock-cert-border-inner::before``."""
    pdf.set_draw_color(236, 238, 244)
    pdf.set_line_width(0.06)
    span = w + h
    step = 1.8
    i = -h
    while i < span:
        pdf.line(x + i, y, x + i + h, y + h)
        i += step


def _draw_centered_underline_segments(
    pdf: FPDF,
    left: float,
    usable_w: float,
    y: float,
    parts: list[tuple[str, bool]],
    font: str = "Helvetica",
    style: str = "B",
    size: float = 8.5,
    line_gap: float = 4.6,
) -> float:
    """Draw a centered line; underline segments where ``parts[i][1]`` is True."""
    pdf.set_font(font, style, size)
    pdf.set_text_color(17, 17, 17)
    full = "".join(t for t, _ in parts)
    tw = pdf.get_string_width(full)
    x0 = left + (usable_w - tw) / 2
    x = x0
    h_cell = 5.0
    for text, under in parts:
        wpart = pdf.get_string_width(text)
        pdf.set_xy(x, y)
        pdf.cell(wpart, h_cell, _safe_pdf_text(text), align="L", ln=0)
        if under:
            pdf.line(x, y + line_gap, x + wpart, y + line_gap)
        x += wpart
    y_end = y + h_cell + 1.5
    pdf.set_y(y_end)
    return y_end


def _draw_ownership_block(
    pdf: FPDF,
    left: float,
    usable_w: float,
    y: float,
    share_qty: str,
    stock_of: str,
) -> float:
    """Three-line ownership block aligned with the HTML template (lead / qty + phrase / issuer)."""
    qty = _safe_pdf_text(share_qty).upper()
    stock = _safe_pdf_text(stock_of).upper()
    y_line = y

    pdf.set_font("Helvetica", "B", 7.0)
    pdf.set_text_color(71, 85, 105)
    pdf.set_xy(left, y_line)
    pdf.cell(usable_w, 3.8, "IS THE OWNER OF", align="C", ln=1)
    y_line = pdf.get_y() + 0.6
    pdf.set_text_color(17, 17, 17)

    pdf.set_font("Helvetica", "B", 8.0)
    tail = " SHARES OF STOCK OF"
    q_w = pdf.get_string_width(qty)
    t_w = pdf.get_string_width(tail)
    gap = 1.2
    row_w = q_w + gap + t_w
    x0 = left + (usable_w - row_w) / 2
    pdf.set_xy(x0, y_line)
    pdf.cell(q_w, 4.6, qty, align="L", ln=0)
    ul_w = max(q_w, 16.0)
    pdf.line(x0, y_line + 4.0, x0 + ul_w, y_line + 4.0)
    pdf.set_xy(x0 + q_w + gap, y_line)
    pdf.cell(t_w, 4.6, tail, align="L", ln=1)
    y_line = pdf.get_y() + 0.5

    pdf.set_font("Times", "B", 9.5)
    s_w = pdf.get_string_width(stock)
    box_w = max(s_w + 3.0, min(usable_w * 0.88, s_w + 12.0))
    x_stock = left + (usable_w - box_w) / 2
    pdf.set_xy(x_stock, y_line)
    pdf.cell(box_w, 5.0, stock, align="C", ln=0)
    pdf.line(x_stock, y_line + 4.4, x_stock + box_w, y_line + 4.4)
    return y_line + 6.8


def _chromium_executable() -> str | None:
    path = (os.environ.get(_CHROMIUM_EXECUTABLE_ENV) or "").strip()
    return path if path and os.path.isfile(path) else None


def _pdf_device_scale() -> int:
    raw = (os.environ.get(_CERT_PDF_DEVICE_SCALE_ENV) or "1").strip()
    try:
        n = int(raw)
    except ValueError:
        return 1
    return 2 if n >= 2 else 1


def _build_share_certificate_pdf_playwright(cert: ShareCertificate, *, extra: dict | None = None) -> bytes:
    """Render ``certificate_document.html`` with Chromium — layout matches the print preview."""
    from flask import render_template, request

    ctx = share_certificate_print_context(cert, extra=extra)
    ctx["certificate_pdf_export"] = True
    html = render_template("certificates/certificate_document.html", **ctx)
    base = (request.url_root if request else None) or "http://127.0.0.1/"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is required for template-accurate certificate PDFs. "
            "Install: pip install playwright && python -m playwright install chromium"
        ) from e

    # Viewport ≈ printable area: 281mm × 194mm @ 96dpi (A4 landscape minus 8mm margins).
    _vp_w = int(round((297 - 16) * 96 / 25.4))
    _vp_h = int(round((210 - 16) * 96 / 25.4))
    _launch_args = (
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--font-render-hinting=medium",
    )
    _exe = _chromium_executable()
    _scale = _pdf_device_scale()
    with sync_playwright() as p:
        launch_kw: dict = {"headless": True, "args": list(_launch_args)}
        if _exe:
            launch_kw["executable_path"] = _exe
        browser = p.chromium.launch(**launch_kw)
        context = None
        try:
            # Python Playwright has no base_url on set_content(); use context base_url for relative URLs.
            context = browser.new_context(
                viewport={"width": _vp_w, "height": _vp_h},
                device_scale_factor=_scale,
                base_url=base,
            )
            page = context.new_page()
            page.emulate_media(media="print")
            page.set_content(html, wait_until="load", timeout=120_000)
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            try:
                page.evaluate("async () => { await document.fonts.ready; }")
            except Exception:
                pass
            time.sleep(0.6 if _scale < 2 else 0.4)
            # Explicit paper size avoids portrait/landscape mismatches with some @page + preferCSS combinations.
            pdf_bytes = page.pdf(
                width="297mm",
                height="210mm",
                print_background=True,
                margin={"top": "8mm", "right": "8mm", "bottom": "8mm", "left": "8mm"},
                prefer_css_page_size=False,
            )
        finally:
            if context is not None:
                context.close()
            browser.close()

    if not pdf_bytes or len(pdf_bytes) < 64 or not pdf_bytes.startswith(b"%PDF"):
        raise RuntimeError("Chromium produced empty or invalid PDF bytes (expected %PDF header).")
    logger.info(
        "Certificate PDF (Playwright): %d bytes, viewport=%dx%d, device_scale=%s",
        len(pdf_bytes),
        _vp_w,
        _vp_h,
        _scale,
    )
    return pdf_bytes


def build_share_certificate_pdf_fpdf(cert: ShareCertificate, *, extra: dict | None = None) -> bytes:
    """
    Landscape A4 certificate: same structure and styling cues as ``certificates/print.html``
    (triple frame, cert no. badge, blackletter title when font file present, corner stars,
    cream field, diagonal hatch, particulars panel, underlined date/ownership, signatures,
    company block, notes, revoked watermark).
    """
    extra = extra or {}
    sub = cert.subscription
    member = cert.member
    company = (extra.get("company_name") or "Estithmar Investment Management").strip()
    addr = (extra.get("company_address") or "").strip()
    reg_no = (extra.get("company_registration") or "").strip()
    cur_code = extra.get("currency_code") or "USD"
    cur_sym = extra.get("currency_symbol") or "$"
    signatory = (extra.get("authorized_signatory") or "").strip()
    sign_title = (extra.get("signatory_title") or "").strip()
    second_sig = (extra.get("second_signatory") or "").strip()
    second_title = (extra.get("second_signatory_title") or "").strip()

    stock_of = certificate_stock_of_name(sub, company)
    share_qty = format_certificate_share_quantity(sub, cur_code)
    share_detail = certificate_share_position_detail(sub, cur_sym, cur_code)

    issued_line = cert.issued_date.strftime("%d %B %Y") if cert.issued_date else "—"

    cert_issued_by_label = None
    if cert.issued_by:
        u = cert.issued_by
        cert_issued_by_label = (u.full_name or u.username or "").strip() or None

    idate = cert.issued_date
    if idate:
        day_o = _ordinal_day(idate.day).upper()
        month_n = idate.strftime("%B").upper()
        year_n = str(idate.year)
    else:
        day_o, month_n, year_n = "—", "—", "—"

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    W, H = float(pdf.w), float(pdf.h)

    m = 6.0
    iw, ih = W - 2 * m, H - 2 * m
    left = m + 8.0
    usable_w = iw - 16.0
    body_right = left + usable_w
    inner_x = m + 2.8
    inner_y = m + 2.8
    inner_w = iw - 5.6
    inner_h = ih - 5.6

    # --- Triple frame (template: 3px / double inner) ---
    pdf.set_draw_color(26, 26, 26)
    pdf.set_line_width(0.85)
    pdf.rect(m, m, iw, ih)
    pdf.set_line_width(0.35)
    pdf.rect(m + 1.5, m + 1.5, iw - 3.0, ih - 3.0)
    pdf.set_fill_color(*_CREAM)
    pdf.rect(inner_x, inner_y, inner_w, inner_h, style="FD")
    pdf.set_draw_color(69, 69, 69)
    pdf.set_line_width(0.35)
    pdf.rect(inner_x, inner_y, inner_w, inner_h, style="D")

    _draw_inner_stripes(pdf, inner_x, inner_y, inner_w, inner_h)

    pdf.set_draw_color(69, 69, 69)
    pdf.set_line_width(0.35)
    pdf.rect(inner_x, inner_y, inner_w, inner_h, style="D")

    # Corner ornaments (inset ~2mm from inner edge)
    inset = 3.5
    sz_out, sz_in = 3.2, 1.25
    _draw_star_ornament(pdf, inner_x + inset + sz_out, inner_y + inset + sz_out, sz_out, sz_in)
    _draw_star_ornament(pdf, inner_x + inner_w - inset - sz_out, inner_y + inset + sz_out, sz_out, sz_in)
    _draw_star_ornament(pdf, inner_x + inset + sz_out, inner_y + inner_h - inset - sz_out, sz_out, sz_in)
    _draw_star_ornament(pdf, inner_x + inner_w - inset - sz_out, inner_y + inner_h - inset - sz_out, sz_out, sz_in)

    y_body = m + 10.0

    # --- Certificate number box (top-right) ---
    box_w = 44.0
    box_x = body_right - box_w
    box_y = m + 4.0
    pdf.set_fill_color(255, 252, 250)
    pdf.set_draw_color(*_CERT_BLUE)
    pdf.set_line_width(0.2)
    pdf.rect(box_x, box_y, box_w, 11.0, style="DF")
    pdf.set_xy(box_x + 1.0, box_y + 1.2)
    pdf.set_font("Helvetica", "B", 5.5)
    pdf.set_text_color(*_CERT_BLUE)
    pdf.cell(box_w - 2.0, 2.8, "CERTIFICATE", align="R", ln=1)
    pdf.set_x(box_x + 1.0)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*_CERT_BLUE)
    pdf.cell(box_w - 2.0, 4.0, _safe_pdf_text(cert.certificate_no or "—"), align="R", ln=1)
    pdf.set_text_color(0, 0, 0)

    pdf.set_xy(left, y_body)

    has_title_font = _try_load_title_font(pdf)
    if has_title_font:
        pdf.set_font("CertTitle", "", 26)
    else:
        pdf.set_font("Times", "B", 22)
    pdf.set_text_color(10, 10, 10)
    pdf.cell(usable_w, 11.0, "Stock Certificate", align="C", ln=1)

    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(26, 26, 26)
    pdf.cell(usable_w, 4.8, "THIS IS TO CERTIFY THAT", align="C", ln=1)

    pdf.set_font("Times", "B", 13)
    nm = _safe_pdf_text(member.full_name or "")
    pdf.cell(usable_w, 6.5, nm, align="C", ln=1)
    ly = pdf.get_y()
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.2)
    pdf.line(left + usable_w * 0.08, ly, left + usable_w * 0.92, ly)
    pdf.ln(3.0)

    y_own = pdf.get_y()
    y_after_own = _draw_ownership_block(pdf, left, usable_w, y_own, share_qty, stock_of)
    pdf.set_y(y_after_own + 1.5)

    # --- Particulars panel ---
    ph_top = pdf.get_y()
    pdf.set_draw_color(*_CERT_BLUE)
    pdf.set_line_width(0.15)
    pad_x = 2.8
    head_h = 6.2
    label_w = 48.0
    val_x = left + pad_x + label_w
    val_w = usable_w - 2 * pad_x - label_w

    pdf.line(left, ph_top, left + usable_w, ph_top)
    pdf.set_fill_color(*_CERT_BLUE_SOFT)
    pdf.rect(left, ph_top, usable_w, head_h, style="FD")
    pdf.set_xy(left, ph_top + 1.2)
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_text_color(*_CERT_BLUE_DEEP)
    pdf.cell(usable_w, 4.0, "CERTIFICATE PARTICULARS", align="C", ln=1)
    pdf.set_text_color(0, 0, 0)

    row_top = ph_top + head_h
    pdf.line(left, row_top, left + usable_w, row_top)

    rows_data: list[tuple[str, str]] = [
        ("Member reference", format_member_public_id(member.member_id) or "—"),
        ("Shareholding", share_detail),
        ("Date of issue", issued_line),
        ("Official record", ""),
    ]

    y_row = row_top
    for i, (lbl, val) in enumerate(rows_data):
        y_row += 0.45
        y_start = y_row
        pdf.set_xy(left + pad_x, y_row)
        pdf.set_font("Helvetica", "B", 6.0)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(label_w, 4.0, _safe_pdf_text(lbl.upper()), align="L", ln=0)
        pdf.set_xy(val_x, y_row)
        if lbl == "Official record":
            w_lab = 30.0
            pdf.set_font("Helvetica", "B", 5.8)
            pdf.set_text_color(100, 116, 139)
            pdf.cell(w_lab, 3.5, "RECORD ID", align="L", ln=0)
            pdf.set_font("Courier", "B", 8.0)
            pdf.set_text_color(15, 23, 42)
            pdf.cell(val_w - w_lab, 3.5, _safe_pdf_text(f"#{cert.id}"), align="R", ln=1)
            if cert_issued_by_label:
                pdf.set_xy(val_x, pdf.get_y() + 0.25)
                pdf.set_font("Helvetica", "B", 5.8)
                pdf.set_text_color(100, 116, 139)
                pdf.cell(w_lab, 3.5, "RECORDED BY", align="L", ln=0)
                pdf.set_font("Helvetica", "B", 7.5)
                pdf.set_text_color(15, 23, 42)
                pdf.multi_cell(val_w - w_lab, 3.4, _safe_pdf_text(cert_issued_by_label), align="R")
            y_row = max(pdf.get_y(), y_start + 4.5)
        elif lbl == "Member reference":
            pdf.set_font("Courier", "B", 8.0)
            pdf.set_text_color(15, 23, 42)
            pdf.multi_cell(val_w, 3.7, _safe_pdf_text(val), align="L")
            y_row = max(pdf.get_y(), y_start + 4.5)
        elif lbl == "Shareholding":
            pdf.set_font("Times", "B", 8.0)
            pdf.set_text_color(15, 23, 42)
            pdf.multi_cell(val_w, 3.7, _safe_pdf_text(val), align="L")
            y_row = max(pdf.get_y(), y_start + 4.5)
        else:
            pdf.set_font("Helvetica", "", 8.0)
            pdf.set_text_color(15, 23, 42)
            pdf.multi_cell(val_w, 3.7, _safe_pdf_text(val), align="L")
            y_row = max(pdf.get_y(), y_start + 4.5)
        pdf.set_text_color(0, 0, 0)
        if i < len(rows_data) - 1:
            pdf.line(left, y_row, left + usable_w, y_row)

    pdf.line(left, y_row, left + usable_w, y_row)
    ph_bottom = y_row
    pdf.line(left, ph_top, left, ph_bottom)
    pdf.line(left + usable_w, ph_top, left + usable_w, ph_bottom)

    pdf.set_y(ph_bottom + 2.5)

    # --- Date line (uppercase + underlined blanks like template) ---
    date_parts: list[tuple[str, bool]] = [
        ("ON THE ", False),
        (day_o, True),
        (" DAY OF ", False),
        (month_n, True),
        (" IN THE YEAR ", False),
        (year_n, True),
    ]
    y_date = pdf.get_y()
    _draw_centered_underline_segments(pdf, left, usable_w, y_date, date_parts)
    pdf.ln(2.5)

    # --- Signatures ---
    gap = 14.0
    col_w = (usable_w - gap) / 2.0
    y_sig = pdf.get_y()
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.2)
    pdf.line(left, y_sig, left + col_w, y_sig)
    pdf.line(left + col_w + gap, y_sig, left + 2 * col_w + gap, y_sig)
    pdf.set_xy(left, y_sig + 1.0)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.cell(col_w, 3.5, "SIGNATURE", align="C", ln=0)
    pdf.cell(gap, 3.5, "", ln=0)
    pdf.cell(col_w, 3.5, "SIGNATURE", align="C", ln=1)

    cap_y = pdf.get_y() + 0.5
    pdf.set_font("Helvetica", "", 7.0)
    if signatory:
        pdf.set_text_color(60, 60, 60)
        cap1 = _safe_pdf_text(signatory)
        if sign_title:
            cap1 += "\n" + _safe_pdf_text(sign_title)
    else:
        pdf.set_text_color(130, 130, 130)
        cap1 = "-"  # ASCII only: Helvetica core font is Latin-1
    pdf.set_xy(left, cap_y)
    pdf.multi_cell(col_w, 3.2, cap1, align="C")
    c1_h = pdf.get_y() - cap_y

    if second_sig:
        pdf.set_text_color(60, 60, 60)
        cap2 = _safe_pdf_text(second_sig)
        if second_title:
            cap2 += "\n" + _safe_pdf_text(second_title)
    else:
        pdf.set_text_color(130, 130, 130)
        cap2 = "-"
    pdf.set_xy(left + col_w + gap, cap_y)
    pdf.multi_cell(col_w, 3.2, cap2, align="C")
    c2_h = pdf.get_y() - cap_y
    pdf.set_y(cap_y + max(c1_h, c2_h, 8.0) + 1.0)
    pdf.set_text_color(0, 0, 0)

    pdf.ln(2.0)
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.12)
    line_y = pdf.get_y()
    pdf.line(left + usable_w * 0.04, line_y, left + usable_w * 0.96, line_y)
    pdf.ln(2.5)

    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_x(left)
    pdf.multi_cell(usable_w, 4.0, _safe_pdf_text(company), align="C")
    pdf.set_font("Helvetica", "", 7.5)
    if addr:
        pdf.set_x(left)
        pdf.multi_cell(usable_w, 3.6, _safe_pdf_text(addr), align="C")
    if reg_no:
        pdf.set_x(left)
        pdf.multi_cell(usable_w, 3.6, _safe_pdf_text(reg_no), align="C")
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_text_color(*_TEXT_MUTED)
    pdf.set_x(left)
    pdf.cell(
        usable_w,
        3.2,
        _safe_pdf_text(f"Estithmar system - Certificate record #{cert.id}"),
        align="C",
        ln=1,
    )
    pdf.set_text_color(0, 0, 0)

    notes = (cert.notes or "").strip()
    if notes:
        shown = notes[:600] + ("…" if len(notes) > 600 else "")
        pdf.ln(1.5)
        pdf.set_font("Helvetica", "I", 6.8)
        pdf.set_text_color(*_TEXT_MUTED)
        pdf.set_x(left + usable_w * 0.06)
        pdf.multi_cell(usable_w * 0.88, 3.0, _safe_pdf_text(shown), align="C")
        pdf.set_text_color(0, 0, 0)

    if cert.status == "Revoked":
        try:
            cx, cy = W / 2, H / 2
            with pdf.rotation(-18, x=cx, y=cy):
                pdf.set_font("Helvetica", "B", 36)
                pdf.set_text_color(220, 180, 180)
                wtxt = pdf.get_string_width("REVOKED")
                pdf.text(cx - wtxt / 2, cy, "REVOKED")
        except Exception:
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(180, 0, 0)
            pdf.set_y(H - 22)
            pdf.set_x(left)
            pdf.cell(usable_w, 5, "STATUS: REVOKED — This certificate is void.", align="C", ln=1)
        pdf.set_text_color(0, 0, 0)

    raw = pdf.output(dest="S")
    if isinstance(raw, str):
        return raw.encode("latin-1", errors="replace")
    return bytes(raw)


def _fpdf_fallback_allowed() -> bool:
    v = os.environ.get(_CERT_PDF_FPDF_FALLBACK_ENV, "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def build_share_certificate_pdf(cert: ShareCertificate, *, extra: dict | None = None) -> bytes:
    """PDF bytes — HTML template via Playwright first; optional FPDF fallback if Playwright fails."""
    try:
        return _build_share_certificate_pdf_playwright(cert, extra=extra)
    except Exception as e:
        logger.exception(
            "Certificate HTML→PDF (Playwright) failed; template layout will not match until this is fixed."
        )
        if not _fpdf_fallback_allowed():
            raise RuntimeError(
                "Certificate PDF could not be generated with the HTML template (Playwright/Chromium). "
                "Install Chromium: python -m playwright install chromium. "
                f"Or set {_CERT_PDF_FPDF_FALLBACK_ENV} to allow legacy FPDF output. "
                f"Original error: {e}"
            ) from e
        logger.warning(
            "Using FPDF fallback (different layout). Set %s=0 to fail fast instead.",
            _CERT_PDF_FPDF_FALLBACK_ENV,
        )
        return build_share_certificate_pdf_fpdf(cert, extra=extra)
