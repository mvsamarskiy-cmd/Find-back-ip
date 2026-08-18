import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import provenance


class ProvenanceTests(TestCase):
    def test_generation_metadata_records_model_versions_and_source(self):
        with patch.dict(os.environ, {"OPENAI_MODEL": "test-model-2026"}, clear=False):
            metadata = provenance.generation_provenance("local_lexical_expansion")

        self.assertEqual(metadata["generator_version"], "namemachine-generator-v3")
        self.assertEqual(metadata["naming_prompt_version"], "naming-prompt-v2")
        self.assertEqual(metadata["prompt_intelligence_version"], "prompt-intelligence-v1")
        self.assertEqual(metadata["model"], "test-model-2026")
        self.assertEqual(metadata["candidate_source"], "local_lexical_expansion")
        self.assertEqual(metadata["candidate_schema_version"], "candidate-result-v2")

    def test_annotation_copies_rows_and_preserves_source_specific_metadata(self):
        original = {"name": "Botella", "candidate_source": "local_lexical_expansion"}
        output = provenance.annotate_generated_candidates([original])

        self.assertIsNot(output[0], original)
        self.assertNotIn("generation_provenance", original)
        self.assertEqual(
            output[0]["generation_provenance"]["candidate_source"],
            "local_lexical_expansion",
        )

    def test_generator_install_is_idempotent_and_updates_app_reference(self):
        calls = []

        def generator(*args, **kwargs):
            calls.append((args, kwargs))
            return [{"name": "Glasetta"}]

        ai_module = SimpleNamespace(generate_ai_names=generator)
        app_module = SimpleNamespace(generate_ai_names=generator)

        first = provenance.install_generation_provenance(ai_module, app_module)
        second = provenance.install_generation_provenance(ai_module, app_module)
        rows = app_module.generate_ai_names("brief", count=1)

        self.assertIs(first, second)
        self.assertIs(app_module.generate_ai_names, first)
        self.assertEqual(len(calls), 1)
        self.assertEqual(rows[0]["name"], "Glasetta")
        self.assertEqual(
            rows[0]["generation_provenance"]["generator_version"],
            provenance.GENERATOR_VERSION,
        )

    def test_verification_metadata_is_embedded_in_each_verdict(self):
        import availability_v2

        result = {
            "verification": {
                "telegram": {"verdict": "claimable"},
                "youtube": {"verdict": "unknown"},
            }
        }
        enriched = availability_v2._attach_verification_provenance(result)

        self.assertEqual(
            enriched["verification_provenance"]["verification_engine_version"],
            provenance.VERIFICATION_ENGINE_VERSION,
        )
        for verdict in enriched["verification"].values():
            self.assertEqual(
                verdict["verification_engine_version"],
                provenance.VERIFICATION_ENGINE_VERSION,
            )
            self.assertEqual(
                verdict["evidence_fusion_version"],
                provenance.EVIDENCE_FUSION_VERSION,
            )
