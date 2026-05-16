"""Tests that patient-facing strings are not hardcoded in JS."""
import json
import pathlib


def test_no_hardcoded_english_triage_actions_in_js():
    js_path = pathlib.Path("app/static/js/visual_triage.js")
    content = js_path.read_text()
    assert "Call 911" not in content
    assert "Contact your oncology team NOW" not in content
    assert "Schedule an appointment within" not in content


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
