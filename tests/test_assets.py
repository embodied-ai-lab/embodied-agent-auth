from __future__ import annotations

import hashlib

from PIL import Image


def test_required_scene_images_are_real_and_distinct(repo_root):
    names = ("green_clear.png", "red_clear.png")
    digests = set()
    for name in names:
        path = repo_root / "assets" / "vision" / name
        assert 25_000 < path.stat().st_size < 45_000
        with Image.open(path) as image:
            assert image.size == (384, 288)
            image.verify()
        digests.add(hashlib.sha256(path.read_bytes()).hexdigest())
    assert len(digests) == 2
