"""
Built-in domain methodology packs (schema v2).

Each pack lives in its own module so packs can be edited / extended in
isolation. The :data:`ALL_PACKS` tuple is the canonical registry consumed by
:mod:`web.backend.services.domain_methodology.registry`.

To add a new domain pack:

1. Create ``packs/<domain>.py`` exporting a single :class:`DomainPack`
   constant (e.g. ``CRM_SALES``).
2. Re-export it here and append to :data:`ALL_PACKS`.

The pack catalog is intentionally small and curated; the ``lessons.jsonl``
knowledge store handles per-deployment customisations on top.
"""

from web.backend.services.domain_methodology.packs.crm_sales import CRM_SALES
from web.backend.services.domain_methodology.packs.helpdesk_support import HELPDESK_SUPPORT
from web.backend.services.domain_methodology.packs.ecommerce import ECOMMERCE
from web.backend.services.domain_methodology.packs.lms_education import LMS_EDUCATION
from web.backend.services.domain_methodology.packs.hr_recruiting import HR_RECRUITING
from web.backend.services.domain_methodology.packs.project_management import PROJECT_MANAGEMENT
from web.backend.services.domain_methodology.packs.finance_billing import FINANCE_BILLING
from web.backend.services.domain_methodology.packs.healthcare_wellness import HEALTHCARE_WELLNESS
from web.backend.services.domain_methodology.packs.analytics_bi import ANALYTICS_BI
from web.backend.services.domain_methodology.packs.devtools_ops import DEVTOOLS_OPS

#: Ordered tuple of built-in packs. Order does not affect selection
#: (selection is score-based), but it does drive the default catalog
#: listing order in the admin API.
ALL_PACKS = (
    CRM_SALES,
    HELPDESK_SUPPORT,
    ECOMMERCE,
    LMS_EDUCATION,
    HR_RECRUITING,
    PROJECT_MANAGEMENT,
    FINANCE_BILLING,
    HEALTHCARE_WELLNESS,
    ANALYTICS_BI,
    DEVTOOLS_OPS,
)
