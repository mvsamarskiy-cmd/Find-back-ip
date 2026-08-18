import unittest
from unittest.mock import patch

import variant_session_api
from session_store import SessionStore
from telegram_bootstrap import app
from variant_store import VariantExpansionStore, clean_expansion


class VariantExpansionStoreTests(unittest.TestCase):
    def setUp(self):
        self.session_store = SessionStore('sqlite+pysqlite:///:memory:')
        self.variant_store = VariantExpansionStore(self.session_store)
        self.created = self.session_store.create_session({
            'client_session_id': 'variant-test',
            'title': 'Variant test',
            'prompt_history': [],
            'resources': ['telegram', 'youtube'],
            'shortlist': [],
            'direction_anchors': [],
            'runs': [],
            'feedback': {},
            'batch_counter': 0,
        })
        self.patcher = patch.object(variant_session_api, 'VARIANT_STORE', self.variant_store)
        self.patcher.start()
        self.client = app.test_client()
        self.headers = {'X-NameMachine-Session-Token': self.created['token']}

    def tearDown(self):
        self.patcher.stop()

    def payload(self):
        return {
            'resources': ['telegram', 'youtube'],
            'options': {
                'underscore': True,
                'digits': True,
                'number_tokens': ['24'],
            },
            'checked_at': '2026-08-19T00:00:00Z',
            'results': [
                {
                    'resource': 'telegram',
                    'identifier': 'bot_ella',
                    'mutation': 'underscore',
                    'status': 'claimable',
                    'strict_free': False,
                    'availability': {
                        'status': 'claimable',
                        'detail': 'assignable',
                        'source': 'telegram_claimability_service',
                        'claimability': 'confirmed',
                        'extra_raw': 'drop me',
                    },
                    'verification': {
                        'verdict': 'claimable',
                        'verification_engine_version': 'verification-engine-v2',
                        'raw_evidence': ['drop me'],
                    },
                },
                {
                    'resource': 'youtube',
                    'identifier': 'bota.vess',
                    'status': 'not_found',
                    'strict_free': True,
                    'availability': {'status': 'not_found', 'detail': 'no public channel'},
                },
            ],
        }

    def test_cleaner_recomputes_green_from_status_and_drops_raw_extras(self):
        clean = clean_expansion('Botella', self.payload())
        telegram, youtube = clean['results']
        self.assertTrue(telegram['strict_free'])
        self.assertFalse(youtube['strict_free'])
        self.assertNotIn('extra_raw', telegram['availability'])
        self.assertNotIn('raw_evidence', telegram['verification'])
        self.assertEqual(clean['options']['number_tokens'], ['24'])

    def test_put_then_get_round_trip(self):
        path = f"/api/sessions/{self.created['id']}/variant-expansions/Botella"
        written = self.client.put(path, json=self.payload(), headers=self.headers)
        self.assertEqual(written.status_code, 200)
        self.assertTrue(written.get_json()['expansion']['results'][0]['strict_free'])

        loaded = self.client.get(path, headers=self.headers)
        self.assertEqual(loaded.status_code, 200)
        expansion = loaded.get_json()['expansion']
        self.assertEqual(expansion['parent_name'], 'Botella')
        self.assertEqual(len(expansion['results']), 2)
        self.assertFalse(expansion['results'][1]['strict_free'])
        self.assertTrue(expansion.get('updated_at'))

    def test_missing_expansion_is_not_an_error(self):
        path = f"/api/sessions/{self.created['id']}/variant-expansions/Unknown"
        response = self.client.get(path, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()['expansion'])

    def test_wrong_token_cannot_read_or_write(self):
        path = f"/api/sessions/{self.created['id']}/variant-expansions/Botella"
        wrong = {'X-NameMachine-Session-Token': 'wrong'}
        self.assertEqual(self.client.get(path, headers=wrong).status_code, 404)
        self.assertEqual(self.client.put(path, json=self.payload(), headers=wrong).status_code, 404)

    def test_diagnostics_keep_variants_separate_from_candidate_bundles(self):
        diagnostics = self.variant_store.diagnostics()
        self.assertTrue(diagnostics['configured'])
        self.assertTrue(diagnostics['separate_from_candidate_bundles'])
        self.assertEqual(diagnostics['max_results_per_parent'], 24)
        self.assertEqual(diagnostics['strict_free_status'], 'claimable')


if __name__ == '__main__':
    unittest.main()
