from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_text(path: Path, text: str, *, overwrite: bool = False) -> bool:
    """原子写入 UTF-8 文本。

    返回 False 表示目标已存在且 overwrite=False；写入失败时不会留下半截文件。
    """
    path = Path(path)
    if path.exists() and not overwrite:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

        # mkstemp 创建的是 0600，改成普通文件的常见权限。
        os.chmod(tmp_path, 0o644)

        # 预检查之后可能有人创建了同名文件，这里再确认一次。
        if path.exists() and not overwrite:
            tmp_path.unlink(missing_ok=True)
            return False

        os.replace(tmp_path, path)
        return True
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
