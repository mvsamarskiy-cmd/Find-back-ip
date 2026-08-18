from datetime import timedelta
from pathlib import Path
import unittest

from audit_store import AUDIT_STORE, AuditStore, audit_events
from session_store import SessionStore, _utcnow
from telegram_bootstrap import RELEASE_MARKER, app


class ClientReportV5Tests(unittest.TestCase):
    def test_client_report_loads_before_controls_and_mode_overlay_is_cache_busted(self):
        body = app.test_client().get("/").get_data(as_text=True)
        self.assertIn('/static/client_report.js?v=6', body)
        self.assertIn('/static/client_report_modes.js?v=1', body)
        self.assertIn('/static/report_controls.js?v=5', body)
        self.assertLess(body.index('/static/client_report.js?v=6'), body.index('/static/client_report_modes.js?v=1'))
        self.assertLess(body.index('/static/client_report_modes.js?v=1'), body.index('/static/report_controls.js?v=5'))
        self.assertTrue(RELEASE_MARKER.startswith('v8.'))

    def test_normal_menu_is_client_facing_not_technical_dump(self):
        source = Path('static/report_controls.js').read_text(encoding='utf-8')
        self.assertIn('Клієнтський звіт HTML', source)
        self.assertIn('Клієнтський звіт TXT', source)
        self.assertIn('Надіслати на email', source)
        self.assertNotIn('Технічний аудит TXT', source)

    def test_client_report_has_categories_and_truthful_promising_language(self):
        source = Path('static/client_report.js').read_text(encoding='utf-8')
        self.assertIn('Що привернуло увагу', source)
        self.assertIn('Що система зрозуміла про смак', source)
        self.assertIn('Підтверджені кандидати', source)
        self.assertIn('Перспективні кандидати', source)
        self.assertIn('Влучні за напрямом, але зайняті', source)
        self.assertIn('Відсіяно користувачем', source)
        self.assertIn('“Не знайдено” не означає “вільне”', source)
        self.assertIn('root_blend', source)

    def test_generic_report_never_pretends_ideas_were_verified(self):
        source = Path('static/client_report_modes.js').read_text(encoding='utf-8')
        self.assertIn('ЗВІТ ГЕНЕРАЦІЇ НАЗВ', source)
        self.assertIn('Перевірки доменів і соцмереж не запускаються', Path('static/entry_modes.js').read_text(encoding='utf-8'))
        self.assertIn('не перевіряє домени, соцмережі, компанії чи торгові марки', source)
        self.assertIn("row?.product_mode === 'generic_name'", source)

    def test_audit_sync_is_separate_and_prunes_browser_copy(self):
        audit_source = Path('static/audit_sync.js').read_text(encoding='utf-8')
        client_source = Path('static/client_report.js').read_text(encoding='utf-8')
        self.assertIn('/audit-events/batch', audit_source)
        self.assertIn('seven-day TTL', audit_source)
        self.assertIn('LOCAL_RETENTION_MS = 7 * 24 * 60 * 60 * 1000', audit_source)
        self.assertIn('pruneLocalAudit', audit_source)
        self.assertNotIn('/audit-events/batch', client_source)

    def test_worker_uses_retention_entrypoint(self):
        worker_config = Path('railway.worker.json').read_text(encoding='utf-8')
        wrapper = Path('worker_entry.py').read_text(encoding='utf-8')
        self.assertIn('python worker_entry.py', worker_config)
        self.assertIn('AUDIT_STORE.prune_expired()', wrapper)
        self.assertIn('3600.0', wrapper)


class AuditRetentionStoreTests(unittest.TestCase):
    def test_audit_event_expires_without_deleting_session(self):
        store = SessionStore('sqlite+pysqlite:///:memory:')
        audit = AuditStore(store)
        created = store.create_session({
            'client_session_id': 's-test',
            'title': 'test',
            'prompt_history': [],
            'resources': ['youtube'],
            'shortlist': [],
            'direction_anchors': [],
            'runs': [],
            'feedback': {},
            'batch_counter': 0,
            'created': _utcnow().isoformat(),
            'updated': _utcnow().isoformat(),
        })
        result = audit.upsert_events(created['id'], created['token'], [{
            'at': _utcnow().isoformat(),
            'type': 'feedback_change',
            'job_id': None,
            'details': {'name': 'Botella', 'vote': 1},
        }])
        self.assertEqual(result['accepted'], 1)
        engine = store._ensure_engine()
        with engine.connect() as conn:
            self.assertEqual(conn.execute(audit_events.select()).fetchall().__len__(), 1)
        removed = audit.prune_expired(_utcnow() + timedelta(days=8))
        self.assertEqual(removed, 1)
        self.assertIsNotNone(store.load_session(created['id'], created['token']))

    def test_default_retention_is_seven_days(self):
        self.assertEqual(AUDIT_STORE.diagnostics()['retention_days'], 7)


if __name__ == '__main__':
    unittest.main()
