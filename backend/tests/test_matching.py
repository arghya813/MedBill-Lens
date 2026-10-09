"""Benchmark matching scorers.

``description_score`` decides which benchmark record a charge is compared
against, so its definition must stay exactly what it claims to be: the best of
the three scorers, computed once each.
"""

from __future__ import annotations

import pytest

from app.services.benchmark_matching import description_score
from app.utils.text import combined_match_score, keyword_score, similarity

PAIRS = [
    (
        "Cataract Surgery with IOL",
        "Small Incision Cataract Surgery (SICS) with IOL excluding the cost of IOL per eye",
    ),
    ("X Ray Chest PA", "X Ray Chest PA /AP/ Oblique view (one film)"),
    ("CT Brain Plain", "Brain / Heart FDG PET CT Scan"),
    ("Consultant Doctor Fee", "Consultant Doctor Fee"),
    ("Haemoglobin (Hb)", "Haemoglobin"),
    ("ECG", ""),
    ("", ""),
]


@pytest.mark.parametrize(("description", "service_name"), PAIRS)
def test_description_score_is_the_best_of_the_scorers(description, service_name):
    assert description_score(description, service_name) == max(
        combined_match_score(description, service_name),
        keyword_score(description, service_name),
        similarity(description, service_name),
    )
