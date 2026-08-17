from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.errors import DomainError
from app.models import MandateRecord, MandateStateRecord
from app.service import _fulfill


def test_stale_fulfillment_update_fails_safely(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'state.sqlite3'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory() as setup:
        setup.add(
            MandateRecord(
                id="mdt_concurrent",
                version=1,
                principal_id="cm_test",
                agent_id="agent_test",
                payload_json="{}",
                authorization_reference="demo",
                status="active",
                authenticated_at=now,
                created_at=now,
            )
        )
        setup.add(
            MandateStateRecord(
                mandate_id="mdt_concurrent",
                current_version=1,
                status="active",
                fulfilled_amount_minor=0,
                fulfillment_count=0,
                prior_transaction_ids_json="[]",
                row_version=0,
                last_updated_at=now,
            )
        )
        setup.commit()

    first, second = factory(), factory()
    try:
        first_state = first.get(MandateStateRecord, "mdt_concurrent")
        second_state = second.get(MandateStateRecord, "mdt_concurrent")
        assert first_state is not None and second_state is not None
        _fulfill(first, first_state, "cart_first", 4000)
        first.commit()
        with pytest.raises(DomainError, match="Mandate state changed"):
            _fulfill(second, second_state, "cart_second", 4000)
    finally:
        first.close()
        second.close()
