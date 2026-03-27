from __future__ import annotations

import shutil
from pathlib import Path

from vl2d.config import Settings
from vl2d.domain import AudioArtifact
from vl2d.providers.base import EnhancerProvider


class SEMambaEnhancerProvider(EnhancerProvider):
    name = "semamba"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def enhance(self, segment_path: Path, output_path: Path) -> AudioArtifact:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(segment_path, output_path)
        return AudioArtifact(
            path=output_path,
            sample_rate=self.settings.sample_rate,
            metadata={
                "provider": self.name,
                "degraded": True,
                "message": "SEMamba integration shell is in place; install the real model runtime to replace passthrough behavior.",
            },
        )

