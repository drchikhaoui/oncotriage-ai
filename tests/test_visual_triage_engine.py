"""
Tests for the visual triage engine pipeline.
All external API calls are mocked.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.visual_triage_engine import analyze_image, get_available_aes
from app.integrations.vision_providers.base import VisionResponse
from app.models.patient import PatientContext, TreatmentModality
from app.models.triage import TriageLevel
from app.models.visual_assessment import (
    CTCAEGradeVisual,
    ImageQuality,
    VisualAssessment,
    VisualFindings,
)

FIXTURES = Path(__file__).parent / "fixtures"
IMAGES = FIXTURES / "images"
MOCKS = FIXTURES / "mock_responses"


def _read_image(name: str) -> bytes:
    return (IMAGES / name).read_bytes()


def _make_assessment(grade: int | None = 2, adequate: bool = True, ae_match: bool = True) -> VisualAssessment:
    return VisualAssessment(
        image_quality=ImageQuality(adequate=adequate, issues=[] if adequate else ["blurry"], retake_recommended=not adequate),
        ae_match=ae_match,
        ae_match_explanation="Test explanation",
        visual_findings=VisualFindings(
            body_surface_area_percent_estimate=15,
            distribution="regional",
            primary_morphology=["papules"],
            secondary_features=[],
            anatomical_site="face",
        ) if (adequate and ae_match and grade) else None,
        ctcae_grade_visual=CTCAEGradeVisual(
            grade=grade,
            ctcae_descriptor=f"Grade {grade} descriptor",
            confidence="moderate",
        ) if (adequate and ae_match and grade) else None,
        caveats=["Test caveat"],
    )


def _make_vision_response(assessment: VisualAssessment, provider: str = "Gemini") -> VisionResponse:
    """Wrap a VisualAssessment in a VisionResponse (what the chain returns)."""
    return VisionResponse(
        assessment_dict=assessment.model_dump(),
        provider_used=provider,
        model_used="gemini-2.5-flash",
        latency_ms=100,
    )


def _targeted_patient():
    return PatientContext(
        session_id="vis-test",
        treatment_modalities=[TreatmentModality.TARGETED_THERAPY],
    )


def _immunotherapy_patient():
    return PatientContext(
        session_id="vis-irae-test",
        treatment_modalities=[TreatmentModality.IMMUNOTHERAPY],
    )


def _mock_chain(assessment: VisualAssessment, provider: str = "Gemini"):
    """Return a mock FallbackChain whose analyze() returns the given assessment."""
    chain = MagicMock()
    chain.analyze = AsyncMock(return_value=_make_vision_response(assessment, provider))
    return chain


# ─── AE availability ──────────────────────────────────────────────────────────

class TestGetAvailableAEs:
    def test_immunotherapy_shows_checkpoint_dermatitis(self):
        aes = get_available_aes(["immunotherapy"])
        ids = [ae["id"] for ae in aes]
        assert "checkpoint_dermatitis" in ids

    def test_targeted_shows_papulopustular(self):
        aes = get_available_aes(["targeted_therapy"])
        ids = [ae["id"] for ae in aes]
        assert "papulopustular_eruption" in ids

    def test_radiation_shows_radiation_dermatitis(self):
        aes = get_available_aes(["radiation"])
        ids = [ae["id"] for ae in aes]
        assert "radiation_dermatitis" in ids

    def test_cytotoxic_shows_hand_foot_and_mucositis(self):
        aes = get_available_aes(["cytotoxic_chemo"])
        ids = [ae["id"] for ae in aes]
        assert "hand_foot_syndrome" in ids
        assert "oral_mucositis" in ids

    def test_no_modalities_returns_all(self):
        aes = get_available_aes([])
        assert len(aes) == 6  # 5 specific AEs + unsure

    def test_unsure_always_included_with_any_modality(self):
        """The 'unsure' option must appear regardless of which modality is selected."""
        for modality in ["targeted_therapy", "immunotherapy", "cytotoxic_chemo", "radiation"]:
            aes = get_available_aes([modality])
            ids = [ae["id"] for ae in aes]
            assert "unsure" in ids, f"'unsure' missing when modality={modality}"

    def test_invalid_ae_raises_in_engine(self):
        """Unknown AE type must raise ValueError."""
        with pytest.raises(ValueError, match="Unknown AE type"):
            import asyncio
            asyncio.run(analyze_image(b"x", "test.jpg", "not_an_ae_type", _targeted_patient()))


# ─── Pipeline: happy path ──────────────────────────────────────────────────────

class TestAnalyzeImagePipeline:
    @pytest.mark.asyncio
    async def test_grade3_targeted_is_urgent(self):
        """Grade 3 skin rash always escalates to URGENT regardless of modality."""
        assessment = _make_assessment(grade=3)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"

            result = await analyze_image(
                image_bytes=b"fake",
                filename="test.jpg",
                suspected_ae="papulopustular_eruption",
                patient=_targeted_patient(),
            )

        assert result.status == "success"
        assert result.triage_level in (TriageLevel.URGENT, TriageLevel.EMERGENCY)

    @pytest.mark.asyncio
    async def test_grade2_targeted_is_routine(self):
        """Grade 2 skin rash without immunotherapy = ROUTINE per COSTaRS v2020."""
        assessment = _make_assessment(grade=2)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"

            result = await analyze_image(
                image_bytes=b"fake",
                filename="test.jpg",
                suspected_ae="papulopustular_eruption",
                patient=_targeted_patient(),
            )

        assert result.status == "success"
        assert result.triage_level == TriageLevel.ROUTINE

    @pytest.mark.asyncio
    async def test_grade3_immunotherapy_is_emergency(self):
        assessment = _make_assessment(grade=3)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"

            result = await analyze_image(
                image_bytes=b"fake",
                filename="test.jpg",
                suspected_ae="checkpoint_dermatitis",
                patient=_immunotherapy_patient(),
            )

        assert result.status == "success"
        assert result.triage_level == TriageLevel.EMERGENCY
        assert result.irae_suspected is True

    @pytest.mark.asyncio
    async def test_inadequate_image_returns_retake_status(self):
        assessment = _make_assessment(adequate=False)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"

            result = await analyze_image(
                image_bytes=b"fake",
                filename="blurry.jpg",
                suspected_ae="papulopustular_eruption",
                patient=_targeted_patient(),
            )

        assert result.status == "retake_required"
        assert result.triage_level is None

    @pytest.mark.asyncio
    async def test_ae_no_match_returns_ambiguous(self):
        assessment = _make_assessment(ae_match=False)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"

            result = await analyze_image(
                image_bytes=b"fake",
                filename="test.jpg",
                suspected_ae="papulopustular_eruption",
                patient=_targeted_patient(),
            )

        assert result.status == "ambiguous"

    @pytest.mark.asyncio
    async def test_result_has_thumbnail_data_url(self):
        assessment = _make_assessment(grade=2)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,TESTTHUMB"

            result = await analyze_image(b"fake", "test.jpg", "papulopustular_eruption", _targeted_patient())

        assert result.thumbnail_data_url == "data:image/jpeg;base64,TESTTHUMB"

    @pytest.mark.asyncio
    async def test_result_has_provider_info(self):
        """VisualTriageResult must expose which provider/model was used."""
        assessment = _make_assessment(grade=2)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment, provider="Groq")), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"
            result = await analyze_image(b"fake", "test.jpg", "papulopustular_eruption", _targeted_patient())

        assert result.provider_used == "Groq"
        assert result.model_used == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_all_6_ae_types_route_without_error(self):
        """Smoke test: all 6 AE types (including unsure) should complete pipeline without raising."""
        ae_types = [
            "papulopustular_eruption",
            "hand_foot_syndrome",
            "checkpoint_dermatitis",
            "radiation_dermatitis",
            "oral_mucositis",
            "unsure",
        ]
        for ae_type in ae_types:
            assessment = _make_assessment(grade=2)
            patient = PatientContext(session_id="smoke", treatment_modalities=[
                TreatmentModality.IMMUNOTHERAPY,
                TreatmentModality.CYTOTOXIC_CHEMO,
                TreatmentModality.TARGETED_THERAPY,
                TreatmentModality.RADIATION,
            ])
            with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
                 patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
                 patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
                 patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
                mock_prep.return_value = (b"jpeg", "image/jpeg")
                mock_thumb.return_value = "data:image/jpeg;base64,xyz"
                result = await analyze_image(b"fake", "test.jpg", ae_type, patient)
            assert result.status == "success", f"AE type {ae_type} failed: {result.status}"


# ─── Privacy guarantees ────────────────────────────────────────────────────────

class TestPrivacyGuarantees:
    @pytest.mark.asyncio
    async def test_image_bytes_not_in_result(self):
        """VisualTriageResult must not contain image bytes anywhere."""
        assessment = _make_assessment(grade=2)
        sentinel = b"SENTINEL_IMAGE_BYTES_12345"

        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (sentinel, "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"
            result = await analyze_image(sentinel, "test.jpg", "papulopustular_eruption", _targeted_patient())

        result_json = result.model_dump_json()
        assert b"SENTINEL_IMAGE_BYTES_12345".decode() not in result_json
        assert "SENTINEL" not in result_json

    @pytest.mark.asyncio
    async def test_thumbnail_is_data_url_not_raw_bytes(self):
        """Thumbnail must be a data URL string, never raw bytes."""
        assessment = _make_assessment(grade=1)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,abc123"
            result = await analyze_image(b"fake", "test.jpg", "hand_foot_syndrome", _targeted_patient())

        assert isinstance(result.thumbnail_data_url, str)
        assert result.thumbnail_data_url.startswith("data:image/")


# ─── Unsure AE open-classification path ───────────────────────────────────────

class TestUnsureAEType:
    @pytest.mark.asyncio
    async def test_unsure_routes_through_pipeline(self):
        """'unsure' AE type must complete pipeline without raising."""
        assessment = _make_assessment(grade=2)
        patient = PatientContext(
            session_id="unsure-test",
            treatment_modalities=[TreatmentModality.TARGETED_THERAPY],
        )
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"
            result = await analyze_image(b"fake", "test.jpg", "unsure", patient)

        assert result.status == "success"
        assert result.triage_level is not None

    @pytest.mark.asyncio
    async def test_unsure_uses_open_classification_prompt(self):
        """When 'unsure' is selected, the prompt sent to the chain must not pre-specify an AE."""
        from app.integrations.vision_providers.prompts import _OPEN_CLASSIFICATION_SUFFIX

        assessment = _make_assessment(grade=2)
        patient = PatientContext(session_id="unsure-prompt-test", treatment_modalities=[])
        chain = _mock_chain(assessment)

        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=chain), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"
            await analyze_image(b"fake", "test.jpg", "unsure", patient)

        prompt_used = chain.analyze.call_args[1]["prompt"]
        assert _OPEN_CLASSIFICATION_SUFFIX.strip() in prompt_used
        assert "open classification" in prompt_used.lower()


# ─── Sprint C: anatomical location flow ───────────────────────────────────────

class TestAnatomicalLocationFlow:
    @pytest.mark.asyncio
    async def test_location_stored_in_result(self):
        """anatomical_location kwarg must appear as anatomical_location_hint in result."""
        assessment = _make_assessment(grade=2)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"
            result = await analyze_image(
                b"fake", "test.jpg", "papulopustular_eruption",
                _targeted_patient(), anatomical_location="face, neck",
            )

        assert result.anatomical_location_hint == "face, neck"

    @pytest.mark.asyncio
    async def test_empty_location_gives_none_hint(self):
        """An empty string anatomical_location must store None (not empty string) in result."""
        assessment = _make_assessment(grade=1)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"
            result = await analyze_image(
                b"fake", "test.jpg", "papulopustular_eruption",
                _targeted_patient(), anatomical_location="",
            )

        assert result.anatomical_location_hint is None

    @pytest.mark.asyncio
    async def test_location_injected_into_prompt(self):
        """anatomical_location must appear in the prompt sent to the vision chain."""
        assessment = _make_assessment(grade=2)
        chain = _mock_chain(assessment)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=chain), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"
            await analyze_image(
                b"fake", "test.jpg", "hand_foot_syndrome",
                _targeted_patient(), anatomical_location="left palm",
            )

        prompt_used = chain.analyze.call_args[1]["prompt"]
        assert "left palm" in prompt_used

    @pytest.mark.asyncio
    async def test_location_preserved_on_retake_path(self):
        """anatomical_location_hint must be set even when image quality is poor."""
        assessment = _make_assessment(adequate=False)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"
            result = await analyze_image(
                b"fake", "blurry.jpg", "papulopustular_eruption",
                _targeted_patient(), anatomical_location="chest",
            )

        assert result.status == "retake_required"
        assert result.anatomical_location_hint == "chest"


# ─── Sprint C: AE-specific clinical rules ─────────────────────────────────────

class TestAESpecificRules:
    @pytest.mark.asyncio
    async def test_papulopustular_g2_rule_mentions_doxycycline(self):
        """Grade 2 EGFR rash rule must include doxycycline guidance."""
        assessment = _make_assessment(grade=2)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"
            result = await analyze_image(
                b"fake", "test.jpg", "papulopustular_eruption", _targeted_patient(),
            )

        assert result.triage_rules, "Expected at least one rule"
        rule_text = " ".join(r.get("reasoning", "") for r in result.triage_rules)
        assert "doxycycline" in rule_text.lower()

    @pytest.mark.asyncio
    async def test_oral_mucositis_g2_rule_id_is_mucositis(self):
        """Grade 2 mucositis rule ID must start with MUC- not SKIN-."""
        assessment = _make_assessment(grade=2)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"
            result = await analyze_image(
                b"fake", "test.jpg", "oral_mucositis",
                PatientContext(session_id="muc-test", treatment_modalities=[]),
            )

        rule_ids = [r.get("id", "") for r in result.triage_rules]
        assert any(rid.startswith("MUC-") for rid in rule_ids), f"Got: {rule_ids}"
        assert not any(rid.startswith("SKIN-") for rid in rule_ids), f"SKIN rule leaked: {rule_ids}"

    @pytest.mark.asyncio
    async def test_generic_skin_rule_not_present_when_ae_specific_available(self):
        """SKIN- prefixed generic rules must be absent when an AE-specific rule exists."""
        assessment = _make_assessment(grade=2)
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"
            result = await analyze_image(
                b"fake", "test.jpg", "hand_foot_syndrome", _targeted_patient(),
            )

        rule_ids = [r.get("id", "") for r in result.triage_rules]
        assert not any(rid.startswith("SKIN-") for rid in rule_ids), f"Generic SKIN rule leaked: {rule_ids}"

    @pytest.mark.asyncio
    async def test_radiation_g3_rule_mentions_radiation(self):
        """Grade 3 radiation dermatitis rule must reference radiation-specific guidance."""
        assessment = _make_assessment(grade=3)
        patient = PatientContext(
            session_id="rad-test",
            treatment_modalities=[TreatmentModality.RADIATION],
        )
        with patch("app.core.visual_triage_engine.gemini_vision.preprocess_image") as mock_prep, \
             patch("app.core.visual_triage_engine.gemini_vision.make_thumbnail") as mock_thumb, \
             patch("app.core.visual_triage_engine.get_chain", return_value=_mock_chain(assessment)), \
             patch("app.core.visual_triage_engine._build_enrichment", AsyncMock(return_value=None)):
            mock_prep.return_value = (b"jpeg", "image/jpeg")
            mock_thumb.return_value = "data:image/jpeg;base64,xyz"
            result = await analyze_image(
                b"fake", "test.jpg", "radiation_dermatitis", patient,
            )

        rule_text = " ".join(r.get("reasoning", "") for r in result.triage_rules)
        assert "radiation" in rule_text.lower()
