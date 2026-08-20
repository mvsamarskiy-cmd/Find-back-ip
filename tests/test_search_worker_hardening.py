import unittest

import search_worker_hardening as hardening


class _App:
    BANNED_ROOTS = set()
    BANNED_SUFFIXES = set()
    _counter = 0

    @classmethod
    def candidate(cls):
        # Deterministic enough for the test while still producing many distinct
        # pronounceable ASCII candidates.
        cls._counter += 1
        n = cls._counter
        onset = ["m", "v", "r", "k", "s", "t", "b", "d"][n % 8]
        mid = ["a", "e", "i", "o", "u"][n % 5]
        tail = ["nor", "vek", "lum", "dar", "ris", "mon", "tel"][n % 7]
        return (onset + mid + tail + chr(97 + (n % 20))).capitalize()


class _Module:
    app_module = _App


class SearchWorkerHardeningTests(unittest.TestCase):
    def test_same_intent_accepts_same_search_and_rejects_unrelated_topic(self):
        self.assertTrue(hardening.same_intent(
            "Знайди вільні нікнейми в стилі boom",
            "Знайди вільні нікнейми в стилі boom",
        ))
        self.assertFalse(hardening.same_intent(
            "бренд для квіткових значків та pins",
            "знайди короткі нікнейми в стилі boom",
        ))
        self.assertFalse(hardening.same_intent("Kasko", "boom"))

    def test_local_fallback_can_fill_one_word_style_prompt(self):
        job = {
            "prompt": "boom",
            "brand_dna": None,
            "search_context": {"mode": "new_brand", "brand_name": "", "guidance": ""},
        }
        context = {"batch_number": 1, "exclude_names": [], "conflict_names": [], "successful_names": []}
        rows = hardening._fallback_generate(_Module, job, 20, context, RuntimeError("model unavailable"))
        self.assertEqual(len(rows), 20)
        self.assertEqual(len({row["name"].lower() for row in rows}), 20)
        self.assertTrue(all(row.get("generation_source") == "local_resilient_fallback" for row in rows))
        self.assertTrue(all(row.get("generation_fallback_reason") == "RuntimeError" for row in rows))

    def test_stale_anchor_guidance_is_removed_but_mode_lock_survives(self):
        result = hardening._strip_stale_anchor_guidance({
            "mode": "new_brand",
            "brand_name": "",
            "guidance": "[[nm-mode-lock:new_brand]] | Орієнтуйся на: FloralPosy, Bloomara",
        })
        self.assertIn("nm-mode-lock:new_brand", result["guidance"])
        self.assertNotIn("FloralPosy", result["guidance"])
        self.assertNotIn("Bloomara", result["guidance"])


if __name__ == "__main__":
    unittest.main()
