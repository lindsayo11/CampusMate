"""Official-source adapter implementations."""

from .civil_service import CivilServiceWorkbookAdapter
from .education import MoEPolicyAdapter, UniversityNoticeAdapter, YZChsiAdapter
from .public_recruitment import (
    InstitutionRecruitmentAdapter,
    MohrssPublicJobAdapter,
    RegionalRecruitmentDirectoryAdapter,
)

__all__ = ["CivilServiceWorkbookAdapter", "InstitutionRecruitmentAdapter", "MoEPolicyAdapter",
           "MohrssPublicJobAdapter", "RegionalRecruitmentDirectoryAdapter",
           "UniversityNoticeAdapter", "YZChsiAdapter"]
