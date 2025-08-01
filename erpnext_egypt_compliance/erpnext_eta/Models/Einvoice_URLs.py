from dataclasses import dataclass

@dataclass
class ETAURLs:
    base_api_url: str
    id_url: str
    document_submission: str
    document_types: str
    document_pdf_template: str
    document_status_template: str
    document_submission_template: str

    @classmethod
    def for_environment(cls, environment: str) -> "ETAURLs":
        """Factory method to create URLs for a specific environment (Production/Preproduction)."""
        if environment == "Production":
            base_api = "https://api.invoicing.eta.gov.eg/api/v1"
            id_url = "https://id.eta.gov.eg/connect/token"
        else:
            base_api = "https://api.preprod.invoicing.eta.gov.eg/api/v1"
            id_url = "https://id.preprod.eta.gov.eg/connect/token"

        return cls(
            base_api_url=base_api,
            id_url=id_url,
            document_submission=f"{base_api}/documentsubmissions",
            document_types=f"{base_api}/documenttypes",
            document_pdf_template=f"{base_api}/documents/{{uuid}}/pdf",
            document_status_template=f"{base_api}/documents/{{uuid}}/raw",
            document_submission_template=f"{base_api}/documentSubmissions/{{submission_id}}",
        )

    def get_document_pdf_url(self, uuid: str) -> str:
        """Returns the PDF download URL for a document UUID."""
        return self.document_pdf_template.format(uuid=uuid)

    def get_document_status_url(self, uuid: str) -> str:
        """Returns the raw document URL for a document UUID."""
        return self.document_status_template.format(uuid=uuid)

    def get_submission_url(self, submission_id: str) -> str:
        """Returns the submission status URL for a submission ID."""
        return self.document_submission_template.format(submission_id=submission_id)