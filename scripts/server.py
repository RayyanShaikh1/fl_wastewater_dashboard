"""Serve the dashboard and query incident data through SQLite.

Run from the repository root with: python scripts/server.py
"""
import json
import os
import sqlite3
import sys
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB = DATA / "incidents.sqlite3"


def build_database():
    source = DATA / "fdep_pnp_10y.geojson"
    if not source.exists():
        raise FileNotFoundError(
            f"Missing {source}. Run `python scripts\\download_data.py` first."
        )
    if DB.exists() and DB.stat().st_mtime >= source.stat().st_mtime:
        return
    with source.open(encoding="utf-8") as handle:
        features = json.load(handle).get("features", [])
    connection = sqlite3.connect(DB)
    try:
        connection.executescript(
            """
            DROP TABLE IF EXISTS incidents;
            CREATE TABLE incidents (
                object_id INTEGER PRIMARY KEY,
                year INTEGER NOT NULL,
                report_ms INTEGER,
                county TEXT,
                latitude REAL,
                longitude REAL,
                properties TEXT NOT NULL
            );
            CREATE INDEX incidents_year_idx ON incidents(year);
            CREATE INDEX incidents_county_idx ON incidents(county);
            """
        )
        rows = []
        for feature in features:
            properties = feature.get("properties") or {}
            report_ms = properties.get("DATE_TIME_OF_REPORT")
            try:
                year = datetime.fromtimestamp(int(report_ms) / 1000).year
            except (TypeError, ValueError, OSError):
                continue
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates") or [None, None]
            county = str(
                properties.get("AFFECTED_COUNTIES")
                or properties.get("FACILITY_COUNTY")
                or ""
            ).split(";")[0].split(",")[0].strip()
            rows.append(
                (
                    int(properties.get("OBJECTID") or len(rows) + 1),
                    year,
                    int(report_ms) if report_ms else None,
                    county,
                    coordinates[1],
                    coordinates[0],
                    json.dumps(properties, ensure_ascii=False),
                )
            )
        connection.executemany(
            "INSERT OR REPLACE INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?)", rows
        )
        connection.commit()
    finally:
        connection.close()


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/years":
            self.send_json(
                {"years": [row[0] for row in self.query("SELECT DISTINCT year FROM incidents ORDER BY year")]}
            )
            return
        if parsed.path == "/api/summary":
            self.send_json(
                {
                    "years": [
                        {"year": row[0], "incidents": row[1]}
                        for row in self.query(
                            "SELECT year, COUNT(*) FROM incidents GROUP BY year ORDER BY year"
                        )
                    ],
                    "counties": [
                        {"county": row[0] or "Unknown", "incidents": row[1]}
                        for row in self.query(
                            "SELECT county, COUNT(*) FROM incidents GROUP BY county ORDER BY COUNT(*) DESC"
                        )
                    ],
                }
            )
            return
        if parsed.path == "/api/incidents":
            query = parse_qs(parsed.query)
            try:
                start = int(query.get("start", ["1900"])[0])
                end = int(query.get("end", ["2100"])[0])
            except ValueError:
                self.send_error(400, "start and end must be years")
                return
            if start > end:
                start, end = end, start
            rows = self.query(
                "SELECT object_id, properties, latitude, longitude "
                "FROM incidents WHERE year BETWEEN ? AND ? ORDER BY report_ms",
                (start, end),
            )
            features = []
            for object_id, properties, latitude, longitude in rows:
                source = json.loads(properties)
                feature_properties = {
                    "OBJECTID": object_id,
                    "INCIDENT_NUMBER": source.get("INCIDENT_NUMBER"),
                    "INCIDENT_NAME": source.get("INCIDENT_NAME"),
                    "FACILITY_NAME": source.get("FACILITY_NAME"),
                    "AFFECTED_COUNTIES": source.get("AFFECTED_COUNTIES"),
                    "DATE_TIME_OF_REPORT": source.get("DATE_TIME_OF_REPORT"),
                }
                features.append(
                    {
                        "type": "Feature",
                        "properties": feature_properties,
                        "geometry": {
                            "type": "Point",
                            "coordinates": [longitude, latitude],
                        },
                    }
                )
            self.send_json({"type": "FeatureCollection", "features": features})
            return
        super().do_GET()

    @staticmethod
    def query(statement, parameters=()):
        connection = sqlite3.connect(DB)
        try:
            return connection.execute(statement, parameters).fetchall()
        finally:
            connection.close()

    def send_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    try:
        build_database()
        port = int(os.environ.get("DASHBOARD_PORT", "8000"))
        server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
        print(f"Dashboard: http://127.0.0.1:{port}")
        print("Keep this terminal open while using the dashboard. Press Ctrl+C to stop.")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    except OSError as error:
        print(
            f"Could not start the dashboard server: {error}\n"
            "Try another port, for example: $env:DASHBOARD_PORT='8001'; "
            "python scripts\\server.py",
            file=sys.stderr,
        )
        raise SystemExit(1)
