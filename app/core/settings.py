"""settings 表读写；GitHub Token 独立存放于项目根 .env（不入库）。"""
from contextlib import closing

from app.constants import ENV_FILE, SETTING_GITHUB_TOKEN
from app.core.db import get_connection


def _read_env() -> dict[str, str]:
    """手工解析 .env（key=value，支持 # 注释），无依赖。"""
    if not ENV_FILE.exists():
        return {}
    out: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, _, v = s.partition("=")
            out[k.strip()] = v.strip()
    return out


def _write_env(values: dict[str, str]) -> None:
    """更新 .env 中的键（保留原有注释和顺序，追加新键）。"""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.partition("=")[0].strip()
            if k in values:
                out.append(f"{k}={values[k]}")
                seen.add(k)
                continue
        out.append(line)
    for k, v in values.items():
        if k not in seen:
            out.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def get_github_token() -> str | None:
    """优先读 .env；发现 DB 里的旧 token 自动迁移到 .env 并作废旧值。"""
    env = _read_env()
    if env.get("GITHUB_TOKEN"):
        return env["GITHUB_TOKEN"]
    old = SettingsStore.get(SETTING_GITHUB_TOKEN)
    if old:
        _write_env({"GITHUB_TOKEN": old})
        SettingsStore.set(SETTING_GITHUB_TOKEN, "")
        return old
    return None


def set_github_token(token: str) -> None:
    """token 只写 .env，DB 旧值同时作废。"""
    _write_env({"GITHUB_TOKEN": token})
    SettingsStore.set(SETTING_GITHUB_TOKEN, "")


class SettingsStore:
    """键值设置存储，全部走短连接。"""

    @staticmethod
    def get(key: str, default: str | None = None) -> str | None:
        with closing(get_connection()) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    @staticmethod
    def set(key: str, value: str) -> None:
        with closing(get_connection()) as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()

    # ---------- 扫描根目录（多值，换行分隔存储，兼容旧的单路径值） ----------

    @staticmethod
    def get_scan_roots() -> list[str]:
        """返回扫描根目录列表（按添加顺序，自动去重保序）。"""
        val = SettingsStore.get(SETTING_SCAN_ROOT) or ""
        seen: dict[str, None] = {}
        for line in val.splitlines():
            p = line.strip()
            if p:
                seen.setdefault(p)
        return list(seen)

    @staticmethod
    def set_scan_roots(roots: list[str]) -> None:
        SettingsStore.set(SETTING_SCAN_ROOT, "\n".join(roots))
