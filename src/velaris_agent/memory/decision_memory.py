"""决策记忆存储与检索。

每次决策的完整上下文都被记录, 支持:
- 按用户+场景检索历史决策
- 按意图相似度查找参考决策
- 按选项类型聚合历史满意度
- 反馈回填 (用户选择 + 满意度)
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from velaris_agent.memory.types import DecisionRecord


_QUERY_TOKEN_SPLIT_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionMemory:
    """决策记忆 - 存储、检索、反馈闭环。

    存储结构:
      base_dir/
        index.jsonl          # 索引 (每行一条摘要, 快速扫描)
        records/
          dec-xxxx.json      # 完整决策记录
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        """初始化决策记忆。

        Args:
            base_dir: 存储目录, 默认 ~/.velaris/decisions/
        """
        if base_dir is None:
            base_dir = Path.home() / ".velaris" / "decisions"
        self._base_dir = Path(base_dir)
        self._records_dir = self._base_dir / "records"
        self._index_path = self._base_dir / "index.jsonl"
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._records_dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: DecisionRecord) -> str:
        """保存决策记录, 返回 decision_id。"""
        # 写完整记录
        record_path = self._records_dir / f"{record.decision_id}.json"
        record_path.write_text(
            record.model_dump_json(indent=2), encoding="utf-8"
        )

        # 追加索引 (轻量摘要, 用于快速扫描)
        index_entry = {
            "decision_id": record.decision_id,
            "user_id": record.user_id,
            "scenario": record.scenario,
            "query": record.query[:200],
            "recommended_id": record.recommended.get("id", ""),
            "user_choice_id": record.user_choice.get("id", "") if record.user_choice else None,
            "user_feedback": record.user_feedback,
            "created_at": record.created_at.isoformat(),
        }
        with self._index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(index_entry, ensure_ascii=False) + "\n")

        return record.decision_id

    def get(self, decision_id: str) -> DecisionRecord | None:
        """按 ID 获取完整决策记录。"""
        record_path = self._records_dir / f"{decision_id}.json"
        if not record_path.exists():
            return None
        data = json.loads(record_path.read_text(encoding="utf-8"))
        return DecisionRecord.model_validate(data)

    def update_feedback(
        self,
        decision_id: str,
        user_choice: dict[str, Any] | None = None,
        user_feedback: float | None = None,
        outcome_notes: str | None = None,
    ) -> DecisionRecord | None:
        """回填用户选择和满意度反馈。"""
        record = self.get(decision_id)
        if record is None:
            return None

        updates: dict[str, Any] = {}
        if user_choice is not None:
            updates["user_choice"] = user_choice
        if user_feedback is not None:
            updates["user_feedback"] = user_feedback
        if outcome_notes is not None:
            updates["outcome_notes"] = outcome_notes

        updated = record.model_copy(update=updates)
        record_path = self._records_dir / f"{decision_id}.json"
        record_path.write_text(
            updated.model_dump_json(indent=2), encoding="utf-8"
        )
        return updated

    def list_by_user(
        self,
        user_id: str,
        scenario: str | None = None,
        limit: int = 50,
    ) -> list[DecisionRecord]:
        """按用户检索历史决策 (最近优先)。"""
        results: list[DecisionRecord] = []
        for entry in self._scan_index_reversed():
            if entry.get("user_id") != user_id:
                continue
            if scenario and entry.get("scenario") != scenario:
                continue
            record = self.get(entry["decision_id"])
            if record:
                results.append(record)
            if len(results) >= limit:
                break
        return results

    def count_by_user(
        self,
        user_id: str,
        scenario: str | None = None,
    ) -> int:
        """统计用户在指定场景下的历史决策数量。"""
        count = 0
        for entry in self._scan_index_reversed():
            if entry.get("user_id") != user_id:
                continue
            if scenario and entry.get("scenario") != scenario:
                continue
            count += 1
        return count

    def recall_similar(
        self,
        user_id: str,
        scenario: str,
        query: str,
        limit: int = 5,
    ) -> list[DecisionRecord]:
        """找到相似的历史决策。

        当前实现: 轻量关键词匹配。
        相比简单的 `split()`，这里会先清洗中英文标点，
        让中文问题在没有空格分词时也能得到基本可用的召回效果。
        未来可升级为 embedding 语义搜索。
        """
        query_words = self._tokenize_query(query)
        candidates: list[tuple[int, DecisionRecord]] = []

        for entry in self._scan_index_reversed():
            if entry.get("user_id") != user_id:
                continue
            if entry.get("scenario") != scenario:
                continue
            # 简单关键词匹配评分
            entry_words = self._tokenize_query(str(entry.get("query", "")))
            overlap = len(query_words & entry_words)
            if overlap > 0:
                record = self.get(entry["decision_id"])
                if record:
                    candidates.append((overlap, record))

        # 按匹配度排序
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in candidates[:limit]]

    def _tokenize_query(self, query: str) -> set[str]:
        """把查询文本切成可比较的关键词集合。

        这里不追求复杂分词，只做两件事：
        1. 清洗掉中英文标点和噪音符号；
        2. 保留英文单词与中文短语块。

        这样做的原因是当前仓库以中文使用场景为主，
        仅用空格分词会导致大量中文查询无法召回。
        """
        normalized = _QUERY_TOKEN_SPLIT_RE.sub(" ", query.lower())
        return {token for token in normalized.split() if token}

    def aggregate_outcomes(
        self,
        scenario: str,
        option_field: str = "id",
        option_value: str = "",
    ) -> dict[str, Any]:
        """聚合某类选项的历史满意度。

        用于回答: "这个酒店/航班/模型, 用过的人满意度如何?"
        """
        feedbacks: list[float] = []
        choice_count = 0
        total_seen = 0

        for entry in self._scan_index_reversed():
            if entry.get("scenario") != scenario:
                continue
            record = self.get(entry["decision_id"])
            if record is None:
                continue
            # 检查是否包含该选项
            for opt in record.options_discovered:
                if opt.get(option_field) == option_value:
                    total_seen += 1
                    if (
                        record.user_choice
                        and record.user_choice.get(option_field) == option_value
                    ):
                        choice_count += 1
                        if record.user_feedback is not None:
                            feedbacks.append(record.user_feedback)
                    break

        return {
            "option_value": option_value,
            "times_seen": total_seen,
            "times_chosen": choice_count,
            "choice_rate": choice_count / total_seen if total_seen > 0 else 0,
            "avg_satisfaction": sum(feedbacks) / len(feedbacks) if feedbacks else None,
            "sample_size": len(feedbacks),
        }

    def _scan_index_reversed(self) -> list[dict[str, Any]]:
        """逆序扫描索引 (最近优先)。"""
        if not self._index_path.exists():
            return []
        lines = self._index_path.read_text(encoding="utf-8").strip().split("\n")
        entries: list[dict[str, Any]] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    @staticmethod
    def generate_id() -> str:
        """生成决策 ID。"""
        return f"dec-{uuid.uuid4().hex[:12]}"
