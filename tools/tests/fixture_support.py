"""The two versioned baseline documents share one immutable golden export."""

import shutil
from pathlib import Path

BASELINE_DOCUMENTS = ("Fixture2000", "Fixture2001")


def copy_baseline_repository(source: Path, destination: Path) -> Path:
    """Copy only the golden's authored inputs, even inside a larger checkout."""
    destination.mkdir(parents=True, exist_ok=True)
    for directory in ("schema", "taxonomy"):
        shutil.copytree(source / directory, destination / directory)
    for directory in ("HomAlg", "literature"):
        (destination / directory).mkdir()
        for key in BASELINE_DOCUMENTS:
            shutil.copytree(source / directory / key, destination / directory / key)
    for filename in ("HomAlg.lean", "lakefile.toml", "lean-toolchain"):
        shutil.copyfile(source / filename, destination / filename)
    from homalg.roots import generate_roots

    for relative, text in generate_roots(destination).items():
        (destination / relative).write_text(text)
    return destination
