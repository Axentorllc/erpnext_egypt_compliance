# Copyright (c) 2026, Axentor, LLC and Contributors
# See license.txt

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_egypt_compliance.erpnext_eta.uom_mapping import (
	DEFAULT_ETA_UOM,
	apply_default_eta_uom,
)

# test-only UOM names mapped to an ETA code, so the tests never touch real UOMs
TEST_MAP = {"_Test ETA UOM Blank": "KGM", "_Test ETA UOM Preset": "KGM"}


def make_uom(uom_name, eta_uom=None):
	return frappe.get_doc({"doctype": "UOM", "uom_name": uom_name, "eta_uom": eta_uom}).insert()


class TestUOMMapping(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_map_uses_standard_uoms_and_known_eta_codes(self):
		with open(frappe.get_app_path("erpnext", "setup", "setup_wizard", "data", "uom_data.json")) as f:
			standard_uoms = [d["uom_name"] for d in json.load(f)]

		self.assertSequenceSubset(standard_uoms, DEFAULT_ETA_UOM.keys())
		self.assertSequenceSubset(frappe.get_all("ETA UOM", pluck="name"), DEFAULT_ETA_UOM.values())

	@patch.dict(DEFAULT_ETA_UOM, TEST_MAP)
	def test_new_uom_gets_default_eta_uom(self):
		self.assertEqual(make_uom("_Test ETA UOM Blank").eta_uom, "KGM")
		self.assertEqual(make_uom("_Test ETA UOM Preset", "GRM").eta_uom, "GRM")
		self.assertFalse(make_uom("_Test ETA UOM Custom").eta_uom)

	@patch.dict(DEFAULT_ETA_UOM, TEST_MAP)
	def test_backfill_fills_only_blank_uoms(self):
		blank = make_uom("_Test ETA UOM Blank")
		frappe.db.set_value("UOM", blank.name, "eta_uom", None)  # as if created before the app was installed
		preset = make_uom("_Test ETA UOM Preset", "GRM")

		apply_default_eta_uom()

		self.assertEqual(frappe.db.get_value("UOM", blank.name, "eta_uom"), "KGM")
		self.assertEqual(frappe.db.get_value("UOM", preset.name, "eta_uom"), "GRM")

	@patch.dict(DEFAULT_ETA_UOM, TEST_MAP)
	def test_backfill_skips_site_without_uom_table(self):
		uom = make_uom("_Test ETA UOM Blank")
		frappe.db.set_value("UOM", uom.name, "eta_uom", None)

		with patch.object(frappe.local.db, "table_exists", return_value=False):
			apply_default_eta_uom()

		self.assertFalse(frappe.db.get_value("UOM", uom.name, "eta_uom"))
