import json
from pathlib import Path

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "erpnext_egypt_compliance"
    / "fixtures"
    / "custom_field.json"
)


def _field(name):
    return next(f for f in json.loads(FIXTURE.read_text()) if f["name"] == name)


def test_activity_code_is_mandatory_only_for_egyptian_companies():
    field = _field("Company-eta_default_activity_code")
    assert not field["reqd"]
    assert field["mandatory_depends_on"] == 'eval:doc.country=="Egypt"'


def test_tax_row_fields_are_not_mandatory_for_every_tax_row():
    # A tax row cannot see its parent's country; the ETA schema check in before_submit
    # reports a missing tax type for companies that have a connector.
    for name in (
        "Sales Taxes and Charges-eta_tax_type",
        "Sales Taxes and Charges-eta_tax_sub_type",
    ):
        assert not _field(name)["reqd"]
