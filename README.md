# Settecose for Home Assistant

[Settecose](https://settecose.com) keeps track of what is where and what needs doing where. This integration brings your Settecose tasks into Home Assistant.

- **To-do lists:** one list per task group, the same groups as in the app (a place, a place type such as *Supermarket*, a person, an item). Add items and tick them off in Home Assistant; it syncs back.
- **Arriving somewhere:** when a person enters a zone that matches a Settecose place (same name, or the place's position lies inside the zone), the integration fires the event `settecose_tasks_here` with the tasks that show there. Use it in an automation to send a notification.
- **Sensors:** open tasks, items, places with a position.
- **Actions:** `settecose.add_task`, `settecose.tasks_at` (returns the tasks at a place), `settecose.import_zone` (copies a zone's position and radius to a Settecose place).

The integration only uses the public API (`/api/v1`) with a personal token. A token belongs to exactly one space; it can be read-only or allow changes.

## Installation

### HACS (custom repository)

1. HACS › three dots › *Custom repositories* › add `https://github.com/immpres/settecose-ha`, category *Integration*.
2. Install *Settecose*, restart Home Assistant.

### Manual

Copy `custom_components/settecose` into the `custom_components` folder of your Home Assistant configuration and restart.

## Setup

1. In the Settecose app: *More › Home Assistant › Create token*. Choose *Read and change* if Home Assistant should add and tick off tasks.
2. In Home Assistant: *Settings › Devices & services › Add integration › Settecose*. Paste the address and the token shown in the app.

## Example: notification on arrival

```yaml
automation:
  - alias: Settecose tasks on arrival
    triggers:
      - trigger: event
        event_type: settecose_tasks_here
    actions:
      - action: notify.mobile_app_my_phone
        data:
          title: "{{ trigger.event.data.count }} tasks at {{ trigger.event.data.location }}"
          message: "{{ trigger.event.data.tasks | map(attribute='title') | join(', ') }}"
```

## Not yet included

Assist intents («Where is the drill?»), creating Home Assistant zones from Settecose places, and a sidebar panel with the app.

---

## Kurz auf Deutsch

1. In der Settecose-App: *Mehr › Home Assistant › Token anlegen* (für Aufgaben anlegen und abhaken: *Lesen und ändern*).
2. In Home Assistant: *Einstellungen › Geräte und Dienste › Integration hinzufügen › Settecose*, Adresse und Token aus der App einfügen.

Aufgaben-Gruppen erscheinen als To-do-Listen; kommt jemand an einem Settecose-Ort an, feuert das Ereignis `settecose_tasks_here` mit den Aufgaben dort.

## License

MIT. Settecose itself is a commercial product of immpres.
