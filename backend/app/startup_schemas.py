"""Startup input is user-supplied evidence or explicitly labeled assumptions."""
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Kind = Literal['business_model','architecture','equity','bp','user_agreement','privacy','exit','ipo','compliance','ip','finance','fundraising','organization','validation']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, validate_default=True)


class Founder(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(default='', max_length=120)
    percent: Decimal = Field(gt=0, le=100, max_digits=9, decimal_places=6, allow_inf_nan=False)
    contribution: str = Field(default='', max_length=500)


class Finance(StrictModel):
    price: Decimal | None = Field(default=None, ge=0, le=10**9, max_digits=24, decimal_places=6, allow_inf_nan=False)
    monthly_units: Decimal | None = Field(default=None, ge=0, le=10**9, max_digits=24, decimal_places=6, allow_inf_nan=False)
    variable_cost: Decimal | None = Field(default=None, ge=0, le=10**9, max_digits=24, decimal_places=6, allow_inf_nan=False)
    fixed_cost: Decimal | None = Field(default=None, ge=0, le=10**12, max_digits=24, decimal_places=6, allow_inf_nan=False)
    cash: Decimal | None = Field(default=None, ge=0, le=10**12, max_digits=24, decimal_places=6, allow_inf_nan=False)
    annual_volume_growth_pct: Decimal = Field(default=0, ge=-100, le=300, max_digits=24, decimal_places=6, allow_inf_nan=False)
    annual_cost_growth_pct: Decimal = Field(default=0, ge=-100, le=100, max_digits=24, decimal_places=6, allow_inf_nan=False)
    pre_money: Decimal | None = Field(default=None, gt=0, le=10**12, max_digits=24, decimal_places=6, allow_inf_nan=False)
    investment: Decimal | None = Field(default=None, ge=0, le=10**12, max_digits=24, decimal_places=6, allow_inf_nan=False)
    new_pool_pct: Decimal = Field(default=0, ge=0, le=50, max_digits=24, decimal_places=6, allow_inf_nan=False)


class Brief(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    summary: str = Field(default='', max_length=1500)
    industry: str = Field(default='', max_length=120)
    stage: Literal['idea','mvp','growth','scale'] = 'idea'
    jurisdiction: Literal['CN','HK','US','other'] = 'CN'
    target_market: str = Field(default='', max_length=300)
    customers: str = Field(default='', max_length=1500)
    problem: str = Field(default='', max_length=1500)
    solution: str = Field(default='', max_length=1500)
    revenue_model: str = Field(default='', max_length=1500)
    costs: str = Field(default='', max_length=1500)
    channels: str = Field(default='', max_length=1500)
    resources: str = Field(default='', max_length=1500)
    activities: str = Field(default='', max_length=1500)
    partners: str = Field(default='', max_length=1500)
    moat: str = Field(default='', max_length=1500)
    competitors: str = Field(default='', max_length=1500)
    traction: str = Field(default='', max_length=1500)
    team: str = Field(default='', max_length=1500)
    funding_use: str = Field(default='', max_length=1500)
    entity_name: str = Field(default='', max_length=160)
    service_scope: str = Field(default='', max_length=1500)
    data_practices: str = Field(default='', max_length=1500)
    refund_policy: str = Field(default='', max_length=1500)
    contact: str = Field(default='', max_length=300)
    evidence: str = Field(default='', max_length=3000)
    founders: list[Founder] = Field(default_factory=list, max_length=20)
    finance: Finance = Field(default_factory=Finance)
    completed_steps: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def validate_founders(self):
        if self.founders and sum((f.percent for f in self.founders), Decimal(0)) != 100:
            raise ValueError('当前股东比例合计必须为 100%，期权池增设单独测算')
        if len({f.name for f in self.founders}) != len(self.founders):
            raise ValueError('股东名称不能重复')
        valid={f's{i:02}' for i in range(1,11)}
        if len(set(self.completed_steps))!=len(self.completed_steps) or not set(self.completed_steps)<=valid:
            raise ValueError('创业流程步骤无效或重复')
        return self


class ProjectUpdate(Brief):
    expected_revision: int = Field(ge=1)


class DraftIn(StrictModel):
    kind: Kind
    instruction: str = Field(default='',max_length=2000)
    model_assist: bool = False
    expected_revision: int = Field(ge=1)


class ArtifactIn(DraftIn):
    markdown: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1,max_length=80000)

    @field_validator('markdown')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('文稿不能为空')
        return value
    expected_document_version: int = Field(default=0,ge=0)
