import unittest
from pathlib import Path

from telegram_bootstrap import app


class SearchActionsV2Tests(unittest.TestCase):
    def test_final_search_controllers_are_loaded_in_order(self):
        body = app.test_client().get('/').get_data(as_text=True)
        self.assertIn('/static/search_actions_v2.js?v=1', body)
        self.assertIn('/static/flow_clarity_v4.js?v=1', body)
        self.assertLess(
            body.index('/static/search_actions_v2.js?v=1'),
            body.index('/static/flow_clarity_v4.js?v=1'),
        )

    def test_create_name_with_zero_resources_runs_generation_only(self):
        source = Path('static/search_actions_v2.js').read_text(encoding='utf-8')
        self.assertIn("if (!resources.length && !isIdentityFlow())", source)
        self.assertIn('return generateOnly();', source)
        self.assertIn('0 ресурсів вибрано — генерую назви без перевірки.', source)
        self.assertIn("product_mode: 'generic_name'", source)

    def test_existing_name_recheck_is_separate_from_generation(self):
        source = Path('static/search_actions_v2.js').read_text(encoding='utf-8')
        self.assertIn("fetch('/api/recheck'", source)
        self.assertIn('Перепровіряю', source)
        self.assertIn('нові назви не генеруються', source)
        self.assertIn('isRecheckIntent', source)

    def test_flow_clarity_makes_resource_contract_explicit(self):
        source = Path('static/flow_clarity_v4.js').read_text(encoding='utf-8')
        self.assertIn('0 вибрано · лише генерація', source)
        self.assertIn('0 вибрано · вибери канал', source)
        self.assertIn("currentFlow === 'brand' && count > 0", source)
        self.assertIn("deep.hidden = !available", source)
        self.assertIn("strategy.value = 'turbo'", source)
        self.assertIn("policy.value = 'any_opportunity'", source)

    def test_fragment_purchase_offer_is_visible_but_not_green(self):
        actions = Path('static/search_actions_v2.js').read_text(encoding='utf-8')
        claimability = Path('static/claimability_ui.js').read_text(encoding='utf-8')
        self.assertIn('function offerText(result)', actions)
        self.assertIn('minimum_bid_ton', actions)
        self.assertIn('current_bid_ton', actions)
        self.assertIn('nm-fragment-offer', actions)
        self.assertIn('TON', actions)
        self.assertIn("status === 'purchasable'", claimability)
        self.assertIn("status === 'claimable'", claimability)
        self.assertNotIn("statusOf((row.availability || {})[key]) === 'purchasable'", claimability)

    def test_diagnostics_advertise_turbo_default_and_zero_resource_generation(self):
        diagnostics = app.test_client().get('/api/verification/diagnostics').get_json()
        self.assertTrue(diagnostics['generation_intelligence']['zero_resource_generation'])
        self.assertTrue(diagnostics['entry_modes']['zero_selected_resources_runs_generation_only'])
        self.assertEqual(diagnostics['background_search_ui']['default_search_strategy'], 'turbo')
        self.assertIn('any_opportunity', diagnostics['background_search_ui']['match_policies'])


if __name__ == '__main__':
    unittest.main()
