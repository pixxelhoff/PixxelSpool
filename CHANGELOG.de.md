# Changelog – PixxelSpool

Format: [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach [SemVer](https://semver.org/lang/de/)
(MAJOR.MINOR.PATCH: MAJOR = Umbau mit Datenmigration, MINOR = neue Funktion, PATCH = Fehlerbehebung).
Vorabversionen heißen `-alpha.N`, `-beta.N` und `-rc.N`; sie werden nur Installationen angeboten, die schon eine
Vorabversion nutzen oder es in den Optionen einschalten. Pi, Windows-App und Mac-App haben dieselbe Versionsnummer. Korrekturen
nur für die Apps bekommen die Nummer der aktuellen Version mit dem Zusatz `-patch.N`; der Pi bietet diese nicht an.

Der englische Changelog ist [CHANGELOG.md](CHANGELOG.md).

## [1.0.0-beta.7] – 2026-11-28

Sechstes Sammelrelease. Neu sind vor allem Bestellungen: von der Einkaufsliste über die laufende Bestellung bis zum Einscannen der Lieferung. Dazu sind Statistik und Optionen übersichtlicher.

### Neu
- **Bestellungen:** Bestellung mit Preisen, Versand und Bambu-Lab-Credits erfassen. Laufende Bestellungen haben eine eigene Karte, mit Paketen und Sendungsnummer. „Lieferung einscannen“ hakt die neuen Rollen ab und übernimmt Preis und Refill. „Nochmal bestellen“ holt eine alte Bestellung zurück auf die Liste.
- **Einkaufsliste:** Jeder Eintrag hat einen Status (Vorgemerkt, Im Warenkorb, Bestellt, Nicht lieferbar) und einen Refill-Schalter. Eine Spulen-Bilanz zeigt, ob die leeren Spulen für die Refills reichen. „+N“ setzt die fehlende Anzahl zum Mindestbestand auf die Liste. Die Liste lässt sich als Text teilen.
- **Farben** (bisher „Katalog“): Kacheln nach Status gefärbt und mit Mindestbestand; Filter nach Status, Material und Suche; neue Farbkarte.
- **Statistik:** Reiter Überblick, Verbrauch, Kosten und Drucke mit frei wählbarem Zeitraum; neue Karte „Ausgaben“ und laufende Bestellungen im Überblick.
- **Fehler melden** per E-Mail, auch für falsche Katalogdaten.

### Geändert
- Optionen neu sortiert: Lager, Einkauf, Hinweise, Geräte, App, System, Über.
- „Heute“ zeigt auch Rollen, die unterwegs sind, und Rollen, die laut AMS leer sind.
- 9 PETG-Matte-Farben, die es im Shop nicht gibt, sind ausgeblendet.
- „Farbe aus Bild“ ist in den Reiter Drucken umgezogen.

### Behoben
- Druckprüfung: „danach Slot …“ beim AMS-Filament-Backup griff nie.
- Lager sortieren: Hin- und Zurückschieben zählte als Änderung.
- Einkaufsliste: Der Klick auf „Shop“ ging manchmal verloren.
- Eine Rolle, die laut AMS leer ist, wurde zum Zurücklegen statt zum Austragen vorgeschlagen.

## [1.0.0-beta.6] – 2026-11-26

Fünftes Sammelrelease mit Fehlerkorrekturen.

### Behoben
- AMS HT: Die Einheit hieß „AMS 129 · Slot 1“ und galt immer als leer, auch mit eingelegter Rolle. Sie heißt jetzt „AMS HT 1“, die Rolle wird erkannt, und Drucke daraus werden dem richtigen Platz zugeordnet.
- 3MF prüfen: Der Link „Shop“ öffnete oft nichts, weil Live-Meldungen vom Drucker das Ergebnis neu zeichneten; aufgeklappte Abschnitte klappen auch nicht mehr von selbst zu. „Shop“ ist jetzt ein kleiner Knopf.
- Etiketten (Safari): Ein offener Druckdialog konnte den PixxelSpool-Tab im Hintergrund einfrieren. Die Etiketten öffnen jetzt im selben Tab mit einem Link „‹ PixxelSpool“ zurück.

## [1.0.0-beta.5] – 2026-11-26

Viertes Sammelrelease mit Sicherheitskorrekturen. Installationen mit automatischen Sicherheitsupdates bekommen es von selbst.

### Sicherheit
- Mehrere Sicherheitsverbesserungen an der Weboberfläche, beim Wiederherstellen von Sicherungen und bei der Anmeldung. Update wird empfohlen.
- Tipp: Ein Kennwort setzen (Optionen › System), wenn andere dein Netzwerk nutzen oder du Fernzugriff verwendest.

### Behoben
- Etiketten: Safari druckte alles etwas zu groß, dadurch rutschte die letzte Reihe auf eine eigene Seite.
- Etiketten: Die Wahl der `.local`-Adresse für den QR-Code tat in manchen Browsern nichts; über Tailscale war die Adresse falsch.
- Etiketten: „1 Seite“ und „1 Etikett“ statt „1 Seiten“ und „1 Etiketten“.
- Druckprüfung: Mit AMS-Filament-Backup zeigt ein knapper Slot nicht mehr „knapp“ und Ersatz aus dem Lager, wenn dieselbe Rolle in einem anderen AMS-Slot steckt; stattdessen „danach Slot 4“.
- 3MF prüfen: Abbrechen einer neuen Datei lässt das vorige Ergebnis stehen.
- Stromausfall-Hinweis: Die Zeit steht im üblichen Format (z. B. 26.11. 10:44).
- Mac-App: Öffnet im Standardbrowser; nur mit Chrome oder Edge als Standard gibt es ein eigenes Fenster.
- Projekt planen: Das Suchfeld hat wie die anderen Suchfelder eine Lupe.
- „Getrocknet“ bei einer nicht mehr vorhandenen Rolle gibt eine klare Meldung statt eines Serverfehlers.

### Geändert
- Ladebildschirm: „xx“ und Faden in PixxelSpool-Pink, das runde Logo in der Spulenmitte.

## [1.0.0-beta.4] – 2026-11-25

Drittes Sammelrelease, dazu eine Docker-Version.

### Behoben
- Etiketten: Safari schneidet am Seitenumbruch keine Reihen mehr ab. Ein Hinweis erklärt, wie man Kopf- und Fußzeile in Safari ausschaltet.
- Etiketten ohne QR-Code: der Text füllt das Etikett, statt winzig zu werden.
- Etiketten: die Infozeile über dem Bogen ist übersetzt.
- 3MF prüfen: große Modelle (z. B. 50 MB) werden viel schneller und mit einem Bruchteil des Speichers gelesen. Reicht der Speicher trotzdem nicht, kommt eine klare Meldung statt eines Absturzes.
- Raspberry Pi ohne Uhren-Chip: ein gezogener Stecker wird jetzt sicher erkannt, der Stromausfall-Hinweis erscheint beim nächsten Start.

### Geändert
- 3MF prüfen: neues Ergebnis. Oben eine Zusammenfassung (Gewicht, Kosten, Farben im Lager), darunter pro Filament eine klare Zeile, die Erklärung zur Schätzung ist eingeklappt.

### Neu
- Docker: PixxelSpool läuft als Container (amd64 und arm64). Siehe README-Abschnitt „Docker“.
- Etiketten: wählbar, welche Adresse der QR-Code öffnet, auch der `.local`-Name, der bei einer neuen IP-Adresse vom Router weiter funktioniert.
- 3MF prüfen: Fortschrittsbalken für Hochladen und Auswerten, mit Abbrechen-Knopf.
- README: Waveshare PN532 HAT und PN532 V3 getestet, mit Schalter- und Jumper-Einstellungen; Raspberry Pi 4 und 5 getestet.

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
