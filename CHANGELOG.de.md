# Changelog – PixxelSpool

Format: [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach [SemVer](https://semver.org/lang/de/)
(MAJOR.MINOR.PATCH: MAJOR = Umbau mit Datenmigration, MINOR = neue Funktion, PATCH = Fehlerbehebung).
Vorabversionen heißen `-alpha.N`, `-beta.N` und `-rc.N`; sie werden nur Installationen angeboten, die schon eine
Vorabversion nutzen oder es in den Optionen einschalten. Pi, Windows-App und Mac-App haben dieselbe Versionsnummer. Korrekturen
nur für die Apps bekommen die Nummer der aktuellen Version mit dem Zusatz `-patch.N`; der Pi bietet diese nicht an.

Der englische Changelog ist [CHANGELOG.md](CHANGELOG.md).

## [1.0.0-beta.3] – 2026-11-25

Zweite Sammelversion: alles, was zu beta.2 gemeldet wurde.

### Behoben
- Ein Neustart (z. B. nach einem Update) bucht den letzten fertigen Druck des Druckers nicht mehr ein zweites Mal.
- Kann die Druckdatei nicht vom Drucker gelesen werden, erscheint ein Hinweis und der Druck wird markiert, auch nach einem Neustart.
- Eine Rolle am externen Halter zeigt "Externe Spule" statt "im AMS: External spool".
- Katalog: Der Hinweis bei Farben, die Bambu Lab nicht mehr verkauft, heißt jetzt "nicht mehr erhältlich" und ragt nicht mehr in die Nachbarkachel. Der Schalter zum Einblenden ist von Optionen › Darstellung in die Katalog-Filter gewandert ("Nicht mehr erhältliche zeigen").
- Keine sichtbaren Scrollbalken mehr; Scrollen geht wie bisher.
- 3MF prüfen: Der Hinweis sagt jetzt, dass man für exakte Werte die geslicte Druckplatte (.gcode.3mf) aus Bambu Studio exportiert.

### Geändert
- Sortieren durch Ziehen ging zu leicht aus Versehen: Es geht jetzt nur nach "Sortieren", und die Änderungen sind nur vorgemerkt, bis du "übernehmen" klickst.
- Neuer Ladebildschirm: eine Spule, die sich in Bambu-Farben aufwickelt, statt grauer Platzhalter.

### Neu
- Letzte Drucke: Bei einem Druck, dessen Datei nicht gelesen werden konnte, lassen sich die Mengen von Hand nachtragen oder aus der exportierten .gcode.3mf übernehmen.
- Einkaufsliste: Anzahl je Farbe wählbar (− / +). Der Eintrag bleibt, bis so viele neue Rollen eingelagert sind.
- Preise je Lieferung: Lieferung als Refills markieren. Der Preisverlauf zeigt Spulen und Refills als zwei Linien; Gratis-Rollen (0 €) zählen nicht mit.

## [1.0.0-beta.2] – 2026-11-25

Erste Sammelversion der Beta: alle seit beta.1 gemeldeten Fehler, dazu einige kleine Ergänzungen, die das Melden von
Fehlern und das Prüfen von Drucken leichter machen.

### Behoben
- Externer Halter: "Rolle zuordnen" (β) geht jetzt auch dort; Verbrauch und Kosten von Drucken am externen Halter werden der Rolle gebucht.
- Drucker ohne AMS: Die externe Spule wird angezeigt, Druckkontrolle und Statistik laufen.
- AMS-Rolle ohne Bambu-Chip und ohne eingestelltes Material am Drucker gilt nicht mehr als leer und lässt sich zuordnen.
- Externe Halter werden nach ihrer ID (254/255) benannt; Gramm aus der Druckdatei landen beim richtigen Halter.
- Inventur: Entnommene Rollen (z. B. am externen Halter) zählen nicht mehr als "nicht gefunden".
- Scannen einer Bambu-Rolle hängt den Tag nicht mehr an eine gleichfarbige, von Hand ins AMS zugeordnete Rolle.
- Lager-Kachel: Eine Rolle am externen Halter zeigt "Ext." statt "AMS".
- Preise stehen immer mit zwei Nachkommastellen da (9 → 9,00 €), auch direkt nach der Eingabe.
- Katalog: Farben, die Bambu Lab nicht mehr verkauft (PETG Basic 30404, 30504, 30701, 30702), zählen nicht mehr als fehlend. Sie sind ausgeblendet; unter Optionen › Darstellung lassen sie sich einblenden, mit dem Hinweis "nicht mehr im Sortiment" und ohne Shop-Link.
- Katalog: PLA Basic Gradient und PLA Silk Multi-Color sind eigene Linien statt unter PLA Basic / PLA Silk. Preise und Gewichte werden übernommen.
- Listenansicht am PC: Die linke Spalte (AMS, Klima) scrollt für sich und landet nicht mehr unter einer langen Lagerliste.
- Eine geöffnete Rolle zeigt keinen Refill-Schalter mehr. Wird ein Refill im AMS erkannt, fragt PixxelSpool jetzt immer, ob dafür eine leere Spule genommen wurde.
- Drucke mit Gratis-Rollen (0 €) zeigen 0,00 € statt "–"; Drucke, die vor der Preiseingabe gebucht wurden, bekommen ihre Kosten nachträglich.
- 3MF prüfen: Geslicte Dateien zeigen nicht mehr "0 Objekte".
- 3MF prüfen: Eine Farbe, die nur als Hex-Code vorliegt (z. B. #9C7149), zeigt die nächste Bambu-Farbe, mit dem Hinweis, dass sie nur ähnlich ist.
- 3MF prüfen: Bemalte, ungeslicte Dateien zeigen alle bemalten Filamente mit ihrem Anteil, nicht nur die Grundfarbe.
- Updates: Als "Security" markierte Versionen werden auch angeboten, wenn "Vorabversionen anbieten" auf Aus steht.

### Neu
- 3MF prüfen: Kosten des Drucks je Filament und gesamt, aus dem Lagerpreis, dem Linienpreis oder, wenn beides fehlt, dem Preis in der Datei (als Schätzung beschriftet). Übersichtlichere Darstellung mit Bambu-Farbnamen und Mengen.
- Letzte Drucke: Ein Klick zeigt Verbrauch und Kosten je Filament. Drucke können einen Projektnamen bekommen; die Statistik zeigt eine Karte "Projekte".
- Statistik: Preisverlauf je Linie.
- Raspberry Pi: Meldung, wenn der Strom ohne Herunterfahren getrennt wurde.
- Suche: Ein X leert und schließt die Suche. "/" öffnet sie, Pfeiltasten und Enter wählen einen Treffer.
- "Leer" fragt nicht mehr nach; stattdessen erscheint "Rückgängig".
- Leiste "Heute" auf der Startseite; Platzhalter, während die Seite lädt.
- Rollen-Details und Einkaufsliste zeigen, wie lange eine Farbe bei deinem Verbrauch ungefähr reicht.
- Optionen › Sicherung: Rollen und Drucke als CSV exportieren.
- Ziehen und Ablegen in der AMS-Ansicht: Rolle auf freien Platz = verschieben, auf belegten Platz = tauschen.
- Optionen › Über und Protokoll: "Fehler melden" öffnet ein GitHub-Issue mit Version, Plattform und Gerät vorausgefüllt. Der Protokoll-Export beginnt mit diesen Angaben (ohne Tokens, Kennwörter oder Zugangscodes).

## [1.0.0-beta.1] – 2026-11-19

### Erste Beta
- Erste Beta von **PixxelSpool by pixxelhoff**: Lagerverwaltung für 3D-Filament (Bambu Lab) mit NFC-Leser, Drucker- und AMS-Anbindung, Home Assistant, Sicherungen, Kennwort und Passkeys, Fernzugriff über Tailscale. Raspberry Pi, Windows-App und Mac-App haben dieselbe Version.
- Ab jetzt werden nur noch Fehlerbehebungen gesammelt und gebündelt veröffentlicht, keine neuen Funktionen mehr bis zur fertigen 1.0.0.
- Optionen › System › Updates: „Vorabversionen anbieten“ hat die Stufen **Aus**, **Beta** und **Alpha**.
- Vorher privat entwickelt; die früheren öffentlichen Versionen waren `1.0.0-alpha.1` bis `1.0.0-alpha.97`.
