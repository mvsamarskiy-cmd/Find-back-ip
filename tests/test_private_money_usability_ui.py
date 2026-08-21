import unittest
from pathlib import Path


class PrivateMoneyUsabilityUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("static/private_global_mode.js").read_text(encoding="utf-8")

    def test_results_have_ukrainian_opportunity_summary(self):
        self.assertIn("function ukOpportunityDescription(row)", self.source)
        self.assertIn("Організатор або джерело:", self.source)
        self.assertIn("Попередня відповідність:", self.source)
        self.assertIn("Оригінальний фрагмент джерела", self.source)

    def test_results_are_paginated_and_numbered(self):
        self.assertIn("const PAGE_SIZE = 20", self.source)
        self.assertIn("Сторінка ${currentPage} / ${pageCount}", self.source)
        self.assertIn("`#${index}`", self.source)
        self.assertIn("← Попередня", self.source)
        self.assertIn("Наступна →", self.source)

    def test_scroll_controls_are_visible(self):
        self.assertIn('id="nmScrollUp"', self.source)
        self.assertIn('id="nmScrollDown"', self.source)
        self.assertIn("overflow-y:auto", self.source)
        self.assertIn("scroll-behavior:smooth", self.source)

    def test_sorting_supports_dates_and_currentness(self):
        self.assertIn("Актуальні спочатку", self.source)
        self.assertIn("Найближчий дедлайн", self.source)
        self.assertIn("Остання перевірка ↓", self.source)
        self.assertIn("function currentScore(row)", self.source)
        self.assertIn("function deadlineOf(row)", self.source)
        self.assertIn("function observedAt(row)", self.source)

    def test_stop_preserves_visible_results(self):
        self.assertIn("privateController.abort()", self.source)
        self.assertIn("Пошук зупинено. Переглядай уже показані результати.", self.source)
        self.assertIn("Уже показані результати залишено на екрані.", self.source)

    def test_all_money_types_and_tor_state_are_visible(self):
        self.assertIn("Усі 47 типів", self.source)
        self.assertIn("off_market_public", self.source)
        self.assertIn("market_dislocation", self.source)
        self.assertIn("Tor: авто", self.source)
        self.assertIn("tor_retrieval", self.source)


if __name__ == "__main__":
    unittest.main()
