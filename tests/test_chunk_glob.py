"""The chunked Parquet outputs must be read by a glob that matches only them.

`data/baseline/` holds the ten chunk files of each Step 2 output and also the
outputs of `scripts/step2_diagnostics.py`, which sit beside them. A bare
`label_*.parquet` matches `label_noevent_*.parquet` too, and reads every
zone-year twice, once with event observations excluded. It raises nothing,
returns a plausible row count, and doubles the population underneath every
metric computed on it.

This was latent from Step 2 until Step 4 and cost nothing published, because
the Step 2 gate happened to run before the diagnostics wrote their files. That
is luck, not design, which is why it is pinned here.
"""

import fnmatch
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import build_baseline as bb  # noqa: E402

OUTPUTS = ("label", "feature", "baseline")


def pattern(name):
    return os.path.basename(bb.chunks(name))


def test_the_glob_matches_every_chunk_file():
    for name in OUTPUTS:
        for chunk in range(bb.CHUNKS):
            filename = f"{name}_{chunk:02d}.parquet"
            assert fnmatch.fnmatch(filename, pattern(name)), filename


def test_the_glob_does_not_match_a_diagnostic_output():
    """`label_noevent_03.parquet` is a real file that really sits there."""
    for name in OUTPUTS:
        for other in (f"{name}_noevent_03.parquet", f"tmp_{name}_07.parquet",
                      f"{name}cells_noevent_00.parquet", f"{name}_summary.parquet"):
            assert not fnmatch.fnmatch(other, pattern(name)), other


def test_no_script_reads_a_chunked_output_with_a_bare_glob():
    """The helper only helps if it is the thing every reader calls.

    Diagnostics are exempt: they name their own outputs explicitly, and
    `label_noevent_*.parquet` is unambiguous because nothing else starts that
    way.
    """
    scripts = pathlib.Path(__file__).resolve().parents[1] / "scripts"
    offenders = []
    for path in sorted(scripts.glob("*.py")):
        if path.name == "step2_diagnostics.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "read_parquet" not in line:
                continue          # prose may name the bad pattern; only reads matter
            for name in OUTPUTS:
                if f"{name}_*.parquet" in line:
                    offenders.append(f"{path.name}:{number} reads {name}_*.parquet")
    assert not offenders, "; ".join(offenders)
