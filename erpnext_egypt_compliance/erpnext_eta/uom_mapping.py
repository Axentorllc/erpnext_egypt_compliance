import frappe
from frappe import _

# Standard ERPNext UOM name -> ETA unit type code. UOMs not listed here are mapped by hand.
DEFAULT_ETA_UOM = {
	"Nos": "EA",
	"Unit": "EA",
	"Box": "BOX",
	"Kg": "KGM",
	"Gram": "GRM",
	"Milligram": "MGM",
	"Tonne": "TNE",
	"Pound": "LB",
	"Ounce": "ONZ",
	"Litre": "LTR",
	"Centilitre": "CTL",
	"Gallon Liquid (US)": "GLL",
	"Barrel (Oil)": "BBL",
	"Meter": "M",
	"Centimeter": "CMT",
	"Millimeter": "MMT",
	"Decimeter": "DMT",
	"Kilometer": "KMT",
	"Nanometer": "C45",
	"Foot": "FOT",
	"Inch": "INH",
	"Yard": "YRD",
	"Mile": "SMI",
	"Square Meter": "MTK",
	"Square Centimeter": "CMK",
	"Square Foot": "FTK",
	"Square Inch": "INK",
	"Square Kilometer": "KMK",
	"Cubic Meter": "MTQ",
	"Cubic Centimeter": "CMQ",
	"Cubic Millimeter": "MMQ",
	"Cubic Foot": "FTQ",
	"Cubic Yard": "YDQ",
	"Minute": "MIN",
	"Hour": "HUR",
	"Day": "DAY",
	"Week": "WEE",
	"Ampere": "AMP",
	"Kiloampere": "B22",
	"Milliampere": "4K",
	"Hertz": "HTZ",
	"Kilohertz": "KHZ",
	"Megahertz": "MHZ",
	"Watt": "WTT",
	"Kilowatt": "KWT",
	"Megawatt": "MAW",
	"Pascal": "PAL",
	"Bar": "BAR",
	"Tesla": "D33",
	"Kilometer/Hour": "KMH",
	"Gram/Litre": "GL",
	"Gram/Cubic Meter": "A93",
	"Gram/Cubic Centimeter": "A94",
	"Kilogram/Cubic Meter": "KMQ",
}


def set_default_eta_uom(doc, method=None):
	"""UOM before_insert: pre-fill a blank ETA UOM for standard UOMs (covers the setup wizard)."""
	code = DEFAULT_ETA_UOM.get(doc.uom_name)
	# exists check: before_insert runs after link validation
	if not doc.get("eta_uom") and code and frappe.db.exists("ETA UOM", code):
		doc.eta_uom = code


def apply_default_eta_uom():
	"""Runs once (after_sync on install, patch on existing sites, after the setup wizard): fill blank ETA UOM on standard UOMs. Never overwrites."""
	# skip on sites without ERPNext's UOM table or before the eta_uom custom field is synced
	if not (frappe.db.table_exists("UOM", cached=False) and frappe.db.has_column("UOM", "eta_uom")):
		return
	# the v15 setup wizard names UOMs in the site language (Arabic: Unit -> وحدة)
	lang = frappe.db.get_default("lang") or "en"
	uom_map = {**DEFAULT_ETA_UOM, **{_(uom, lang=lang): code for uom, code in DEFAULT_ETA_UOM.items()}}
	codes = set(frappe.get_all("ETA UOM", pluck="name"))
	blank = frappe.get_all(
		"UOM",
		filters={"name": ["in", list(uom_map)], "eta_uom": ["is", "not set"]},
		pluck="name",
	)
	for uom in blank:
		code = uom_map.get(uom)
		if code in codes:
			frappe.db.set_value("UOM", uom, "eta_uom", code, update_modified=False)


def fill_after_setup_wizard(args=None):
	"""setup_wizard_success: the v15 wizard creates UOMs with db_insert, which skips before_insert."""
	apply_default_eta_uom()
