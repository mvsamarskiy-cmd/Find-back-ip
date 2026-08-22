import unittest
from pathlib import Path

from money_query_planner import build_money_search_plan, compile_money_profile
from private_global_bootstrap import app


class PrivateMoneyControlsV24Tests(unittest.TestCase):
    def test_overlay_is_loaded_between_money_graph_and_research_browser(self):
        body = app.test_client().get('/').get_data(as_text=True)
        graph = '/static/money_graph_ui.js?v=1'
        controls = '/static/private_money_controls_v24.js?v=1'
        research = '/static/private_research_browser.js?v=1'
        self.assertIn(controls, body)
        self.assertLess(body.index(graph), body.index(controls))
        self.assertLess(body.index(controls), body.index(research))

    def test_ui_exposes_full_money_scope_and_visible_transports(self):
        source = Path('static/private_money_controls_v24.js').read_text(encoding='utf-8')
        for family in ('funding', 'capital', 'finance', 'savings', 'revenue', 'assets', 'local', 'markets', 'off_market', 'other'):
            self.assertIn(f"{family}:", source)
        for opportunity_type in ('preferential_loan', 'equipment_financing', 'procurement', 'liquidation', 'market_dislocation', 'off_market_public'):
            self.assertIn(opportunity_type, source)
        self.assertIn('/api/private-mode/diagnostics', source)
        self.assertIn("'WEB · ON'", source)
        self.assertIn('TOR · ${torOn ?', source)
        self.assertIn('ONION · ${onionOn ?', source)
        self.assertIn('DIRECT VERIFY · ${directOn ?', source)

    def test_results_panel_follows_search_without_sticky_overlay(self):
        source = Path('static/private_money_controls_v24.js').read_text(encoding='utf-8')
        self.assertIn("composer.insertAdjacentElement('afterend', panel)", source)
        self.assertIn("panel.classList.add('nmm-primary-results')", source)
        self.assertIn('body.nm-private-global .composer{position:relative;bottom:auto;z-index:auto}', source)
        self.assertIn("panel.scrollIntoView({behavior: 'smooth', block: 'start'})", source)
        self.assertIn("url.includes('/api/private-mode/search')", source)
        self.assertIn('nmPrivateMainCount', source)
        self.assertIn("observer.observe(document.body, {attributes: true, attributeFilter: ['class']})", source)
        self.assertNotIn('observer.observe(document.documentElement, {subtree: true, childList: true', source)
        self.assertNotIn('bar.replaceChildren()', source)

    def test_explicit_off_market_family_is_first_planner_scope_without_mutating_exact_query(self):
        query = 'знайди цікаві можливості у Польщі'
        plan = build_money_search_plan(query, country='PL', category='off_market')
        profile = plan['profile']
        self.assertEqual(plan['lanes'][0]['query'], query)
        self.assertEqual(profile['selected_scope'], {'kind': 'family', 'value': 'off_market'})
        self.assertEqual(profile['requested_families'][0], 'off_market')
        self.assertEqual(plan['lanes'][1]['family'], 'off_market')
        self.assertTrue(profile['money_intent'])

    def test_explicit_type_selects_its_family_and_type(self):
        profile = compile_money_profile('знайди варіанти', country='PL', category='liquidation')
        self.assertEqual(profile['selected_scope'], {'kind': 'type', 'value': 'liquidation'})
        self.assertEqual(profile['requested_types'][0], 'liquidation')
        self.assertEqual(profile['requested_families'][0], 'assets')

    def test_legacy_tender_category_maps_to_procurement(self):
        profile = compile_money_profile('знайди актуальні', country='EU', category='tender')
        self.assertEqual(profile['selected_scope'], {'kind': 'type', 'value': 'procurement'})
        self.assertEqual(profile['requested_types'][0], 'procurement')
        self.assertEqual(profile['requested_families'][0], 'revenue')


if __name__ == '__main__':
    unittest.main()
