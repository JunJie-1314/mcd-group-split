#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦门拼单官 · 公平分账算法

给定每个拼单成员的选品原价，以及订单的实际应付总额，算出每人该付多少，
并保证「各人应付之和」精确等于「订单实付总额」——一分钱都不差。

金额单位约定
------------
本模块内部一律使用「分」(int)，彻底规避浮点误差。
命令行对外使用「元」，读入时用 Decimal 精确换算，不会出现 0.1 + 0.2 的问题。

为什么不把这一步交给大模型口算
------------------------------
分账结果直接决定同事之间谁转谁多少钱。大模型做多步金额加减、带零头的
按比例整除时极易出错，且错误往往很隐蔽（差几分钱）。因此这里的分摊逻辑
全是确定性整数运算，并配有单元测试；大模型只负责调用它、讲解它。

用法
----
    python scripts/split_bill.py --total 29.70 \\
        --member 小美:14.00 --member 阿强:16.00 --member 老王:19.00

    python scripts/split_bill.py --total 29.70 --delivery 3.00 \\
        --goods-strategy proportional --delivery-strategy even \\
        --member 小美:14.00 --member 阿强:16.00
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Sequence

__all__ = ["Member", "allocate", "split_bill", "format_report", "yuan_to_cents", "cents_to_yuan"]

GOODS_STRATEGIES = ("proportional", "even_discount")
DELIVERY_STRATEGIES = ("even", "initiator", "proportional")


@dataclass(frozen=True)
class Member:
    """一个拼单成员。

    name      : 成员称呼
    subtotal  : 该成员所选商品的原价合计，单位「分」
    """

    name: str
    subtotal: int

    def __post_init__(self) -> None:
        if self.subtotal < 0:
            raise ValueError(f"成员 {self.name!r} 的金额不能为负数")


def yuan_to_cents(text: str | int | float) -> int:
    """把「元」精确转成「分」。支持 '14'、'14.5'、'14.50'、14.5 等写法。"""
    try:
        value = Decimal(str(text))
    except InvalidOperation as exc:  # pragma: no cover - 防御性
        raise ValueError(f"无法解析金额: {text!r}") from exc
    cents = value.scaleb(2)
    if cents != cents.to_integral_value():
        raise ValueError(f"金额 {text!r} 的最小单位超过「分」，无法精确表示")
    return int(cents)


def cents_to_yuan(cents: int) -> str:
    """把「分」格式化成两位小数的「元」字符串。"""
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def allocate(weights: Sequence[int], amount: int) -> list[int]:
    """按权重把 amount 精确拆成 len(weights) 份，加总恰好等于 amount。

    采用「最大余数法」(Hamilton / largest remainder)：

    1. 先按权重占比向下取整，得到每份的基础值；
    2. 因为有向下取整，会产生一个零头（余数总额）；
    3. 把零头按「各自除不尽的余数」从大到小，每份补 1 分，直到分完。

    这样既贴近比例，又保证加总严格等于 amount，不会出现 1 分钱漂移。
    余数相同时按原始顺序补，保证同输入永远得到同输出（可复现）。

    weights 全为 0（例如所有人都没点东西）时，退化为按人头均分。
    """
    if amount < 0:
        raise ValueError("amount 不能为负数")
    n = len(weights)
    if n == 0:
        raise ValueError("至少需要一个份额")

    safe_weights = [w if w > 0 else 0 for w in weights]
    total_w = sum(safe_weights)
    if total_w <= 0:
        safe_weights = [1] * n
        total_w = n

    base = [amount * w // total_w for w in safe_weights]
    remainder = [amount * w % total_w for w in safe_weights]
    missing = amount - sum(base)

    order = sorted(range(n), key=lambda i: (-remainder[i], i))
    for k in range(missing):
        base[order[k]] += 1

    return base


def split_bill(
    members: Sequence[Member],
    total_paid: int,
    delivery_fee: int = 0,
    goods_strategy: str = "proportional",
    delivery_strategy: str = "even",
) -> list[tuple[str, int]]:
    """把订单实付总额拆到每个人头上。

    参数（金额单位均为「分」）
    -------------------------
    members            各成员及其选品原价合计，顺序即账单展示顺序
    total_paid         订单实际应付总额（含配送费），取自 calculate-price 的实付字段
    delivery_fee       total_paid 中所包含的配送费
    goods_strategy     商品部分的优惠分摊方式：
                       - "proportional"  按各人原价占比分摊（默认；点得多、省得多）
                       - "even_discount" 优惠按人头均摊（吃多吃少，省一样多）
    delivery_strategy  配送费分摊方式：
                       - "even"          按人头均摊（默认）
                       - "initiator"     由发起人（第 1 位成员）承担
                       - "proportional"  按各人原价占比分摊

    返回
    ----
    [(姓名, 应付分), ...]，顺序与 members 一致，加总恒等于 total_paid。
    """
    if not members:
        raise ValueError("至少需要一个成员")
    if total_paid < 0:
        raise ValueError("total_paid 不能为负数")
    if not 0 <= delivery_fee <= total_paid:
        raise ValueError("delivery_fee 必须落在 [0, total_paid] 区间内")
    if goods_strategy not in GOODS_STRATEGIES:
        raise ValueError(f"未知的 goods_strategy: {goods_strategy!r}，可选 {GOODS_STRATEGIES}")
    if delivery_strategy not in DELIVERY_STRATEGIES:
        raise ValueError(
            f"未知的 delivery_strategy: {delivery_strategy!r}，可选 {DELIVERY_STRATEGIES}"
        )

    n = len(members)
    subtotals = [m.subtotal for m in members]
    goods_original = sum(subtotals)
    goods_paid = total_paid - delivery_fee
    weights = subtotals if goods_original > 0 else [1] * n

    if goods_strategy == "proportional":
        goods_due = allocate(weights, goods_paid)
    else:  # even_discount
        discount = max(goods_original - goods_paid, 0)
        cut = allocate([1] * n, discount)
        # 封顶：优惠不该让某个人倒找钱
        goods_due = [max(subtotals[i] - cut[i], 0) for i in range(n)]
        drift = goods_paid - sum(goods_due)
        if drift > 0:
            fix = allocate(weights, drift)
            goods_due = [goods_due[i] + fix[i] for i in range(n)]
        elif drift < 0:
            # 极罕见：优惠大于某人的全部原价，回退比例法保证守恒
            goods_due = allocate(weights, goods_paid)

    if delivery_strategy == "even":
        fee_due = allocate([1] * n, delivery_fee)
    elif delivery_strategy == "initiator":
        fee_due = [delivery_fee] + [0] * (n - 1)
    else:  # proportional
        fee_due = allocate(weights, delivery_fee)

    result = [(members[i].name, goods_due[i] + fee_due[i]) for i in range(n)]

    if sum(amount for _, amount in result) != total_paid:
        raise AssertionError("分账加总与订单实付不符，算法异常")  # 不该发生
    return result


def _display_width(text: str) -> int:
    """按终端显示宽度计算字符串长度（中日韩宽字符按 2 计）。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int, align: str = "left") -> str:
    gap = max(width - _display_width(text), 0)
    if align == "right":
        return " " * gap + text
    return text + " " * gap


def format_report(
    members: Sequence[Member],
    total_paid: int,
    delivery_fee: int = 0,
    goods_strategy: str = "proportional",
    delivery_strategy: str = "even",
) -> str:
    """生成适合直接贴进群里的分账账单（纯文本表格）。"""
    dues = split_bill(members, total_paid, delivery_fee, goods_strategy, delivery_strategy)
    goods_original = sum(m.subtotal for m in members)
    goods_paid = total_paid - delivery_fee

    strat_label = {
        "proportional": "商品优惠按原价比例分摊",
        "even_discount": "商品优惠按人头均摊",
    }[goods_strategy]
    fee_label = {
        "even": "配送费按人头均摊",
        "initiator": "配送费由发起人承担",
        "proportional": "配送费按原价比例分摊",
    }[delivery_strategy]

    lines: list[str] = []
    lines.append("🍟 麦门拼单官 · 分账账单")
    lines.append(
        f"订单实付 ¥{cents_to_yuan(total_paid)}"
        f"（商品 ¥{cents_to_yuan(goods_paid)} + 配送费 ¥{cents_to_yuan(delivery_fee)}）"
    )
    lines.append(f"分摊方式：{strat_label} · {fee_label}")
    lines.append("")

    header = (
        _pad("成员", 12)
        + _pad("原价", 10, "right")
        + _pad("占比", 8, "right")
        + _pad("应付", 10, "right")
        + _pad("共省", 9, "right")
    )
    lines.append(header)
    lines.append("-" * _display_width(header))

    for (name, due), m in zip(dues, members):
        ratio = (m.subtotal / goods_original * 100) if goods_original else 0.0
        saved = m.subtotal - due if m.subtotal else -due
        lines.append(
            _pad(name, 12)
            + _pad(f"¥{cents_to_yuan(m.subtotal)}", 10, "right")
            + _pad(f"{ratio:.1f}%", 8, "right")
            + _pad(f"¥{cents_to_yuan(due)}", 10, "right")
            + _pad(f"¥{cents_to_yuan(saved)}", 9, "right")
        )

    total_saved = goods_original - total_paid
    lines.append("-" * _display_width(header))
    lines.append(
        _pad("合计", 12)
        + _pad(f"¥{cents_to_yuan(goods_original)}", 10, "right")
        + _pad("100.0%", 8, "right")
        + _pad(f"¥{cents_to_yuan(total_paid)}", 10, "right")
        + _pad(f"¥{cents_to_yuan(total_saved)}", 9, "right")
    )
    lines.append("")
    lines.append(
        f"核对：各人应付加总 = ¥{cents_to_yuan(sum(a for _, a in dues))}"
        f"，与订单实付一致 ✓"
    )
    return "\n".join(lines)


def _parse_member(raw: str) -> Member:
    if ":" not in raw and "：" not in raw:
        raise argparse.ArgumentTypeError(f"成员格式应为 姓名:金额，收到 {raw!r}")
    name, _, amount = raw.replace("：", ":").partition(":")
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError("成员姓名不能为空")
    return Member(name=name, subtotal=yuan_to_cents(amount.strip()))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="split_bill",
        description="麦门拼单官 · 公平分账：把订单实付精确拆到每个人头上",
    )
    parser.add_argument("--member", "-m", action="append", required=True, type=_parse_member,
                        metavar="姓名:原价", help="可重复，顺序即账单顺序")
    parser.add_argument("--total", "-t", required=True, type=yuan_to_cents,
                        metavar="实付元", help="订单实际应付总额（券后），来自 calculate-price")
    parser.add_argument("--delivery", "-d", default=0, type=yuan_to_cents,
                        metavar="配送费元", help="total 中所含的配送费，默认 0")
    parser.add_argument("--goods-strategy", choices=GOODS_STRATEGIES, default="proportional",
                        help="商品优惠分摊方式，默认 proportional")
    parser.add_argument("--delivery-strategy", choices=DELIVERY_STRATEGIES, default="even",
                        help="配送费分摊方式，默认 even")
    args = parser.parse_args(argv)

    try:
        report = format_report(
            members=args.member,
            total_paid=args.total,
            delivery_fee=args.delivery,
            goods_strategy=args.goods_strategy,
            delivery_strategy=args.delivery_strategy,
        )
    except ValueError as exc:
        print(f"参数有误：{exc}", file=sys.stderr)
        return 2

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
