"""The organization's documents and the editable prompts (D54).

Mounted on the settings router, behind its guard: this wording steers every
team's agent, so it is the operator's, like the model connection.
Every write answers with the whole library, so the panel never merges.
"""

from fastapi import APIRouter, Depends

from app.api.contracts import KnowledgeDocumentRequest, PromptTextRequest


def add_routes(router: APIRouter, library, unlocked) -> None:
    @router.get("/settings/library")
    def read_library(session: dict = Depends(unlocked)) -> dict:
        return library.describe()

    @router.post("/settings/library/documents")
    def add_document(
        request: KnowledgeDocumentRequest, session: dict = Depends(unlocked)
    ) -> dict:
        return library.save_document(
            None, request.title, request.content, request.enabled,
        )

    @router.put("/settings/library/documents/{document_id}")
    def update_document(
        document_id: str, request: KnowledgeDocumentRequest,
        session: dict = Depends(unlocked),
    ) -> dict:
        return library.save_document(
            document_id, request.title, request.content, request.enabled,
        )

    @router.delete("/settings/library/documents/{document_id}")
    def delete_document(
        document_id: str, session: dict = Depends(unlocked)
    ) -> dict:
        return library.delete_document(document_id)

    # `:path`, since a shared fragment's name holds a slash.
    @router.put("/settings/library/prompts/{name:path}")
    def save_prompt(
        name: str, request: PromptTextRequest, session: dict = Depends(unlocked)
    ) -> dict:
        return library.save_prompt(name, request.text)

    @router.delete("/settings/library/prompts/{name:path}")
    def reset_prompt(name: str, session: dict = Depends(unlocked)) -> dict:
        """Back to the shipped text."""
        return library.reset_prompt(name)
