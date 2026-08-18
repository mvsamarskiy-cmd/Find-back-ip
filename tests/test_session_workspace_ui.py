import unittest

import app


class SessionWorkspaceUiTests(unittest.TestCase):
    def setUp(self):
        self.body = app.app.test_client().get("/").get_data(as_text=True)

    def test_session_controls_exist(self):
        self.assertIn("Нова сесія", self.body)
        self.assertIn("Зберегти", self.body)
        self.assertIn("Завантажити TXT", self.body)
        self.assertIn("Надіслати на email", self.body)
        self.assertIn("function newSession()", self.body)
        self.assertIn("function exportTxt()", self.body)

    def test_session_state_contains_continuation_memory(self):
        self.assertIn("promptHistory", self.body)
        self.assertIn("results:[]", self.body)
        self.assertIn("feedback:{}", self.body)
        self.assertIn("shortlist:[]", self.body)
        self.assertIn("directionAnchors:[]", self.body)
        self.assertIn("runs:[]", self.body)
        self.assertIn("namemachine_session_v2", self.body)

    def test_new_session_archives_old_browser_session(self):
        self.assertIn("namemachine_session_archive_v2", self.body)
        self.assertIn("archive.unshift(current)", self.body)
        self.assertIn("Поточна лишиться в локальному архіві", self.body)

    def test_email_is_explicitly_deferred_not_faked(self):
        self.assertIn('disabled title="Email буде додано після серверних сесій"', self.body)
        self.assertIn("Серверне збереження та email будуть окремим наступним етапом", self.body)


if __name__ == "__main__":
    unittest.main()
