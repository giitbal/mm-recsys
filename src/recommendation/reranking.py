"""Cold start, new items, bandit slots, then quota-preserving diversity repair."""
from __future__ import annotations

from typing import Any, Callable

from dataclasses import dataclass, replace
from collections import Counter
import math
import numpy as np
import pandas as pd

from src.recommendation.mab import create_strategy


@dataclass(frozen=True)
class RankedItem:
    product_id: str
    score: float
    reason: str = 'DeepFM 클릭·구매 가능성'
    is_exploration: bool = False


def diversity_capacity(counts: dict[str, int],limit: int,tail: str | None=None,run: int=0) -> int:
    total=sum(counts.values())
    return min([total]+[(limit+1)*(total-number)+limit-(run if category==tail else 0)
                        for category,number in counts.items() if number>0])


def completion_feasible(counts: dict[str, int],required: dict[str, int],slots: int,
                        limit: int,tail: str | None,run: int) -> bool:
    if slots<sum(required.values()) or diversity_capacity(counts,limit,tail,run)<slots:
        return False
    if any(number>counts.get(category,0) for category,number in required.items()): return False
    total_required=sum(required.values())
    separators=max([0]+[math.ceil(max(0,number-(limit-(run if category==tail else 0))
                                            -limit*(total_required-number))/limit)
                         for category,number in required.items() if number>0])
    return total_required+separators<=slots


class Reranker:
    def __init__(self,cfg: dict,products: pd.DataFrame):
        self.cfg=cfg; self.spec=cfg['recommend']; field=self.spec['reranking']['category_field']
        if field not in ('category_l2','category_l3'): raise ValueError('unsupported diversity category')
        catalog = products.set_index('product_id')
        self.categories = catalog[field].astype(str).to_dict()
        self.created = catalog.created_at.to_dict()
        # A repeated child label implies a repeated parent only when the label has one parent.
        # Keep independent levels, including names shared by different branches (e.g. casual).
        levels = catalog[[col for col in ('category_l1', 'category_l2', 'category_l3') if col in catalog]].astype(str)
        self.diversity_fields: list[str] = []
        for level in levels:
            if not any(levels.groupby(level)[parent].nunique().le(1).all() for parent in self.diversity_fields):
                self.diversity_fields.append(level)
        self.paths = dict(zip(catalog.index, levels[self.diversity_fields].itertuples(index=False, name=None)))
        self.bandit=create_strategy(self.spec['mab'])
        if set(self.spec['reranking']['pipeline'])!={'cold_start','new_item','exploration','diversity'} or self.spec['reranking']['pipeline'][-1]!='diversity':
            raise ValueError('pipeline must include all strategies and finish with diversity')
        if self.spec['reranking']['cold_sort']!='popularity_growth': raise ValueError('unsupported cold sort')
        if self.spec['max_consecutive_same_category']<1 or self.spec['mab']['exploration_slots']<0:
            raise ValueError('invalid reranking quotas')

    def run(self,items: list[RankedItem],top_n: int,at: pd.Timestamp,history_count: int,
            fallback_scores: dict,stats: dict,arm_for: Callable[[str], str],rng: np.random.Generator) -> tuple[list[RankedItem],dict]:
        if top_n<1: raise ValueError('top_n must be positive')
        unique: dict[str, RankedItem] = {}
        for item in items:
            if item.product_id not in self.created or self.created[item.product_id]>at: continue
            unique.setdefault(item.product_id,item)
        pool=sorted(unique.values(),key=lambda x:(-x.score,x.product_id))
        count = min(top_n, len(pool))
        limit = self.spec['max_consecutive_same_category']
        available = [Counter(self.paths[p][i] for p in unique) for i in range(len(self.diversity_fields))]
        initial_counts = {field: dict(counts) for field, counts in zip(self.diversity_fields, available)}
        capacity = min(diversity_capacity(counts, limit) for counts in available)
        target = min(count, capacity)
        slots = min(2, self.spec['mab']['exploration_slots'], target)
        new={item.product_id for item in pool if at-pd.Timedelta(days=self.spec['new_item_days'])<=self.created[item.product_id]<=at}
        selected_ids: list[str] = []; new_anchor: str | None = None
        for stage in self.spec['reranking']['pipeline'][:-1]:
            if (stage=='cold_start' and history_count<self.spec['cold_start_min_events']
                    and self.spec.get('scoring',{}).get('strategy')!='newest'):
                pool=[replace(item,score=float(fallback_scores.get(item.product_id,0)),reason='인기·최근 상승 상품')
                      for item in sorted(pool,key=lambda x:(-fallback_scores.get(x.product_id,0),x.product_id))]
            elif stage=='new_item' and new:
                new_anchor=next(item.product_id for item in pool if item.product_id in new)
            elif stage=='exploration':
                selected_ids=self.bandit.select([item.product_id for item in pool],stats,arm_for,rng,slots)
        # At small N a new item can satisfy both quotas in the same slot.
        if new and slots and not (set(selected_ids)&new):
            assert new_anchor is not None
            selected_ids[-1]=new_anchor
        mandatory=set(selected_ids)
        if new and count and not mandatory&new:
            assert new_anchor is not None
            mandatory.add(new_anchor)
        mapped={item.product_id:replace(item,is_exploration=item.product_id in selected_ids,
                reason='MAB 탐색' if item.product_id in selected_ids else '신상품 추천' if item.product_id in mandatory&new else item.reason) for item in pool}
        ids, diagnostics = self._diverse_order(mapped, mandatory, available, target, limit)
        output = [mapped[p] for p in ids]
        violations = []
        if len(ids) < count:
            diagnostics.append('insufficient_diverse_candidates')
            violations.append('diversity')
        if new and not set(ids)&new: violations.append('new_item_missing')
        if sum(x.is_exploration for x in output)!=slots: violations.append('exploration_quota')
        if not new: diagnostics.append('new_item_unavailable_in_candidate_pool')
        if len(pool)<top_n: diagnostics.append('insufficient_distinct_candidates')
        return output,dict(requested=top_n,returned=len(output),exploration_slots=slots,new_available=len(new),
                           diversity_capacity=capacity,diversity_feasible_for_returned=capacity>=count,
                           candidate_category_counts=dict(Counter(self.categories[p] for p in mapped)),
                           candidate_counts_by_diversity_field=initial_counts,
                           diagnostics=sorted(set(diagnostics)),violations=violations,
                           status='INCOMPLETE' if 'diversity_search_limit' in diagnostics else 'INFEASIBLE' if violations else 'PASS')

    def _diverse_order(self, items: dict[str, RankedItem], mandatory: set[str],
                      available: list[Counter], target: int, limit: int) -> tuple[list[str], list[str]]:
        # Items with the same category path and quota status are interchangeable for feasibility.
        groups: dict[tuple[tuple, bool], list[str]] = {}
        for pid in sorted(items, key=lambda p: (items[p].score, p)):
            groups.setdefault((self.paths[pid], pid in mandatory), []).append(pid)
        levels = range(len(available))
        needed = [Counter(self.paths[p][i] for p in mandatory) for i in levels]
        order: list[str] = []
        best: list[str] = []
        failed: set[tuple] = set()
        # Bound recovery work for pathological, mutually incompatible category/slot constraints.
        # Even a partial response must respect all consecutive-category limits.
        max_failures = max(len(items), target * len(groups))

        def fill(tails: tuple, runs: tuple, missing: int) -> bool:
            nonlocal best
            slots = target - len(order)
            if slots == 0:
                return missing == 0
            if len(failed) >= max_failures:
                return False
            state = (tuple(map(len, groups.values())), tails, runs)
            if state in failed:
                return False
            options = sorted((key for key, ids in groups.items() if ids),
                             key=lambda key: (key[1], items[groups[key][-1]].score, groups[key][-1]), reverse=True)
            for path, required in options:
                if missing - required >= slots:
                    continue
                next_runs = tuple(runs[i]+1 if path[i]==tails[i] else 1 for i in levels)
                if max(next_runs) > limit:
                    continue
                for i, label in enumerate(path):
                    available[i][label] -= 1
                    if required:
                        needed[i][label] -= 1
                group = groups[path, required]
                order.append(group.pop())
                feasible = all(completion_feasible(available[i], needed[i], slots-1, limit, path[i], next_runs[i])
                               for i in levels)
                if feasible and fill(path, next_runs, missing-required):
                    return True
                if len(order) > len(best):
                    best = order.copy()
                group.append(order.pop())
                for i, label in enumerate(path):
                    available[i][label] += 1
                    if required:
                        needed[i][label] += 1
                if len(failed) >= max_failures:
                    return False
            failed.add(state)
            return False

        if fill((None,)*len(levels), (0,)*len(levels), len(mandatory)):
            return order, []
        return best, ['diversity_search_limit' if len(failed) >= max_failures else 'incompatible_diversity_quotas']
