from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .auth import current_user
from .confirmations import check_in
from .db import get_db

router = APIRouter(prefix="/api/checkin")


class CodeIn(BaseModel):
    code: str


@router.post("")
def scan(body: CodeIn, db: Session = Depends(get_db), _=Depends(current_user)):
    return check_in(db, body.code)
