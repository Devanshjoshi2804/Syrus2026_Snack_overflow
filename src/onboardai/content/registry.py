from __future__ import annotations

from pathlib import Path

from onboardai.models import ContentFile, ContentTier


def build_default_registry(dataset_root) -> list[ContentFile]:
    return [
        ContentFile(
            path=str(dataset_root / "company_overview.md"),
            tier=ContentTier.RAG,
            parser="markdown_chunks",
            searchable=True,
        ),
        ContentFile(
            path=str(dataset_root / "engineering_standards.md"),
            tier=ContentTier.RAG,
            parser="markdown_chunks",
            searchable=True,
        ),
        ContentFile(
            path=str(dataset_root / "architecture_documentation.md"),
            tier=ContentTier.RAG,
            parser="markdown_chunks",
            searchable=True,
        ),
        ContentFile(
            path=str(dataset_root / "policies.md"),
            tier=ContentTier.RAG,
            parser="markdown_chunks",
            searchable=True,
        ),
        ContentFile(
            path=str(dataset_root / "org_structure.md"),
            tier=ContentTier.RAG,
            parser="markdown_chunks",
            searchable=True,
        ),
        ContentFile(
            path=str(dataset_root / "onboarding_faq.md"),
            tier=ContentTier.RAG,
            parser="markdown_chunks",
            searchable=True,
        ),
        ContentFile(
            path=str(dataset_root / "employee_personas.md"),
            tier=ContentTier.LOGIC,
            parser="personas",
            searchable=False,
        ),
        ContentFile(
            path=str(dataset_root / "onboarding_checklists.md"),
            tier=ContentTier.LOGIC,
            parser="checklists",
            searchable=False,
        ),
        ContentFile(
            path=str(dataset_root / "email_templates.md"),
            tier=ContentTier.TEMPLATE,
            parser="templates",
            searchable=False,
        ),
        ContentFile(
            path=str(dataset_root / "setup_guides.md"),
            tier=ContentTier.RAG,
            parser="markdown_chunks",
            searchable=True,
        ),
        ContentFile(
            path=str(dataset_root / "starter_tickets.md"),
            tier=ContentTier.LOGIC,
            parser="starter_tickets",
            searchable=False,
        ),
        ContentFile(
            path=str(dataset_root / "guidelines.md"),
            tier=ContentTier.LOGIC,
            parser="markdown_chunks",
            searchable=False,
        ),
    ]


def validate_registry_files(registry: list[ContentFile]) -> list[str]:
    missing: list[str] = []
    for item in registry:
        if item.required and not Path(item.path).exists():
            missing.append(item.path)
    return missing
