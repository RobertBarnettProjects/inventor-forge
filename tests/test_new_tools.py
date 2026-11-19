"""Argument checks of weld_body and add_custom_table, and the scratch-folder report (no Inventor needed)."""
import math
import os

import pytest

from inventor_forge.com import InventorError
from inventor_forge.tools.features import _weld_runs
from inventor_forge.tools.studies import scratch_folders


def test_square_weld_area_and_legs():
    w = _weld_runs([{"start": [0, 0, 0], "end": [100, 0, 0], "leg": 6, "leg_dirs": [[0, 0, 1], [0, 1, 0]]}])[0]
    assert w["L"] == 100 and w["angle_deg"] == 90.0
    assert math.isclose(w["area"], 18.0)


def test_leg_directions_are_made_square_to_the_run():
    # a leg given with a component along the run is projected off it, so the section stays a true triangle
    w = _weld_runs([{"start": [0, 0, 0], "end": [0, 0, 50], "leg": 5, "leg_dirs": [[1, 0, 1], [0, 1, 0]]}])[0]
    assert all(abs(x) < 1e-9 for x in (w["legs"][0][2], w["legs"][1][2]))
    assert math.isclose(w["area"], 12.5)


def test_skewed_corner_uses_the_real_angle():
    c = math.cos(math.radians(60))
    w = _weld_runs([{"start": [0, 0, 0], "end": [10, 0, 0], "leg": 4,
                     "leg_dirs": [[0, 1, 0], [0, c, math.sin(math.radians(60))]]}])[0]
    assert math.isclose(w["area"], 0.5 * 16 * math.sin(math.radians(60)), rel_tol=1e-6)


@pytest.mark.parametrize("run, msg", [
    ({"start": [0, 0, 0], "end": [0, 0, 0], "leg": 6, "leg_dirs": [[0, 0, 1], [0, 1, 0]]}, "same point"),
    ({"start": [0, 0, 0], "end": [10, 0, 0], "leg": 6, "leg_dirs": [[1, 0, 0], [0, 1, 0]]}, "along the weld"),
    ({"start": [0, 0, 0], "end": [10, 0, 0], "leg": 6, "leg_dirs": [[0, 1, 0], [0, 2, 0]]}, "same way"),
    ({"start": [0, 0, 0], "end": [10, 0, 0], "leg": 0, "leg_dirs": [[0, 1, 0], [0, 0, 1]]}, "positive"),
    ({"start": [0, 0, 0], "end": [10, 0, 0]}, "needs start"),
])
def test_bad_runs_are_refused(run, msg):
    with pytest.raises(InventorError, match=msg):
        _weld_runs([run])


def test_scratch_folders_are_found_and_sized(tmp_path):
    d = tmp_path / "AFEA_1234.tmp"
    d.mkdir()
    (d / "mesh.bin").write_bytes(b"x" * 2048)
    old = 1_000_000_000
    os.utime(d / "mesh.bin", (old, old))
    os.utime(d, (old, old))
    (tmp_path / "other").mkdir()
    rows = scratch_folders(str(tmp_path))
    assert [os.path.basename(x["path"]) for x in rows] == ["AFEA_1234.tmp"]
    assert rows[0]["idle_hours"] > 1000
