from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from yt_research.models import SortOrder, VideoQuery


def test_video_query_accepts_public_aliases() -> None:
    query = VideoQuery.model_validate(
        {
            "match": "TUTORIAL",
            "from": "2025-01-01",
            "to": "2025-12-31",
            "sort": "views",
            "limit": 5,
        }
    )

    assert query.match_text == "TUTORIAL"
    assert query.date_from == date(2025, 1, 1)
    assert query.date_to == date(2025, 12, 31)
    assert query.sort is SortOrder.VIEWS
    assert query.limit == 5


@pytest.mark.parametrize(
    "value",
    [
        {"year": 2025, "from": "2025-01-01"},
        {"year": 2025, "to": "2025-12-31"},
        {"from": "2025-12-31", "to": "2025-01-01"},
    ],
)
def test_video_query_rejects_conflicting_date_filters(value: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        VideoQuery.model_validate(value)


@pytest.mark.parametrize("limit", [0, -1])
def test_video_query_requires_positive_limit(limit: int) -> None:
    with pytest.raises(ValidationError):
        VideoQuery(limit=limit)
