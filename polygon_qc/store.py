"""Atomic, attribute-only GeoPackage edits, independent of QGIS UI state.

The feature table is updated ONLY through class_final and reviewed. A separate
table records explicit plot completion. No geometry is decoded or written.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3


class ReviewError(Exception):
    """An actionable error which can be shown directly to the reviewer."""


def quote(name):
    return '"' + name.replace('"', '""') + '"'


@dataclass(frozen=True)
class FeatureState:
    fid: int
    automatic: str
    final: str
    reviewed: int


@dataclass(frozen=True)
class Change:
    plot: int
    before: tuple
    after: tuple
    completed_before: bool
    completed_after: bool
    label: str


class ReviewStore:
    STATE_TABLE = "polygon_qc_plots"

    def __init__(self, path, table="superpixels"):
        self.path = Path(path).resolve()
        self.table = table
        self.sql_table = quote(table)
        self.history = []
        with self.connection() as db:
            columns = db.execute(f"PRAGMA table_info({self.sql_table})").fetchall()
            names = {r[1] for r in columns}
            required = {"fid", "plot_id", "class_auto", "class_final", "reviewed"}
            if not required <= names:
                raise ReviewError("Layer needs fid, plot_id, class_auto, class_final, and reviewed fields.")
            primary = [r for r in columns if r[5]]
            if len(primary) != 1 or primary[0][1] != "fid" or primary[0][2].upper() != "INTEGER":
                raise ReviewError("The GeoPackage must use an INTEGER fid primary key.")
            geometry = db.execute(
                "SELECT geometry_type_name FROM gpkg_geometry_columns WHERE table_name=?", (table,)
            ).fetchone()
            if not geometry or geometry[0].upper() not in ("POLYGON", "MULTIPOLYGON"):
                raise ReviewError("Choose a polygon GeoPackage layer.")
            bad = db.execute(
                f"SELECT COUNT(*) FROM {self.sql_table} WHERE "
                "typeof(plot_id) != 'integer' OR class_auto IS NULL OR class_final IS NULL "
                "OR typeof(class_auto) != 'text' OR typeof(class_final) != 'text' "
                "OR typeof(reviewed) != 'integer' OR reviewed NOT IN (0,1,2) "
                "OR (reviewed=1 AND class_auto != class_final) "
                "OR (reviewed=2 AND class_auto = class_final)"
            ).fetchone()[0]
            if bad:
                raise ReviewError(f"{bad} features have invalid plot IDs, classes, or review states. No data changed.")
            self.plots = tuple(r[0] for r in db.execute(
                f"SELECT DISTINCT plot_id FROM {self.sql_table} ORDER BY plot_id"
            ))
            self.classes = tuple(r[0] for r in db.execute(
                f"SELECT class_auto FROM {self.sql_table} UNION SELECT class_final "
                f"FROM {self.sql_table} ORDER BY 1"
            ))
            if not self.plots:
                raise ReviewError("The layer has no polygons.")

    @staticmethod
    def _deny_geometry(*args):
        # Standard GeoPackage RTree triggers reference these functions even on
        # attribute-only UPDATEs. Their WHEN clauses skip calls when fid and
        # geometry are unchanged. Fail closed if a custom trigger calls them.
        raise sqlite3.OperationalError("Geometry operations are not permitted by Polygon QC")

    @contextmanager
    def connection(self, write=False):
        db = None
        try:
            uri = self.path.as_uri() + ("?mode=rw" if write else "?mode=ro")
            db = sqlite3.connect(uri, uri=True, timeout=2)
            for function in ("ST_IsEmpty", "ST_MinX", "ST_MaxX", "ST_MinY", "ST_MaxY"):
                db.create_function(function, 1, self._deny_geometry)
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except sqlite3.Error as exc:
            if db is not None:
                db.rollback()
            raise ReviewError(f"GeoPackage operation failed; no partial changes were saved. {exc}") from exc
        finally:
            if db is not None:
                db.close()

    def _ensure_state(self, db):
        db.execute(
            f"CREATE TABLE IF NOT EXISTS {self.STATE_TABLE} ("
            "layer_name TEXT NOT NULL, plot_id INTEGER NOT NULL, "
            "completed INTEGER NOT NULL CHECK(completed IN (0,1)), "
            "PRIMARY KEY(layer_name,plot_id))"
        )

    def _has_state(self, db):
        return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                          (self.STATE_TABLE,)).fetchone() is not None

    def _completed(self, db, plot):
        if not self._has_state(db):
            return False
        row = db.execute(f"SELECT completed FROM {self.STATE_TABLE} WHERE layer_name=? AND plot_id=?",
                         (self.table, plot)).fetchone()
        return bool(row and row[0])

    def _set_completed(self, db, plot, completed):
        self._ensure_state(db)
        db.execute(
            f"INSERT INTO {self.STATE_TABLE}(layer_name,plot_id,completed) VALUES (?,?,?) "
            "ON CONFLICT(layer_name,plot_id) DO UPDATE SET completed=excluded.completed",
            (self.table, plot, int(completed)),
        )

    def _rows(self, db, plot):
        return tuple(FeatureState(*r) for r in db.execute(
            f"SELECT fid,class_auto,class_final,reviewed FROM {self.sql_table} WHERE plot_id=? ORDER BY fid",
            (plot,),
        ))

    def _check_plot(self, plot):
        if plot not in self.plots:
            raise ReviewError("Unknown plot.")

    def summary(self):
        with self.connection() as db:
            counts = dict(db.execute(f"SELECT plot_id,COUNT(*) FROM {self.sql_table} GROUP BY plot_id"))
            completed = set()
            if self._has_state(db):
                completed = {r[0] for r in db.execute(
                    f"SELECT plot_id FROM {self.STATE_TABLE} WHERE layer_name=? AND completed=1",
                    (self.table,),
                )} & set(self.plots)
            return counts, completed

    def _write_rows(self, db, rows):
        db.executemany(f"UPDATE {self.sql_table} SET class_final=?,reviewed=? WHERE fid=?",
                       [(r.final, r.reviewed, r.fid) for r in rows])

    def _touch(self, db):
        db.execute("UPDATE gpkg_contents SET last_change=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                   "WHERE table_name=?", (self.table,))

    def assign(self, plot, fids, target):
        self._check_plot(plot)
        chosen = set(fids)
        if not chosen:
            raise ReviewError("Select one or more polygons first.")
        if target not in self.classes:
            raise ReviewError("Choose a class from the class list.")
        with self.connection(write=True) as db:
            rows = self._rows(db, plot)
            if not chosen <= {r.fid for r in rows}:
                raise ReviewError("Selection includes polygons outside the active plot. Nothing changed.")
            before = tuple(r for r in rows if r.fid in chosen)
            after = tuple(FeatureState(r.fid, r.automatic, target,
                                       1 if r.automatic == target else 2) for r in before)
            if before == after:
                return False
            was_complete = self._completed(db, plot)
            self._write_rows(db, after)
            # Any correction to a completed plot requires explicit completion again.
            self._set_completed(db, plot, False)
            self._touch(db)
        self.history.append(Change(plot, before, after, was_complete, False, "class change"))
        return True

    def complete(self, plot):
        self._check_plot(plot)
        with self.connection(write=True) as db:
            before = self._rows(db, plot)
            was_complete = self._completed(db, plot)
            after = tuple(FeatureState(r.fid, r.automatic, r.final,
                                       1 if r.automatic == r.final else 2) for r in before)
            if was_complete and before == after:
                return False
            self._write_rows(db, after)
            self._set_completed(db, plot, True)
            self._touch(db)
        self.history.append(Change(plot, before, after, was_complete, True, "plot completion"))
        return True

    def undo(self):
        if not self.history:
            raise ReviewError("There are no actions to undo in this review session.")
        change = self.history[-1]
        with self.connection(write=True) as db:
            current = {r.fid: r for r in self._rows(db, change.plot)}
            if (any(current.get(r.fid) != r for r in change.after)
                    or self._completed(db, change.plot) != change.completed_after):
                raise ReviewError("This plot changed outside this session. Undo was refused to preserve those changes.")
            self._write_rows(db, change.before)
            self._set_completed(db, change.plot, change.completed_before)
            self._touch(db)
        self.history.pop()
        return change

