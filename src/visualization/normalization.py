"""Greek administrative-text normalization for fire-station coverage matching.

Provides accent stripping, case folding, stop-word removal, and an alias
table that maps OSM nominative-case municipality names to the genitive forms
used in official ΠΣ coverage documents and the project's JSON data files.
"""

from __future__ import annotations

import unicodedata

# ---------------------------------------------------------------------------
# OSM → JSON alias table
# ---------------------------------------------------------------------------
# OSM returns municipality names in Greek nominative case; the JSON coverage
# arrays use the genitive form (standard in official administrative texts).
# This table maps raw OSM names → pre-normalised genitive keys.
# ``strip_political_terms()`` is applied AFTER the lookup, so values must
# already be UPPERCASE, accent-free, and ``-`` replaced by space.

ALIASES: dict[str, str] = {
    # Αθήνα
    "Αθήνα":                                "ΑΘΗΝΑΙΩΝ",
    "Αθηναίοι":                             "ΑΘΗΝΑΙΩΝ",
    # Πειραιάς zone
    "Πειραιάς":                             "ΠΕΙΡΑΙΩΣ",
    "Κερατσίνι-Δραπετσώνα":                "ΚΕΡΑΤΣΙΝΙΟΥ ΔΡΑΠΕΤΣΩΝΑΣ",
    "Κερατσίνι - Δραπετσώνα":              "ΚΕΡΑΤΣΙΝΙΟΥ ΔΡΑΠΕΤΣΩΝΑΣ",
    "Νίκαια-Αγ. Ιωάννης Ρέντης":          "ΝΙΚΑΙΑΣ ΑΓ Ι ΡΕΝΤΗ",
    "Νίκαια - Αγ. Ιωάννης Ρέντης":        "ΝΙΚΑΙΑΣ ΑΓ Ι ΡΕΝΤΗ",
    "Κορυδαλλός":                           "ΚΟΡΥΔΑΛΛΟΥ",
    # Βόρειος Τομέας
    "Μαρούσι":                              "ΑΜΑΡΟΥΣΙΟΥ",
    "Αχαρνές":                              "ΑΧΑΡΝΩΝ",
    "Βριλήσσια":                            "ΒΡΙΛΗΣΣΙΩΝ",
    # Κεντρικός / Νότιος Τομέας
    "Βύρωνας":                              "ΒΥΡΩΝΟΣ",
    "Δήμος Βύρωνα":                         "ΒΥΡΩΝΟΣ",
    "Ηλιούπολη":                            "ΗΛΙΟΥΠΟΛΕΩΣ",
    "Δήμος Ηλιούπολης":                     "ΗΛΙΟΥΠΟΛΕΩΣ",
    "Άλιμος":                               "ΑΛΙΜΟΥ",
    "Αλιμος":                               "ΑΛΙΜΟΥ",
    "Αγ. Δημήτριος":                        "ΑΓΙΟΥ ΔΗΜΗΤΡΙΟΥ",
    "Άγιος Δημήτριος":                      "ΑΓΙΟΥ ΔΗΜΗΤΡΙΟΥ",
    # Δυτικός Τομέας
    "Πετρούπολη":                           "ΠΕΤΡΟΥΠΟΛΕΩΣ",
    "Δήμος Πετρούπολης":                    "ΠΕΤΡΟΥΠΟΛΕΩΣ",
    "Ίλιον":                                "ΙΛΙΟΥ",
    "Χαϊδάρι":                              "ΧΑΙΔΑΡΙΟΥ",
    "Χαΐδάρι":                              "ΧΑΙΔΑΡΙΟΥ",
    # Δυτική Αττική
    "Μάνδρα":                               "ΜΑΝΔΡΑΣ ΕΙΔΥΛΛΙΑΣ",
    "Μάνδρα - Ειδύλλια":                   "ΜΑΝΔΡΑΣ ΕΙΔΥΛΛΙΑΣ",
    "Μέγαρα":                               "ΜΕΓΑΡΕΩΝ",
    # Ανατολική Αττική
    "Ραφήνα-Πικέρμι":                       "ΡΑΦΗΝΑΣ ΠΙΚΕΡΜΙΟΥ",
    "Ραφήνα - Πικέρμι":                     "ΡΑΦΗΝΑΣ ΠΙΚΕΡΜΙΟΥ",
    "Σπάτα-Αρτέμιδα":                       "ΣΠΑΤΩΝ ΑΡΤΕΜΙΔΟΣ",
    "Σπάτα - Αρτέμιδα":                     "ΣΠΑΤΩΝ ΑΡΤΕΜΙΔΟΣ",
    "Μαραθώνας":                            "ΜΑΡΑΘΩΝΟΣ",
    "Νέα Μάκρη":                            "ΜΑΡΑΘΩΝΟΣ",
    "Λαυρεωτική":                           "ΛΑΥΡΕΩΤΙΚΗΣ",
    "Κρωπία":                               "ΚΡΩΠΙΑΣ",
    "Σαρωνικός":                            "ΣΑΡΩΝΙΚΟΥ",
    "Μαρκόπουλο Μεσογαίας":                "ΜΑΡΚΟΠΟΥΛΟΥ ΜΕΣΟΓΑΙΑΣ",
    "Παιανία":                              "ΠΑΙΑΝΙΑΣ",
    "Βάρη-Βούλα-Βουλιαγμένη":             "ΒΑΡΗΣ ΒΟΥΛΑΣ ΒΟΥΛΙΑΓΜΕΝΗΣ",
    "Βάρη - Βούλα - Βουλιαγμένη":         "ΒΑΡΗΣ ΒΟΥΛΑΣ ΒΟΥΛΙΑΓΜΕΝΗΣ",
    # Νέα + compounds (ΝΕΑ → ΝΕΑΣ mismatch)
    "Νέα Ιωνία":                            "ΝΕΑΣ ΙΩΝΙΑΣ",
    "Νέα Σμύρνη":                           "ΝΕΑΣ ΣΜΥΡΝΗΣ",
    # OSM GeoPackage boundary is "Δήμος Νέας Φιλαδέλφειας - Νέας Χαλκηδόνας";
    # municipalities.json uses the short form "Δ. ΦΙΛΑΔΕΛΦΕΙΑΣ - ΧΑΛΚΗΔΟΝΟΣ".
    "Νέα Φιλαδέλφεια-Νέα Χαλκηδόνα":                  "ΦΙΛΑΔΕΛΦΕΙΑΣ ΧΑΛΚΗΔΟΝΟΣ",
    "Νέα Φιλαδέλφεια - Νέα Χαλκηδόνα":                "ΦΙΛΑΔΕΛΦΕΙΑΣ ΧΑΛΚΗΔΟΝΟΣ",
    "Νέα Φιλαδέλφεια":                                  "ΦΙΛΑΔΕΛΦΕΙΑΣ ΧΑΛΚΗΔΟΝΟΣ",
    "Δήμος Νέας Φιλαδέλφειας - Νέας Χαλκηδόνας":      "ΦΙΛΑΔΕΛΦΕΙΑΣ ΧΑΛΚΗΔΟΝΟΣ",
}


def strip_political_terms(text: str) -> str:
    """Remove accents, special characters, and administrative stop-words.

    Transformation pipeline:

    1. UPPER-case folding.
    2. NFD accent decomposition (robust for all Greek encodings).
    3. Delimiter normalisation (``-``, ``_``, en/em dashes → space).
    4. Administrative stop-word removal (``ΔΗΜΟΤΙΚΗ ΕΝΟΤΗΤΑ``,
       ``ΔΗΜΟΣ``, ``Δ.Ε.``, ``Δ.``), longest first to avoid partial hits.
    5. Whitespace collapse.

    Parameters
    ----------
    text : str
        Raw Greek administrative name, e.g.
        ``"Δημοτική Ενότητα Κρυονερίου"``.

    Returns
    -------
    str
        Normalised key, e.g. ``"ΚΡΥΟΝΕΡΙΟΥ"``.  Returns an empty string if
        *text* is not a ``str``.
    """
    if not isinstance(text, str):
        return ""

    t = text.upper().strip()

    t = "".join(
        c for c in unicodedata.normalize("NFD", t)
        if unicodedata.category(c) != "Mn"
    )

    for delimiter in ("-", "_", "–", "—"):
        t = t.replace(delimiter, " ")

    _STOP_WORDS: tuple[str, ...] = (
        "ΔΗΜΟΤΙΚΗ ΕΝΟΤΗΤΑ",
        "ΔΗΜΟΤΙΚΕΣ ΕΝΟΤΗΤΕΣ",
        "ΔΗΜΟΣ",
        "Δ.Ε.",
        "Δ.",
    )
    for sw in _STOP_WORDS:
        t = t.replace(sw, "")

    return " ".join(t.split())


def normalize_name(raw_name: str) -> str:
    """Apply alias lookup followed by political-term stripping.

    This is the single entry-point callers should use when preparing a name
    for dictionary lookup.  It first checks :data:`ALIASES` for a known
    nominative → genitive mapping; if found, the pre-normalised value is
    returned after stop-word stripping.  If no alias exists, the raw name
    is normalised directly.

    Parameters
    ----------
    raw_name : str
        The name exactly as it appears in OSM or in user-facing labels.

    Returns
    -------
    str
        Normalised key suitable for lookup-table matching.
    """
    aliased = ALIASES.get(raw_name, raw_name)
    return strip_political_terms(aliased)
