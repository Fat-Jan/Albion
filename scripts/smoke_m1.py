"""M1 数据层端到端 smoke test（对真实免鉴权 API）。

跑：.venv/bin/python -m scripts.smoke_m1
验证：search / events / 估值 / 金价 / 玩家档案 全链路返回合理值。
"""
import asyncio

from bot.albion import items, valuation
from bot.albion.client import AlbionClient
from bot.albion.gameinfo import GameInfo
from bot.albion.market import Market


async def main() -> None:
    async with AlbionClient() as client:
        gi = GameInfo(client)
        mk = Market(client)

        # 1) 搜索
        s = await gi.search("Albion")
        print(f"[search] players={len(s.get('players', []))} guilds={len(s.get('guilds', []))}")

        # 2) 金价
        gold = await mk.gold(count=3)
        print(f"[gold] 最近: {gold[-1] if gold else 'N/A'}")

        # 3) 最近击杀事件 → 找一个带完整装备的死者
        events = await gi.events(limit=20)
        print(f"[events] 拉到 {len(events)} 条")
        victim = None
        for ev in events:
            v = ev.get("Victim") or {}
            eq = v.get("Equipment") or {}
            if any(eq.get(s) for s in valuation.SLOTS):
                victim = v
                break
        if not victim:
            print("[valuation] 没找到带装备的死者，跳过")
            return

        eq = victim["Equipment"]
        sample = [eq[s]["Type"] for s in valuation.SLOTS if eq.get(s)][:4]
        print(f"[items] 死者: {victim.get('Name')} | 装备样例: "
              + ", ".join(f"{t}->{items.localized(t)}" for t in sample))

        # 4) 估值
        result = await valuation.estimate(victim, mk)
        nonzero = [b for b in result["items"] if b["value"] > 0]
        print(f"[valuation] 总估值 = {result['total']:,} 银 | 计价件数 {len(nonzero)}/{len(result['items'])}")
        for b in sorted(nonzero, key=lambda x: -x["value"])[:5]:
            print(f"    {items.localized(b['type'])} x{b['count']} = {b['value']:,}")

        # 5) 玩家档案（用死者 Id）
        pid = victim.get("Id")
        if pid:
            p = await gi.player(pid)
            kf = p.get("KillFame"); df = p.get("DeathFame")
            print(f"[player] {p.get('Name')} KillFame={kf} DeathFame={df} IP={p.get('AverageItemPower')}")

        print("\nM1 smoke test 通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())
