import json
from pathlib import Path

import erpnext
import frappe

import erpnext_egypt_compliance.erpnext_eta.uom_mapping as uom_mapping
from erpnext_egypt_compliance.erpnext_eta.uom_mapping import DEFAULT_ETA_UOM


def test_map_uses_standard_uoms_and_known_eta_codes():
	uom_data = Path(erpnext.__file__).parent / "setup/setup_wizard/data/uom_data.json"
	standard = {d["uom_name"] for d in json.loads(uom_data.read_text())}
	fixture = Path(uom_mapping.__file__).parents[1] / "fixtures/eta_uom.json"
	eta_codes = {d["code"] for d in json.loads(fixture.read_text())}

	assert set(DEFAULT_ETA_UOM) <= standard
	assert set(DEFAULT_ETA_UOM.values()) <= eta_codes


def test_before_insert_fills_only_blank_known_uoms(monkeypatch):
	monkeypatch.setattr(frappe, "db", frappe._dict(exists=lambda doctype, name: True))

	blank = frappe._dict(uom_name="Kg", eta_uom=None)
	uom_mapping.set_default_eta_uom(blank)
	assert blank.eta_uom == "KGM"

	preset = frappe._dict(uom_name="Kg", eta_uom="GRM")
	uom_mapping.set_default_eta_uom(preset)
	assert preset.eta_uom == "GRM"

	custom = frappe._dict(uom_name="Carton 12", eta_uom=None)
	uom_mapping.set_default_eta_uom(custom)
	assert custom.eta_uom is None


def test_before_insert_skips_missing_eta_code(monkeypatch):
	monkeypatch.setattr(frappe, "db", frappe._dict(exists=lambda doctype, name: False))

	doc = frappe._dict(uom_name="Kg", eta_uom=None)
	uom_mapping.set_default_eta_uom(doc)
	assert doc.eta_uom is None
