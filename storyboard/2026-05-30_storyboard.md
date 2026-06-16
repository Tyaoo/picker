"""
每日安全资讯视频故事板生成器 - 生产级版本

Module: sec_news_storyboard
Author: AIGON Enterprise v3.0
Version: 3.0.0
Desc: 基于结构化场景数据生成可发布的 Markdown 故事板，内置全面校验、日志与安全措施。
      符合最大生产质量要求：完整错误处理、类型注解、文档、日志、输入验证、安全、性能、整洁代码。
"""

import json
import logging
import os
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import (
    Dict, List, Optional, Tuple, Union, Final, Any, cast,
    Generator, ContextManager, Iterable, Sequence
)
from collections.abc import Callable

# ---------------------------------------------------------------------------
# 日志配置（可通过环境变量调整级别与目标）
# ---------------------------------------------------------------------------
_log_configured: bool = False
_DEFAULT_LOG_LEVEL: Final[int] = logging.INFO
_DEFAULT_LOG_FORMAT: Final[str] = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOGGER_NAME: Final[str] = "StoryboardGenerator"

def configure_logging(
    level: Optional[int] = None,
    log_file: Optional[Union[str, Path]] = None
) -> None:
    """全局日志配置，可调用多次（后续调用仅调整级别与文件）。

    Args:
        level: 日志级别，默认从 ``AIGON_LOG_LEVEL`` 环境变量读取，否则使用 INFO。
        log_file: 日志文件路径。若未提供，则输出到标准错误（stderr）。

    Raises:
        ValueError: 如果提供的日志级别无效或环境变量值无效。
    """
    global _log_configured

    if level is None:
        env_level: Optional[str] = os.environ.get("AIGON_LOG_LEVEL")
        if env_level is not None:
            level_int: Optional[int] = getattr(logging, env_level.upper(), None)
            if level_int is None:
                raise ValueError(
                    f"无效的日志级别环境变量 AIGON_LOG_LEVEL={env_level!r}"
                )
            level = level_int
        else:
            level = _DEFAULT_LOG_LEVEL
    else:
        if not isinstance(level, int) or level not in (
            logging.DEBUG, logging.INFO, logging.WARNING,
            logging.ERROR, logging.CRITICAL
        ):
            raise ValueError(f"无效的日志级别值: {level!r}")

    logger = logging.getLogger(_LOGGER_NAME)
    # 清除已有 handler 防止重复
    logger.handlers.clear()
    logger.setLevel(level)

    handlers: List[logging.Handler] = []
    stderr_handler: logging.StreamHandler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(level)
    stderr_handler.setFormatter(logging.Formatter(_DEFAULT_LOG_FORMAT))
    handlers.append(stderr_handler)

    if log_file is not None:
        log_path: Path = validate_path_safety(log_file)
        try:
            file_handler: logging.FileHandler = logging.FileHandler(
                log_path, encoding="utf-8", delay=True
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(logging.Formatter(_DEFAULT_LOG_FORMAT))
            handlers.append(file_handler)
        except (OSError, PermissionError) as e:
            logger.error("无法创建日志文件 %s: %s", log_path, e)
            # 继续使用 stderr

    for handler in handlers:
        logger.addHandler(handler)

    logger.debug(
        "日志系统已配置: level=%s, file=%s",
        logging.getLevelName(level),
        log_file or "(仅stderr)",
    )
    _log_configured = True

# 自动配置（可通过显式调用覆盖）
try:
    configure_logging()
except ValueError as exc:
    print(f"日志初始化失败: {exc}", file=sys.stderr)
    sys.exit(1)

logger = logging.getLogger(_LOGGER_NAME)

# ---------------------------------------------------------------------------
# 版本与常量
# ---------------------------------------------------------------------------
VERSION: Final[str] = "3.0.0"
ALLOWED_TIMING_TOLERANCE: Final[float] = 0.1       # 时间校验容差（秒）
ALLOWED_DURATION_TOLERANCE: Final[float] = 0.2    # 总时长校验容差（秒）
MARKDOWN_SAFE_CHARS_RE: Final[re.Pattern] = re.compile(r"([|\\*_`~#<>\[\]()])")
MAX_SCENE_COUNT: Final[int] = 200                  # 防止意外过大的场景列表
_MIN_DURATION_SECONDS: Final[float] = 0.5          # 每个场景最少时长
_MAX_DURATION_SECONDS: Final[float] = 300.0        # 每个场景最长时间（5分钟）

__all__: List[str] = [
    "StoryboardError",
    "SceneValidationError",
    "DurationMismatchError",
    "ExportError",
    "Scene",
    "StoryboardGenerator",
    "configure_logging",
    "seconds_to_timestamp",
    "escape_markdown",
    "validate_path_safety",
]

# ---------------------------------------------------------------------------
# 自定义异常类
# ---------------------------------------------------------------------------
class StoryboardError(Exception):
    """故事板生成基础异常类。"""
    __slots__ = ()

class SceneValidationError(StoryboardError):
    """场景校验失败。"""
    __slots__ = ()

class DurationMismatchError(StoryboardError):
    """总时长与各场景之和不等。"""
    __slots__ = ()

class ExportError(StoryboardError):
    """导出过程中的 I/O 或安全错误。"""
    __slots__ = ()

class InputValidationError(StoryboardError):
    """输入数据（如JSON）格式校验失败。"""
    __slots__ = ()

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def seconds_to_timestamp(seconds: float) -> str:
    """将秒数转换为 ``mm:ss`` 格式。

    Args:
        seconds: 非负秒数。

    Returns:
        格式化后的时间戳字符串，格式为 ``"MM:SS"``。

    Raises:
        ValueError: 如果秒数为负。
    """
    if not isinstance(seconds, (int, float)):
        raise TypeError(f"seconds 必须为数字，收到: {type(seconds).__name__}")
    if seconds < 0:
        raise ValueError(f"时间不能为负: {seconds!r}")
    # 使用整数截断，避免微小浮点误差导致格式异常
    total_seconds: int = int(timedelta(seconds=seconds).total_seconds())
    minutes, sec = divmod(total_seconds, 60)
    return f"{minutes:02d}:{sec:02d}"

def escape_markdown(text: str) -> str:
    """对文本中的 Markdown 特殊字符进行转义，确保表格与常规文本安全。

    支持转义：`|`, `\\`, `*`, `_`, `` ` ``, `~`, `#`, `<`, `>`, `[`, `]`, `(`, `)`。

    Args:
        text: 原始文本。

    Returns:
        转义后文本。若 ``text`` 为 ``None``，则返回空字符串。
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        raise TypeError(f"text 必须为字符串或 None，收到: {type(text).__name__}")
    # 反斜杠需优先转义，避免二次转义
    text = text.replace("\\", "\\\\")
    # 管道符在表格中必须转义
    text = text.replace("|", "\\|")
    # 其他 Markdown 符号
    text = MARKDOWN_SAFE_CHARS_RE.sub(r"\\\1", text)
    return text

def validate_path_safety(path: Union[str, Path]) -> Path:
    """验证文件路径安全性，阻止路径遍历攻击。

    Args:
        path: 待验证的文件路径。

    Returns:
        规范化的绝对 Path 对象。

    Raises:
        ExportError: 如果路径包含 ``..`` 或 ``~`` 等不安全模式，或解析失败。
    """
    if not path:
        raise ExportError("路径不能为空")
    path_str: str = str(path)
    # 检查字符串形式是否包含危险模式
    if ".." in path_str or "~" in path_str:
        raise ExportError(f"路径包含不安全字符: {path_str!r}")
    try:
        p: Path = Path(path_str).resolve()
    except (RuntimeError, OSError) as e:
        raise ExportError(f"路径解析失败: {path_str!r}") from e
    # 可选：检查父目录是否可写（防止写入系统路径）
    # 此处不做强制检查，交由上层调用者处理
    logger.debug("路径安全校验通过: %s -> %s", path, p)
    return p

def _validate_positive_float(value: float, field_name: str, min_val: float = 0.0, max_val: Optional[float] = None) -> None:
    """通用浮点数校验辅助函数。

    Args:
        value: 待校验值。
        field_name: 字段名称（用于错误消息）。
        min_val: 最小值（如果为 None 则不限制）。
        max_val: 最大值（如果为 None 则不限制）。

    Raises:
        InputValidationError: 如果校验失败。
    """
    if not isinstance(value, (int, float)):
        raise InputValidationError(f"{field_name} 必须为数字，收到: {type(value).__name__}")
    if value < min_val:
        raise InputValidationError(f"{field_name} ({value}) 不能小于 {min_val}")
    if max_val is not None and value > max_val:
        raise InputValidationError(f"{field_name} ({value}) 不能大于 {max_val}")

# ---------------------------------------------------------------------------
# 场景数据结构
# ---------------------------------------------------------------------------
class Scene:
    """单个视频场景的完整定义。

    Attributes:
        id (int): 场景序号（从1开始）。
        title (str): 场景标题（用于内部标识）。
        start_time (float): 开始时间（秒）。
        end_time (float): 结束时间（秒）。
        visual (str): 视觉描述。
        audio (str): 音频描述（VO + 背景音乐）。
        notes (str): 备注说明（可为空字符串）。

    Properties:
        duration (float): 场景时长（秒），由 ``end_time - start_time`` 计算。

    Raises:
        SceneValidationError: 如果字段值不符合要求。
    """

    __slots__ = (
        "_id", "_title", "_start_time", "_end_time",
        "_visual", "_audio", "_notes",
    )

    def __init__(
        self,
        id: int,
        title: str,
        start_time: float,
        end_time: float,
        visual: str,
        audio: str,
        notes: Optional[str] = None,
    ) -> None:
        # 参数类型和范围校验
        if not isinstance(id, int) or id < 1:
            raise SceneValidationError(f"场景 id 必须为正整数，收到: {id!r}")
        if not title or not isinstance(title, str):
            raise SceneValidationError(f"场景标题不能为空且必须为字符串，收到: {title!r}")
        _validate_positive_float(start_time, "start_time", min_val=0.0)
        _validate_positive_float(end_time, "end_time", min_val=0.0)
        if end_time <= start_time:
            raise SceneValidationError(
                f"场景 {id} 结束时间 ({end_time}) 必须大于开始时间 ({start_time})"
            )
        duration = end_time - start_time
        if duration < _MIN_DURATION_SECONDS:
            raise SceneValidationError(
                f"场景 {id} 时长 ({duration:.2f}s) 小于最小允许值 {_MIN_DURATION_SECONDS}s"
            )
        if duration > _MAX_DURATION_SECONDS:
            raise SceneValidationError(
                f"场景 {id} 时长 ({duration:.2f}s) 超出最大允许值 {_MAX_DURATION_SECONDS}s"
            )
        if not visual or not isinstance(visual, str):
            raise SceneValidationError(f"场景 {id} 视觉描述不能为空")
        if not audio or not isinstance(audio, str):
            raise SceneValidationError(f"场景 {id} 音频描述不能为空")
        if notes is None:
            notes = ""
        elif not isinstance(notes, str):
            raise SceneValidationError(f"场景 {id} notes 必须为字符串，收到: {type(notes).__name__}")

        # 使用前导下划线存储，通过��性访问
        object.__setattr__(self, "_id", id)
        object.__setattr__(self, "_title", title)
        object.__setattr__(self, "_start_time", float(start_time))
        object.__setattr__(self, "_end_time", float(end_time))
        object.__setattr__(self, "_visual", visual)
        object.__setattr__(self, "_audio", audio)
        object.__setattr__(self, "_notes", notes)

        logger.debug("场景 %d 创建成功: %s (%s - %s)", id, title,
                     seconds_to_timestamp(start_time), seconds_to_timestamp(end_time))

    # ---- 属性访问 ----
    @property
    def id(self) -> int:
        return self._id

    @property
    def title(self) -> str:
        return self._title

    @property
    def start_time(self) -> float:
        return self._start_time

    @property
    def end_time(self) -> float:
        return self._end_time

    @property
    def visual(self) -> str:
        return self._visual

    @property
    def audio(self) -> str:
        return self._audio

    @property
    def notes(self) -> str:
        return self._notes

    @property
    def duration(self) -> float:
        """场景时长（秒）。"""
        return self._end_time - self._start_time

    # ---- 对象表示 ----
    def __repr__(self) -> str:
        return (
            f"Scene(id={self._id}, title={self._title!r}, "
            f"time=[{seconds_to_timestamp(self._start_time)}-{seconds_to_timestamp(self._end_time)}])"
        )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于JSON导出）。"""
        return {
            "id": self._id,
            "title": self._title,
            "start_time": round(self._start_time, 3),
            "end_time": round(self._end_time, 3),
            "visual": self._visual,
            "audio": self._audio,
            "notes": self._notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Scene":
        """从字典创建 Scene 实例，并执行完整校验。

        Args:
            data: 包含场景字段的字典。

        Returns:
            新建的 Scene 实例。

        Raises:
            InputValidationError: 如果字典缺少必需字段或字段类型错误。
        """
        required_fields = ["id", "title", "start_time", "end_time", "visual", "audio"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise InputValidationError(f"缺少必需字段: {missing}")

        try:
            scene = cls(
                id=int(data["id"]),
                title=str(data["title"]),
                start_time=float(data["start_time"]),
                end_time=float(data["end_time"]),
                visual=str(data["visual"]),
                audio=str(data["audio"]),
                notes=data.get("notes", None),
            )
        except (ValueError, TypeError, SceneValidationError) as e:
            raise InputValidationError(f"从字典创建 Scene 失败: {e}") from e
        return scene

# ---------------------------------------------------------------------------
# 故事板生成器
# ---------------------------------------------------------------------------
class StoryboardGenerator:
    """基于场景列表生成 Markdown 故事板的核心类。

    支持添加场景、校验、生成 Markdown 表格、导出到文件、从 JSON 加载等操作。

    Attributes:
        title (str): 故事板标题。
        total_duration (float): 期望总时长（秒）（默认为各场景时长之和）。
        scenes (List[Scene]): 已添加的场景列表（只读）。

    Raises:
        StoryboardError: 如果初始化参数无效。
    """

    def __init__(self, title: str = "视频故事板") -> None:
        if not title or not isinstance(title, str):
            raise StoryboardError(f"故事板标题不能为空且必须为字符串，收到: {title!r}")
        self._title: str = title
        self._scenes: List[Scene] = []
        self._total_duration: Optional[float] = None
        logger.info("StoryboardGenerator 初始化: title=%s", title)

    # ---- 属性 ----
    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        if not value or not isinstance(value, str):
            raise StoryboardError(f"标题不能为空且必须为字符串，收到: {value!r}")
        self._title = value
        logger.debug("标题已更新: %s", value)

    @property
    def scenes(self) -> List[Scene]:
        """返回场景列表的只读副本。"""
        return list(self._scenes)

    @property
    def total_duration(self) -> Optional[float]:
        return self._total_duration

    @total_duration.setter
    def total_duration(self, value: Optional[float]) -> None:
        if value is not None:
            _validate_positive_float(value, "total_duration", min_val=0.0)
        self._total_duration = value
        logger.debug("总时长已设置: %s", value if value is not None else "自动计算")

    # ---- 场景管理 ----
    def add_scene(self, scene: Scene) -> None:
        """添加一个已验证的场景。

        Args:
            scene: Scene 实例（应已通过构造函数校验）。

        Raises:
            SceneValidationError: 如果场景与现有场景时间重叠或不连续。
            ValueError: 如果场景数量超出限制。
        """
        if not isinstance(scene, Scene):
            raise TypeError(f"scene 必须为 Scene 实例，收到: {type(scene).__name__}")
        if len(self._scenes) >= MAX_SCENE_COUNT:
            raise ValueError(f"场景数量已达上限 {MAX_SCENE_COUNT}")

        # 检查时间连续性（允许紧接，但不允许重叠）
        if self._scenes:
            last_scene = self._scenes[-1]
            if scene.start_time < last_scene.end_time - ALLOWED_TIMING_TOLERANCE:
                raise SceneValidationError(
                    f"场景 {scene.id} 开始时间 ({scene.start_time:.3f}) "
                    f"与前场景 {last_scene.id} 结束时间 ({last_scene.end_time:.3f}) 重叠"
                )
            # 如果存在间隔，记录警告但不阻止
            if scene.start_time > last_scene.end_time + ALLOWED_TIMING_TOLERANCE:
                logger.warning("场景 %d 与场景 %d 之间存在 %0.3fs 间隔",
                               scene.id, last_scene.id,
                               scene.start_time - last_scene.end_time)

        self._scenes.append(scene)
        logger.info("已添加场景 %d: %s", scene.id, scene.title)

    def remove_scene(self, scene_id: int) -> None:
        """按 ID 移除场景。

        Args:
            scene_id: 要移除的场景 ID。

        Raises:
            ValueError: 如果未找到指定 ID 的场景。
        """
        for i, s in enumerate(self._scenes):
            if s.id == scene_id:
                removed = self._scenes.pop(i)
                logger.info("已移除场景 %d: %s", removed.id, removed.title)
                return
        raise ValueError(f"未找到 ID 为 {scene_id} 的场景")

    def clear_scenes(self) -> None:
        """清空所有场景。"""
        self._scenes.clear()
        logger.info("已清空所有场景")

    # ---- 校验 ----
    def validate(self) -> bool:
        """校验当前故事板的一致性。

        检查所有场景时间是否正确，总时长是否匹配（如果设置了总时长）。

        Returns:
            如果通过校验返回 True。

        Raises:
            SceneValidationError: 如果场景顺序或时间异常。
            DurationMismatchError: 如果总时长与场景时长之和差异超出容差。
        """
        logger.debug("开始校验故事板: %s", self._title)

        if not self._scenes:
            raise SceneValidationError("故事板中没有场景")

        # 检查场景 ID 是否从 1 开始连续
        for idx, scene in enumerate(self._scenes):
            expected_id = idx + 1
            if scene.id != expected_id:
                raise SceneValidationError(
                    f"场景 ID 不连续: 位置 {idx+1} 期望 ID {expected_id}，收到 {scene.id}"
                )

        # 检查时间连续性
        for i in range(1, len(self._scenes)):
            prev = self._scenes[i-1]
            curr = self._scenes[i]
            if curr.start_time < prev.end_time - ALLOWED_TIMING_TOLERANCE:
                raise SceneValidationError(
                    f"场景 {curr.id} 开始时间 ({curr.start_time:.3f}) 与场景 {prev.id} "
                    f"结束时间 ({prev.end_time:.3f}) 重叠"
                )

        # 校验总时长
        if self._total_duration is not None:
            computed_total = sum(s.duration for s in self._scenes)
            diff = abs(computed_total - self._total_duration)
            if diff > ALLOWED_DURATION_TOLERANCE:
                raise DurationMismatchError(
                    f"总时长不匹配: 期望 {self._total_duration:.3f}s, "
                    f"实际场景总和 {computed_total:.3f}s, 差异 {diff:.3f}s"
                )
            logger.debug("总时长校验通过: %0.3f s", computed_total)

        logger.info("故事板校验通过: %d 个场景", len(self._scenes))
        return True

    # ---- Markdown 生成 ----
    def generate_markdown(self, validate: bool = True) -> str:
        """生成完整的 Markdown 故事板。

        包括标题、元信息（总时长、场景数）、生成日期、场景表格。

        Args:
            validate: 是否在生成前执行校验（默认 True）。

        Returns:
            Markdown 格式的字符串。

        Raises:
            StoryboardError: 如果生成过程中出现错误。
        """
        if validate:
            self.validate()

        lines: List[str] = []
        lines.append(f"# {self._title}")
        lines.append("")
        lines.append("## 故事板")
        lines.append("")

        # 元信息
        total_seconds = sum(s.duration for s in self._scenes)
        if self._total_duration is not None:
            total_str = seconds_to_timestamp(self._total_duration)
        else:
            total_str = seconds_to_timestamp(total_seconds)
        lines.append(f"- **总时长**: {total_str} ({total_seconds:.2f}s)")
        lines.append(f"- **场景数量**: {len(self._scenes)}")
        lines.append(f"- **生成日期**: {self._get_current_date()}")
        lines.append("")

        # 表格头部
        lines.append("| 编号 | 时间范围 | 时长 | 视觉描述 | 音频描述 | 备注 |")
        lines.append("|------|----------|------|----------|----------|------|")

        for scene in self._scenes:
            start_ts = seconds_to_timestamp(scene.start_time)
            end_ts = seconds_to_timestamp(scene.end_time)
            dur_str = f"{scene.duration:.1f}s"

            # 转义内容
            visual_esc = escape_markdown(scene.visual)
            audio_esc = escape_markdown(scene.audio)
            notes_esc = escape_markdown(scene.notes)

            lines.append(
                f"| {scene.id} | {start_ts}-{end_ts} | {dur_str} "
                f"| {visual_esc} | {audio_esc} | {notes_esc} |"
            )

        lines.append("")
        lines.append("---")
        lines.append(f"*由 AIGON Enterprise v3.0 StoryboardGenerator v{VERSION} 生成*")

        result = "\n".join(lines)
        logger.debug("Markdown 生成完成，共 %d 字符", len(result))
        return result

    @staticmethod
    def _get_current_date() -> str:
        """获取当前日期字符串 (YYYY-MM-DD)。

        Returns:
            格式化日期字符串。
        """
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d")

    # ---- 导出 ----
    def export_to_file(self, filepath: Union[str, Path]) -> None:
        """将故事板导出到 Markdown 文件。

        Args:
            filepath: 输出文件路径。

        Raises:
            ExportError: 如果路径不安全或写入失败。
            StoryboardError: 如果校验或生成失败。
        """
        safe_path = validate_path_safety(filepath)
        try:
            markdown_content = self.generate_markdown(validate=True)
        except (SceneValidationError, DurationMismatchError) as e:
            raise ExportError(f"故事板校验失败，无法导出: {e}") from e

        try:
            # 确保父目录存在
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            # 原子写入（先写临时文件，再重命名）
            temp_path = safe_path.with_suffix(".tmp.md")
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            temp_path.replace(safe_path)
            logger.info("故事板已导出到: %s", safe_path)
        except OSError as e:
            raise ExportError(f"写入文件失败 {safe_path}: {e}") from e

    # ---- JSON 导入 ----
    @classmethod
    def from_json(cls, json_path: Union[str, Path], title: Optional[str] = None) -> "StoryboardGenerator":
        """从 JSON 文件加载场景并创建 StoryboardGenerator。

        JSON 格式应为包含 "scenes" 键的字典，或直接为场景数组。
        每个场景字典需包含所有必需字段。

        Args:
            json_path: JSON 文件路径。
            title: 故事板标题（如果为 None，则从 JSON 中 "title" 字段读取或使用默认）。

        Returns:
            新创建的 ``StoryboardGenerator`` 实例。

        Raises:
            ExportError: 如果文件读取失败或 JSON 格式无效。
            InputValidationError: 如果场景数据格式不符合要求。
        """
        safe_path = validate_path_safety(json_path)
        try:
            with open(safe_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise ExportError(f"读取 JSON 文件失败 {safe_path}: {e}") from e

        # 支持两种 JSON 格式
        if isinstance(data, dict):
            scenes_data = data.get("scenes", [])
            if title is None:
                title = data.get("title", "从 JSON 导入的故事板")
        elif isinstance(data, list):
            scenes_data = data
            if title is None:
                title = "从 JSON 导入的故事板"
        else:
            raise InputValidationError(f"JSON 根元素必须为对象或数组，收到: {type(data).__name__}")

        generator = cls(title=str(title))

        for index, scene_dict in enumerate(scenes_data):
            if not isinstance(scene_dict, dict):
                raise InputValidationError(f"场景 {index} 不是字典，收到: {type(scene_dict).__name__}")
            try:
                scene = Scene.from_dict(scene_dict)
            except InputValidationError as e:
                raise InputValidationError(f"场景 {index} 格式错误: {e}") from e
            generator.add_scene(scene)

        logger.info("已从 JSON 文件加载 %d 个场景: %s", len(generator._scenes), safe_path)
        return generator


# ---------------------------------------------------------------------------
# 示例（仅在直接运行时执行）
# ---------------------------------------------------------------------------
def main() -> None:
    """演示 StoryboardGenerator 的基本用法。"""
    # 创建生成器
    generator = StoryboardGenerator("每日安全资讯视频 - 2026-05-30")

    # 添加示例场景
    scenes_data = [
        {"id": 1, "title": "开场", "start_time": 0.0, "end_time": 10.0,
         "visual": "标题动画：每日安全资讯", "audio": "开场音乐 + VO: 欢迎收看每日安全资讯",
         "notes": "背景为蓝色科技感"},
        {"id": 2, "title": "Paper 摘要", "start_time": 10.0, "end_time": 25.0,
         "visual": "论文截图 + 404实验室 Logo",
         "audio": "VO: 今天Paper栏目带来BLAST攻击研究",
         "notes": ""},
        {"id": 3, "title": "SecWiki", "start_time": 25.0, "end_time": 35.0,
         "visual": "SecWiki 页面截图",
         "audio": "VO: 查看昨日安全新闻汇总",
         "notes": "链接在描述中"},
    ]

    for sd in scenes_data:
        try:
            scene = Scene.from_dict(sd)
            generator.add_scene(scene)
        except (SceneValidationError, InputValidationError) as e:
            logger.error("添加场景失败: %s", e)
            return

    # 生成 Markdown 并输出
    try:
        md = generator.generate_markdown()
        print(md)
    except StoryboardError as e:
        logger.error("生成故事板失败: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    configure_logging(level=logging.DEBUG)
    main()