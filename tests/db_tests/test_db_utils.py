from typing import Generator

import pytest
from sqlmodel import create_engine, Field, Session, SQLModel, select
from sqlmodel.pool import StaticPool

from plastered.db.db_utils import add_record


@pytest.fixture(scope="function")
def mock_session() -> Generator[Session, None, None]:
    """
    Creates a temporary in-memory session, following example here:
    https://sqlmodel.tiangolo.com/tutorial/fastapi/tests/?h=#pytest-fixtures
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class MockTable(SQLModel, table=True):
    __tablename__: str = "mock_table"
    id: int | None = Field(default=None, primary_key=True)
    foo: str
    bar: str


def test_add_record(mock_session: Session) -> None:
    m1 = MockTable(foo="a", bar="b")
    assert m1.id is None
    add_record(session=mock_session, model_inst=m1)
    assert isinstance(m1.id, int)
    assert m1.id == 1

    m2 = MockTable(foo="x", bar="y")
    assert m2.id is None
    add_record(session=mock_session, model_inst=m2)
    assert isinstance(m2.id, int)
    assert m2.id == 2

    all_mock_records = mock_session.exec(select(MockTable)).all()
    assert len(all_mock_records) == 2
