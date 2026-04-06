"""人生目标决策智能 Demo 脚本入口。

这个脚本保留为仓库级快捷入口，
但真实逻辑已经收敛到 `velaris_agent.scenarios.lifegoal.demo`，
避免脚本和 CLI 各自维护一份实现。
"""

from __future__ import annotations

import argparse

from velaris_agent.scenarios.lifegoal.demo import (
    render_lifegoal_demo_output,
    run_lifegoal_demo_sync,
    save_lifegoal_demo_output,
    serialize_lifegoal_demo_output,
)


def _build_parser() -> argparse.ArgumentParser:
    """构造脚本参数解析器。

    脚本参数与 CLI 子命令保持一致，避免两套入口的使用方式割裂。
    """
    parser = argparse.ArgumentParser(description="运行 Velaris 人生目标决策 demo")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出 demo 结果")
    parser.add_argument("--save-to", type=str, default=None, help="把 demo 结果保存到指定文件")
    return parser


def main() -> None:
    """运行人生目标决策 demo 并输出结果。"""
    args = _build_parser().parse_args()
    payload = run_lifegoal_demo_sync()
    if args.save_to:
        saved = save_lifegoal_demo_output(payload, args.save_to)
        print(f"Demo 结果已保存到: {saved}")
    if args.json:
        print(serialize_lifegoal_demo_output(payload))
        return
    print(render_lifegoal_demo_output(payload))


if __name__ == "__main__":
    main()
