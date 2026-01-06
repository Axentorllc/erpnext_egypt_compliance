import frappe
import json
from datetime import datetime
from frappe.utils import add_to_date
from erpnext_egypt_compliance.erpnext_eta.utils import get_company_eta_connector
import pytz



def sinv_istax_disabled(inv):
    ret = False
    if inv.get("apply_t", "") == "No":
        ret = True
    if ret:
        frappe.throw("This is an invalid Tax Invoice")


def before_submit_validate_eta_invoice(doc, event):
    docname = doc.get("name")
    get_eta_invoice(docname, event)
    validate_eta_grace_period(docname)


def validate_eta_grace_period(docname):
    connector = get_company_eta_connector(
        frappe.get_value("Sales Invoice", docname, "company"),
        throw_if_no_connector=False,
    )
    if connector:
        if connector.get("enable_eta_grace_period_validation"):
            if not (get_eta_inv_datetime_diff(docname) < connector.get("einvoice_submission_grace_period")):
                frappe.throw("Issue with Invoice and ETA Grace Period.")


def get_eta_invoice(docname, event=None):
    eta_invoice = frappe._dict()
    inv = frappe.get_doc("Sales Invoice", docname)

    if not event == "before_submit":
        sinv_istax_disabled(inv)

    if frappe.get_value("Company", inv.company, "default_currency") != "EGP":
        inv._exchange_rate = inv.eta_exchange_rate
        inv._foreign_company_currency = True
    else:
        inv._exchange_rate = inv.conversion_rate or 1.0
        inv._foreign_company_currency = False
    inv._total_qty = _get_item_total_qty(inv)
    eta_invoice.update(_get_maped_dict(inv, get_eta_sales_invoice_map()))
    eta_invoice.documentType = "C" if inv.is_return else "I"
    eta_invoice.documentTypeVersion = "1.0" if inv.eta_signature else "0.9"
    eta_invoice.taxpayerActivityCode = frappe.db.get_value("Company", inv.company, "eta_default_activity_code")
    eta_invoice.signatures = [
        {
            "signatureType": "I",
            "value": inv.eta_signature if inv.eta_signature else "ANY",
        }
    ]

    naive = datetime.strptime(
        add_to_date(inv.posting_date, seconds=inv.posting_time.seconds).strftime("%Y-%m-%d %H:%M:%S"),
        "%Y-%m-%d %H:%M:%S",
    )
    eta_invoice.dateTimeIssued = (
        pytz.timezone("Africa/Cairo").localize(naive, is_dst=None).astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    eta_invoice.issuer = get_eta_inv_issuer(inv)
    eta_invoice.receiver = get_eta_inv_receiver(inv)

    eta_invoice.invoiceLines = [_get_eta_item(item, inv) for item in inv.items]
    eta_invoice.totalItemsDiscountAmount = 0.0  # sum of all Invoicelines.ItemsDiscount
    eta_invoice.extraDiscountAmount = 0.0  # sum of all Invoicelines.ItemsDiscount
    eta_invoice.totalDiscountAmount = _get_inv_items_sum_by_key_nested(eta_invoice.invoiceLines, "discount", "amount")
    eta_invoice.totalSalesAmount = _get_inv_items_sum_by_key(eta_invoice.invoiceLines, "salesTotal")
    if inv._foreign_company_currency:
        eta_invoice.netAmount = _eta_round(inv.base_total * inv._exchange_rate)
        eta_invoice.totalAmount = _eta_round(inv.base_grand_total * inv._exchange_rate)
    else:
        eta_invoice.netAmount = _eta_round(
            inv.net_total * (inv._exchange_rate or 1),
            decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
        )
        eta_invoice.totalAmount = _eta_round(
            inv.base_grand_total,
            decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
        )

    eta_invoice.taxTotals = _get_inv_tax_total(inv, eta_invoice)

    if inv.is_consolidated or inv.is_pos:
        eta_invoice.totalAmount = _eta_round(
            eta_invoice.taxTotals[0].get("amount") + eta_invoice.netAmount,
            decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
        )

    eta_invoice = _remove_none(eta_invoice)
    eta_invoice = _abs_values(eta_invoice)
    validate_eta_invoice(eta_invoice)

    return eta_invoice


def get_eta_inv_datetime_diff(invname):
    inv_posting_date = frappe.get_value("Sales Invoice", invname, "posting_date")
    inv_posting_time = frappe.get_value("Sales Invoice", invname, "posting_time")
    inv_naive_datetime = add_to_date(inv_posting_date, seconds=inv_posting_time.seconds)
    inv_utc_datetime = pytz.timezone("Africa/Cairo").localize(inv_naive_datetime, is_dst=None).astimezone(pytz.utc)
    now_utc = pytz.timezone("Africa/Cairo").localize(datetime.now(), is_dst=None).astimezone(pytz.utc)

    return frappe.utils.time_diff_in_hours(now_utc, inv_utc_datetime)


def _get_inv_tax_total(inv, eta_invoice):
    _taxes = []
    if len(inv.taxes):
        for tax in inv.taxes:
            if not tax.get("disable_eta"):
                _tax = frappe._dict()
                _tax.taxType = tax.eta_tax_type
                if inv._foreign_company_currency:
                    _tax.amount = _eta_round(
                        tax.base_tax_amount_after_discount_amount * inv._exchange_rate,
                        decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
                    )
                else:
                    _tax.amount = _eta_round(
                        tax.base_tax_amount_after_discount_amount,
                        decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
                    )
                if inv.is_consolidated or inv.is_pos:
                    sum = 0.0
                    for i in eta_invoice.invoiceLines:
                        if i.taxableItems:
                            sum += i.taxableItems[0].get("amount")
                    _tax.amount = _eta_round(
                        sum,
                        decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
                    )
                _taxes.append(_tax)
    return _taxes


def _get_eta_item(item, inv):
    eta_inv_item = _get_maped_dict(item, get_eta_sales_invoice_line_item_map())
    item_doc = frappe.get_doc("Item", item.item_code)
    eta_inv_item = frappe._dict(eta_inv_item)

    _get_item_code(eta_inv_item, item_doc)

    eta_inv_item.unitType = frappe.get_value("UOM", item.uom, "eta_uom") or frappe.get_value(
        "ETA Settings", "ETA Settings", "eta_uom"
    )
    if inv._foreign_company_currency:
        eta_inv_item.salesTotal = _eta_round(
            item.base_amount * (inv._exchange_rate),
            decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
        )
        eta_inv_item.netTotal = _eta_round(
            item.base_amount * (inv._exchange_rate),
            decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
        )
    else:
        eta_inv_item.salesTotal = _eta_round(
            item.net_amount * (inv._exchange_rate or 1),
            decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
        )
        eta_inv_item.netTotal = _eta_round(
            item.net_amount * (inv._exchange_rate or 1),
            decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
        )
    eta_inv_item._taxableItems = _get_item_tax_values(item, inv, eta_inv_item)
    eta_inv_item.unitValue = _get_item_unit_value(item, inv)
    eta_inv_item.total = _get_item_total(item, eta_inv_item)
    eta_inv_item.taxableItems = _abs_taxableItems(eta_inv_item, inv)

    eta_inv_item.valueDifference = 0
    eta_inv_item.totalTaxableFees = 0  # Should be extra expenses or charges.
    eta_inv_item.itemsDiscount = 0
    eta_inv_item.pop("_taxableItems")
    return eta_inv_item


def _get_item_code(eta_inv_item, item_doc):
    if item_doc.get("eta_inherit_brand"):
        eta_inv_item.itemType = frappe.get_value("Brand", item_doc.get("brand"), "eta_code_type")
        eta_inv_item.itemCode = frappe.get_value("Brand", item_doc.get("brand"), "eta_item_code")
    elif item_doc.get("eta_inherit_item_group"):
        eta_inv_item.itemType = frappe.get_value("Item Group", item_doc.get("item_group"), "eta_code_type")
        eta_inv_item.itemCode = frappe.get_value("Item Group", item_doc.get("item_group"), "eta_item_code")
    else:
        eta_inv_item.itemType = item_doc.eta_code_type or "EGS"
        eta_inv_item.itemCode = item_doc.eta_item_code or frappe.get_value(
            "ETA Settings", "ETA Settings", "eta_item_code"
        )


def _abs_taxableItems(_eta_inv_item, inv):
    abs_taxes = []
    for tax in _eta_inv_item._taxableItems:
        abs_tax = frappe._dict({})
        abs_tax.amount = _eta_round(
            tax.amount,
            decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
        )
        abs_tax.taxType = tax.taxType
        abs_tax.subType = tax.subType
        abs_tax.rate = tax.rate
        abs_taxes.append(abs_tax)
    return abs_taxes


def _get_item_total(item, eta_inv_item):
    parts = [eta_inv_item.netTotal]
    [parts.append(i_tax.get("amount", 0.0)) for i_tax in eta_inv_item._taxableItems]
    return _eta_round(sum(parts), decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2)


def get_eta_sales_invoice_map():
    return frappe._dict(
        {
            "internalID": "name"
            # "extraDiscountAmount": "discount_amount",
        }
    )


def get_eta_sales_invoice_line_item_map():
    return {
        "description": "item_name",
        "itemType": "eta_code_type",
        "itemCode": "eta_item_code",
        "unitType": "eta_uom",
        "quantity": "qty",
        "internalCode": "item_code",
    }


def get_eta_inv_issuer(invoice):
    eta_issuer = frappe._dict()
    company = frappe.get_doc("Company", invoice.company)
    eta_issuer.type = company.eta_issuer_type
    eta_issuer.id = company.eta_tax_id
    eta_issuer.name = company.eta_issuer_name
    branch = frappe.get_doc("Branch", company.eta_default_branch)
    branch_address = frappe.get_doc("Address", branch.eta_branch_address)
    country_code = frappe.db.get_value("Country", branch_address.country, "code")
    eta_issuer.address = {
        "branchID": branch.eta_branch_id,
        "country": country_code,
        "governate": branch_address.state,
        "regionCity": branch_address.city,
        "street": branch_address.address_line1,
        "buildingNumber": branch_address.building_number,
    }
    return eta_issuer


def get_eta_inv_issuer_map():
    return {
        "Type": "eta_type",
        "Id": "eta_tax_id",
        "Name": "eta_name",
    }


def get_eta_inv_receiver(invoice):
    eta_receiver = frappe._dict()
    customer = frappe.get_doc("Customer", invoice.customer)
    eta_receiver.type = customer.eta_receiver_type or "P"
    eta_receiver.name = invoice.customer_name
    if eta_receiver.type == "B":
        eta_receiver.id = customer.tax_id.replace("-", "")
    else:
        eta_receiver.name = "Walkin Customer"

    if eta_receiver.type == "P" and invoice.grand_total >= 45000:
        eta_receiver.id = customer.tax_id.replace("-", "")

    eta_receiver.address = frappe._dict(
        {
            "country": "EG",
            "governate": "Egypt",
            "regionCity": "EG City",
            "street": "Street 1",
            "buildingNumber": "B0",
        }
    )
    return eta_receiver


def _get_item_unit_value(item, inv):
    res = frappe._dict()
    if inv.currency != "EGP":
        if inv._foreign_company_currency:
            res = frappe._dict(
                {
                    "currencySold": inv.currency,
                    "amountEGP": _get_item_unit_price(item, inv._exchange_rate),
                    "amountSold": item.rate,
                    "currencyExchangeRate": inv._exchange_rate,
                }
            )
        else:
            res = frappe._dict(
                {
                    "currencySold": inv.currency,
                    "amountEGP": _get_item_unit_price(item, inv._exchange_rate),
                    "amountSold": item.rate,
                    "currencyExchangeRate": inv.conversion_rate,
                }
            )

    else:
        res = frappe._dict(
            {
                "currencySold": inv.currency,
                "amountEGP": _get_item_unit_price(item),
            }
        )
    return res


def _get_item_total_qty(inv):
    total = {}
    for item in inv.items:
        if total.get(item.get("item_code")):
            total[item.get("item_code")] += item.get("qty")
        else:
            total[item.get("item_code")] = item.get("qty")
    return total


def _get_item_unit_price(item, conversion_rate=1):
    unit_price = item.net_rate * conversion_rate
    return _eta_round(unit_price, decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2)


def _get_item_tax_values(item, inv, eta_inv_item):
    item_tax_type = []
    if len(inv.taxes):
        for tax in inv.taxes:
            if not tax.get("disable_eta"):
                inv_item_tax_detail_list = json.loads(tax.item_wise_tax_detail)
                # TODO First Verison - other types should follow.
                if tax.charge_type in ("On Net Total", "On Previous Row Total"):
                    item_tax_detail = inv_item_tax_detail_list[item.item_code]
                    _item_total_qty = inv._total_qty.get(item.item_code)
                    if inv._foreign_company_currency:
                        item_tax_type.append(
                            frappe._dict(
                                {
                                    "taxType": tax.eta_tax_type,
                                    "amount": (
                                        _eta_round(
                                            (item_tax_detail[0] / 100) * item.rate * item.qty * inv._exchange_rate,
                                            decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
                                        )
                                    ),
                                    "subType": tax.eta_tax_sub_type,
                                    "rate": item_tax_detail[0],
                                }
                            )
                        )
                    else:
                        item_tax_type.append(
                            frappe._dict(
                                {
                                    "taxType": tax.eta_tax_type,
                                    "amount": (
                                        _eta_round(
                                            (item_tax_detail[0] / 100) * item.net_rate * item.qty * inv._exchange_rate,
                                            decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
                                        )
                                    ),
                                    "subType": tax.eta_tax_sub_type,
                                    "rate": item_tax_detail[0],
                                }
                            )
                        )
                if tax.charge_type == "Actual" and (inv.is_consolidated or inv.is_pos):
                    if not tax.get("disable_eta"):
                        item_tax_detail = inv_item_tax_detail_list[item.item_code]
                        if tax.eta_tax_type == "T1":
                            item_tax_type.append(
                                frappe._dict(
                                    {
                                        "taxType": tax.eta_tax_type,
                                        "subType": tax.eta_tax_sub_type,
                                        # ((_eta_round(item_tax_detail[1], 5) / (item.qty or 1) * (item.qty or 1))),
                                        "amount": (
                                            _eta_round(
                                                (item_tax_detail[0] / 100) * item.net_rate * item.qty,
                                                decimal=frappe.get_precision("Sales Invoice Item", "net_rate") or 2,
                                            )
                                        ),
                                        "rate": 14,
                                    }
                                )
                            )
    return item_tax_type


def _remove_none(_dict):
    """Delete None values recursively from all of the dictionaries"""
    for key, value in list(_dict.items()):
        if isinstance(value, dict):
            _remove_none(value)
        elif value is None:
            _dict[key] = ""
        elif isinstance(value, list):
            for v_i in value:
                if isinstance(v_i, dict):
                    _remove_none(v_i)
    return _dict


def _abs_values(_dict):
    """Delete None values recursively from all of the dictionaries"""
    for key, value in list(_dict.items()):
        if isinstance(value, dict):
            _abs_values(value)
        elif isinstance(value, float):
            _dict[key] = abs(_dict[key])
        elif isinstance(value, list):
            for v_i in value:
                if isinstance(v_i, dict):
                    _abs_values(v_i)
    return _dict


def _get_maped_dict(old_dict, key_map):
    return {newkey: old_dict.get(oldkey) for (newkey, oldkey) in key_map.items()}


def _eta_round(no, decimal=2):
    if decimal > 5:
        decimal = 5
    return round(no, decimal)


def _get_inv_items_sum_by_key(inv_items, key):
    res = 0.0
    for item in inv_items:
        res += item[key] or 0.0
    return _eta_round(res)


def _get_inv_items_sum_by_key_nested(inv_items, parent_key, child_key):
    res = 0.0
    for item in inv_items:
        if item.get(parent_key):
            res += item[parent_key][child_key] or 0.0
    return _eta_round(res)


def validate_eta_invoice(inv):
    def validate_item_salesTotal(item):
        if not (_eta_round(item.base_amount) == item.salesTotal):
            frappe.throw("Invalid Item Sales Total")

    def validate_item_discountAmount(item):
        pass

    def validate_item_netTotal(item):
        if not (_eta_round(item.base_amount) == item.netTotal):
            frappe.throw("Invalid Item Net Total")

    def validate_itemTotal(item):
        _itemTotal = 0  # _itemTotal = NetTotal + Taxable Item.Amount + TotalTaxableFees + TaxableItem.Amount + TaxableItem.Amount + LineTotalNoneTaxableFees – Items Discount – sum of all(TaxableItem < WHT-T4 + Subtype > .Amount)
        if not (_itemTotal == item.total):
            frappe.throw("Invalid Item Total")

    def validate_itemCode(inv):
        throw = []
        throw_flag = False

        row_no = 0
        for line in inv.invoiceLines:
            row_no += 1
            item_code = line.get("itemCode")
            if item_code is None or len(item_code) == 0:
                throw_flag = True
                throw.append(f"Row No #{row_no}: Item <b>{line.get('internalCode')}</b> Invalid ETA Item Code")

            item_uom = line.get("unitType")
            if item_uom is None or len(item_uom) == 0:
                throw_flag = True
                throw.append(f"Row No #{row_no}: Item <b>{line.get('internalCode')}</b> Invalid UOM")

        if throw_flag:
            message = "<br><hr>".join(throw)
            frappe.throw(message, title="Invalid ETA Item")

    def validate_salesTotal(inv):
        pass

    def validate_tax_id(inv):
        if (inv.receiver.type == "P" and inv.netAmount >= 49000) and not inv.receiver.id:
            frappe.throw("Invalid Tax ID Please Review Customer Tax ID.", title="Invalid Tax ID")
        if inv.receiver.type == "B" and not inv.receiver.id:
            frappe.throw("Invalid Tax ID Please Review Customer Tax ID.", title="Invalid Tax ID")

    def validate_totalItemDiscount(inv):
        pass

    def validate_netAmount(inv):
        pass

    def validate_itemDiscountAmount(inv):
        pass

    def validate_totalAmount(inv):
        pass

    def validate_extraDiscountAmount(inv):
        pass

    def validate_taxableFees(inv):
        pass

    def validate_nonTaxableFees(inv):
        pass

    validate_itemCode(inv)
    validate_tax_id(inv)
