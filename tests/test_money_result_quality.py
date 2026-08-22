import unittest

from money_result_quality import MAX_CLIENT_RESULTS, apply_money_result_quality


class MoneyResultQualityTests(unittest.TestCase):
    def test_selected_prize_scope_rejects_unrelated_web_result(self):
        payload = {
            "results": [
                {
                    "title": "TRICARE West Region",
                    "description": "TRICARE West beneficiary portal and health plan information.",
                    "url": "https://tricare.triwest.com/",
                    "category": "prize",  # dangerous upstream fallback must not count as evidence
                    "money_record": {"opportunity_id": "bad-1", "opportunity_type": "prize"},
                },
                {
                    "title": "European startup competition — cash prize",
                    "description": "Competition for founders with a cash prize for the winning team.",
                    "url": "https://example.org/startup-prize",
                    "money_record": {"opportunity_id": "good-1", "opportunity_type": "prize"},
                },
            ],
            "money_records": [
                {"opportunity_id": "bad-1", "opportunity_type": "prize"},
                {"opportunity_id": "good-1", "opportunity_type": "prize"},
            ],
        }
        result = apply_money_result_quality(payload, category="prize")
        self.assertEqual([row["title"] for row in result["results"]], ["European startup competition — cash prize"])
        self.assertEqual([row["opportunity_id"] for row in result["money_records"]], ["good-1"])
        self.assertEqual(result["result_quality"]["scope_rejected"], 1)
        self.assertTrue(result["result_quality"]["selected_category_is_requirement_not_evidence"])

    def test_selected_family_requires_source_text_evidence(self):
        payload = {
            "results": [
                {"title": "Random portal", "description": "General account login", "url": "https://example.org/a"},
                {"title": "Public tender for services", "description": "Procurement notice for a service contract", "url": "https://example.org/b"},
            ]
        }
        result = apply_money_result_quality(payload, category="revenue")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["title"], "Public tender for services")

    def test_duplicate_urls_and_titles_are_removed(self):
        payload = {
            "results": [
                {"title": "Cash prize competition", "description": "cash prize", "url": "https://example.org/call?utm_source=x"},
                {"title": "Cash prize competition", "description": "cash prize", "url": "https://example.org/call?utm_source=y"},
            ]
        }
        result = apply_money_result_quality(payload, category="prize")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["result_quality"]["duplicates_removed"], 1)

    def test_client_payload_is_bounded(self):
        rows = [
            {"title": f"Opportunity {index}", "description": "general information", "url": f"https://example.org/{index}"}
            for index in range(MAX_CLIENT_RESULTS + 25)
        ]
        result = apply_money_result_quality({"results": rows}, category="all")
        self.assertEqual(len(result["results"]), MAX_CLIENT_RESULTS)
        self.assertEqual(result["result_quality"]["truncated"], 25)

    def test_card_explanation_is_truthful_and_structured(self):
        payload = {
            "results": [{
                "title": "Founder cash prize",
                "description": "A founder competition offers a cash prize to the winner.",
                "url": "https://example.org/prize",
                "money_record": {
                    "opportunity_id": "call-1",
                    "opportunity_type": "prize",
                    "amount": {"min": 5000, "max": 5000, "currency": "EUR"},
                    "source_observed": False,
                    "current_call_verified": False,
                    "eligibility_state": "unknown",
                },
            }],
            "money_records": [{"opportunity_id": "call-1"}],
        }
        result = apply_money_result_quality(payload, category="prize")
        explanation = result["results"][0]["ui_explanation"]
        self.assertIn("cash prize", explanation["about"].lower())
        self.assertIn("prize", explanation["why"])
        self.assertIn("5000", explanation["value"])
        self.assertIn("не підтверджена", explanation["uncertainty"])


if __name__ == "__main__":
    unittest.main()
