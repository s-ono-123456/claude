"""
JavaASTParser: Java ソースを javalang でパースし、
各メソッドの分岐・ループ構造を JSON 互換の dict として返す。
"""

import json
import javalang
import javalang.tree as jt


class JavaASTParser:
    def parse_file(self, file_path: str) -> dict:
        with open(file_path, "r", encoding="utf-8") as f:
            return self.parse_source(f.read())

    def parse_source(self, source: str) -> dict:
        tree = javalang.parse.parse(source)
        result = {
            "package": tree.package.name if tree.package else None,
            "imports": [imp.path for imp in (tree.imports or [])],
            "classes": [],
        }
        for _, cls in tree.filter(jt.ClassDeclaration):
            cls_info = {
                "name": cls.name,
                "methods": [self._parse_method(m) for m in (cls.methods or [])],
            }
            result["classes"].append(cls_info)
        return result

    # ------------------------------------------------------------------ #
    # Method
    # ------------------------------------------------------------------ #
    def _parse_method(self, method) -> dict:
        return {
            "name": method.name,
            "returnType": method.return_type.name if method.return_type else "void",
            "parameters": [
                {"type": p.type.name, "name": p.name}
                for p in (method.parameters or [])
            ],
            "body": self._parse_stmts(method.body or []),
        }

    # ------------------------------------------------------------------ #
    # Statement list
    # ------------------------------------------------------------------ #
    def _parse_stmts(self, stmts) -> list:
        result = []
        for s in stmts:
            node = self._parse_stmt(s)
            if node is not None:
                result.append(node)
        return result

    # ------------------------------------------------------------------ #
    # Single statement dispatch
    # ------------------------------------------------------------------ #
    def _parse_stmt(self, s) -> dict | None:
        if isinstance(s, jt.IfStatement):
            return self._if(s)
        if isinstance(s, jt.WhileStatement):
            return self._while(s)
        if isinstance(s, jt.ForStatement):
            return self._for(s)
        if isinstance(s, jt.DoStatement):
            return self._dowhile(s)
        if isinstance(s, jt.SwitchStatement):
            return self._switch(s)
        if isinstance(s, jt.ReturnStatement):
            return {"type": "return",
                    "value": self._expr(s.expression)}
        if isinstance(s, jt.BreakStatement):
            return {"type": "break",
                    "label": s.goto}
        if isinstance(s, jt.ContinueStatement):
            return {"type": "continue",
                    "label": s.goto}
        if isinstance(s, jt.ThrowStatement):
            return {"type": "throw",
                    "expression": self._expr(s.expression)}
        if isinstance(s, jt.TryStatement):
            return self._try(s)
        if isinstance(s, jt.BlockStatement):
            return {"type": "block",
                    "body": self._parse_stmts(s.statements or [])}
        if isinstance(s, jt.StatementExpression):
            return {"type": "statement",
                    "expression": self._expr(s.expression)}
        if isinstance(s, jt.LocalVariableDeclaration):
            return self._local_var(s)
        if isinstance(s, jt.SynchronizedStatement):
            return {"type": "synchronized",
                    "lock": self._expr(s.lock),
                    "body": self._parse_stmts(s.block.statements or [])}
        # fallback
        return {"type": "other", "class": type(s).__name__}

    # ------------------------------------------------------------------ #
    # Branch statements
    # ------------------------------------------------------------------ #
    def _block_body(self, node) -> list:
        if node is None:
            return []
        if hasattr(node, "statements") and node.statements is not None:
            return self._parse_stmts(node.statements)
        return [self._parse_stmt(node)] if self._parse_stmt(node) else []

    def _if(self, s) -> dict:
        return {
            "type": "if",
            "condition": self._expr(s.condition),
            "trueBranch": self._block_body(s.then_statement),
            "falseBranch": self._block_body(s.else_statement),
        }

    def _while(self, s) -> dict:
        return {
            "type": "while",
            "condition": self._expr(s.condition),
            "body": self._block_body(s.body),
        }

    def _for(self, s) -> dict:
        ctrl = s.control
        if isinstance(ctrl, jt.ForControl):
            init = self._for_init(ctrl.init)
            condition = self._expr(ctrl.condition)
            update = (", ".join(self._expr(u) for u in ctrl.update)
                      if ctrl.update else None)
        else:  # EnhancedForControl
            init = f"{ctrl.type.name} {ctrl.var.name} : {self._expr(ctrl.iterable)}"
            condition = None
            update = None
        return {
            "type": "for",
            "init": init,
            "condition": condition,
            "update": update,
            "body": self._block_body(s.body),
        }

    def _dowhile(self, s) -> dict:
        return {
            "type": "dowhile",
            "condition": self._expr(s.condition),
            "body": self._block_body(s.body),
        }

    def _switch(self, s) -> dict:
        cases = []
        for c in (s.cases or []):
            cases.append({
                "value": self._expr(c.case) if c.case else "default",
                "body": self._parse_stmts(c.statements or []),
            })
        return {
            "type": "switch",
            "expression": self._expr(s.expression),
            "cases": cases,
        }

    def _try(self, s) -> dict:
        return {
            "type": "try",
            "body": self._parse_stmts(s.block.statements if s.block else []),
            "catches": [
                {
                    "exception": c.parameter.types[0] if c.parameter.types else "Exception",
                    "body": self._parse_stmts(c.block.statements if c.block else []),
                }
                for c in (s.catches or [])
            ],
            "finally": self._parse_stmts(
                s.finally_block.statements
                if s.finally_block and hasattr(s.finally_block, "statements")
                else []
            ),
        }

    def _local_var(self, s) -> dict:
        variables = []
        for d in (s.declarators or []):
            variables.append({
                "name": d.name,
                "initializer": self._expr(d.initializer),
            })
        return {
            "type": "declaration",
            "varType": s.type.name,
            "variables": variables,
        }

    def _for_init(self, init) -> str | None:
        if init is None:
            return None
        if isinstance(init, jt.LocalVariableDeclaration):
            decls = ", ".join(
                (f"{d.name} = {self._expr(d.initializer)}" if d.initializer else d.name)
                for d in init.declarators
            )
            return f"{init.type.name} {decls}"
        if isinstance(init, list):
            return ", ".join(self._expr(e) for e in init)
        return self._expr(init)

    # ------------------------------------------------------------------ #
    # Expression → string
    # ------------------------------------------------------------------ #
    def _expr(self, e) -> str | None:
        if e is None:
            return None
        if isinstance(e, bool):
            return "true" if e else "false"
        if isinstance(e, (int, float)):
            return str(e)
        if isinstance(e, str):
            return e
        if isinstance(e, jt.Literal):
            return str(e.value)
        if isinstance(e, jt.MemberReference):
            parts = []
            if e.qualifier:
                parts.append(e.qualifier)
            parts.append(e.member)
            base = ".".join(parts)
            pre = "".join(e.prefix_operators or [])
            post = "".join(e.postfix_operators or [])
            return f"{pre}{base}{post}"
        if isinstance(e, jt.MethodInvocation):
            args = ", ".join(self._expr(a) for a in (e.arguments or []))
            name = f"{e.qualifier}.{e.member}" if e.qualifier else e.member
            return f"{name}({args})"
        if isinstance(e, jt.BinaryOperation):
            return f"{self._expr(e.operandl)} {e.operator} {self._expr(e.operandr)}"
        if isinstance(e, jt.Assignment):
            return f"{self._expr(e.expressionl)} {e.type} {self._expr(e.value)}"
        if isinstance(e, jt.TernaryExpression):
            return (f"{self._expr(e.condition)} ? "
                    f"{self._expr(e.if_true)} : {self._expr(e.if_false)}")
        if isinstance(e, jt.Cast):
            return f"({e.type.name}) {self._expr(e.expression)}"
        if isinstance(e, jt.ClassCreator):
            args = ", ".join(self._expr(a) for a in (e.arguments or []))
            return f"new {e.type.name}({args})"
        if isinstance(e, jt.ArrayCreator):
            dims = "".join(f"[{self._expr(d)}]" if d else "[]"
                          for d in (e.dimensions or []))
            return f"new {e.type.name}{dims}"
        if isinstance(e, jt.ArraySelector):
            return f"[{self._expr(e.index)}]"
        if isinstance(e, jt.MethodReference):
            return f"{self._expr(e.expression)}::{e.method}"
        if isinstance(e, jt.LambdaExpression):
            params = (", ".join(p.name if hasattr(p, "name") else str(p)
                                for p in e.parameters)
                      if e.parameters else "")
            return f"({params}) -> ..."
        if isinstance(e, jt.This):
            return "this"
        if isinstance(e, jt.SuperMemberReference):
            return f"super.{e.member}"
        if isinstance(e, jt.ClassReference):
            return f"{e.type.name}.class"
        if isinstance(e, list):
            return ", ".join(self._expr(x) for x in e)
        return type(e).__name__


def parse_to_json(source_path: str) -> str:
    parser = JavaASTParser()
    result = parser.parse_file(source_path)
    return json.dumps(result, ensure_ascii=False, indent=2)
