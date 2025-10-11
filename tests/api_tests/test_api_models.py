from datetime import datetime

from plastered.api.response_models.run_record import RunRecord


class TestRunRecord:
    def test_init(self) -> None:
        mock_run_date = datetime.now()
        rr = RunRecord(run_date=mock_run_date)
        assert rr.run_date == mock_run_date
