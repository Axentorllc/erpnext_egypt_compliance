from . import __version__ as app_version

app_name = "erpnext_egypt_compliance"
app_title = "ERPNext ETA"
app_publisher = "Axentor, LLC"
app_description = "Integration for Egyptian Tax Authority"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "apps@axentor.co"
app_license = "CC"


doctype_js = {
    "Sales Invoice": "erpnext_eta/public/js/sales_invoice.js",
    "POS Invoice": "erpnext_eta/public/js/pos_invoice.js",
    "Item": "erpnext_eta/public/js/item.js",
	"Sales Taxes and Charges Template": "erpnext_eta/public/js/sales_taxes_and_charges_template.js",
}

doc_events = {
    # "Sales Invoice": {
        # "before_submit": "erpnext_egypt_compliance.erpnext_eta.utils.before_submit_validate_eta_invoice",
    # },
}


# User Data Protection
# --------------------

user_data_fields = [
    {
        "doctype": "{doctype_1}",
        "filter_by": "{filter_by}",
        "redact_fields": ["{field_1}", "{field_2}"],
        "partial": 1,
    },
    {
        "doctype": "{doctype_2}",
        "filter_by": "{filter_by}",
        "partial": 1,
    },
    {
        "doctype": "{doctype_3}",
        "strict": False,
    },
    {"doctype": "{doctype_4}"},
]

scheduler_events = {
    "hourly_long": [
        "erpnext_egypt_compliance.erpnext_eta.main.autosubmit_eta_batch_process",
        "erpnext_egypt_compliance.erpnext_eta.utils.autofetch_eta_status_process",
    ],
}


# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"erpnext_egypt_compliance.auth.validate"
# ]


fixtures = [
    {
        "dt": "Role",
        "filters": [
            [
                "name",
                "in",
                [
                    "ETA Manager",
                ],
            ]
        ],
    },
    {"dt": "ETA UOM"},
    {"dt": "ETA Activity Code"},
    {"dt": "ETA Tax Type"},
    {
        "dt": "Custom Field",
        "filters": [
            [
                "name",
                "in",
                [
                    "UOM-eta_uom",
                    "Sales Invoice Item-eta_code_type",
                    "Sales Invoice Item-eta_item_code",
                    "Sales Invoice Item-eta_uom",
                    "Sales Invoice-eta_details",
                    "Sales Invoice-eta_status",
                    "Sales Invoice-eta_submission_id",
                    "Sales Invoice-eta_uuid",
                    # "Sales Invoice-signature_status",
                    "Sales Invoice-eta_response_cb",
                    "Sales Invoice-eta_hash_key",
                    "Sales Invoice-eta_long_key",
                    "Sales Invoice-eta_signature",
                    "Sales Invoice-eta_exchange_rate",
                    "Sales Invoice-eta_cancellation_reason",
					"Sales Invoice-custom_eta_more_details",
                    "Company-eta_details",
                    "Company-eta_issuer_type",
                    "Company-eta_tax_id",
                    "Company-eta_cb",
                    "Company-eta_issuer_name",
                    "Company-eta_default_branch",
                    "Company-eta_default_activity_code",
                    # "Company-eta_document_type_version",
                    # "Company-eta_company_environment",
                    "Address-building_number",
                    "Customer-eta_details",
                    "Customer-eta_receiver_type",
                    "Branch-eta_details",
                    "Branch-is_eta_branch",
                    "Branch-eta_sb",
                    "Branch-eta_branch_id",
                    "Branch-eta_cb1",
                    "Branch-eta_branch_address",
                    "Sales Taxes and Charges-eta_tax_type",
                    "Sales Taxes and Charges-eta_tax_sub_type",
                    "Sales Taxes and Charges-disable_eta",
                    "Item Group-eta_details",
                    "Item Group-eta_code_type",
                    "Item Group-eta_cb_1",
                    "Item Group-eta_item_code",
                    "Item Group-eta_cb_2",
                    "Item Group-gpc",
                    "Brand-eta_details",
                    "Brand-eta_code_type",
                    "Brand-eta_cb_1",
                    "Brand-eta_item_code",
                    "Brand-eta_cb_2",
                    "Brand-gpc",
                    "Item-eta_details_inherit",
                    "Item-eta_inherit_brand",
                    "Item-override_eta_cb",
                    "Item-eta_inherit_item_group",
                    "Item-eta_details",
                    "Item-eta_code_type",
                    "Item-eta_cb",
                    "Item-eta_item_code",
                    "Item-eta_cb_2",
                    "Item-gpc",
                ],
            ]
        ],
    },
]
