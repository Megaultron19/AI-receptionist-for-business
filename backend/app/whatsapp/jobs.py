from sqlalchemy.orm import Session

from ..core.jobs import handler
from . import inbound


@handler("whatsapp.inbound")
def process_inbound(db: Session, payload: dict) -> None:
    inbound.process(db, payload["webhook_id"])
