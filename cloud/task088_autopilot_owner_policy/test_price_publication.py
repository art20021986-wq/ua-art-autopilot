from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from owner_policy import Identity, PolicyInputError
from price_publication import PriceVersion, Readback, publication_decision


class PricePublicationTests(unittest.TestCase):
    def setUp(self):
        self.identity = Identity("TASK088-STAGE3", "a" * 64, "attempt-1")
        self.start = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
        self.version = PriceVersion("UA-0010", 7, "8700.00", "6500.00")
        self.observations = tuple(Readback(self.identity, s, self.version,
            self.start + timedelta(seconds=40), "b" * 64, True, True)
            for s in ("CRM", "CARD", "CATALOG"))

    def decide(self, **overrides):
        args = dict(identity=self.identity, expected=self.version,
            committed_at=self.start, now=self.start + timedelta(seconds=45),
            observations=self.observations, publication_failed=False)
        args.update(overrides)
        result = publication_decision(**args)
        self.assertEqual(result.crm_action, "KEEP_COMMITTED_PRICE")
        return result

    def test_only_all_three_semantic_readbacks_allow_acknowledgement(self):
        self.assertEqual(self.decide().action, "ACK_PUBLISHED_ELIGIBLE")
        for missing in range(3):
            remaining = self.observations[:missing] + self.observations[missing + 1:]
            self.assertEqual(self.decide(observations=remaining).action, "WAIT_FOR_VERIFIED_PUBLICATION")

    def test_http_success_without_semantics_or_preservation_never_acknowledges(self):
        for flag in ("semantics_verified", "non_price_content_preserved"):
            changed = replace(self.observations[1], **{flag: False})
            self.assertEqual(self.decide(observations=(self.observations[0], changed,
                self.observations[2])).action, "STOP_AND_NOTIFY")

    def test_one_stale_public_price_does_not_acknowledge_either_market(self):
        changed_revision = replace(self.observations[2], version=replace(self.version, revision=8))
        self.assertEqual(self.decide(observations=self.observations[:2] + (changed_revision,)).action,
            "STOP_AND_NOTIFY")
        for field in ("ukraine_usd", "georgia_usd"):
            changed = replace(self.observations[2], version=replace(self.version, **{field: "100.00"}))
            partial = self.observations[:2] + (changed,)
            self.assertEqual(self.decide(observations=partial).action, "STOP_AND_NOTIFY")
            self.assertEqual(self.decide(observations=partial).reason, "PUBLIC_PRICE_VERSION_MISMATCH")

    def test_later_crm_revision_stops_old_event_even_if_site_matches_old_prices(self):
        for new in (replace(self.version, revision=8), replace(self.version, georgia_usd="6600.00")):
            crm = replace(self.observations[0], version=new)
            self.assertEqual(self.decide(observations=(crm,) + self.observations[1:]).action,
                "STOP_AND_RECONCILE")

    def test_ambiguous_failure_stops_even_after_matching_public_readbacks(self):
        self.assertEqual(self.decide(publication_failed=True).action, "STOP_AND_NOTIFY")

    def test_sla_boundary_and_late_success_are_reported_honestly(self):
        self.assertEqual(self.decide(observations=self.observations[:2],
            now=self.start + timedelta(seconds=60)).reason, "PUBLICATION_DEADLINE_MISSED")
        for seconds, action in ((60, "ACK_PUBLISHED_ELIGIBLE"), (61, "PUBLISHED_LATE_NOTIFY")):
            reads = tuple(replace(o, observed_at=self.start + timedelta(seconds=seconds))
                          for o in self.observations)
            self.assertEqual(self.decide(observations=reads,
                now=self.start + timedelta(seconds=seconds + 1)).action, action)

    def test_unrelated_old_future_or_unbound_observations_cannot_acknowledge(self):
        replacements = (
            replace(self.observations[1], identity=replace(self.identity, attempt_id="other")),
            replace(self.observations[1], version=replace(self.version, car_id="UA-0011")),
            replace(self.observations[1], observed_at=self.start - timedelta(seconds=1)),
            replace(self.observations[1], observed_at=self.start + timedelta(seconds=46)),
            replace(self.observations[1], observed_at=self.start + timedelta(seconds=14)),
        )
        for wrong in replacements:
            self.assertEqual(self.decide(observations=(self.observations[0], wrong,
                self.observations[2])).action, "STOP_AND_NOTIFY")
        with self.assertRaises(PolicyInputError):
            self.decide(observations=self.observations + (self.observations[0],))
        for invalid in (1, "true", None):
            with self.assertRaises(PolicyInputError):
                replace(self.observations[0], semantics_verified=invalid)
        for invalid in (8700, "8,700", "NaN", "-1.00", "8.0"):
            with self.assertRaises(PolicyInputError):
                replace(self.version, ukraine_usd=invalid)

    def test_missing_georgia_price_is_distinct_from_zero_and_other_market_unchanged(self):
        expected = replace(self.version, georgia_usd=None)
        reads = tuple(replace(o, version=expected) for o in self.observations)
        self.assertEqual(self.decide(expected=expected, observations=reads).action, "ACK_PUBLISHED_ELIGIBLE")
        zero = replace(reads[2], version=replace(expected, georgia_usd="0.00"))
        self.assertEqual(self.decide(expected=expected, observations=reads[:2] + (zero,)).action,
            "STOP_AND_NOTIFY")


if __name__ == "__main__":
    unittest.main()
