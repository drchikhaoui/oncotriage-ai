"""
Route-level tests for /visual-triage HTML page.
Verifies Alpine.js initialization prerequisites — no browser required.
"""
import json
import re

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_page_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_alpinejs_script_present():
    """Alpine.js CDN script tag must be in <head> with defer."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    assert "alpinejs" in html
    assert 'defer' in html


@pytest.mark.asyncio
async def test_xdata_uses_single_quotes():
    """
    x-data attribute MUST use single quotes so the embedded JSON
    (which contains double quotes) does not break the HTML attribute.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    # Find the x-data attribute — must be single-quoted
    assert "x-data='visualTriage(" in html, (
        "x-data attribute must use single quotes; double-quoted attribute breaks "
        "when JSON (which contains \" chars) is embedded inside it."
    )
    # Must NOT be double-quoted (would break Alpine init)
    assert 'x-data="visualTriage(' not in html


@pytest.mark.asyncio
async def test_embedded_ae_types_json_is_valid():
    """The ae-options API returns all 6 AE types with correct IDs."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage/ae-options")
    assert resp.status_code == 200
    ae_types = resp.json()
    assert isinstance(ae_types, list)
    assert len(ae_types) == 6
    ids = [ae["id"] for ae in ae_types]
    assert "papulopustular_eruption" in ids
    assert "oral_mucositis" in ids
    assert "unsure" in ids


@pytest.mark.asyncio
async def test_visual_triage_js_included():
    """visual_triage.js must be referenced in the page scripts block."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    assert "visual_triage.js" in html


@pytest.mark.asyncio
async def test_all_four_step_divs_present():
    """All four x-show step divs must be in the page."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    assert 'x-show="step === 1"' in html
    assert 'x-show="step === 2"' in html
    assert 'x-show="step === 3"' in html
    assert 'x-show="step === 4"' in html


@pytest.mark.asyncio
async def test_no_capture_attribute_on_file_input():
    """
    capture='environment' must NOT be on the file input.
    On desktop Chrome it blocks the file picker; removing it still prompts
    the camera on iOS/Android via accept='image/*'.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    assert 'capture="environment"' not in html
    assert "capture='environment'" not in html
    # But accept="image/*" must still be present for mobile camera prompting
    assert 'accept="image/*"' in html


@pytest.mark.asyncio
async def test_french_locale_renders():
    """Page renders correctly in French locale."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage?lang=fr")
    assert resp.status_code == 200
    html = resp.text
    assert "x-data='visualTriage(" in html


@pytest.mark.asyncio
async def test_no_clinical_jargon_in_ae_labels():
    """Patient-facing AE labels must not expose clinical terminology."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage/ae-options")
    ae_types = resp.json()

    forbidden_in_labels = [
        "papulopustular", "maculo-papular", "erythrodysesthesia",
        "SJS/TEN", "acneiform", "Rash acneiform",
    ]
    for ae in ae_types:
        label_en = ae["label"].get("en", "")
        desc_en = ae["description"].get("en", "")
        patient_text = label_en + " " + desc_en
        for term in forbidden_in_labels:
            assert term.lower() not in patient_text.lower(), (
                f"Clinical term '{term}' found in patient-facing text for AE '{ae['id']}': {patient_text!r}"
            )


@pytest.mark.asyncio
async def test_ctcae_term_not_rendered_in_card_html():
    """The CTCAE term element must not be rendered as visible text in AE cards."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    # The x-text="ae.ctcae_term" binding must not be in the template
    assert 'x-text="ae.ctcae_term"' not in html


@pytest.mark.asyncio
async def test_unsure_option_present():
    """The 'unsure' option must be available in all AE types."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage/ae-options")
    ae_types = resp.json()
    unsure = next((ae for ae in ae_types if ae["id"] == "unsure"), None)
    assert unsure is not None
    assert "unsure" in unsure["label"]["en"].lower() or "not sure" in unsure["label"]["en"].lower()


@pytest.mark.asyncio
async def test_step2_heading_uses_ae_label_not_ctcae():
    """Step 2 heading must bind to ae.label (patient-friendly), not ae.ctcae_term."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    # Step 2 heading should use selectedAE?.label
    assert 'x-text="getLabel(selectedAE?.label)"' in html


# ─── Sprint C Issue 3: patient-friendly result page ───────────────────────────

@pytest.mark.asyncio
async def test_result_shows_severity_not_ctcae_grade_heading():
    """Step 4 must show 'Severity' heading, not 'CTCAE Visual Grade'."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    assert "Severity" in html
    assert "CTCAE Visual Grade" not in html


@pytest.mark.asyncio
async def test_grade_badge_uses_severity_label():
    """Severity badge must call gradeToSeverity(), not render 'Grade X' at top level."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    assert "gradeToSeverity(" in html


@pytest.mark.asyncio
async def test_field_labels_are_patient_friendly():
    """BSA/Distribution/Morphology must be renamed to patient-friendly labels in Step 4."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    assert "Body Area Affected" in html
    assert "Spread" in html
    assert "Appearance" in html
    # Old clinical terms must not appear as visible labels
    assert "BSA Estimate" not in html
    assert "Distribution" not in html
    assert "Morphology" not in html


@pytest.mark.asyncio
async def test_collapsible_clinical_details_section_present():
    """A <details> collapsible element for 'Clinical details' must exist in Step 4."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    assert "<details" in html
    assert "Clinical details" in html


@pytest.mark.asyncio
async def test_ctcae_grade_number_hidden_in_collapsible():
    """'CTCAE v5.0 Grade:' label must only appear inside the <details> block, not at top level."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    # CTCAE v5.0 Grade label must exist somewhere (in collapsible)
    assert "CTCAE v5.0 Grade" in html
    # But the section before <details> must not contain it
    details_pos = html.find("<details")
    assert details_pos > 0, "<details> element not found"
    pre_details = html[:details_pos]
    assert "CTCAE v5.0 Grade" not in pre_details


@pytest.mark.asyncio
async def test_provider_badge_present_in_step4():
    """Step 4 must include a provider badge showing which AI model was used."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/visual-triage")
    html = resp.text
    assert "provider_used" in html
    assert "Analyzed by:" in html


@pytest.mark.asyncio
async def test_grade_to_severity_in_js():
    """gradeToSeverity helper must be defined in visual_triage.js."""
    import pathlib
    js_path = pathlib.Path("app/static/js/visual_triage.js")
    js_text = js_path.read_text()
    assert "gradeToSeverity" in js_text
    assert "Mild" in js_text
    assert "Moderate" in js_text
    assert "Severe" in js_text
