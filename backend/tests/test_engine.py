"""End-to-end engine behaviour against the synthetic demo dataset.

These tests assert the properties that matter to a user: numbers reconcile,
ranges come from real records, and nothing is invented where data is missing.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.enums import BillStatus, FlagStatus
from app.repositories.bill_repository import BillRepository
from app.schemas.bill import BillItemInput
from app.services.analysis_service import AnalysisService
from app.services.bill_service import BillService
from app.services.seeding import SCENARIOS, create_scenario_bill, scenario_catalog
from app.utils.money import sum_money


@pytest.fixture()
def analysed(session_factory, seeded_benchmarks):
    """Run the analysis for a demo scenario and return the API view."""

    def _run(key: str):
        with session_factory() as db:
            bill = create_scenario_bill(db, key)
            service = AnalysisService(db)
            return service.to_schema(asyncio.run(service.run(bill.id)))

    return _run


class TestScenarioCatalog:
    def test_three_scenarios_are_published(self):
        assert sorted(SCENARIOS) == ["A", "B", "C"]

    def test_catalog_marks_everything_as_demo(self):
        for entry in scenario_catalog():
            assert entry["is_demo_data"] is True
            assert entry["title"] and entry["description"] and entry["expectation"]

    def test_demo_bills_are_labelled_demo(self, session_factory, seeded_benchmarks):
        with session_factory() as db:
            bill = create_scenario_bill(db, "A")
            assert bill.is_demo is True
            assert bill.extraction_meta["dataset_label"]
            assert "demo" in bill.hospital_name.lower()


class TestTotalsReconcile:
    @pytest.mark.parametrize("key", ["A", "B", "C"])
    def test_grand_total_equals_line_items(self, session_factory, seeded_benchmarks, key):
        with session_factory() as db:
            bill = create_scenario_bill(db, key)
            expected = sum_money(item.total_price for item in bill.items)
            assert bill.grand_total == pytest.approx(expected, abs=0.01)
            assert bill.stated_grand_total == pytest.approx(expected, abs=0.01)

    def test_credits_are_counted_exactly_once(self, session_factory, seeded_benchmarks):
        """Regression: discounts were subtracted twice in recompute_totals."""
        with session_factory() as db:
            bill = create_scenario_bill(db, "A")
            credits = sum_money(i.total_price for i in bill.items if i.total_price < 0)
            charges = sum_money(i.total_price for i in bill.items if i.total_price > 0)
            assert bill.grand_total == pytest.approx(charges + credits, abs=0.01)

    def test_negative_line_items_survive_the_review_schema(
        self, session_factory, seeded_benchmarks
    ):
        """Regression: BillItemInput rejected negative prices, blocking any
        bill that contained a discount or insurance credit."""
        with session_factory() as db:
            bill = create_scenario_bill(db, "A")
            view = BillService(db).to_schema(BillRepository(db).get(bill.id))
            credits = [i for i in view.items if i.total_price < 0]
            assert credits, "scenario A should include a discount line"
            for item in credits:
                assert BillItemInput(**item.model_dump()).total_price == item.total_price


class TestScenarioA:
    def test_most_charges_are_within_range(self, analysed):
        view = analysed("A")
        assert view.counts.within_range >= 6
        assert view.counts.attention == 0

    def test_headline_does_not_claim_an_overcharge(self, analysed):
        view = analysed("A")
        assert "No compared charge sits above" in view.headline

    def test_multi_visit_doctor_fee_is_scaled_before_comparison(self, analysed):
        """Regression: a 3-visit fee was compared against a single-visit
        benchmark and reported as ~226% above."""
        view = analysed("A")
        doctor = next(
            c for c in view.comparisons if c.description == "Consultant Doctor Fee"
        )
        assert doctor.quantity == 3
        assert doctor.benchmark_max is not None
        assert doctor.benchmark_max > 2_000
        assert doctor.flag_status == FlagStatus.WITHIN_RANGE.value


class TestScenarioB:
    def test_procedure_and_surgery_are_flagged(self, analysed):
        view = analysed("B")
        flagged = {c.description: c.flag_status for c in view.flagged}
        assert flagged.get("Procedure Charges") == FlagStatus.ATTENTION.value
        assert flagged.get("Surgery Charges") == FlagStatus.REVIEW.value

    def test_procedure_percentage_above_maximum_is_accurate(self, analysed):
        view = analysed("B")
        procedure = next(
            c for c in view.comparisons if c.description == "Procedure Charges"
        )
        expected = (
            (procedure.actual_amount - procedure.benchmark_max)
            / procedure.benchmark_max
            * 100
        )
        assert procedure.percentage_above_max == pytest.approx(expected, abs=0.1)

    def test_at_least_one_charge_is_below_range(self, analysed):
        assert analysed("B").counts.below_range >= 1

    def test_every_flagged_charge_has_an_explanation(self, analysed):
        view = analysed("B")
        assert view.flagged
        for comparison in view.flagged:
            assert comparison.ai_explanation
            assert comparison.ai_questions


class TestScenarioC:
    def test_missing_benchmarks_are_reported_not_invented(self, analysed):
        view = analysed("C")
        assert view.counts.insufficient_data >= 3
        unassessed = [
            c
            for c in view.comparisons
            if c.flag_status == FlagStatus.INSUFFICIENT_DATA.value
        ]
        assert unassessed
        for comparison in unassessed:
            assert comparison.benchmark_min is None
            assert comparison.benchmark_median is None
            assert "No sufficient benchmark data" in comparison.benchmark_display

    def test_summary_discloses_partial_coverage(self, analysed):
        view = analysed("C")
        assert view.totals.coverage_percent < 100
        assert "only available for" in view.summary

    def test_comparable_subtotal_excludes_unassessed_charges(self, analysed):
        """A range built from a few charges must not be compared against all."""
        view = analysed("C")
        covered = sum(
            c.actual_amount
            for c in view.comparisons
            if c.benchmark_min is not None and c.benchmark_max is not None
        )
        assert view.totals.comparable_subtotal == pytest.approx(covered, abs=0.01)
        assert view.totals.comparable_subtotal < view.totals.bill_total


class TestAnalysisContract:
    @pytest.mark.parametrize("key", ["A", "B", "C"])
    def test_every_line_item_appears_in_the_comparison_list(
        self, analysed, session_factory, key
    ):
        view = analysed(key)
        with session_factory() as db:
            items = BillService(db).to_schema(
                BillRepository(db).get(view.bill_id)
            ).items
        assert len(view.comparisons) == len(items)
        assert len({c.sort_index for c in view.comparisons}) == len(view.comparisons)

    @pytest.mark.parametrize("key", ["A", "B", "C"])
    def test_matched_benchmarks_carry_provenance(self, analysed, key):
        view = analysed(key)
        matched = [c for c in view.comparisons if c.benchmark_min is not None]
        assert matched
        for comparison in matched:
            assert comparison.source_name
            assert comparison.dataset_label
            assert comparison.verification_status

    @pytest.mark.parametrize("key", ["A", "B"])
    def test_demo_only_bills_are_labelled_demo(self, analysed, key):
        view = analysed(key)
        assert view.is_demo_data is True
        assert view.provider_is_real is False

    def test_mixed_sources_are_labelled_mixed(self, analysed):
        """Scenario C mixes the demo set with the published CGHS tariff.

        A cardiology bill in Jaipur finds no demo record for some charges but
        does match the government's published rate for the same city, so the
        analysis must stop claiming to be demo-only while keeping each row's
        own source label.
        """
        view = analysed("C")
        assert view.is_demo_data is False
        assert view.provider_is_real is False
        verified = [
            c
            for c in view.comparisons
            if c.verification_status == "government_rate"
        ]
        assert verified
        for comparison in verified:
            assert comparison.match_scope == "hospital_category_relaxed"
            assert comparison.benchmark_min is not None

    @pytest.mark.parametrize("key", ["A", "B", "C"])
    def test_difference_matches_the_covered_range(self, analysed, key):
        totals = analysed(key).totals
        if totals.benchmark_min_total is None:
            pytest.skip("no benchmarks available")
        assert totals.difference_max == pytest.approx(
            totals.comparable_subtotal - totals.benchmark_min_total, abs=0.01
        )
        assert totals.difference_min == pytest.approx(
            totals.comparable_subtotal - totals.benchmark_max_total, abs=0.01
        )

    def test_counters_reconcile(self, analysed):
        view = analysed("B")
        counts = view.counts.model_dump()
        assert counts["analyzed"] == len(view.comparisons)
        assert counts["within_range"] + counts["below_range"] == counts["analyzed"] - (
            counts["above_range"]
            + counts["insufficient_data"]
            + counts["not_comparable"]
        )

    def test_language_avoids_accusatory_terms(self, analysed):
        view = analysed("B")
        blob = " ".join(
            [view.headline, view.summary]
            + [c.ai_explanation or "" for c in view.comparisons]
            + [q for c in view.comparisons for q in c.ai_questions]
        ).lower()
        for word in ("fraud", "scam", "illegal", "malpractice", "unlawful", "overcharg"):
            assert word not in blob, f"{word!r} leaked into analysis output"

    def test_disclaimer_is_always_present(self, analysed):
        assert analysed("A").disclaimer


class TestLifecycle:
    def test_bill_reaches_completed_state(self, session_factory, seeded_benchmarks):
        with session_factory() as db:
            bill = create_scenario_bill(db, "A")
            asyncio.run(AnalysisService(db).run(bill.id))
            db.refresh(bill)
            assert bill.status == BillStatus.COMPLETED.value

    def test_rerunning_analysis_is_idempotent(self, session_factory, seeded_benchmarks):
        with session_factory() as db:
            bill = create_scenario_bill(db, "A")
            service = AnalysisService(db)
            first = asyncio.run(service.run(bill.id))
            second = asyncio.run(service.run(bill.id))
            assert first.id == second.id
            assert len(second.results) == len(first.results)
            assert second.bill_total == pytest.approx(first.bill_total)

    def test_editing_items_invalidates_a_stale_analysis(
        self, session_factory, seeded_benchmarks
    ):
        from app.repositories.bill_repository import AnalysisRepository

        with session_factory() as db:
            bill = create_scenario_bill(db, "A")
            asyncio.run(AnalysisService(db).run(bill.id))
            assert AnalysisRepository(db).get_for_bill(bill.id) is not None

            service = BillService(db)
            view = service.to_schema(BillRepository(db).get(bill.id))
            items = [BillItemInput(**item.model_dump()) for item in view.items]
            items[0].total_price = 999_999
            service.update_items(bill.id, items, mark_confirmed=True)

            assert AnalysisRepository(db).get_for_bill(bill.id) is None

    def test_questions_are_available_without_an_analysis(
        self, session_factory, seeded_benchmarks
    ):
        with session_factory() as db:
            bill = create_scenario_bill(db, "A")
            questions = asyncio.run(AnalysisService(db).bill_questions(bill.id))
            assert questions
            assert all(q.strip().endswith("?") for q in questions)
