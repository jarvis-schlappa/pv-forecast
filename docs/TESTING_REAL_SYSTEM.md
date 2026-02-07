# Real-System Testkonzept

Dieses Dokument beschreibt manuelle Tests für Szenarien, die Unit-Tests nicht abdecken können.

## 🎯 Ziel

Fehler finden, die nur im echten Betrieb auftreten:
- Netzwerk-Timeouts, Rate-Limits
- Datenbank-Zustandsabhängigkeiten
- Interaktion zwischen Komponenten
- Edge Cases bei Datumsberechnung

---

## 📋 Testszenarien

### 1. HOSTRADA Duplikat-Erkennung

**Ziel:** Sicherstellen, dass bereits heruntergeladene Daten nicht erneut geladen werden.

```bash
# Setup: Leere Test-DB
pvforecast --db /tmp/test-hostrada.db setup

# Test 1: Erster Download
pvforecast --db /tmp/test-hostrada.db fetch-historical \
  --source hostrada --start 2024-01-01 --end 2024-01-31 -y

# Test 2: Gleicher Zeitraum → sollte "bereits vorhanden" melden
pvforecast --db /tmp/test-hostrada.db fetch-historical \
  --source hostrada --start 2024-01-01 --end 2024-01-31

# Test 3: Überlappender Zeitraum → nur Feb laden
pvforecast --db /tmp/test-hostrada.db fetch-historical \
  --source hostrada --start 2024-01-15 --end 2024-02-15

# Test 4: --force überschreibt
pvforecast --db /tmp/test-hostrada.db fetch-historical \
  --source hostrada --start 2024-01-01 --end 2024-01-31 --force
```

**Erwartung:**
- Test 2: "Alle Monate bereits in Datenbank"
- Test 3: "1 Monat übersprungen, 1 fehlend"
- Test 4: Lädt alle Monate trotz Existenz

---

### 2. Datenquellen-Mischung

**Ziel:** HOSTRADA-Daten in DB mit Open-Meteo-Daten → --force nötig?

```bash
# Setup: DB mit Open-Meteo-Daten
pvforecast --db /tmp/test-mixed.db import ~/e3dc-data/

# Frage: fetch-historical --source hostrada → überspringt Monate?
pvforecast --db /tmp/test-mixed.db fetch-historical \
  --source hostrada --start 2020-01-01 --end 2020-03-31

# Mit --force sollte es funktionieren
pvforecast --db /tmp/test-mixed.db fetch-historical \
  --source hostrada --start 2020-01-01 --end 2020-03-31 --force -y
```

**Erwartung:** Ohne --force wird übersprungen (BUG oder Feature?). Mit --force funktioniert.

**TODO:** Quellen-Spalte in weather_history hinzufügen?

---

### 3. Datums-Edge-Cases

**Ziel:** Grenzfälle bei Monats-/Jahreswechsel.

```bash
# Jahreswechsel
pvforecast fetch-historical --source hostrada \
  --start 2023-12-15 --end 2024-01-15

# Schaltjahr Februar
pvforecast fetch-historical --source hostrada \
  --start 2024-02-01 --end 2024-02-29

# Zukunft (sollte fehlschlagen)
pvforecast fetch-historical --source hostrada \
  --start 2026-01-01 --end 2026-01-31
```

---

### 4. Prognose-Konsistenz

**Ziel:** MOSMIX und Open-Meteo liefern unterschiedliche Werte - sind beide plausibel?

```bash
# Vergleich für heute
pvforecast today --source mosmix --format json > /tmp/mosmix.json
pvforecast today --source open-meteo --format json > /tmp/openmeteo.json

# Diff prüfen
jq -s '.[0] as $m | .[1] as $o | 
  {mosmix_total: ($m | map(.predicted_wh) | add),
   openmeteo_total: ($o | map(.predicted_wh) | add)}' \
  /tmp/mosmix.json /tmp/openmeteo.json
```

**Erwartung:** Unterschied <30% an den meisten Tagen.

---

### 5. Netzwerk-Resilienz

**Ziel:** Retry-Logik funktioniert bei Netzwerkproblemen.

```bash
# Simulieren: Firewall-Block oder Offline-Test
# (manuell Netzwerk trennen nach Start)

pvforecast fetch-historical --source hostrada \
  --start 2024-06-01 --end 2024-06-30 -y

# Sollte nach Timeout retry versuchen
```

---

## ✅ Checkliste vor Release

- [ ] Duplikat-Erkennung Test 1-4 bestanden
- [ ] Datenquellen-Mischung dokumentiert
- [ ] Datums-Edge-Cases keine Abstürze
- [ ] MOSMIX vs Open-Meteo Vergleich plausibel
- [ ] --force Flag funktioniert

---

## 🐛 Bekannte Einschränkungen

1. **Keine Quellen-Unterscheidung:** weather_history weiß nicht ob Daten von Open-Meteo oder HOSTRADA stammen. Workaround: Separate DBs oder --force.

2. **Monats-Granularität:** Skip-Check prüft nur Monat-Existenz, nicht Vollständigkeit. Wenn nur halber Monat geladen wurde, wird er trotzdem übersprungen.

3. **HOSTRADA ~2 Monate behind:** Aktuelle Monate sind nicht verfügbar.
