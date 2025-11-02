"""Vocabulary management routes."""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from ..db import get_db
from ..schemas import VocabularyCreate, VocabularyResponse, VocabularyTerm

router = APIRouter(prefix="/vocabularies", tags=["Vocabularies"])


@router.post(
    "",
    response_model=VocabularyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create custom vocabulary",
    description="""
    Create a custom vocabulary for improving transcription accuracy.

    Vocabularies contain term patterns and replacements that are applied
    post-transcription to correct domain-specific terminology, proper nouns,
    acronyms, etc.

    **Note**: Setting `is_global=true` requires admin privileges.
    """,
)
def create_vocabulary(payload: VocabularyCreate, db=Depends(get_db)):
    """Create a new vocabulary."""
    # TODO: Add user authentication and check admin for is_global
    # For now, we'll create without user_id (global-like behavior)

    vocab_id = uuid.uuid4()
    import json

    terms_json = json.dumps([t.model_dump() for t in payload.terms])

    with db.begin():
        db.execute(
            text(
                """
                INSERT INTO user_vocabularies (id, name, terms, is_global)
                VALUES (:id, :name, :terms::jsonb, :is_global)
            """
            ),
            {
                "id": str(vocab_id),
                "name": payload.name,
                "terms": terms_json,
                "is_global": payload.is_global,
            },
        )

    # Fetch and return the created vocabulary
    vocab = db.execute(text("SELECT * FROM user_vocabularies WHERE id = :id"), {"id": str(vocab_id)}).mappings().first()

    return VocabularyResponse(
        id=vocab["id"],
        name=vocab["name"],
        terms=[VocabularyTerm(**t) for t in vocab["terms"]],
        is_global=vocab["is_global"],
        created_at=vocab["created_at"],
        updated_at=vocab["updated_at"],
    )


@router.get(
    "",
    response_model=List[VocabularyResponse],
    summary="List vocabularies",
    description="List all available vocabularies (global and user-specific).",
)
def list_vocabularies(db=Depends(get_db)):
    """List all vocabularies."""
    # TODO: Add user authentication and filter by user_id

    vocabs = db.execute(text("SELECT * FROM user_vocabularies ORDER BY created_at DESC")).mappings().all()
    return [
        VocabularyResponse(
            id=v["id"],
            name=v["name"],
            terms=[VocabularyTerm(**t) for t in v["terms"]],
            is_global=v["is_global"],
            created_at=v["created_at"],
            updated_at=v["updated_at"],
        )
        for v in vocabs
    ]


@router.get(
    "/{vocabulary_id}",
    response_model=VocabularyResponse,
    summary="Get vocabulary",
    description="Get details of a specific vocabulary.",
)
def get_vocabulary(vocabulary_id: uuid.UUID, db=Depends(get_db)):
    """Get a vocabulary by ID."""
    vocab = (
        db.execute(text("SELECT * FROM user_vocabularies WHERE id = :id"), {"id": str(vocabulary_id)})
        .mappings()
        .first()
    )

    if not vocab:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Vocabulary {vocabulary_id} not found")
    return VocabularyResponse(
        id=vocab["id"],
        name=vocab["name"],
        terms=[VocabularyTerm(**t) for t in vocab["terms"]],
        is_global=vocab["is_global"],
        created_at=vocab["created_at"],
        updated_at=vocab["updated_at"],
    )


@router.delete(
    "/{vocabulary_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete vocabulary",
    description="Delete a custom vocabulary.",
)
def delete_vocabulary(vocabulary_id: uuid.UUID, db=Depends(get_db)):
    """Delete a vocabulary."""
    # TODO: Add user authentication and ownership check

    result = db.execute(text("DELETE FROM user_vocabularies WHERE id = :id"), {"id": str(vocabulary_id)})
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Vocabulary {vocabulary_id} not found")
