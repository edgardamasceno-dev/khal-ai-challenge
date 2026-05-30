"""Knowledge: busca lexica na base de conhecimento (ADR-0004).
Alimenta a tool MCP search_knowledge_base.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.application.ports import KnowledgeRetrievalPort
from src.interfaces.rest.dependencies import get_knowledge_retrieval
from src.interfaces.rest.schemas import KbResultDTO

router = APIRouter(tags=["knowledge"])


@router.get("/kb/search", response_model=list[KbResultDTO])
def search_kb(
    q: str = Query(..., min_length=2, description="Termo de busca"),
    limit: int = Query(3, ge=1, le=10),
    retrieval: KnowledgeRetrievalPort = Depends(get_knowledge_retrieval),
) -> list[KbResultDTO]:
    return [KbResultDTO.from_entity(r) for r in retrieval.search(q, limit)]
