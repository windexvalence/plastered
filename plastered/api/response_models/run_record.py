from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RunRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    run_date: datetime
    # TODO: (later) convert stats tables into proper pydantic models
