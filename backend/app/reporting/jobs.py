from sqlalchemy.orm import Session

from ..core.events import audit
from ..core.jobs import handler, periodic
from . import service


@handler("maintenance.purge")
def purge(db: Session, payload: dict) -> None:
    audit(db, "maintenance.purged", "system", None, **service.purge_old_data(db))


periodic("maintenance.purge", 24 * 3600)
