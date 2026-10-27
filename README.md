# Polygon QC

A small QGIS plugin for reviewing existing polygon classifications one plot at a
time. Select incorrect polygons, assign the correct class, then complete the plot
to accept the rest. The plugin never splits, merges, creates, deletes, or redraws
polygons, and never writes to `class_auto`.

Licensed under **GNU GPL version 3 or later**; see [LICENSE](LICENSE).

## Try it locally

Version **0.2.0** supports **QGIS 3.40–3.x and QGIS 4.x**. Verified on Linux with
QGIS **3.40.15 / Qt 5.15.18** and **4.2.3 / Qt 6.9.2**. Other operating systems
have not been tested. No pip packages are required to use the plugin.

Version **0.1.0** remains available in Git history as the original QGIS 3 release.
Both versions are marked experimental; repository installs require enabling
**Show also experimental plugins** in the QGIS Plugin Manager settings.

1. Build the installable ZIP:

   ```sh
   python3 scripts/build.py
   ```

2. Prepare a project with a **copy** of the supplied sample GeoPackage:

   ```sh
   python3 scripts/prepare_sample.py
   ```

   Run this command with Python that can import `qgis` (on this Linux machine,
   system `python3` works). It creates `dev/review.gpkg` and `dev/sample_qc.qgz`
   and references the original RGB TIFF without copying it. Existing test work
   is never overwritten. Use `--data /path/to/sample_directory` for another
   sample containing `superpixels.gpkg` and a TIFF named after that directory.

3. In QGIS, open **Plugins → Manage and Install Plugins → Install from ZIP**,
   select `dist/polygon_qc.zip`, and install it. If necessary, enable Polygon QC
   in the Installed list.
4. Open `dev/sample_qc.qgz`.
5. Open **Vector → Polygon QC → Polygon QC** (or its toolbar button), choose
   **Polygon QC — working copy**, and click **Start review**.

The sample data is local and excluded from Git. Someone cloning this repository
must supply their own data or the same sample directory.

## Review controls

- **Click:** click polygons to add them to the selection; click again to remove
  them. No modifier key is required. This is the initial selection mode.
- **Rectangle / Polygon / Freehand:** use QGIS's corresponding selection tools.
  These draw a selection area; they do not change feature geometry. Standard
  QGIS selection modifiers still apply.
- **Class buttons:** apply a class to all selected polygons in the active plot.
  The selection clears after applying. An empty selection cannot change data.
- **Overlay:** adjust class opacity or hide the overlay to inspect the imagery.
- **Complete plot & next:** accept all remaining polygons, save completion, and
  open the next pending plot. There is no per-polygon sign-off requirement.
- **Plot list:** revisit plots after completing the current plot. Correcting a
  completed plot reopens it and requires completion again.
- **Undo last action:** undo a class change or plot completion, including after
  advancing. Undo returns to the affected plot. Undo history lasts only for the
  current session; saved corrections and plot completion survive restarts.
- **End session / close panel:** keep saved work and restore the layer's previous
  appearance and filter. Starting again resumes the first pending plot.

**Every change is saved immediately.** The QGIS Save Edits command is not needed.
Use the panel's Undo button, not QGIS's edit-buffer Undo. Closing QGIS keeps your
work. The plugin also recognizes its plot filter in a project saved mid-session.

## Data contract

The plugin supports local polygon GeoPackages with a named feature layer and
these fields:

| Field | Requirement / behavior |
| --- | --- |
| `fid` | Integer primary key; preserved |
| `plot_id` | Non-null integer grouping polygons into review units; preserved |
| `class_auto` | Non-null text containing the original class; preserved |
| `class_final` | Non-null text containing the current QC class; editable through the panel |
| `reviewed` | Integer: `0` pending, `1` original class accepted, `2` corrected |

The class palette comes from existing values in `class_auto` and `class_final`.
All other feature attributes and the geometry remain untouched. Restoring a
polygon to its original class sets `reviewed=1`. Completing a plot sets its
review states according to whether final and original classes match.

The plugin creates one small, non-spatial SQLite table, `polygon_qc_plots`, in the
working GeoPackage to record **explicit plot completion**, keyed by layer name
and plot ID. A plot whose polygons have all been corrected is still pending until
the reviewer completes it. The feature table's `gpkg_contents.last_change` is
updated when writing. No server, sidecar database, geometry conversion, or raster
editing is involved.

During review the QGIS layer is read-only. The plugin writes just the two QC
fields using an atomic SQLite transaction; a selection containing a feature from
another plot is rejected. Standard GeoPackage spatial-index triggers remain
intact. GeoPackages with custom geometry-changing triggers are unsupported.

Use **one working GeoPackage per reviewer**. Simultaneous editing of the same
file is not supported. Undo checks affected feature states and refuses to
overwrite conflicting external changes. This is a workflow tool, not a database
access-control mechanism for other applications.

## Development and verification

The source has no runtime dependencies beyond QGIS's Python environment. Tests
also need `pytest` and the GDAL/OGR Python bindings shipped with this installation.

```sh
QT_QPA_PLATFORM=offscreen python3 -m pytest -q

# Optional real-data integration: edits a temporary copy only.
QC_SAMPLE=2025-05-12_us-co-denver-2025_sample_one/superpixels.gpkg \
  QT_QPA_PLATFORM=offscreen python3 -m pytest -q

python3 scripts/build.py

# Optional desktop smoke test, using an isolated profile and temporary data copy.
# Requires the built ZIP and dev/sample_qc.qgz from the setup steps.
python3 tests/desktop_smoke.py
```

Tests cover protected data, atomic rollback, selection scope, explicit plot
completion, resuming, undo conflicts, QGIS layer refresh, panel lifecycle, and
click selection. Small test GeoPackages are generated in pytest's temporary
directory; no test datasets are committed.

For a new build, rebuild the ZIP, close QGIS, and reinstall the ZIP after reopening.
Restart QGIS after replacing an already loaded plugin so Python loads the new
modules. The build overwrites one fixed ZIP and includes only plugin source and
metadata, the icon, license, README, and changelog; it never bundles imagery,
GeoPackages, tests, or caches. Use `python3 scripts/build.py --versioned` for a
release ZIP such as `dist/polygon_qc-0.1.0.zip`.

The QGIS 4 environment can be reproduced without changing the installed desktop:

```sh
docker run --rm --network none \
  -e QT_QPA_PLATFORM=offscreen -e PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$PWD,dst=/workspace,readonly" -w /workspace \
  --entrypoint /bin/bash qgis/qgis:4.2.3-questing \
  -lc 'python3 -m pytest -q -p no:cacheprovider'
```

For the optional desktop smoke test in that container, also pass `-e DISPLAY=:99`
and run `python3 tests/desktop_smoke.py`; the QGIS launcher requires a display
variable even when Qt uses its offscreen platform. The sample project must have
been prepared first. All writes during testing go to temporary copies.

GitHub Actions runs the QGIS 4 checks and builds a downloadable ZIP on pushes and
pull requests. The full real-data integration is local because the sample is
excluded from Git. The separate **Publish to QGIS** workflow submits tagged
releases to the registry using a repository secret.

## Publishing releases

The public source repository and issue links are configured in
`polygon_qc/metadata.txt`. Keep the package directory `polygon_qc` unchanged across
releases so QGIS recognizes updates to the same plugin.

One-time setup for automatic uploads:

1. Sign in to QGIS using the existing GitHub connection. If Polygon QC does not
   yet exist in your account, [create an empty plugin](https://plugins.qgis.org/plugins/add-empty/)
   with package name `polygon_qc` and display name `Polygon QC`.
2. Create a plugin upload token from its [Tokens page](https://plugins.qgis.org/plugins/polygon_qc/tokens/).
3. Save it as `QGIS_PLUGIN_TOKEN` in this repository's
   [GitHub Actions secrets](https://github.com/aboettcher-sig/polygon-qc/settings/secrets/actions).
   GitHub sign-in connects your identity to QGIS; this separate token authorizes
   the upload workflow. Do not put the token in source files or chat.
4. Open [Publish to QGIS](https://github.com/aboettcher-sig/polygon-qc/actions/workflows/publish.yml),
   choose **Run workflow** on `main`, and use `v0.1.0 v0.2.0` for the first uploads.

For subsequent releases, run the tests, update the metadata version and both
changelogs, commit, and push a matching `vX.Y.Z` tag. The workflow builds from
that exact tag, runs QGIS 4 tests, and uploads automatically. The original
`v0.1.0` tag predates Qt 6 and was tested locally on QGIS 3 before publication.
The manual workflow also accepts a single existing tag if a release needs to
be submitted later. Submitted versions still need QGIS security scanning and
approval before users can download them from the registry.

Uploads stop on the first failure and are not automatically retried. If a
request times out, check the registry before rerunning; if the first of multiple
versions was already accepted, rerun with only the remaining tags. Existing
registry versions are never overwritten by this workflow.

The initial release is `v0.1.0`; the compatibility update is `v0.2.0`. Submit
them in that order. The review fields and existing working GeoPackages need no
migration for the compatibility update. Registry authentication belongs in the
publisher's account or a secret store, never in this repository or a ZIP.

## Repository layout

```text
polygon_qc/  Plugin source and QGIS metadata
scripts/     ZIP builder and local sample-project setup
.github/     CI checks and authenticated QGIS publishing
tests/       Storage and QGIS integration tests
dev/         Ignored local working copy and test project
dist/        Ignored generated plugin ZIP
```

Commit the source, scripts, tests, documentation, license, `pyproject.toml`, and `.gitignore`.
The original sample directory and generated artifacts are ignored. No generated
UI files, vendored dependencies, or versioned build directories are needed.
