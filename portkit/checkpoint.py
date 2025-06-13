#!/usr/bin/env python3

import filecmp
import shutil
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field


class SourceCheckpoint(BaseModel):
    """Checkpoint helper to save/restore source directory state."""

    source_dir: Path
    checkpoint_dir: Path = Field(
        default_factory=lambda: Path(tempfile.mkdtemp(prefix="portkit_checkpoint_"))
    )
    saved: bool = False

    def save(self) -> None:
        """Save current state of source directory."""
        shutil.copytree(
            self.source_dir, self.checkpoint_dir, symlinks=True, dirs_exist_ok=True
        )
        self.saved = True

    def restore(self) -> None:
        """Restore source directory to checkpointed state."""
        if not self.saved:
            raise RuntimeError("Source directory not saved before restore.")

        # Ensure source directory exists
        self.source_dir.mkdir(parents=True, exist_ok=True)

        # First pass: restore files from backup
        for backup_path in self.checkpoint_dir.rglob("*"):
            if backup_path.is_file():
                rel_path = backup_path.relative_to(self.checkpoint_dir)
                target_path = self.source_dir / rel_path

                # Create parent directories if needed
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # Replace if different or missing
                if not target_path.exists() or not self._files_equal(
                    backup_path, target_path
                ):
                    shutil.copy2(backup_path, target_path)

        # Second pass: remove files that don't exist in backup
        if self.source_dir.exists():
            for target_path in self.source_dir.rglob("*"):
                if target_path.is_file():
                    rel_path = target_path.relative_to(self.source_dir)
                    backup_path = self.checkpoint_dir / rel_path

                    if not backup_path.exists():
                        target_path.unlink()

            # Remove empty directories
            for target_path in sorted(
                self.source_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True
            ):
                if target_path.is_dir() and not any(target_path.iterdir()):
                    target_path.rmdir()

    def _files_equal(self, path1: Path, path2: Path) -> bool:
        return filecmp.cmp(path1, path2, shallow=False)

    def cleanup(self) -> None:
        """Clean up checkpoint without restoring."""
        if self.checkpoint_dir.exists():
            shutil.rmtree(self.checkpoint_dir)

    def __enter__(self):
        self.save()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            print(
                f"Restoring source directory to checkpointed state: {self.checkpoint_dir}"
            )
            self.restore()
        self.cleanup()
