# Football Tracker for Home Assistant

Follow one football club (default: **FC Bayern München**) across **every competition**:
Bundesliga, Champions League, DFB-Pokal, Supercup, Club World Cup …
No per-competition setup: ESPN's club feed is used, so new competitions show up automatically.
Friendlies are hidden unless you switch them on.

Includes a dashboard card made for wall tablets:

- **Live** panel with score, minute and timeline (goals with scorer and assist, penalties, own goals, cards) – refreshes every 20 s
- **Next match** with countdown, venue, round (e.g. *Champions League · Ligaphase · 2. Spieltag*) and German TV channels
- **Fixtures**, **results grouped by competition and season** (filter chips), penalty shootouts (*i.E.*)
- **Tables** for Bundesliga and the Champions League league phase with qualification zones
- **Lineups** with formation, bench and substitutions as soon as ESPN publishes them
- Club crests (dark-mode variants when available), German (default) or English, follows your HA light/dark theme

## Installation (HACS)

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/chrfetzer/ha-football-tracker`, type *Integration*.
2. Install **Football Tracker**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → Football Tracker*, search `Bayern`,
   pick **Bayern München · ger.1** (`uefa.wchampions` is the women's team).

The integration adds the card to your dashboard resources itself (`/football_tracker/football-tracker-card.js`)
and bumps its version after each update. If you still see *Custom element doesn't exist*, reload the page once or,
in the Companion app, use *Settings → Companion app → Troubleshooting → Reset frontend cache*.

## Card

```yaml
type: custom:football-tracker-card
entity: sensor.bayern_munchen_spiele   # the "Spiele"/"Matches" sensor
```

| Option | Default | Description |
| --- | --- | --- |
| `entity` | – | The *Matches* sensor of the club |
| `title` | club name | Header text; `""` hides the header |
| `default_tab` | `upcoming` | `upcoming`, `results`, `table`, `lineup` |
| `upcoming_count` | `8` | Number of fixtures in the list |
| `show_timeline` | `true` | Goals and cards in the live/last-match panel |
| `language` | `de` | `de` or `en` |
| `accent_color` | club colour | Any CSS colour, e.g. `"#dc052d"` |
| `max_height` | – | e.g. `700px` to make the tab content scroll (the CL table has 36 rows) |

## Entities

Names follow your Home Assistant language (German shown).

| Entity | State | Notes |
| --- | --- | --- |
| `sensor.<club>_spiele` | upcoming match count | All data for the card (not written to the recorder) |
| `sensor.<club>_nachstes_spiel` | kickoff (timestamp) | Opponent, competition, round, matchday, `tv` |
| `sensor.<club>_letztes_ergebnis` | e.g. `3:1` | `result` = `W`/`D`/`L` (penalties count) |
| `binary_sensor.<club>_live` | on during a match | Live score and minute as attributes |

## Notifications

The integration fires `football_tracker_event` with `type`:
`kickoff_soon`, `kickoff`, `goal`, `goal_cancelled` (VAR), `red_card`, `halftime`, `full_time`.

Every event has `team`, `opponent`, `team_score`, `opponent_score`, `competition`, `round`, `clock`, `tv`.
`goal`, `goal_cancelled` and `red_card` add `for_us` (true when it concerns your club).
`goal` adds `goal_type` (`goal`, `penalty`, `own_goal`), `player`, `assist`, `minute`;
`full_time` adds `result` and the shootout score if there was one.

```yaml
automation:
  - alias: Bayern – Tor!
    triggers:
      - trigger: event
        event_type: football_tracker_event
        event_data: { type: goal, for_us: true }
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "⚽ TOR! {{ trigger.event.data.team_score }}:{{ trigger.event.data.opponent_score }} gegen {{ trigger.event.data.opponent }}"
          message: >-
            {{ trigger.event.data.player | default('Torschütze folgt', true) }}
            ({{ trigger.event.data.minute }})
            {%- if trigger.event.data.assist %} – Vorlage {{ trigger.event.data.assist }}{% endif %}
      # e.g. flash the living room lights red
      - action: light.turn_on
        target: { entity_id: light.wohnzimmer }
        data: { flash: long, color_name: red }

  - alias: Bayern – Anpfiff bald
    triggers:
      - trigger: event
        event_type: football_tracker_event
        event_data: { type: kickoff_soon }
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "{{ trigger.event.data.team }} – {{ trigger.event.data.opponent }}"
          message: >-
            Anpfiff in {{ trigger.event.data.minutes }} Min.
            ({{ trigger.event.data.competition }}) auf {{ trigger.event.data.tv | join(', ') }}
```

## Options

*Settings → Devices & services → Football Tracker → Configure*

- **Broadcasters (Germany)** – one rule per line, `part of competition name = channels`, `*` is the fallback. Defaults:
  ```
  Bundesliga = Sky, DAZN
  Champions League = DAZN, Prime Video
  DFB-Pokal = Sky, ARD/ZDF
  Supercup = Sat.1, Sky
  Club World Cup = DAZN
  ```
- **Kickoff reminder** – minutes before kickoff for `kickoff_soon`.
- **Include friendlies** – show pre-season and other club friendlies.
- **Calendar years of results** – 1 = this year (plus the rest of the season that started last year).

## Polling

20 s while a match is live (from 20 min before kickoff), 5 min in the 3 h before, otherwise every 30 min.
Tables refresh every 3 h and right after a match ends. Finished matches are cached on disk.

## Development

`dev/preview.html` renders the card with real sample data, no Home Assistant needed:

```bash
python -m http.server 8766
```

Open `http://localhost:8766/dev/preview.html` – add `?live=1`, `?dark=1`, `?lang=en`, `?tab=results|table|lineup`.

Data: ESPN's public (unofficial) API.
