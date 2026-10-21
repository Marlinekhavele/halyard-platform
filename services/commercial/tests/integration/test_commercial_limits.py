"""Query limits are bounded, so no request can ask for everything."""

import pytest

from halyard_common import testing


@pytest.mark.parametrize(
    ("limit", "status"), [(0, 422), (-1, 422), (201, 422), (1, 200)]
)
async def test_quote_list_limit_is_bounded(client, settings, limit, status):
    headers = testing.auth_headers(settings, testing.customer_user())

    r = await client.get(f"/quotes?limit={limit}", headers=headers)

    assert r.status_code == status
