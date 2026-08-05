"""Explicit, manually reviewed RNE-to-DIVIPOLA aliases for one sensitivity run.

This table is deliberately finite and versioned.  It is not a fuzzy matcher;
every source key and target DIVIPOLA code is named explicitly below.
"""

from __future__ import annotations

ALIAS_CROSSWALK_VERSION = "rne-dane-municipal-aliases/1.0.0"
CATALOG_QUERY_BASE = (
    "https://geoportal.dane.gov.co/mparcgis/rest/services/Divipola/"
    "Serv_DIVIPOLA_MGN_2025/FeatureServer/317/query"
)
REVIEWER = "codex-data-review/2026-08-04"

# source_key, target DIVIPOLA, review method.  The first eight rows contain
# shortened or historical RNE labels; all other rows are a one-to-one literal
# qualifier, spelling, diacritic, or official ANM-label variation reviewed
# against DANE MGN 2025.  No edit distance result is accepted here.
_ROWS = """\
01031 05042 reviewed_short_or_historical_label
01058 05101 reviewed_short_or_historical_label
01082 05148 reviewed_qualifier_or_diacritic
01168 05585 reviewed_qualifier_or_diacritic
01223 05647 reviewed_short_or_historical_label
01235 05664 reviewed_short_or_historical_label
01256 05697 reviewed_qualifier_or_diacritic
01300 05893 reviewed_qualifier_or_diacritic
05001 13001 reviewed_qualifier_or_diacritic
05113 13810 reviewed_qualifier_or_diacritic
07008 15047 reviewed_qualifier_or_diacritic
07112 15332 reviewed_qualifier_or_diacritic
07139 15407 reviewed_qualifier_or_diacritic
11043 19418 reviewed_qualifier_or_diacritic
11055 19517 reviewed_qualifier_or_diacritic
11058 19532 reviewed_qualifier_or_diacritic
11061 19548 reviewed_qualifier_or_diacritic
11067 19585 reviewed_qualifier_or_diacritic
12625 20443 reviewed_qualifier_or_diacritic
13014 23300 reviewed_qualifier_or_diacritic
13020 23350 reviewed_qualifier_or_diacritic
13034 23586 reviewed_qualifier_or_diacritic
13040 23670 reviewed_qualifier_or_diacritic
15198 25530 reviewed_qualifier_or_diacritic
15304 25843 reviewed_qualifier_or_diacritic
17002 27050 reviewed_qualifier_or_diacritic
17006 27025 reviewed_qualifier_or_diacritic
17008 27075 reviewed_qualifier_or_diacritic
17010 27077 reviewed_qualifier_or_diacritic
17011 27099 reviewed_qualifier_or_diacritic
17012 27425 reviewed_qualifier_or_diacritic
17016 27245 reviewed_qualifier_or_diacritic
17017 27135 reviewed_qualifier_or_diacritic
17026 27430 reviewed_qualifier_or_diacritic
17035 27600 reviewed_qualifier_or_diacritic
17060 27810 reviewed_qualifier_or_diacritic
19025 41797 reviewed_qualifier_or_diacritic
19047 41378 reviewed_qualifier_or_diacritic
21012 47058 reviewed_qualifier_or_diacritic
21015 47170 reviewed_qualifier_or_diacritic
21095 47980 reviewed_qualifier_or_diacritic
23004 52019 reviewed_qualifier_or_diacritic
23013 52051 reviewed_qualifier_or_diacritic
23022 52203 reviewed_qualifier_or_diacritic
23043 52258 reviewed_qualifier_or_diacritic
23047 52520 reviewed_qualifier_or_diacritic
23085 52418 reviewed_qualifier_or_diacritic
23088 52427 reviewed_qualifier_or_diacritic
23091 52435 reviewed_qualifier_or_diacritic
23112 52621 reviewed_qualifier_or_diacritic
23125 52696 reviewed_qualifier_or_diacritic
23127 52699 reviewed_qualifier_or_diacritic
23139 52835 reviewed_qualifier_or_diacritic
25001 54001 reviewed_qualifier_or_diacritic
27071 68235 reviewed_qualifier_or_diacritic
28030 70204 reviewed_qualifier_or_diacritic
28048 70235 reviewed_qualifier_or_diacritic
28190 70702 reviewed_qualifier_or_diacritic
28260 70742 reviewed_short_or_historical_label
28300 70820 reviewed_qualifier_or_diacritic
29016 73055 reviewed_qualifier_or_diacritic
31022 76111 reviewed_short_or_historical_label
31040 76126 reviewed_qualifier_or_diacritic
46680 85250 reviewed_qualifier_or_diacritic
50073 94886 reviewed_official_anm_label
50078 94885 reviewed_official_anm_label
50083 94888 reviewed_official_anm_label
50087 94887 reviewed_official_anm_label
50090 94884 reviewed_official_anm_label
50092 94883 reviewed_official_anm_label
52060 50689 reviewed_qualifier_or_diacritic
60010 91263 reviewed_official_anm_label
60013 91405 reviewed_official_anm_label
60016 91407 reviewed_official_anm_label
60017 91430 reviewed_official_anm_label
60019 91460 reviewed_official_anm_label
60021 91669 reviewed_official_anm_label
60022 91798 reviewed_official_anm_label
60030 91530 reviewed_official_anm_label
60040 91536 reviewed_official_anm_label
64018 86757 reviewed_qualifier_or_diacritic
64028 86865 reviewed_qualifier_or_diacritic
68010 97777 reviewed_official_anm_label
68013 97511 reviewed_official_anm_label
68022 97889 reviewed_official_anm_label
"""


def rows() -> tuple[tuple[str, str, str], ...]:
    """Return the explicit source-to-target pairs without accepting proposals."""
    parsed: list[tuple[str, str, str]] = []
    for line in _ROWS.strip().splitlines():
        source_key, target_divipola, method = line.split()
        parsed.append((source_key, target_divipola, method))
    return tuple(parsed)
