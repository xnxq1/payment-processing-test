from app.domain.payments import Payment
from app.infra.db.models import payments
from app.infra.db.repos.base import EntityRepo


class PaymentsRepo(EntityRepo):
    db_entity = payments
    domain_entity = Payment
