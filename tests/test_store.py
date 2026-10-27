import hashlib
import sqlite3

import pytest

from polygon_qc.store import ReviewError, ReviewStore, quote


def rows(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT fid,plot_id,class_auto,class_final,reviewed,notes,geom "
                          "FROM superpixels ORDER BY fid").fetchall()


def protected(rows):
    return [(r[0], r[1], r[2], r[5], r[6]) for r in rows]


def test_inspection_does_not_write(package):
    before = hashlib.sha256(package.read_bytes()).hexdigest()
    store = ReviewStore(package)
    assert store.plots == (1, 2)
    assert store.classes == ("canopy", "roads", "turf")
    assert store.summary() == ({1: 2, 2: 2}, set())
    assert hashlib.sha256(package.read_bytes()).hexdigest() == before


def test_correct_complete_restore_and_undo_preserve_protected_data(package):
    original = rows(package)
    store = ReviewStore(package)
    assert store.assign(1, [1], "canopy")
    assert rows(package)[0][3:5] == ("canopy", 2)
    assert rows(package)[1][3:5] == ("roads", 0)
    store.complete(1)
    assert rows(package)[1][3:5] == ("roads", 1)
    assert store.summary()[1] == {1}
    assert rows(package)[2:] == original[2:]
    store.assign(1, [1], "turf")
    assert rows(package)[0][3:5] == ("turf", 1)
    assert store.summary()[1] == set()
    assert store.undo().label == "class change"
    assert rows(package)[0][3:5] == ("canopy", 2)
    assert store.summary()[1] == {1}
    store.undo()
    assert rows(package)[1][3:5] == ("roads", 0)
    assert store.summary()[1] == set()
    store.undo()
    assert rows(package) == original
    assert protected(rows(package)) == protected(original)


def test_cross_plot_selection_rejected_atomically(package):
    original = rows(package)
    store = ReviewStore(package)
    with pytest.raises(ReviewError, match="outside"):
        store.assign(1, [1, 3], "canopy")
    assert rows(package) == original
    assert not store.history


def test_completion_is_explicit_even_when_every_feature_corrected(package):
    store = ReviewStore(package)
    store.assign(1, [1, 2], "canopy")
    assert all(r[4] == 2 for r in rows(package)[:2])
    assert store.summary()[1] == set()
    store.complete(1)
    resumed = ReviewStore(package)
    assert resumed.summary()[1] == {1}
    assert not resumed.history


def test_empty_selection_and_unknown_class_never_write(package):
    store = ReviewStore(package)
    before = rows(package)
    with pytest.raises(ReviewError, match="Select"):
        store.assign(1, [], "canopy")
    with pytest.raises(ReviewError, match="class list"):
        store.assign(1, [1], "'; DROP TABLE superpixels; --")
    assert rows(package) == before


def test_undo_refuses_conflicting_external_edit(package):
    first = ReviewStore(package)
    first.assign(1, [1], "canopy")
    second = ReviewStore(package)
    second.assign(1, [1], "roads")
    with pytest.raises(ReviewError, match="outside this session"):
        first.undo()
    assert rows(package)[0][3:5] == ("roads", 2)
    assert len(first.history) == 1


def test_failed_batch_rolls_back_all_rows_and_progress(package):
    with sqlite3.connect(package) as db:
        db.execute("CREATE TRIGGER simulate_failure BEFORE UPDATE OF class_final ON superpixels "
                   "WHEN NEW.fid=2 BEGIN SELECT RAISE(ABORT,'simulated failure'); END")
    store = ReviewStore(package)
    original = rows(package)
    with pytest.raises(ReviewError, match="simulated failure"):
        store.assign(1, [1, 2], "canopy")
    assert rows(package) == original
    assert store.summary()[1] == set()
    assert not store.history


def test_invalid_existing_review_state_rejected(package):
    store = ReviewStore(package)
    with store.connection(write=True) as db:
        db.execute("UPDATE superpixels SET reviewed=2 WHERE fid=1")
    with pytest.raises(ReviewError, match="invalid"):
        ReviewStore(package)


def test_same_class_assignment_accepts_original_but_does_not_complete_plot(package):
    store = ReviewStore(package)
    assert store.assign(1, [1], "turf")
    assert rows(package)[0][3:5] == ("turf", 1)
    assert not store.assign(1, [1], "turf")
    assert len(store.history) == 1
    assert store.summary()[1] == set()


def test_unknown_plot_rejected(package):
    store = ReviewStore(package)
    with pytest.raises(ReviewError, match="Unknown plot"):
        store.complete(999)
    assert store.summary()[1] == set()


@pytest.mark.parametrize("table", ["super pixels", 'superpixels"; DROP TABLE gpkg_contents; --'])
def test_quoted_layer_names_remain_identifiers(package, table):
    original = rows(package)
    with sqlite3.connect(package) as db:
        db.execute(f"ALTER TABLE superpixels RENAME TO {quote(table)}")
        db.execute("UPDATE gpkg_contents SET table_name=? WHERE table_name='superpixels'", (table,))
        db.execute("UPDATE gpkg_geometry_columns SET table_name=? WHERE table_name='superpixels'", (table,))
    store = ReviewStore(package, table)
    store.assign(1, [1], "canopy")
    store.complete(1)
    assert ReviewStore(package, table).summary() == ({1: 2, 2: 2}, {1})
    store.undo()
    store.undo()
    with sqlite3.connect(package) as db:
        actual = db.execute(
            f"SELECT fid,plot_id,class_auto,class_final,reviewed,notes,geom FROM {quote(table)} ORDER BY fid"
        ).fetchall()
        assert actual == original
        assert db.execute("SELECT COUNT(*) FROM gpkg_contents WHERE table_name=?", (table,)).fetchone()[0] == 1


def test_sql_like_class_labels_are_bound_as_values(package):
    target = "canopy'; DROP TABLE gpkg_contents; --"
    with ReviewStore(package).connection(write=True) as db:
        db.execute("UPDATE superpixels SET class_final=?,reviewed=2 WHERE fid=3", (target,))
    original = rows(package)
    store = ReviewStore(package)
    store.assign(1, [1, 2], target)
    assert [r[3] for r in rows(package)[:2]] == [target, target]
    assert protected(rows(package)) == protected(original)
    store.complete(1)
    store.undo()
    store.undo()
    assert rows(package) == original

