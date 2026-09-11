import hashlib
import json
import os
import time
from pathlib import Path


class ExportCache:
    """Cache manager for ODB exports.

    Stores metadata about exported ODB files to avoid re-exporting
    when the source ODB hasn't changed.
    """

    def __init__(self, cache_dir=None):
        if cache_dir is None:
            base = Path(__file__).resolve().parent
            cache_dir = base / ".export_cache"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.cache_dir / "cache_index.json"
        self._index = self._load_index()

    def _load_index(self):
        if self._index_path.exists():
            try:
                with open(self._index_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_index(self):
        with open(self._index_path, "w") as f:
            json.dump(self._index, f, indent=2)

    def _file_hash(self, path):
        """Compute SHA256 of a file for cache validation."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def get(self, odb_path, step_index=-1, frame_step=1, deformation_scale=1.0, fields=None):
        """Return cached output path if valid, else None."""
        if fields is None:
            fields = ["S", "U", "PEEQ", "RF", "E", "SDV"]
        if not os.path.isfile(odb_path):
            return None

        odb_key = os.path.abspath(odb_path)
        odb_stat = os.stat(odb_path)
        odb_mtime = odb_stat.st_mtime
        odb_size = odb_stat.st_size

        entry = self._index.get(odb_key)
        if entry is None:
            return None

        # Check if ODB still matches
        if entry.get("mtime") != odb_mtime or entry.get("size") != odb_size:
            return None

        # Check export params match
        params = (step_index, frame_step, deformation_scale, fields)
        if entry.get("params") != list(params):
            return None

        output_dir = entry.get("output_dir")
        if output_dir and os.path.isdir(output_dir):
            model_path = os.path.join(output_dir, "model.json")
            if os.path.isfile(model_path):
                return model_path

        return None

    def put(self, odb_path, output_dir, step_index=-1, frame_step=1, deformation_scale=1.0, fields=None):
        """Store cache entry."""
        if fields is None:
            fields = ["S", "U", "PEEQ", "RF", "E", "SDV"]
        if not os.path.isfile(odb_path):
            return

        odb_key = os.path.abspath(odb_path)
        odb_stat = os.stat(odb_path)
        params = (step_index, frame_step, deformation_scale, fields)

        self._index[odb_key] = {
            "mtime": odb_stat.st_mtime,
            "size": odb_stat.st_size,
            "params": list(params),
            "output_dir": output_dir,
            "cached_at": time.time(),
        }
        self._save_index()

    def clean(self, max_age_days=30):
        """Remove cache entries older than max_age_days."""
        now = time.time()
        cutoff = now - max_age_days * 86400
        to_remove = []
        for key, entry in self._index.items():
            if entry.get("cached_at", 0) < cutoff:
                to_remove.append(key)
        for key in to_remove:
            out_dir = self._index[key].get("output_dir")
            if out_dir and os.path.isdir(out_dir):
                import shutil
                try:
                    shutil.rmtree(out_dir)
                except Exception:
                    pass
            del self._index[key]
        if to_remove:
            self._save_index()
        return len(to_remove)

    def list_cached(self):
        """List all cached models."""
        result = []
        for odb_key, entry in self._index.items():
            output_dir = entry.get("output_dir", "")
            model_path = os.path.join(output_dir, "model.json") if output_dir else ""
            if os.path.isfile(model_path):
                try:
                    with open(model_path, "r") as f:
                        meta = json.load(f)
                except Exception:
                    meta = {}
                result.append({
                    "name": meta.get("model_name", os.path.basename(odb_key)),
                    "path": output_dir,
                    "odb": odb_key,
                    "cached_at": entry.get("cached_at", 0),
                    "num_nodes": meta.get("num_nodes", 0),
                    "num_elements": meta.get("num_elements", 0),
                    "num_frames": len(meta.get("frames", [])),
                })
        return result
