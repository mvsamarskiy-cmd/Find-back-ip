import unittest
from unittest.mock import patch

import session_api
from session_provenance import (
    clean_generation_provenance,
    clean_verification_provenance,
    install_session_provenance,
)
from session_store import SessionStore
from telegram_bootstrap import app


class SessionProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore("sqlite+pysqlite:///:memory:")
        self.patcher = patch.object(session_api, "STORE", self.store)
        self.patcher.start()
        self.client = app.test_client()

    def tearDown(self):
        self.patcher.stop()

    def _create(self):
        response = self.client.post(
            "/api/sessions",
            json={
                "client_session_id": "provenance-local",
                "title": "Provenance test",
                "resources": ["telegram"],
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def test_bootstrap_installs_wrapper_once(self):
        wrapped = session_api._clean_candidate
        self.assertTrue(getattr(wrapped, "_namemachine_provenance_persistence", False))
        self.assertIs(install_session_provenance(session_api), wrapped)

    def test_candidate_round_trip_preserves_bounded_provenance(self):
        created = self._create()
        headers = {session_api.TOKEN_HEADER: created["session_token"]}
        path = f"/api/sessions/{created['session_id']}/candidates/batch"
        candidate = {
            "name": "Botella",
            "checked": True,
            "availability": {
                "telegram": {"status": "claimable", "source": "telegram_evidence_service"}
            },
            "verification": {
                "telegram": {
                    "verdict": "claimable",
                    "verification_engine_version": "verification-engine-v2",
                    "evidence_fusion_version": "evidence-fusion-v2",
                }
            },
            "generation_provenance": {
                "generator_version": "namemachine-generator-v3",
                "naming_prompt_version": "naming-prompt-v2",
                "prompt_intelligence_version": "prompt-intelligence-v1",
                "model": "gpt-5.6-luna",
                "candidate_source": "openai",
                "candidate_schema_version": "candidate-result-v2",
                "unexpected": "must-not-persist",
            },
            "verification_provenance": {
                "verification_engine_version": "verification-engine-v2",
                "evidence_fusion_version": "evidence-fusion-v2",
                "candidate_schema_version": "candidate-result-v2",
                "secret_like_extra": "must-not-persist",
            },
        }

        response = self.client.post(
            path,
            json={"candidates": [candidate]},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)

        loaded = self.client.get(
            f"/api/sessions/{created['session_id']}",
            headers=headers,
        ).get_json()["session"]
        row = loaded["results"][0]
        self.assertEqual(
            row["generation_provenance"]["generator_version"],
            "namemachine-generator-v3",
        )
        self.assertEqual(
            row["verification_provenance"]["verification_engine_version"],
            "verification-engine-v2",
        )
        self.assertNotIn("unexpected", row["generation_provenance"])
        self.assertNotIn("secret_like_extra", row["verification_provenance"])
        self.assertEqual(
            row["verification"]["telegram"]["verification_engine_version"],
            "verification-engine-v2",
        )

    def test_cleaners_bound_strings_and_reject_arbitrary_shapes(self):
        generation = clean_generation_provenance({
            "generator_version": "x" * 200,
            "model": "model" * 30,
            "other": "drop",
        })
        self.assertEqual(len(generation["generator_version"]), 64)
        self.assertLessEqual(len(generation["model"]), 96)
        self.assertNotIn("other", generation)
        self.assertIsNone(clean_generation_provenance(["bad"]))

        verification = clean_verification_provenance({
            "verification_engine_version": "verification-engine-v2",
            "evidence_fusion_version": "evidence-fusion-v2",
        })
        self.assertEqual(
            verification["evidence_fusion_version"],
            "evidence-fusion-v2",
        )


if __name__ == "__main__":
    unittest.main()
