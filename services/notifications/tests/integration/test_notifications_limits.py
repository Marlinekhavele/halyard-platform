"""The notification feed limit is bounded."""

import pytest

from halyard_common import testing


@pytest.mark.parametrize(
    ("limit", "status"), [(0, 422), (-5, 422), (101, 422), (100, 200)]
)
async def test_feed_limit_is_bounded(client, settings, limit, status):
    headers = testing.auth_headers(settings, testing.customer_user())

    r = await client.get(f"/notifications?limit={limit}", headers=headers)

    assert r.status_code == status
