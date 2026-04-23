"""
C1 (ブランチカバレッジ) パス列挙

C1 基準:
  CFG 上の全ての分岐辺 (True / False / case:*) が
  少なくとも 1 本のテストパスで通過されること。

アルゴリズム:
1. ENTRY → EXIT への全単純パスを DFS で列挙する。
   ループの後退辺 (back) は 1 回だけ通過を許容
   (ループ本体を最低 1 回実行するパスを生成するため)。
2. 全分岐辺の集合 B を求める。
3. 貪欲法でパスを選び、B を全てカバーする最小パス集合を返す。
"""

from __future__ import annotations
from typing import List, Set, Tuple, FrozenSet
from .cfg_builder import CFG


PathType = List[Tuple[str, str]]   # [(node_id, edge_label), ...] + 最終 node


def _all_paths(cfg: CFG, max_back: int = 1) -> List[PathType]:
    """
    ENTRY から EXIT への全単純パスを列挙する。
    back ラベルの辺は最大 max_back 回まで通過を許容する。
    """
    results: List[PathType] = []
    exit_id = cfg.exit_id

    def dfs(
        node_id: str,
        path: PathType,
        visited: Set[str],
        back_count: dict,
    ) -> None:
        if node_id == exit_id:
            results.append(path[:])
            return

        node = cfg.nodes.get(node_id)
        if node is None:
            return

        for target, lbl in node.successors:
            if lbl == "back":
                # ループ後退辺: 訪問回数の上限チェック
                key = (node_id, target)
                if back_count.get(key, 0) >= max_back:
                    continue
                back_count[key] = back_count.get(key, 0) + 1
                path.append((target, lbl))
                dfs(target, path, visited, back_count)
                path.pop()
                back_count[key] -= 1
            else:
                if target in visited:
                    continue
                visited.add(target)
                path.append((target, lbl))
                dfs(target, path, visited, back_count)
                path.pop()
                visited.discard(target)

    entry_id = cfg.entry_id
    dfs(entry_id, [(entry_id, "")], {entry_id}, {})
    return results


def _path_branch_edges(path: PathType, cfg: CFG) -> FrozenSet[Tuple[str, str, str]]:
    """パスが通過する分岐辺の集合を返す。"""
    edges: Set[Tuple[str, str, str]] = set()
    for i in range(len(path) - 1):
        src_id, _ = path[i]
        tgt_id, lbl = path[i + 1]
        if lbl in ("True", "False") or lbl.startswith("case:"):
            edges.add((src_id, tgt_id, lbl))
    return frozenset(edges)


def _path_node_labels(path: PathType, cfg: CFG) -> List[str]:
    """パスのノードラベル列を返す (表示用)。"""
    labels = []
    for i, (nid, lbl) in enumerate(path):
        node = cfg.nodes.get(nid)
        node_label = node.label if node else nid
        if i == 0:
            labels.append(node_label)
        else:
            edge_str = f" --[{lbl}]--> " if lbl else " --> "
            labels.append(edge_str + node_label)
    return labels


def enumerate_c1_paths(cfg: CFG) -> dict:
    """
    C1 カバレッジを満たす最小パス集合を返す。

    Returns
    -------
    {
      "method": str,
      "all_branch_edges": [...],
      "c1_paths": [
        {
          "path_id": int,
          "nodes": [str, ...],
          "covered_branches": [...]
        },
        ...
      ],
      "uncovered_branches": [...]   # 到達不能などで未カバーの辺
    }
    """
    all_paths = _all_paths(cfg)

    # 全分岐辺
    all_branch_edges: Set[Tuple[str, str, str]] = set(cfg.branch_edges())

    # 各パスの分岐辺カバレッジ
    path_covers = [
        (path, _path_branch_edges(path, cfg))
        for path in all_paths
    ]

    # 貪欲集合被覆
    covered: Set[Tuple[str, str, str]] = set()
    selected = []

    remaining_targets = set(all_branch_edges)

    while remaining_targets:
        best_path = None
        best_new = frozenset()
        for path, covers in path_covers:
            new = covers & remaining_targets
            if len(new) > len(best_new):
                best_new = new
                best_path = (path, covers)
        if best_path is None or not best_new:
            break
        selected.append(best_path)
        covered |= best_new
        remaining_targets -= best_new

    # パスが 0 本でも空のメソッドには ENTRY→EXIT の1本を追加
    if not selected and all_paths:
        selected.append((all_paths[0], _path_branch_edges(all_paths[0], cfg)))

    uncovered = all_branch_edges - covered

    # 結果整形
    def edge_to_dict(e: Tuple[str, str, str]) -> dict:
        src, tgt, lbl = e
        src_label = cfg.nodes[src].label if src in cfg.nodes else src
        tgt_label = cfg.nodes[tgt].label if tgt in cfg.nodes else tgt
        return {"from": src_label, "to": tgt_label, "branch": lbl}

    c1_paths = []
    for pid, (path, covers) in enumerate(selected, 1):
        node_labels = _path_node_labels(path, cfg)
        c1_paths.append({
            "path_id": pid,
            "nodes": node_labels,
            "covered_branches": [edge_to_dict(e) for e in sorted(covers)],
        })

    return {
        "method": cfg.method_name,
        "total_branch_edges": len(all_branch_edges),
        "all_branch_edges": [edge_to_dict(e) for e in sorted(all_branch_edges)],
        "c1_paths_count": len(c1_paths),
        "c1_paths": c1_paths,
        "uncovered_branches": [edge_to_dict(e) for e in sorted(uncovered)],
    }
