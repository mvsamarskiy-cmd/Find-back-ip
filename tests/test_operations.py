import importlib.util
import json
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "railway_guard", ROOT / "verification" / "railway_guard.py"
)
RAILWAY_GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RAILWAY_GUARD)


def environment(project_id, project_name, repo, variables=None, custom=None):
    return {
        "id": project_id,
        "name": project_name,
        "buckets": {"edges": []},
        "environments": {"edges": [{"node": {
            "id": f"env-{project_id}",
            "name": "production",
            "isEphemeral": False,
            "variables": {"edges": [
                {"node": {"name": name, "serviceId": "service", "isSealed": False}}
                for name in (variables or [])
            ]},
            "volumeInstances": {"edges": []},
            "serviceInstances": {"edges": [{"node": {
                "serviceId": "service",
                "serviceName": "web",
                "source": {"repo": repo, "image": None},
                "domains": {
                    "serviceDomains": [{"domain": f"{project_name}.up.railway.app"}],
                    "customDomains": [
                        {"domain": domain} for domain in (custom or [])
                    ],
                },
                "latestDeployment": {
                    "id": "deployment",
                    "status": "SUCCESS",
                    "createdAt": "2026-08-17T22:47:02.949Z",
                    "deploymentStopped": False,
                },
            }}]},
        }}]},
    }


class OperationsTests(TestCase):
    def setUp(self):
        self.manifest = json.loads(
            (ROOT / "ops" / "railway-production.json").read_text(encoding="utf-8")
        )

    def test_manifest_matches_committed_production_target(self):
        self.assertEqual(
            self.manifest["project"]["id"],
            "ba6f4d56-5ad6-4ad2-be1d-816c3c7d7a88",
        )
        self.assertEqual(
            self.manifest["productionUrl"],
            "https://web-production-04fec.up.railway.app",
        )
        self.assertEqual(self.manifest["deploymentBranch"], "main")

    def test_audit_separates_canonical_and_shadow_projects(self):
        repo = self.manifest["repository"]
        canonical = environment(
            self.manifest["project"]["id"],
            self.manifest["project"]["name"],
            repo,
            variables=["OPENAI_API_KEY"],
        )
        shadow = environment("shadow-id", "shadow", repo)
        unrelated = environment("other-id", "other", "owner/other")
        payload = {"workspace": {
            "id": self.manifest["workspace"]["id"],
            "name": "workspace",
            "projects": {"edges": [
                {"node": canonical}, {"node": shadow}, {"node": unrelated}
            ]},
        }}

        report = RAILWAY_GUARD.analyze_workspace(payload, self.manifest)

        self.assertEqual(report["canonical"]["projectId"], canonical["id"])
        self.assertEqual([item["projectId"] for item in report["shadows"]], ["shadow-id"])
        self.assertTrue(all(report["shadows"][0]["deletionSafety"].values()))

    def test_custom_domain_blocks_clean_shadow_classification(self):
        repo = self.manifest["repository"]
        canonical = environment(
            self.manifest["project"]["id"],
            self.manifest["project"]["name"],
            repo,
        )
        shadow = environment("shadow-id", "shadow", repo, custom=["example.com"])
        payload = {"workspace": {
            "id": self.manifest["workspace"]["id"],
            "name": "workspace",
            "projects": {"edges": [{"node": canonical}, {"node": shadow}]},
        }}

        report = RAILWAY_GUARD.analyze_workspace(payload, self.manifest)

        self.assertFalse(report["shadows"][0]["deletionSafety"]["noCustomDomains"])

