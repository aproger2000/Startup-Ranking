"""
Единая формула скоринга — пересчитывается сервером при каждом создании/
обновлении записи, поэтому рейтинг всегда согласован, даже когда база
пополняется вручную через админку или автоматически через задачу-сборщик.

Скор = Выручка (0-38, лог-шкала) + Рост выручки (от -24 до +24, знак
сохраняется) + Финансирование (0-20, лог-шкала) + Признание (IPO/pre-IPO +10,
официальный отраслевой рейтинг +5, крупный инвестор +3) - 6, если ни выручка,
ни рост, ни финансирование не раскрыты.
"""
import math


def compute_score(rev, growth, funding_rub, is_ipo, is_official_rank, is_major_investor):
    s = 0.0
    if rev:
        s += min(38, max(0, (math.log10(max(rev, 0.01)) + 1) * 5.2))
    if growth is not None:
        sign = 1 if growth >= 0 else -1
        s += sign * min(24, math.log1p(abs(growth)) * 4.4)
    if funding_rub:
        s += min(20, max(0, (math.log10(max(funding_rub, 0.01)) + 1) * 3.3))
    if is_ipo:
        s += 10
    if is_official_rank:
        s += 5
    if is_major_investor:
        s += 3
    if not rev and growth is None and not funding_rub:
        s -= 6
    return round(s, 2)
