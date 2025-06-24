#!/usr/bin/env python3

import filecmp
import shutil
import subprocess
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

    def _is_ignored(self, path: Path) -> bool:
        result = subprocess.run(
            ["git", "check-ignore", str(path)],
            cwd=self.source_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0

    def save(self) -> None:
        """Save current state of source directory."""
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        def walk_unignored(path: Path):
            if self._is_ignored(path):
                return
            if path.is_file():
                rel_path = path.relative_to(self.source_dir)
                target_path = self.checkpoint_dir / rel_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target_path)
            elif path.is_dir():
                for child in path.iterdir():
                    walk_unignored(child)

        walk_unignored(self.source_dir)
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
                if not target_path.exists() or not self._files_equal(backup_path, target_path):
                    shutil.copy2(backup_path, target_path)

        # Second pass: remove files that don't exist in backup
        if self.source_dir.exists():

            def remove_extra_files(path: Path):
                if self._is_ignored(path):
                    return
                if path.is_file():
                    rel_path = path.relative_to(self.source_dir)
                    backup_path = self.checkpoint_dir / rel_path
                    if not backup_path.exists():
                        path.unlink()
                elif path.is_dir():
                    for child in path.iterdir():
                        remove_extra_files(child)

            remove_extra_files(self.source_dir)

    def _files_equal(self, path1: Path, path2: Path) -> bool:
        return filecmp.cmp(path1, path2, shallow=False)

    def cleanup(self) -> None:
        """Clean up checkpoint without restoring."""
        if self.checkpoint_dir.exists():
            shutil.rmtree(self.checkpoint_dir)

    def __enter__(self):
        self.save()
        return self

    def __exit__(self, exc_type, _exc_val, _exc_tb):
        if exc_type is not None:
            print(f"Restoring source directory to checkpointed state: {self.checkpoint_dir}")
            self.restore()
        self.cleanup()
