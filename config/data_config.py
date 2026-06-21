"""Data-layer configuration: paths, filenames, and column contracts.

All constants here describe the raw ODS datasets and their schemas.
Downstream modules (``OdsLoader``, ``preprocessor``, ``encoder``) import
from this module to stay in sync with the source data structure.

Notes
-----
``DATA_PATH`` is resolved relative to this file's location so it is
correct regardless of the working directory when Python is invoked.
"""

import os

# --- Paths ---
DATA_PATH  = os.path.join(os.path.dirname(__file__), '..', 'data')         + os.sep
JSON_PATH  = os.path.join(os.path.dirname(__file__), '..', 'data', 'json') + os.sep
ODS_PATH   = os.path.join(os.path.dirname(__file__), '..', 'data', 'data') + os.sep

# --- File names (plain filenames; loaders prepend the appropriate *_PATH) ---
FILE_NAME_ASTIKA = 'Stoixeia_Symvantwn.ods'
FILE_NAME_DASIKA = 'Dasikes_Pyrkagies_2024.ods'

# --- Column definitions (original Greek names) ---
REQUIRED_COLUMNS = [
    'Α/Α Εγγραφής',
    'Υπηρεσία',
    'Νομός',
    'Είδος Συμβάντος',
    'Ημερ. Έναρξης Συμβάντος',
    'Ώρα Έναρξης',
    'Ημερ. Κατάσβεσης',
    'Ώρα Κατάσβεσης',
    'Δήμος',
    'Περιοχή',
    'Περιγραφή Χώρου',
    'Χαρακτηρισμός Συμβάντος',
    'Σύνολο Πυρ. Οχημάτων',
    'Σύνολο Πυρ. Δυνάμεων (σε άνδρες και γυναίκες)',
]

DATE_COLUMNS = [
    'Ημερ. Έναρξης Συμβάντος',
    'Ημερ. Κατάσβεσης',
]

TIME_COLUMNS = [
    'Ώρα Έναρξης',
    'Ώρα Κατάσβεσης',
]

CATEGORICAL_COLUMNS = [
    'Υπηρεσία',
    'Νομός',
    'Είδος Συμβάντος',
    'Δήμος',
    'Περιοχή',
    'Περιγραφή Χώρου',
    'Χαρακτηρισμός Συμβάντος',
]

NUMERICAL_COLUMNS = [
    'Σύνολο Πυρ. Οχημάτων',
    'Σύνολο Πυρ. Δυνάμεων (σε άνδρες και γυναίκες)',
]

# --- Greek → English column name mapping ---
COLUMN_RENAME_MAP = {
    'Α/Α Εγγραφής':                                   'record_id',
    'Υπηρεσία':                                        'service',
    'Νομός':                                           'prefecture',
    'Είδος Συμβάντος':                                 'incident_type',
    'Ημερ. Έναρξης Συμβάντος':                         'start_date',
    'Ώρα Έναρξης':                                     'start_time',
    'Ημερ. Κατάσβεσης':                                'end_date',
    'Ώρα Κατάσβεσης':                                  'end_time',
    'Δήμος':                                           'municipality',
    'Περιοχή':                                         'area',
    'Περιγραφή Χώρου':                                 'location_description',
    'Χαρακτηρισμός Συμβάντος':                         'incident_characterization',
    'Σύνολο Πυρ. Οχημάτων':                            'total_vehicles',
    'Σύνολο Πυρ. Δυνάμεων (σε άνδρες και γυναίκες)':  'total_personnel',
}
