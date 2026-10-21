"""Demo companies and users created on first start."""

from accounts import models
from accounts import services
from accounts.core import config
from accounts.core import passwords
from halyard_common import demo
from halyard_common import service as service_lib


async def seed_demo_data(runtime: service_lib.ServiceRuntime) -> None:
    """Creates Halyard, the demo customer and one user each, once.

    Args:
        runtime: The started Accounts runtime.
    """
    settings = runtime.settings
    assert isinstance(settings, config.Settings)
    if not settings.seed_demo_data:
        return
    async with runtime.db.sessionmaker() as session:
        account_service = services.AccountService(session, settings)
        if await account_service.companies.get(demo.HALYARD_COMPANY_ID):
            return
        halyard = models.Company(
            id=demo.HALYARD_COMPANY_ID,
            name="Halyard Freight GmbH",
            customer_number="HLY-00001",
            kind="internal",
            city="Berlin",
        )
        nordwerk = models.Company(
            id=demo.DEMO_COMPANY_ID,
            name=demo.DEMO_COMPANY_NAME,
            customer_number="HLY-20418",
            eori="DE4127738100",
            street="Lindenstraße 12",
            postal_code="10969",
            city="Berlin",
        )
        await account_service.companies.add_all([halyard, nordwerk])
        ops = models.User(
            id=demo.OPS_USER_ID,
            company_id=halyard.id,
            email=demo.OPS_EMAIL,
            name="Lena Vogt",
            password_hash=passwords.hash_password(demo.OPS_PASSWORD),
            role="ops",
        )
        anna = models.User(
            id=demo.DEMO_USER_ID,
            company_id=nordwerk.id,
            email=demo.DEMO_EMAIL,
            name=demo.DEMO_NAME,
            password_hash=passwords.hash_password(demo.DEMO_PASSWORD),
            role="customer_admin",
        )
        await account_service.users.add_all([ops, anna])
        account_service.stage_user_created(ops, halyard)
        account_service.stage_user_created(anna, nordwerk)
        await session.commit()
        runtime.log.info(
            "seeded demo accounts: %s / %s and %s / %s",
            demo.DEMO_EMAIL,
            demo.DEMO_PASSWORD,
            demo.OPS_EMAIL,
            demo.OPS_PASSWORD,
        )
