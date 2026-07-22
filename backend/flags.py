"""Flag state lookup, by MMSI.

The first three digits of any MMSI are its Maritime Identification Digits
(MID) — an ITU-allocated block that identifies the vessel's flag state. This
is public, standard, and derivable from data every vessel already broadcasts;
no extra API call or quota is spent getting it.

Source for the MID → flag-state table: ITU allocation as published at
https://www.marinevesseltraffic.com/2013/11/mmsi-mid-codes-by-flag.html
(cross-referenced against the standard MID list). Only entries plausible for
crude tankers trading into India are kept — the major flag-of-convenience
registries (Panama, Liberia, Marshall Islands, Malta, Bahamas, Singapore,
Hong Kong, Greece, Cyprus) plus regional and Gulf states. An MMSI outside this
table returns None — SUPATH shows "flag unknown" rather than guessing.
"""

from __future__ import annotations

from typing import Optional

# MID (3-digit string) -> (ISO 3166-1 alpha-2, display name)
MID_TABLE: dict[str, tuple[str, str]] = {
    # The big flag-of-convenience registries — most VLCC/Suezmax tonnage
    # anywhere flies one of these five.
    "351": ("PA", "Panama"), "352": ("PA", "Panama"), "353": ("PA", "Panama"),
    "354": ("PA", "Panama"), "355": ("PA", "Panama"), "356": ("PA", "Panama"),
    "357": ("PA", "Panama"), "370": ("PA", "Panama"), "371": ("PA", "Panama"),
    "372": ("PA", "Panama"), "373": ("PA", "Panama"),
    "636": ("LR", "Liberia"), "637": ("LR", "Liberia"),
    "538": ("MH", "Marshall Islands"),
    "215": ("MT", "Malta"), "229": ("MT", "Malta"), "248": ("MT", "Malta"),
    "249": ("MT", "Malta"), "256": ("MT", "Malta"),
    "308": ("BS", "Bahamas"), "309": ("BS", "Bahamas"), "311": ("BS", "Bahamas"),
    "563": ("SG", "Singapore"), "564": ("SG", "Singapore"),
    "565": ("SG", "Singapore"), "566": ("SG", "Singapore"),
    "477": ("HK", "Hong Kong"),
    "237": ("GR", "Greece"), "239": ("GR", "Greece"),
    "240": ("GR", "Greece"), "241": ("GR", "Greece"),
    "209": ("CY", "Cyprus"), "210": ("CY", "Cyprus"), "212": ("CY", "Cyprus"),
    "236": ("GI", "Gibraltar"),

    # India and the corridor states this platform is actually about.
    "419": ("IN", "India"),
    "403": ("SA", "Saudi Arabia"), "422": ("IR", "Iran"), "425": ("IQ", "Iraq"),
    "470": ("AE", "United Arab Emirates"), "408": ("BH", "Bahrain"),
    "447": ("KW", "Kuwait"), "466": ("QA", "Qatar"),
    "473": ("YE", "Yemen"), "475": ("YE", "Yemen"), "622": ("EG", "Egypt"),
    "417": ("LK", "Sri Lanka"), "405": ("BD", "Bangladesh"), "463": ("PK", "Pakistan"),

    # Other major merchant/owning states seen in the Gulf–Asia crude trade.
    "412": ("CN", "China"), "413": ("CN", "China"), "414": ("CN", "China"),
    "440": ("KR", "South Korea"), "441": ("KR", "South Korea"),
    "431": ("JP", "Japan"), "432": ("JP", "Japan"),
    "257": ("NO", "Norway"), "258": ("NO", "Norway"), "259": ("NO", "Norway"),
    "219": ("DK", "Denmark"), "220": ("DK", "Denmark"),
    "244": ("NL", "Netherlands"), "245": ("NL", "Netherlands"), "246": ("NL", "Netherlands"),
    "310": ("BM", "Bermuda"), "533": ("MY", "Malaysia"), "525": ("ID", "Indonesia"),
    "574": ("VN", "Vietnam"), "567": ("TH", "Thailand"),
    "232": ("GB", "United Kingdom"), "233": ("GB", "United Kingdom"),
    "234": ("GB", "United Kingdom"), "235": ("GB", "United Kingdom"),
    "273": ("RU", "Russia"), "271": ("TR", "Turkey"),
    "338": ("US", "United States"), "366": ("US", "United States"),
    "367": ("US", "United States"), "368": ("US", "United States"),
    "369": ("US", "United States"),
    "710": ("BR", "Brazil"),
}


def flag_emoji(iso2: str) -> str:
    """Regional-indicator flag emoji from an ISO2 code — computed, not looked
    up, since it's a fixed arithmetic mapping (U+1F1E6 = 'A')."""
    if not iso2 or len(iso2) != 2:
        return ""
    return "".join(chr(0x1F1E6 + (ord(c.upper()) - ord("A"))) for c in iso2)


def flag_for_mmsi(mmsi: str) -> Optional[dict]:
    """{'iso2': 'PA', 'name': 'Panama', 'emoji': '🇵🇦'} or None if the MID
    isn't in the table (unrecognised or a test/reserved range)."""
    mid = (mmsi or "")[:3]
    hit = MID_TABLE.get(mid)
    if not hit:
        return None
    iso2, name = hit
    return {"iso2": iso2, "name": name, "emoji": flag_emoji(iso2)}
