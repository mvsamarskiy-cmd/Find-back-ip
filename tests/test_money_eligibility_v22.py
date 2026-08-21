import unittest

from money_eligibility import compile_eligibility_profile, evaluate_eligibility, extract_eligibility_rules
from money_eligibility_apply import apply_eligibility_to_payload
from money_query_planner import compile_money_profile


class MoneyEligibilityRuleTests(unittest.TestCase):
    def test_extracts_explicit_company_requirements(self):
        text = (
            "Open to SMEs registered in Poland. Company operating at least 2 years. "
            "Maximum 250 employees. Annual turnover below 50 million EUR. "
            "Own contribution at least 20%."
        )
        rules = extract_eligibility_rules(text)
        ids = {row["id"] for row in rules}
        self.assertIn("applicant:sme", ids)
        self.assertIn("geography:PL", ids)
        self.assertIn("company_age:gte", ids)
        self.assertIn("employees:lte", ids)
        self.assertIn("turnover:lte:EUR", ids)
        self.assertIn("own_contribution:gte", ids)

    def test_missing_profile_fact_is_unknown_not_false(self):
        rules = extract_eligibility_rules("Open to SMEs. Company operating at least 2 years.")
        profile = {"facts": {"applicant_type": ["sme"]}}
        result = evaluate_eligibility(rules, profile)
        self.assertNotEqual(result["state"], "ineligible")
        self.assertIn("company_age_years", result["missing_profile_fields"])

    def test_explicit_rule_failure_is_ineligible(self):
        rules = extract_eligibility_rules("Company operating at least 3 years.")
        profile = {"facts": {"company_age_years": 1}}
        result = evaluate_eligibility(rules, profile)
        self.assertEqual(result["state"], "ineligible")
        self.assertEqual(result["failed"], 1)


class MoneyEligibilityProfileTests(unittest.TestCase):
    def test_compiles_explicit_user_facts_without_using_search_country_as_residence(self):
        query = (
            "SME company registered in Poland, company 3 years old, company has 40 employees, "
            "annual turnover 2 mln PLN, I can contribute 30%, I am 34 years old"
        )
        money = compile_money_profile(query, country="PL")
        facts = money["eligibility_profile"]["facts"]
        self.assertIn("sme", facts["applicant_type"])
        self.assertEqual(facts["geography"], ["PL"])
        self.assertEqual(facts["company_age_years"], 3)
        self.assertEqual(facts["employees"], 40)
        self.assertEqual(facts["annual_turnover"], {"amount": 2_000_000, "currency": "PLN"})
        self.assertEqual(facts["own_contribution_percent"], 30)
        self.assertEqual(facts["person_age"], 34)

    def test_search_country_alone_does_not_create_residence_fact(self):
        profile = compile_eligibility_profile("Find grants for an SME", country="PL", base_profile={"applicant_types": ["sme"]})
        self.assertNotIn("geography", profile["facts"])


class MoneyEligibilityApplicationTests(unittest.TestCase):
    def _payload(self, record):
        return {"money_records": [record]}

    def test_direct_rules_preferred_over_snippet_and_can_mark_candidate(self):
        record = {
            "title": "Generic programme",
            "description": "No eligibility details in snippet.",
            "source_urls": ["https://example.org/call"],
            "evidence_score": 80,
            "practical_ranking": {"score": 70, "components": {}},
            "blockers": [],
            "unknown_requirements": [],
            "direct_verification": {
                "eligibility_rules": extract_eligibility_rules("Open to SMEs. Company operating at least 2 years."),
            },
        }
        profile = {"facts": {"applicant_type": ["sme"], "company_age_years": 3}}
        result = apply_eligibility_to_payload(self._payload(record), eligibility_profile=profile)
        out = result["money_records"][0]
        self.assertEqual(out["eligibility_state"], "eligible_candidate")
        self.assertEqual(out["eligibility_evidence_level"], "direct_source")
        self.assertTrue(out["likely_eligible"])
        self.assertEqual(out["eligibility_score"], 100)

    def test_alternative_applicant_rules_are_or_not_and(self):
        record = {
            "title": "Programme",
            "description": "Open to SMEs. Open to startups.",
            "source_urls": ["https://example.org/call"],
            "evidence_score": 70,
            "practical_ranking": {"score": 60, "components": {}},
            "blockers": [],
            "unknown_requirements": [],
            "direct_verification": {
                "eligibility_rules": extract_eligibility_rules("Open to SMEs. Open to startups."),
            },
        }
        profile = {"facts": {"applicant_type": ["startup"]}}
        result = apply_eligibility_to_payload(self._payload(record), eligibility_profile=profile)
        out = result["money_records"][0]
        self.assertEqual(out["eligibility_state"], "eligible_candidate")
        self.assertEqual(out["eligibility"]["alternative_groups"]["applicant_type"], ["sme", "startup"])

    def test_ineligible_candidate_is_hard_demoted(self):
        record = {
            "title": "Programme",
            "description": "Company operating at least 5 years.",
            "source_urls": ["https://example.org/call"],
            "evidence_score": 90,
            "practical_ranking": {"score": 88, "components": {}},
            "blockers": [],
            "unknown_requirements": [],
        }
        profile = {"facts": {"company_age_years": 1}}
        result = apply_eligibility_to_payload(self._payload(record), eligibility_profile=profile)
        out = result["money_records"][0]
        self.assertEqual(out["eligibility_state"], "ineligible")
        self.assertLessEqual(out["practical_ranking"]["score"], 15)
        self.assertTrue(any(x.startswith("eligibility:") for x in out["blockers"]))

    def test_possible_lists_missing_profile_fields(self):
        record = {
            "title": "Programme",
            "description": "Open to SMEs. Company operating at least 2 years. Own contribution at least 20%.",
            "source_urls": ["https://example.org/call"],
            "evidence_score": 75,
            "practical_ranking": {"score": 65, "components": {}},
            "blockers": [],
            "unknown_requirements": [],
        }
        profile = {"facts": {"applicant_type": ["sme"]}}
        result = apply_eligibility_to_payload(self._payload(record), eligibility_profile=profile)
        out = result["money_records"][0]
        self.assertEqual(out["eligibility_state"], "possible")
        self.assertEqual(set(out["eligibility"]["missing_profile_fields"]), {"company_age_years", "own_contribution_percent"})


if __name__ == "__main__":
    unittest.main()
