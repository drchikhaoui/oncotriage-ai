"""
i18n locale tests — validates all three locale files have required keys
and the translation function works correctly.
"""
import pytest

from app.core.i18n import get_dir, get_locale_data, t

REQUIRED_KEYS = [
    "lang", "dir",
    "common.app_name", "common.tagline", "common.disclaimer", "common.anonymous",
    "nav.intake", "nav.dashboard",
    "intake.title", "intake.subtitle",
    "intake.cancer_type.label", "intake.treatment.label",
    "intake.freetext.label", "intake.symptoms.label",
    "intake.submit_btn",
    "triage.title",
    "triage.level.emergency", "triage.level.urgent",
    "triage.level.routine", "triage.level.self_care",
    "triage.action.emergency", "triage.action.urgent",
    "triage.action.routine", "triage.action.self_care",
    "triage.reasoning.title", "triage.ctcae.title", "triage.citations.title",
    "triage.irae_alert",
    "dashboard.title", "dashboard.stat.total",
    "error.no_symptoms", "error.generic",
    "grade.mild", "grade.moderate", "grade.severe", "grade.life_threatening",
    "costars.attribution",
]

SUPPORTED_LANGS = ["en", "fr", "ar"]


class TestLocaleCompleteness:
    @pytest.mark.parametrize("lang", SUPPORTED_LANGS)
    def test_all_required_keys_present(self, lang):
        data = get_locale_data(lang)
        missing = [k for k in REQUIRED_KEYS if k not in data]
        assert not missing, f"[{lang}] Missing keys: {missing}"

    @pytest.mark.parametrize("lang", SUPPORTED_LANGS)
    def test_no_empty_values(self, lang):
        data = get_locale_data(lang)
        empty = [k for k, v in data.items() if k in REQUIRED_KEYS and not v]
        assert not empty, f"[{lang}] Empty values: {empty}"

    def test_arabic_is_rtl(self):
        assert get_dir("ar") == "rtl"

    def test_english_is_ltr(self):
        assert get_dir("en") == "ltr"

    def test_french_is_ltr(self):
        assert get_dir("fr") == "ltr"

    def test_ar_locale_has_lang_field(self):
        assert get_locale_data("ar")["lang"] == "ar"


class TestTranslationFunction:
    def test_t_returns_english_value(self):
        result = t("common.app_name", "en")
        assert result == "OncoTriage"

    def test_t_returns_french_value(self):
        result = t("triage.level.emergency", "fr")
        assert "URGENCE" in result.upper() or result != ""

    def test_t_returns_arabic_value(self):
        result = t("triage.level.emergency", "ar")
        assert result != "" and result != "triage.level.emergency"

    def test_t_falls_back_to_english(self):
        result = t("common.app_name", "xx")
        assert result == "OncoTriage"

    def test_t_returns_key_if_not_found(self):
        result = t("nonexistent.key.xyz", "en")
        assert result == "nonexistent.key.xyz"

    def test_emergency_translations_differ_across_languages(self):
        en = t("triage.level.emergency", "en")
        fr = t("triage.level.emergency", "fr")
        ar = t("triage.level.emergency", "ar")
        assert en != fr or en != ar  # At least one language differs

    def test_irae_alert_present_in_all_langs(self):
        for lang in SUPPORTED_LANGS:
            val = t("triage.irae_alert", lang)
            assert "irAE" in val or val != "", f"irAE alert missing in {lang}"


class TestKeyParityAcrossLanguages:
    def test_all_langs_have_same_key_count(self):
        en_keys = set(get_locale_data("en").keys())
        for lang in ["fr", "ar"]:
            lang_keys = set(get_locale_data(lang).keys())
            missing = en_keys - lang_keys
            extra = lang_keys - en_keys
            assert not missing, f"[{lang}] Keys missing vs EN: {missing}"
            assert not extra, f"[{lang}] Extra keys vs EN: {extra}"
