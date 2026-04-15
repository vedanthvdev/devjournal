---
tags:
  - weekly_note
---

### Summary for the Week


### Daily Notes This Week

```dataview
TABLE WITHOUT ID
  file.link AS "Day",
  choice(length(file.lists.text) > 0, length(file.lists.text) + " items", "—") AS "Entries"
FROM "Journal/Daily"
WHERE contains(tags, "daily_note")
SORT file.name ASC
```

### Key Accomplishments
-

### Carry Forward to Next Week
- [ ]
