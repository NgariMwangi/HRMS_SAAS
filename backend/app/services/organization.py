from app.models import Branch, Country


def apply_country_defaults(branch: Branch, country: Country) -> None:
    if branch.currency_id is None:
        branch.currency_id = country.default_currency_id
    if not branch.timezone:
        branch.timezone = country.default_timezone
