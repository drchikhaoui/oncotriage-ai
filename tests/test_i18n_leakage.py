"""Tests that patient-facing strings are not hardcoded in JS."""
import json
import pathlib
import re


def test_visual_triage_js_has_no_hardcoded_english_patient_text():
    """Patient-facing strings must come from i18n locale data, not JS constants."""
    js = pathlib.Path("app/static/js/visual_triage.js").read_text()
    forbidden_patterns = [
        r"Go to the Emergency",
        r"Contact your oncology team",
        r"Book an appointment",
        r"Schedule an appointment",
        r"Manage at home",
        r"Call (911|999|112|15|190)",
    ]
    found = [pat for pat in forbidden_patterns if re.search(pat, js)]
    assert not found, (
        f"Patient-facing strings found in visual_triage.js: {found}. "
        "These must come from locale files, not JS constants."
    )


def test_no_hardcoded_processing_steps_in_js():
    js_path = pathlib.Path("app/static/js/visual_triage.js")
    content = js_path.read_text()
    assert "Uploading image securely" not in content
    assert "Stripping image metadata (EXIF)" not in content
    assert "Analyzing with AI vision" not in content


def test_locale_files_have_triage_action_keys():
    required_keys = [
        "triage.action.emergency",
        "triage.action.urgent",
        "triage.action.routine",
        "triage.action.self_care",
        "triage.emergency_number",
    ]
    for locale in ["en", "fr", "ar"]:
        data = json.loads(pathlib.Path(f"app/locales/{locale}.json").read_text())
        for key in required_keys:
            assert key in data, f"Key '{key}' missing from {locale}.json"


def test_locale_files_have_processing_step_keys():
    required_keys = [
        "visual_triage.processing.uploading",
        "visual_triage.processing.stripping_exif",
        "visual_triage.processing.analyzing",
        "visual_triage.processing.cross_referencing",
        "visual_triage.processing.applying_rules",
        "visual_triage.processing.building_trace",
    ]
    for locale in ["en", "fr", "ar"]:
        data = json.loads(pathlib.Path(f"app/locales/{locale}.json").read_text())
        for key in required_keys:
            assert key in data, f"Key '{key}' missing from {locale}.json"


def test_locale_parity_all_three_languages():
    """All three locale files must have the same set of keys."""
    en_keys = set(json.loads(pathlib.Path("app/locales/en.json").read_text()).keys())
    fr_keys = set(json.loads(pathlib.Path("app/locales/fr.json").read_text()).keys())
    ar_keys = set(json.loads(pathlib.Path("app/locales/ar.json").read_text()).keys())
    assert en_keys == fr_keys, f"FR missing keys: {en_keys - fr_keys}"
    assert en_keys == ar_keys, f"AR missing keys: {en_keys - ar_keys}"
