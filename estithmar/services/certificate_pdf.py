"""Share certificate PDF — aligned with ``templates/certificates/print.html`` (same data & wording)."""
from __future__ import annotations

from fpdf import FPDF

from estithmar.models import ShareCertificate
from estithmar.services.certificates import (
    certificate_share_position_detail,
    certificate_stock_of_name,
    format_certificate_share_quantity,
)


def _safe_pdf_text(s: str | None) -> str:
    if s is None:
        return ""
    return "".join(c if 32 <= ord(c) < 127 or c in "\t\n" else "?" for c in str(s))


def _ordinal_day(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def build_share_certificate_pdf(cert: ShareCertificate, *, extra: dict | None = None) -> bytes:
    """
    Landscape A4 certificate. Content order and labels match the browser/print template
    (``certificates/print.html``): certificate number badge, title, particulars rows,
    date line, signatures, company block, notes, audit line.
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
        day_o = _ordinal_day(idate.day)
        month_n = idate.strftime("%B")
        year_n = str(idate.year)
    else:
        day_o, month_n, year_n = "—", "—", "—"

    date_sentence = f"On the {day_o} Day of {month_n} In the Year {year_n}".upper()

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    W, H = float(pdf.w), float(pdf.h)

    m = 6.0
    iw, ih = W - 2 * m, H - 2 * m
    left = m + 8.0
    usable_w = iw - 16.0
    body_right = left + usable_w

    # --- Borders (triple frame like template) ---
    pdf.set_draw_color(26, 26, 26)
    pdf.set_line_width(0.85)
    pdf.rect(m, m, iw, ih)
    pdf.set_line_width(0.35)
    pdf.rect(m + 1.5, m + 1.5, iw - 3.0, ih - 3.0)
    pdf.set_line_width(0.18)
    pdf.rect(m + 2.8, m + 2.8, iw - 5.6, ih - 5.6)

    y_body = m + 10.0

    # --- Certificate number (top-right box, same as .stock-cert-certno) ---
    box_w = 44.0
    box_x = body_right - box_w
    box_y = m + 4.0
    pdf.set_fill_color(255, 252, 250)
    pdf.set_draw_color(37, 99, 235)
    pdf.set_line_width(0.2)
    pdf.rect(box_x, box_y, box_w, 11.0, style="DF")
    pdf.set_xy(box_x + 1.0, box_y + 1.2)
    pdf.set_font("Helvetica", "B", 5.5)
    pdf.set_text_color(37, 99, 235)
    pdf.cell(box_w - 2.0, 2.8, "CERTIFICATE", align="R", ln=1)
    pdf.set_x(box_x + 1.0)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(30, 58, 95)
    pdf.cell(box_w - 2.0, 4.0, _safe_pdf_text(cert.certificate_no or "—"), align="R", ln=1)
    pdf.set_text_color(0, 0, 0)

    pdf.set_xy(left, y_body)

    # --- Title: "Stock Certificate" (template h1; print uses blackletter — Times approximates formal) ---
    pdf.set_font("Times", "B", 22)
    pdf.cell(usable_w, 10.0, "Stock Certificate", align="C", ln=1)

    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(26, 26, 26)
    pdf.cell(usable_w, 4.8, "THIS IS TO CERTIFY THAT", align="C", ln=1)

    # --- Member name + underline ---
    pdf.set_font("Times", "B", 13)
    nm = _safe_pdf_text(member.full_name or "")
    pdf.cell(usable_w, 6.5, nm, align="C", ln=1)
    ly = pdf.get_y()
    pdf.line(left + usable_w * 0.08, ly, left + usable_w * 0.92, ly)
    pdf.ln(3.0)

    # --- Ownership (template .stock-cert-owns: uppercase) ---
    own_core = f"Is The Owner Of   {share_qty}   Shares Of Stock Of   {stock_of}"
    pdf.set_font("Helvetica", "B", 8.0)
    pdf.set_x(left)
    pdf.multi_cell(usable_w, 4.2, _safe_pdf_text(own_core.upper()), align="C")
    pdf.ln(2.0)

    # --- Particulars panel (matches template: no certificate number row — only corner badge) ---
    ph_top = pdf.get_y()
    pdf.set_draw_color(37, 99, 235)
    pdf.set_line_width(0.15)
    pad_x = 2.8
    head_h = 6.2
    label_w = 48.0
    val_x = left + pad_x + label_w
    val_w = usable_w - 2 * pad_x - label_w

    pdf.line(left, ph_top, left + usable_w, ph_top)
    pdf.set_fill_color(239, 246, 255)
    pdf.rect(left, ph_top, usable_w, head_h, style="FD")
    pdf.set_xy(left, ph_top + 1.2)
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_text_color(29, 78, 216)
    pdf.cell(usable_w, 4.0, "CERTIFICATE PARTICULARS", align="C", ln=1)
    pdf.set_text_color(0, 0, 0)

    row_top = ph_top + head_h
    pdf.line(left, row_top, left + usable_w, row_top)

    rows_data: list[tuple[str, str]] = [
        ("Member reference", member.member_id or "—"),
        ("Shareholding", share_detail),
        ("Date of issue", issued_line),
    ]
    official_val = f"RECORD ID  #{cert.id}"
    if cert_issued_by_label:
        official_val += "\nRECORDED BY  " + cert_issued_by_label
    rows_data.append(("Official record", official_val))

    y_row = row_top
    for i, (lbl, val) in enumerate(rows_data):
        y_row += 0.45
        y_start = y_row
        pdf.set_xy(left + pad_x, y_row)
        pdf.set_font("Helvetica", "B", 6.0)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(label_w, 4.0, _safe_pdf_text(lbl.upper()), align="L", ln=0)
        pdf.set_xy(val_x, y_row)
        if lbl == "Member reference":
            pdf.set_font("Courier", "B", 8.0)
        else:
            pdf.set_font("Helvetica", "", 8.0)
        pdf.set_text_color(10, 10, 10)
        pdf.multi_cell(val_w, 3.7, _safe_pdf_text(val), align="L")
        y_row = max(pdf.get_y(), y_start + 4.5)
        pdf.set_text_color(0, 0, 0)
        if i < len(rows_data) - 1:
            pdf.line(left, y_row, left + usable_w, y_row)

    pdf.line(left, y_row, left + usable_w, y_row)
    ph_bottom = y_row
    pdf.line(left, ph_top, left, ph_bottom)
    pdf.line(left + usable_w, ph_top, left + usable_w, ph_bottom)

    pdf.set_y(ph_bottom + 2.8)

    # --- Date sentence (uppercase like template) ---
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_x(left)
    pdf.cell(usable_w, 5.5, _safe_pdf_text(date_sentence), align="C", ln=1)
    pdf.ln(3.0)

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
        cap1 = "Add in Settings"
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
        cap2 = "Optional second officer"
    pdf.set_xy(left + col_w + gap, cap_y)
    pdf.multi_cell(col_w, 3.2, cap2, align="C")
    c2_h = pdf.get_y() - cap_y
    pdf.set_y(cap_y + max(c1_h, c2_h, 8.0) + 1.0)
    pdf.set_text_color(0, 0, 0)

    pdf.ln(2.0)
    # --- Company block ---
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
    if not addr and not reg_no:
        pdf.set_text_color(130, 130, 130)
        pdf.set_font("Helvetica", "", 7.0)
        pdf.set_x(left)
        pdf.multi_cell(
            usable_w,
            3.6,
            "Add registered address in Settings for official certificates.",
            align="C",
        )
        pdf.set_text_color(0, 0, 0)

    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_text_color(100, 100, 100)
    pdf.set_x(left)
    pdf.cell(
        usable_w,
        3.2,
        _safe_pdf_text(f"Estithmar system · Certificate record #{cert.id}"),
        align="C",
        ln=1,
    )
    pdf.set_text_color(0, 0, 0)

    # --- Notes (after company, like template; issuance notes only) ---
    notes = (cert.notes or "").strip()
    if notes:
        shown = notes[:600] + ("…" if len(notes) > 600 else "")
        pdf.ln(1.5)
        pdf.set_font("Helvetica", "I", 6.8)
        pdf.set_text_color(100, 100, 100)
        pdf.set_x(left + usable_w * 0.06)
        pdf.multi_cell(usable_w * 0.88, 3.0, _safe_pdf_text(shown), align="C")
        pdf.set_text_color(0, 0, 0)

    # --- Revoked watermark (matches .stock-cert-page.is-revoked) ---
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
