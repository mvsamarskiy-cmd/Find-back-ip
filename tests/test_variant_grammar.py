from unittest import TestCase

from variant_grammar import (
    canonical_namespace_key,
    clean_variant_options,
    generate_variants,
    generate_variants_for_resources,
    mutation_capabilities,
    validate_variant_shape,
)


class VariantGrammarTests(TestCase):
    def test_every_mutation_is_off_by_default(self):
        self.assertEqual(generate_variants("botella", "telegram"), [])
        config = clean_variant_options({})
        self.assertFalse(any(config[key] for key in ("underscore", "digits", "dots", "hyphen", "prefix", "suffix")))

    def test_telegram_uses_only_documented_ascii_shape(self):
        rows = generate_variants(
            "botella",
            "telegram",
            {
                "underscore": True,
                "dots": True,
                "hyphen": True,
                "digits": True,
                "number_tokens": ["7"],
            },
        )
        identifiers = [row["identifier"] for row in rows]
        self.assertIn("bot_ella", identifiers)
        self.assertIn("botella7", identifiers)
        self.assertFalse(any("." in value or "-" in value for value in identifiers))
        self.assertTrue(all(validate_variant_shape("telegram", value) for value in identifiers))
        self.assertFalse(validate_variant_shape("telegram", "abcd"))

    def test_youtube_internal_separators_never_begin_or_end_handle(self):
        rows = generate_variants(
            "glasetta",
            "youtube",
            {"underscore": True, "dots": True, "hyphen": True},
        )
        identifiers = [row["identifier"] for row in rows]
        self.assertIn("glas_etta", identifiers)
        self.assertIn("glas.etta", identifiers)
        self.assertIn("glas-etta", identifiers)
        self.assertTrue(all(value[0].isalnum() and value[-1].isalnum() for value in identifiers))
        self.assertFalse(validate_variant_shape("youtube", "_glasetta"))
        self.assertFalse(validate_variant_shape("youtube", "glasetta."))

    def test_x_prefers_platform_recommended_boundary_underscores(self):
        rows = generate_variants("motormile", "x", {"underscore": True})
        identifiers = [row["identifier"] for row in rows]
        self.assertEqual(identifiers[:2], ["_motormile", "motormile_"])
        self.assertTrue(validate_variant_shape("x", "_motormile"))
        self.assertFalse(validate_variant_shape("x", "motor-mile"))
        self.assertFalse(validate_variant_shape("x", "thisusernameiswaytoolong"))

    def test_numbers_are_never_invented_without_explicit_tokens(self):
        self.assertEqual(
            generate_variants("botella", "instagram", {"digits": True}),
            [],
        )
        rows = generate_variants(
            "botella",
            "instagram",
            {"digits": True, "number_tokens": ["24", "007"]},
        )
        self.assertEqual(
            [row["identifier"] for row in rows],
            ["botella24", "botella007"],
        )

    def test_facebook_period_is_not_used_as_fake_availability_escape(self):
        self.assertTrue(validate_variant_shape("facebook", "motor.mile"))
        self.assertEqual(
            canonical_namespace_key("facebook", "motor.mile"),
            canonical_namespace_key("facebook", "motormile"),
        )
        rows = generate_variants("motormile", "facebook", {"dots": True})
        self.assertEqual(rows, [])

    def test_tiktok_period_is_internal_and_never_trailing(self):
        rows = generate_variants("botavess", "tiktok", {"dots": True})
        identifiers = [row["identifier"] for row in rows]
        self.assertEqual(identifiers, ["bota.vess"])
        self.assertTrue(validate_variant_shape("tiktok", "bota.vess"))
        self.assertFalse(validate_variant_shape("tiktok", "botavess."))

    def test_com_uses_hyphen_and_digits_but_not_social_separators(self):
        rows = generate_variants(
            "goldenmile",
            "com",
            {
                "hyphen": True,
                "underscore": True,
                "dots": True,
                "digits": True,
                "number_tokens": ["24"],
            },
        )
        identifiers = [row["identifier"] for row in rows]
        self.assertIn("golde-nmile", identifiers)
        self.assertIn("goldenmile24", identifiers)
        self.assertFalse(any("_" in value or "." in value for value in identifiers))
        self.assertFalse(validate_variant_shape("com", "-goldenmile"))
        self.assertFalse(validate_variant_shape("com", "goldenmile-"))

    def test_explicit_prefix_suffix_are_quality_first(self):
        rows = generate_variants(
            "botella",
            "youtube",
            {
                "prefix": True,
                "suffix": True,
                "prefixes": ["go"],
                "suffixes": ["hq"],
                "underscore": True,
            },
        )
        identifiers = [row["identifier"] for row in rows]
        self.assertEqual(identifiers[:2], ["gobotella", "botellahq"])
        self.assertIn("go_botella", identifiers)
        self.assertIn("botella_hq", identifiers)

    def test_capabilities_are_explicitly_non_claimability_evidence(self):
        capabilities = mutation_capabilities("telegram")
        self.assertTrue(capabilities["supports"]["underscore"])
        self.assertFalse(capabilities["supports"]["dots"])
        self.assertFalse(capabilities["strict_availability_proof"])

    def test_multi_resource_generation_keeps_platform_grammars_separate(self):
        result = generate_variants_for_resources(
            "botella",
            ["telegram", "youtube", "x"],
            {"dots": True, "underscore": True},
        )
        self.assertEqual(set(result), {"telegram", "youtube", "x"})
        self.assertFalse(any("." in row["identifier"] for row in result["telegram"]))
        self.assertTrue(any("." in row["identifier"] for row in result["youtube"]))
        self.assertFalse(any("." in row["identifier"] for row in result["x"]))

    def test_unknown_resource_fails_closed(self):
        with self.assertRaises(ValueError):
            generate_variants("botella", "threads", {"digits": True, "number_tokens": ["1"]})
