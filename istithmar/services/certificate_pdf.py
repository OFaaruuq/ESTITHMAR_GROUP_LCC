"""Share certificate PDF — concise key details, linear flow (no overlapping layers)."""
from __future__ import annotations

from fpdf import FPDF

from istithmar.models import ShareCertificate
from istithmar.services.certificates import (
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
    """Landscape certificate PDF with concise registry lines; full payment terms live on the subscription."""
    extra = extra or {}
    sub = cert.subscription
    member = cert.member
    company = (extra.get("company_name") or "Istithmar Investment Management").strip()
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

    recorder = "—"
    if cert.issued_by:
        u = cert.issued_by
        recorder = (u.full_name or u.username or "").strip() or "—"

    idate = cert.issued_date
    if idate:
        day_o = _ordinal_day(idate.day)
        month_n = idate.strftime("%B")
        year_n = str(idate.year)
    else:
        day_o, month_n, year_n = "—", "—", "—"

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    W, H = 297.0, 210.0
    m = 8.0
    iw, ih = W - 2 * m, H - 2 * m
    left = m + 9
    usable_w = iw - 18
    label_w = 50.0
    row_h = 3.5
    text_sz = 6.5
    label_sz = 6.5

    pdf.set_draw_color(28, 28, 28)
    pdf.set_line_width(0.85)
    pdf.rect(m, m, iw, ih)
    pdf.set_line_width(0.35)
    pdf.rect(m + 3, m + 3, iw - 6, ih - 6)
    pdf.set_line_width(0.18)
    pdf.rect(m + 5.5, m + 5.5, iw - 11, ih - 11)

    def kv(label: str, value: str) -> None:
        pdf.set_x(left)
        pdf.set_font("Helvetica", "B", label_sz)
        pdf.cell(label_w, row_h, _safe_pdf_text(label) + ":", border=0, align="L", ln=0)
        pdf.set_font("Helvetica", "", text_sz)
        pdf.multi_cell(usable_w - label_w, row_h, _safe_pdf_text(value), align="L")

    # --- Header ---
    pdf.set_xy(left, m + 9)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(usable_w, 8, "STOCK CERTIFICATE", align="C", ln=1)
    hy = pdf.get_y()
    pdf.set_draw_color(130, 100, 45)
    pdf.set_line_width(0.25)
    pdf.line(left + usable_w * 0.28, hy, left + usable_w * 0.72, hy)
    pdf.set_draw_color(28, 28, 28)
    pdf.set_line_width(0.85)
    pdf.set_x(left)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.cell(usable_w, 5, "THIS IS TO CERTIFY THAT", align="C", ln=1)
    pdf.ln(1.5)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_x(left)
    pdf.cell(usable_w, 6, _safe_pdf_text(member.full_name or ""), align="C", ln=1)
    ly = pdf.get_y()
    pdf.line(left + usable_w * 0.07, ly, left + usable_w * 0.93, ly)
    pdf.ln(2)

    own_txt = f"Is The Owner Of   {share_qty}   Shares Of Stock Of   {stock_of}"
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_x(left)
    pdf.multi_cell(usable_w, 4.5, _safe_pdf_text(own_txt), align="C")
    pdf.ln(1.5)

    if cert.status == "Revoked":
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(180, 0, 0)
        pdf.set_x(left)
        pdf.cell(usable_w, 6, "STATUS: REVOKED — This certificate is void.", align="C", ln=1)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(1)

    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_x(left)
    pdf.cell(usable_w, 3.5, "CERTIFICATE PARTICULARS", ln=1)
    pdf.set_draw_color(90, 90, 90)
    pdf.line(left, pdf.get_y(), left + usable_w, pdf.get_y())
    pdf.ln(1.5)

    shareholding_block = share_detail
    kv("Certificate number", cert.certificate_no or "—")
    kv("Member reference", member.member_id or "—")
    kv("Shareholding", shareholding_block)
    kv("Date of issue", issued_line)
    kv("Record ID", f"#{cert.id}")
    kv("Recorded by", recorder)

    notes = (cert.notes or "").strip()
    if notes:
        shown = notes[:400] + ("…" if len(notes) > 400 else "")
        pdf.set_x(left)
        pdf.set_font("Helvetica", "B", label_sz)
        pdf.cell(label_w, row_h, _safe_pdf_text("Notes") + ":", border=0, align="L", ln=0)
        pdf.set_font("Helvetica", "", 5.8)
        pdf.multi_cell(usable_w - label_w, 2.9, _safe_pdf_text(shown), align="L")

    pdf.ln(1.25)
    pdf.set_font("Helvetica", "B", 9)
    date_line = f"On the {day_o} Day of {month_n} In the Year {year_n}"
    pdf.set_x(left)
    pdf.cell(usable_w, 5, _safe_pdf_text(date_line), align="C", ln=1)

    pdf.ln(2.25)
    gap = 12.0
    col_w = (usable_w - gap) / 2.0
    y_sig = pdf.get_y()
    pdf.set_font("Helvetica", "", 8)
    pdf.line(left, y_sig, left + col_w, y_sig)
    pdf.line(left + col_w + gap, y_sig, left + 2 * col_w + gap, y_sig)
    pdf.set_xy(left, y_sig + 1.0)
    pdf.cell(col_w, 4, "Signature", align="C", ln=0)
    pdf.cell(gap, 4, "", ln=0)
    pdf.cell(col_w, 4, "Signature", align="C", ln=1)

    cap_y = pdf.get_y() + 0.5
    pdf.set_font("Helvetica", "", 7)
    pdf.set_xy(left, cap_y)
    pdf.cell(col_w, 3.5, _safe_pdf_text(signatory) if signatory else "", align="C", ln=0)
    pdf.cell(gap, 3.5, "", ln=0)
    pdf.cell(col_w, 3.5, _safe_pdf_text(second_sig) if second_sig else "", align="C", ln=1)

    if sign_title or second_title:
        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_x(left)
        pdf.cell(col_w, 3, _safe_pdf_text(sign_title), align="C", ln=0)
        pdf.cell(gap, 3, "", ln=0)
        pdf.cell(col_w, 3, _safe_pdf_text(second_title), align="C", ln=1)

    pdf.ln(2.5)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(35, 35, 35)
    pdf.set_x(left)
    pdf.multi_cell(usable_w, 4, _safe_pdf_text(company), align="C")
    pdf.set_font("Helvetica", "", 7)
    if addr:
        pdf.set_x(left)
        pdf.multi_cell(usable_w, 3.5, _safe_pdf_text(addr), align="C")
    if reg_no:
        pdf.set_x(left)
        pdf.multi_cell(usable_w, 3.5, _safe_pdf_text(reg_no), align="C")
    pdf.set_text_color(0, 0, 0)

    pdf.set_font("Helvetica", "I", 6)
    pdf.set_text_color(100, 100, 100)
    pdf.set_x(left)
    pdf.cell(
        usable_w,
        3,
        _safe_pdf_text(f"Generated from Istithmar Investment Management system · Certificate record #{cert.id}"),
        align="C",
        ln=1,
    )
    pdf.set_text_color(0, 0, 0)

    raw = pdf.output(dest="S")
    if isinstance(raw, str):
        return raw.encode("latin-1", errors="replace")
    return bytes(raw)
