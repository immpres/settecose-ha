"""Konstanten der Settecose-Integration."""

from datetime import timedelta

DOMAIN = "settecose"

CONF_URL = "url"
CONF_TOKEN = "token"
CONF_SPACE_ID = "space_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_PRESENCE = "presence"

DEFAULT_URL = "https://app.settecose.com"
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 15

UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

# Ereignis, wenn eine Person an einem Settecose-Ort ankommt und dort Aufgaben warten
EVENT_TASKS_HERE = "settecose_tasks_here"

TASK_TYPES = ["kaufen", "abholen", "bringen", "zurueckgeben", "erledigen", "aufraeumen"]

# Typ einer Aufgabe, die in einer To-do-Liste neu angelegt wird, nach Art des Ziels
DEFAULT_TYPE_FOR_TARGET = {
    "ortstyp": "kaufen",
    "person": "bringen",
    "item": "erledigen",
    "ort": "erledigen",
}
