# Copyright (c) 2022, Axentor, LLC and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests
import json
from datetime import datetime
from erpnext_egypt_compliance.erpnext_eta.legacy_einvoice import get_eta_inv_datetime_diff
from erpnext_egypt_compliance.erpnext_eta.doctype.eta_pos_connector.eta_pos_connector import ETASession


class ETAConnector(Document):

    def validate(self):
        self.ensure_single_default_per_company()
    
    def ensure_single_default_per_company(self):
        """Ensure only one default ETA Connector per company."""
        if self.is_default:
            existing = frappe.db.exists(
                "ETA Connector",
                {
                    "company": self.company,
                    "is_default": 1,
                    "name": ["!=", self.name]  # exclude current doc
                }
            )
            if existing:
                frappe.throw(f"There can only be one default ETA Connector for company {self.company}.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.PREPROD_URL = "https://api.preprod.invoicing.eta.gov.eg/api/v1"
        self.PREPROD_ID_URL = "https://id.preprod.eta.gov.eg/connect/token"
        self.PROD_URL = "https://api.invoicing.eta.gov.eg/api/v1"
        self.PROD_ID_URL = "https://id.eta.gov.eg/connect/token"

        self.ETA_BASE = self.PREPROD_URL
        self.ID_URL = self.PREPROD_ID_URL

        if self.environment == "Production":
            self.ETA_BASE = self.PROD_URL
            self.ID_URL = self.PROD_ID_URL

        self.DOCUMET_SUBMISSION = self.ETA_BASE + "/documentsubmissions"
        self.DOCUMENT_TYPES = self.ETA_BASE + "/documenttypes"
        self.session = ETASession().get_session()

    def get_eta_access_token(self):

        if self.access_token:
            access_token = self.get_password(fieldname="access_token")
        else:
            access_token = self.refresh_eta_token()
        return (
            access_token
            if (access_token and frappe.utils.add_to_date(datetime.now(), minutes=3) < self.expires_in)
            else self.refresh_eta_token()
        )

    def refresh_eta_token(self):
        headers = {"content-type": "application/x-www-form-urlencoded"}

        response = self.session.post(
            self.ID_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.get_password(fieldname="client_secret"),
                "scope": "InvoicingAPI",
            },
            headers=headers,
        )
        if response.status_code == 200:
            eta_response = response.json()
            if eta_response.get("access_token"):
                self.access_token = eta_response.get("access_token")
                self.expires_in = frappe.utils.add_to_date(datetime.now(), seconds=eta_response.get("expires_in"))
                self.save()
                frappe.db.commit()
                return eta_response.get("access_token")

    def get_headers(self):
        return {
            "content-type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + self.get_eta_access_token(),
        }


    def get_document_type(self, doc_id=""):
        headers = self.get_headers()
        _path = self.DOCUMENT_TYPES + f"/{doc_id}"
        eta_response = self.session.get(_path, headers=headers)
        print(eta_response.text)


    def gracefully_autofetch_eta_status(self):
        docs = frappe.get_all(
            "Sales Invoice", filters=[["eta_status", "=", "Submitted"], ["company", "=", self.company]], pluck="name"
        )
        for docname in docs:
            self.update_eta_docstatus(docname)
            frappe.db.commit()
