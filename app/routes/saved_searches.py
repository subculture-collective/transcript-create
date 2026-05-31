import uuid

from fastapi import APIRouter, Depends, Request

from .. import crud
from ..common.session import get_session_token as _get_session_token
from ..common.session import get_user_from_session as _get_user_from_session
from ..db import get_db
from ..exceptions import AuthenticationError
from ..schemas import SavedSearch, SavedSearchCreate, SavedSearchesResponse

router = APIRouter(prefix="", tags=["Saved Searches"])


@router.get(
    "/users/me/saved-searches",
    response_model=SavedSearchesResponse,
    summary="List saved searches",
    description="List saved searches for the authenticated user.",
)
def list_saved_searches(request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise AuthenticationError()
    return crud.list_saved_searches(db, user["id"])


@router.post(
    "/users/me/saved-searches",
    response_model=SavedSearch,
    summary="Create saved search",
    description="Save a search query and filter payload for the authenticated user.",
)
def create_saved_search(payload: SavedSearchCreate, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise AuthenticationError()
    return crud.create_saved_search(db, user["id"], payload.query, payload.filters)


@router.delete(
    "/users/me/saved-searches/{saved_search_id}",
    summary="Delete saved search",
    description="Delete a saved search owned by the authenticated user.",
)
def delete_saved_search(saved_search_id: uuid.UUID, request: Request, db=Depends(get_db)):
    user = _get_user_from_session(db, _get_session_token(request))
    if not user:
        raise AuthenticationError()
    return {"ok": crud.delete_saved_search(db, user["id"], saved_search_id)}
