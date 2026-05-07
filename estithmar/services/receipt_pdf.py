"""Contribution receipt HTML → PDF (Playwright)."""

from __future__ import annotations

import logging
import os
import time

from estithmar.models import Contribution, ShareSubscription
from estithmar.services.membership_form_pdf import _logo_data_uri

logger = logging.getLogger(__name__)

_CHROMIUM_EXECUTABLE_ENV = "ESTITHMAR_CHROMIUM_EXECUTABLE"


def _chromium_executable() -> str | None:
    path = (os.environ.get(_CHROMIUM_EXECUTABLE_ENV) or "").strip()
    return path if path and os.path.isfile(path) else None


def build_contribution_receipt_pdf_bytes(
    *,
    c: Contribution,
    receipt_schedule: list | None,
    subscription: ShareSubscription | None,
    settings,
    extra: dict,
    receipt_url: str,
    member_sub_outstanding,
) -> bytes:
    """Render ``receipt_print.html`` and print to PDF via headless Chromium."""
    from flask import render_template, request

    logo_data_uri = _logo_data_uri()
    html = render_template(
        "contributions/receipt_print.html",
        c=c,
        receipt_schedule=receipt_schedule,
        subscription=subscription,
        settings=settings,
        extra=extra,
        receipt_url=receipt_url,
        member_sub_outstanding=member_sub_outstanding,
        logo_data_uri=logo_data_uri,
    )
    base = (request.url_root if request else None) or "http://127.0.0.1/"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is required for receipt PDFs. "
            "Install: pip install playwright && python -m playwright install chromium"
        ) from e

    _launch_args = (
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--font-render-hinting=medium",
    )
    _exe = _chromium_executable()
    with sync_playwright() as p:
        launch_kw: dict = {"headless": True, "args": list(_launch_args)}
        if _exe:
            launch_kw["executable_path"] = _exe
        browser = p.chromium.launch(**launch_kw)
        context = None
        try:
            context = browser.new_context(
                viewport={"width": 820, "height": 1200},
                device_scale_factor=1,
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
            time.sleep(0.5)
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "10mm", "right": "12mm", "bottom": "10mm", "left": "12mm"},
                prefer_css_page_size=True,
            )
        finally:
            if context is not None:
                context.close()
            browser.close()

    if not pdf_bytes or len(pdf_bytes) < 64 or not pdf_bytes.startswith(b"%PDF"):
        raise RuntimeError("Chromium produced empty or invalid PDF bytes (expected %PDF header).")
    logger.info("Contribution receipt PDF (Playwright): %d bytes, contribution_id=%s", len(pdf_bytes), c.id)
    return pdf_bytes
