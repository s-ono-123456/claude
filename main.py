"""
Java AST → CFG → C1 パス列挙

使い方:
    python main.py <JavaFile.java> [--ast-only] [--output <dir>]

    --ast-only   : AST JSON のみ出力 (CFG・パス列挙をスキップ)
    --output <d> : JSON ファイルを <d> ディレクトリに保存
"""

import argparse
import json
import os
import sys

from java_ast_cfg.parser import JavaASTParser
from java_ast_cfg.cfg_builder import CFGBuilder
from java_ast_cfg.path_enumerator import enumerate_c1_paths


# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #
def parse_args():
    p = argparse.ArgumentParser(description="Java AST → CFG → C1 path enumeration")
    p.add_argument("java_file", help="解析対象の Java ファイル")
    p.add_argument("--ast-only", action="store_true", help="AST JSON だけ出力")
    p.add_argument("--output", metavar="DIR", default=None,
                   help="結果を JSON ファイルとして保存するディレクトリ")
    return p.parse_args()


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #
def main():
    args = parse_args()

    if not os.path.isfile(args.java_file):
        print(f"ERROR: ファイルが見つかりません: {args.java_file}", file=sys.stderr)
        sys.exit(1)

    # ── Step 1: Java AST パース ──────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"[STEP 1] Java AST 解析: {args.java_file}")
    print('='*60)

    parser = JavaASTParser()
    ast_result = parser.parse_file(args.java_file)

    ast_json = json.dumps(ast_result, ensure_ascii=False, indent=2)
    print(ast_json)

    if args.output:
        os.makedirs(args.output, exist_ok=True)
        ast_path = os.path.join(args.output, "ast.json")
        with open(ast_path, "w", encoding="utf-8") as f:
            f.write(ast_json)
        print(f"\n[保存] {ast_path}")

    if args.ast_only:
        return

    # ── Step 2: CFG 構築 & Step 3: C1 パス列挙 ──────────────────────
    cfg_builder = CFGBuilder()
    all_c1_results = []

    for cls in ast_result.get("classes", []):
        for method in cls.get("methods", []):
            method_name = f"{cls['name']}.{method['name']}"

            print(f"\n{'='*60}")
            print(f"[STEP 2] CFG 構築: {method_name}")
            print('='*60)

            cfg = cfg_builder.build(method)
            cfg_dict = cfg.to_dict()

            print(json.dumps(cfg_dict, ensure_ascii=False, indent=2))

            if args.output:
                safe_name = method['name'].replace("/", "_")
                cfg_path = os.path.join(args.output, f"cfg_{safe_name}.json")
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg_dict, f, ensure_ascii=False, indent=2)
                print(f"[保存] {cfg_path}")

            print(f"\n{'='*60}")
            print(f"[STEP 3] C1 パス列挙: {method_name}")
            print('='*60)

            c1_result = enumerate_c1_paths(cfg)
            c1_json = json.dumps(c1_result, ensure_ascii=False, indent=2)
            print(c1_json)

            all_c1_results.append(c1_result)

            if args.output:
                c1_path = os.path.join(args.output, f"c1_{safe_name}.json")
                with open(c1_path, "w", encoding="utf-8") as f:
                    f.write(c1_json)
                print(f"[保存] {c1_path}")

    # ── サマリ ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("[SUMMARY] C1 カバレッジ サマリ")
    print('='*60)
    total_branches = sum(r["total_branch_edges"] for r in all_c1_results)
    total_paths = sum(r["c1_paths_count"] for r in all_c1_results)
    total_uncovered = sum(len(r["uncovered_branches"]) for r in all_c1_results)

    for r in all_c1_results:
        uc = len(r["uncovered_branches"])
        status = "✓ 全分岐カバー" if uc == 0 else f"✗ 未カバー分岐: {uc} 本"
        print(f"  {r['method']:30s}  分岐数={r['total_branch_edges']:2d}  "
              f"C1パス数={r['c1_paths_count']:2d}  {status}")

    print(f"\n  合計: 分岐辺 {total_branches} 本 / C1 パス {total_paths} 本 / "
          f"未カバー {total_uncovered} 本")

    if args.output:
        summary_path = os.path.join(args.output, "summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(all_c1_results, f, ensure_ascii=False, indent=2)
        print(f"\n[保存] {summary_path}")


if __name__ == "__main__":
    main()
