"""Human-readable reference numbers such as Q-26-00001."""

import datetime

from halyard_common import repository


async def next_ref(
    repo: repository.Repository, prefix: str, today: datetime.date
) -> str:
    """Returns the next reference, like ``Q-26-00001``, counting all rows.

    Concurrent callers are serialised until commit, so two transactions
    never allocate the same reference.

    Args:
        repo: The repository of the numbered table.
        prefix: The reference prefix, for example ``"Q"``.
        today: Supplies the two-digit year.

    Returns:
        The reference.
    """
    await repository.lock_sequence(repo.session, f"ref-{prefix}")
    return f"{prefix}-{today:%y}-{await repo.count() + 1:05d}"
