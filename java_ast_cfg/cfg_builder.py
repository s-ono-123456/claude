"""
CFGBuilder: パーサが返した dict (メソッド単位) から
制御フローグラフ (CFG) を構築する。

ノード種別
  ENTRY     メソッド開始
  EXIT      メソッド終了
  STMT      通常文
  COND      分岐条件 (if / while / for / dowhile / switch)
  MERGE     合流点

エッジラベル
  ""        無条件遷移
  "True"    条件 True 側
  "False"   条件 False 側
  "case:<v>" switch の各ケース
  "back"    ループの後退辺
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Dict


@dataclass
class CFGNode:
    id: str
    kind: str          # ENTRY / EXIT / STMT / COND / MERGE
    label: str
    successors: List[Tuple[str, str]] = field(default_factory=list)

    def add_edge(self, target_id: str, label: str = "") -> None:
        self.successors.append((target_id, label))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "successors": [{"target": t, "label": l} for t, l in self.successors],
        }


@dataclass
class CFG:
    method_name: str
    nodes: Dict[str, CFGNode] = field(default_factory=dict)
    entry_id: str = ""
    exit_id: str = ""

    def add_node(self, node: CFGNode) -> None:
        self.nodes[node.id] = node

    def branch_edges(self) -> List[Tuple[str, str, str]]:
        """True / False / case:* ラベルの付いたエッジを返す。"""
        result = []
        for nid, node in self.nodes.items():
            for target, lbl in node.successors:
                if lbl in ("True", "False") or lbl.startswith("case:"):
                    result.append((nid, target, lbl))
        return result

    def to_dict(self) -> dict:
        return {
            "method": self.method_name,
            "entry": self.entry_id,
            "exit": self.exit_id,
            "nodes": [n.to_dict() for n in self.nodes.values()],
        }


class CFGBuilder:
    def __init__(self):
        self._counter = 0
        self._cfg: CFG | None = None

    # ------------------------------------------------------------------ #
    # Public
    # ------------------------------------------------------------------ #
    def build(self, method: dict) -> CFG:
        self._counter = 0
        self._cfg = CFG(method_name=method["name"])

        entry = self._node("ENTRY", f"ENTRY:{method['name']}")
        exit_ = self._node("EXIT", "EXIT")
        self._cfg.entry_id = entry.id
        self._cfg.exit_id = exit_.id

        body = method.get("body") or []
        if body:
            first, ends = self._stmts(body)
            entry.add_edge(first)
            for e in ends:
                if e != exit_.id:
                    self._cfg.nodes[e].add_edge(exit_.id)
        else:
            entry.add_edge(exit_.id)

        return self._cfg

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _node(self, kind: str, label: str) -> CFGNode:
        self._counter += 1
        nid = f"n{self._counter}"
        node = CFGNode(id=nid, kind=kind, label=label)
        self._cfg.add_node(node)
        return node

    def _connect_ends(self, ends: List[str], target: str) -> None:
        exit_id = self._cfg.exit_id
        for e in ends:
            if e != exit_id:
                self._cfg.nodes[e].add_edge(target)

    # ------------------------------------------------------------------ #
    # Statement list
    # ------------------------------------------------------------------ #
    def _stmts(self, stmts: list) -> Tuple[str, List[str]]:
        if not stmts:
            skip = self._node("STMT", "(empty)")
            return skip.id, [skip.id]

        first_id: str | None = None
        cur_ends: List[str] = []

        for s in stmts:
            s_first, s_ends = self._stmt(s)
            if first_id is None:
                first_id = s_first
            else:
                self._connect_ends(cur_ends, s_first)
            cur_ends = s_ends

        return first_id, cur_ends  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Single statement
    # ------------------------------------------------------------------ #
    def _stmt(self, s: dict) -> Tuple[str, List[str]]:
        t = s.get("type", "other")
        if t == "if":
            return self._if(s)
        if t == "while":
            return self._while(s)
        if t == "for":
            return self._for(s)
        if t == "dowhile":
            return self._dowhile(s)
        if t == "switch":
            return self._switch(s)
        if t == "return":
            return self._return(s)
        if t in ("break", "continue"):
            n = self._node("STMT", t + (f"({s['label']})" if s.get("label") else ""))
            n.add_edge(self._cfg.exit_id)
            return n.id, [self._cfg.exit_id]
        if t == "throw":
            n = self._node("STMT", f"throw {s.get('expression', '')}")
            n.add_edge(self._cfg.exit_id)
            return n.id, [self._cfg.exit_id]
        if t == "block":
            return self._stmts(s.get("body") or [])
        if t == "try":
            return self._try(s)
        if t == "declaration":
            vs = ", ".join(
                f"{v['name']} = {v['initializer']}" if v.get("initializer") else v["name"]
                for v in s.get("variables", [])
            )
            n = self._node("STMT", f"{s.get('varType', '')} {vs}")
            return n.id, [n.id]
        if t == "synchronized":
            n = self._node("STMT", f"synchronized({s.get('lock', '')})")
            body_first, body_ends = self._stmts(s.get("body") or [])
            n.add_edge(body_first)
            return n.id, body_ends
        # statement / other
        label = s.get("expression") or s.get("class") or t
        n = self._node("STMT", str(label))
        return n.id, [n.id]

    # ------------------------------------------------------------------ #
    # if
    # ------------------------------------------------------------------ #
    def _if(self, s: dict) -> Tuple[str, List[str]]:
        cond = self._node("COND", f"if ({s['condition']})")
        merge = self._node("MERGE", "merge")

        true_body = s.get("trueBranch") or []
        false_body = s.get("falseBranch") or []

        if true_body:
            tf, te = self._stmts(true_body)
            cond.add_edge(tf, "True")
            self._connect_ends(te, merge.id)
        else:
            cond.add_edge(merge.id, "True")

        if false_body:
            ff, fe = self._stmts(false_body)
            cond.add_edge(ff, "False")
            self._connect_ends(fe, merge.id)
        else:
            cond.add_edge(merge.id, "False")

        return cond.id, [merge.id]

    # ------------------------------------------------------------------ #
    # while
    # ------------------------------------------------------------------ #
    def _while(self, s: dict) -> Tuple[str, List[str]]:
        cond = self._node("COND", f"while ({s['condition']})")
        loop_exit = self._node("MERGE", "loop_exit")
        cond.add_edge(loop_exit.id, "False")

        body = s.get("body") or []
        if body:
            bf, be = self._stmts(body)
            cond.add_edge(bf, "True")
            for e in be:
                if e != self._cfg.exit_id:
                    self._cfg.nodes[e].add_edge(cond.id, "back")
        else:
            cond.add_edge(cond.id, "back")

        return cond.id, [loop_exit.id]

    # ------------------------------------------------------------------ #
    # for
    # ------------------------------------------------------------------ #
    def _for(self, s: dict) -> Tuple[str, List[str]]:
        # init node (optional)
        first_id: str

        if s.get("init"):
            init_n = self._node("STMT", f"for-init: {s['init']}")
            first_id = init_n.id
        else:
            init_n = None

        # condition node
        if s.get("condition"):
            cond = self._node("COND", f"for-cond: {s['condition']}")
        else:
            # enhanced for / no condition → treat as always-true
            cond = self._node("COND", "for-cond: (each)")

        if init_n:
            init_n.add_edge(cond.id)
        else:
            first_id = cond.id

        loop_exit = self._node("MERGE", "loop_exit")
        cond.add_edge(loop_exit.id, "False")

        # update node (optional)
        if s.get("update"):
            upd = self._node("STMT", f"for-update: {s['update']}")
            upd.add_edge(cond.id, "back")
            loop_back_target = upd.id
        else:
            loop_back_target = cond.id

        body = s.get("body") or []
        if body:
            bf, be = self._stmts(body)
            cond.add_edge(bf, "True")
            for e in be:
                if e != self._cfg.exit_id:
                    self._cfg.nodes[e].add_edge(loop_back_target)
        else:
            cond.add_edge(loop_back_target, "True")

        return first_id, [loop_exit.id]

    # ------------------------------------------------------------------ #
    # do-while
    # ------------------------------------------------------------------ #
    def _dowhile(self, s: dict) -> Tuple[str, List[str]]:
        # body runs first, then condition
        body = s.get("body") or []
        cond = self._node("COND", f"do-while ({s['condition']})")
        loop_exit = self._node("MERGE", "do_loop_exit")

        cond.add_edge(loop_exit.id, "False")

        if body:
            bf, be = self._stmts(body)
            self._connect_ends(be, cond.id)
            cond.add_edge(bf, "back")
            return bf, [loop_exit.id]
        else:
            cond.add_edge(cond.id, "back")
            return cond.id, [loop_exit.id]

    # ------------------------------------------------------------------ #
    # switch
    # ------------------------------------------------------------------ #
    def _switch(self, s: dict) -> Tuple[str, List[str]]:
        cond = self._node("COND", f"switch ({s['expression']})")
        merge = self._node("MERGE", "switch_merge")
        all_ends: List[str] = []

        has_default = False
        for case in s.get("cases") or []:
            val = case["value"]
            if val == "default":
                has_default = True
                lbl = "case:default"
            else:
                lbl = f"case:{val}"

            body = case.get("body") or []
            if body:
                cf, ce = self._stmts(body)
                cond.add_edge(cf, lbl)
                all_ends.extend(ce)
            else:
                cond.add_edge(merge.id, lbl)

        if not has_default:
            cond.add_edge(merge.id, "case:default")

        self._connect_ends(all_ends, merge.id)
        return cond.id, [merge.id]

    # ------------------------------------------------------------------ #
    # return
    # ------------------------------------------------------------------ #
    def _return(self, s: dict) -> Tuple[str, List[str]]:
        val = s.get("value")
        label = f"return {val}" if val else "return"
        n = self._node("STMT", label)
        n.add_edge(self._cfg.exit_id)
        return n.id, [self._cfg.exit_id]

    # ------------------------------------------------------------------ #
    # try
    # ------------------------------------------------------------------ #
    def _try(self, s: dict) -> Tuple[str, List[str]]:
        try_n = self._node("STMT", "try")
        merge = self._node("MERGE", "try_merge")

        body = s.get("body") or []
        if body:
            bf, be = self._stmts(body)
            try_n.add_edge(bf)
            self._connect_ends(be, merge.id)
        else:
            try_n.add_edge(merge.id)

        for catch in s.get("catches") or []:
            exc = catch.get("exception", "Exception")
            catch_n = self._node("COND", f"catch ({exc})")
            try_n.add_edge(catch_n.id, f"catch:{exc}")
            cbody = catch.get("body") or []
            if cbody:
                cf, ce = self._stmts(cbody)
                catch_n.add_edge(cf, "True")
                catch_n.add_edge(merge.id, "False")
                self._connect_ends(ce, merge.id)
            else:
                catch_n.add_edge(merge.id, "True")
                catch_n.add_edge(merge.id, "False")

        fin = s.get("finally") or []
        if fin:
            ff, fe = self._stmts(fin)
            merge.add_edge(ff)
            fin_merge = self._node("MERGE", "finally_merge")
            self._connect_ends(fe, fin_merge.id)
            return try_n.id, [fin_merge.id]

        return try_n.id, [merge.id]
