"""Tests for accounts.repositories."""

from accounts import models
from accounts import repositories


def _company(number: str, name: str = "Acme") -> models.Company:
    return models.Company(name=name, customer_number=number)


def _user(company_id: str, email: str, name: str) -> models.User:
    return models.User(
        company_id=company_id,
        email=email,
        name=name,
        password_hash="x",
        role="customer",
    )


async def test_next_customer_number_counts_companies(session):
    companies = repositories.CompanyRepository(session)
    assert await companies.next_customer_number() == "HLY-20501"

    await companies.add(_company("HLY-20501"))

    assert await companies.next_customer_number() == "HLY-20502"


async def test_list_by_name_is_alphabetical(session):
    companies = repositories.CompanyRepository(session)
    await companies.add_all(
        [_company("1", "Zeta"), _company("2", "Alpha"), _company("3", "Mid")]
    )

    names = [c.name for c in await companies.list_by_name()]

    assert names == ["Alpha", "Mid", "Zeta"]


async def test_get_user_by_email(session):
    company = await repositories.CompanyRepository(session).add(_company("1"))
    users = repositories.UserRepository(session)
    await users.add(_user(company.id, "a@x.example", "A"))

    assert (await users.get_by_email("a@x.example")).name == "A"
    assert await users.get_by_email("b@x.example") is None


async def test_list_for_company_is_scoped_and_sorted(session):
    companies = repositories.CompanyRepository(session)
    mine = await companies.add(_company("1"))
    other = await companies.add(_company("2"))
    users = repositories.UserRepository(session)
    await users.add_all(
        [
            _user(mine.id, "z@x.example", "Zoe"),
            _user(mine.id, "a@x.example", "Ann"),
            _user(other.id, "o@y.example", "Otto"),
        ]
    )

    names = [u.name for u in await users.list_for_company(mine.id)]

    assert names == ["Ann", "Zoe"]
