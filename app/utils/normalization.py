import re
from typing import Optional

def normalize_artist_name(name: str) -> str:
    """
    Normalizes artist / event title for deduplication:
    - Removes country codes like (US), (UK), (SWE), (FIN)
    - Removes common prefixes/suffixes like 'Live:', 'Loppuunmyyty:', 'Levyjulkkarit'
    - Strips extra spaces, punctuation and lowercases.
    """
    if not name:
        return ""
    
    clean = name.strip()
    # Remove bracketed country codes or info e.g. (US), (UK), (FRA), (GER), (SWE), (FI)
    clean = re.sub(r"\s*\([A-Za-z\s\.,\-]+\)", "", clean)
    # Remove common status prefixes
    clean = re.sub(r"(?i)^(loppuunmyyty|peruttu|canceled|cancelled|live|tavastian|alkuillan konsertti|presents)\s*:\s*", "", clean)
    # Remove promoter prefixes like 'Ankea presents: Haken' or 'We Jazz presents:'
    clean = re.sub(r"(?i)^[a-z0-9\s]+presents\s*:\s*", "", clean)
    # Remove release party notes
    clean = re.sub(r"(?i)\s*[\(\-–]\s*levyjulkkarit.*", "", clean)
    clean = re.sub(r"(?i)\s*[\(\-–]\s*levynjulkaisukeikka.*", "", clean)
    clean = re.sub(r"(?i)\s*[\(\-–]\s*ep-julkkarit.*", "", clean)
    # Remove anniversary notes e.g. - 20 vuotta, 25-vuotisjuhla
    clean = re.sub(r"(?i)\s*[\(\-–]\s*\d+[\s\-]*vuotis.*", "", clean)
    clean = re.sub(r"(?i)\s*[\(\-–]\s*\d+[\s\-]*v[\s\-]*bileet.*", "", clean)
    # Remove album release tour suffixes e.g. 5th Album Release Tour
    clean = re.sub(r"(?i)\s*[\(\-–]\s*\d+(st|nd|rd|th)?\s+album\s+release.*", "", clean)
    
    # Remove multiple spaces and lowercase
    clean = " ".join(clean.lower().split())
    # Keep first main artist if joined with '+' or ',' or 'feat' or 'plays' or '&'
    for delimiter in [" + ", ", ", " feat.", " featuring ", " plays ", " & ", " ja "]:
        if delimiter in clean:
            clean = clean.split(delimiter)[0].strip()

    # Strip punctuation
    clean = re.sub(r"[^\w\s]", "", clean).strip()
    return clean

def normalize_venue_name(venue: str) -> str:
    """
    Normalizes venue name so 'Tavastia-klubi' and 'Tavastia' match.
    """
    if not venue:
        return ""
    v = venue.lower()
    if "tavastia" in v:
        return "tavastia"
    if "semifinal" in v:
        return "semifinal"
    if "rocks" in v:
        return "on the rocks"
    if "kuudes" in v or "6. linja" in v or "6 linja" in v:
        return "kuudes linja"
    if "aaniwalli" in v or "ääniwalli" in v:
        return "ääniwalli"
    if "lepakkomies" in v:
        return "lepakkomies"
    if "skenesali" in v:
        return "skenesali"
    if "tiivistamo" in v or "tiivistämö" in v:
        return "tiivistämö"
    if "glivelab" in v or "g livelab" in v:
        return "g livelab"
    if "loose" in v:
        return "bar loose"
    if "dubrovnik" in v:
        return "dubrovnik"
    return re.sub(r"[^\w\s]", "", v).strip()

def extract_tiketti_event_id(url: str) -> Optional[str]:
    """
    Extracts the unique numeric Tiketti event ID from URLs if present:
    e.g. 'https://www.tiketti.fi/.../118788' -> '118788'
    e.g. 'https://tavastiaklubi.fi/events/2026-10-11/ankea-presents-haken-uk/118788/' -> '118788'
    """
    if not url:
        return None
    match = re.search(r"/(\d{5,7})(?:/|\?|$)", url)
    return match.group(1) if match else None
