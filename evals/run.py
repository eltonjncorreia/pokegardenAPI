"""Executa os casos de ``evals.cases`` e grava o relatório por caso.

Uso::

    python -m evals.run                 # offline: pytest + agente com modelo roteirizado
    python -m evals.run --mode live     # modelo real + PokéAPI real (requer OPENAI_API_KEY)
    python -m evals.run --mode all --cases E01,E05

Saída: ``evidence/evals/report-<modo>.json`` e ``.md`` + logs JSON de cada caso
em ``evidence/evals/<modo>/<caso>.jsonl``. Falhas nunca são omitidas.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from config import settings  # noqa: E402

from evals.cases import CASES  # noqa: E402
from evals.harness import Case, RunOutcome, check, execute, runs_for  # noqa: E402

EVIDENCE = ROOT / "evidence" / "evals"


# --------------------------------------------------------------------------- #
# pytest (casos determinísticos referenciados)
# --------------------------------------------------------------------------- #
def run_pytest() -> dict[str, tuple[str, str]]:
    """Roda a suíte offline uma vez e devolve ``node_id -> (resultado, detalhe)``."""
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "junit.xml"
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml_path}"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        if not xml_path.exists():
            return {}
        results = {}
        for tc in ET.parse(xml_path).iter("testcase"):
            node = f"{tc.get('classname', '').replace('.', '/')}.py::{tc.get('name')}"
            failure = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
            if failure is not None:
                results[node] = ("fail", (failure.get("message") or "")[:200])
            elif tc.find("skipped") is not None:
                results[node] = ("not_run", "skipped")
            else:
                results[node] = ("pass", "")
        return results


# --------------------------------------------------------------------------- #
# Avaliação de um caso
# --------------------------------------------------------------------------- #
def evaluate(case: Case, mode: str, pytest_results: dict[str, tuple[str, str]] | None) -> dict:
    """Resultado de um caso no modo dado (``pass``/``fail``/``not_run``)."""
    started = time.monotonic()
    row: dict = {"id": case.id, "scenario": case.scenario, "acceptance": case.acceptance, "runs": [], "pytest": []}
    reasons: list[str] = []
    executed_any = False

    if mode == "offline" and pytest_results is not None:
        for ref in case.pytest_refs:
            result, detail = pytest_results.get(ref, ("fail", "teste não encontrado na coleta"))
            row["pytest"].append({"ref": ref, "result": result, "detail": detail})
            executed_any = True
            if result != "pass":
                reasons.append(f"pytest {ref}: {result} {detail}".strip())

    runs = runs_for(case, mode)
    if mode == "live" and runs and not settings.openai_api_key:
        row.update(result="not_run", mode="live", reason="OPENAI_API_KEY ausente: execução live não realizada",
                   duration_ms=0, evidence=[])
        return row
    if runs:
        outcomes = execute(case, mode)
        executed_any = True
        log_path = _write_log(case, mode, outcomes)
        row["evidence"] = [str(log_path.relative_to(ROOT))]
        for o in outcomes:
            fails = check(o, mode)
            row["runs"].append(_run_row(o, fails))
            reasons.extend(f"[{o.run.label or 'run'}] {f}" for f in fails)
        if case.cross_check and len(outcomes) == len(runs) and all(o.result for o in outcomes):
            cross = case.cross_check(outcomes)
            row["cross_check"] = cross or "ok"
            reasons.extend(f"[entre requisições] {f}" for f in cross)
    else:
        row["evidence"] = []
    row["evidence"] += [p["ref"] for p in row["pytest"]]

    if not executed_any:
        why = "coberto no modo offline (sem execução live definida)" if mode == "live" else "sem execução definida"
        row.update(result="not_run", mode=mode, reason=why, duration_ms=0)
        return row
    parts = []
    if row["pytest"]:
        parts.append("offline-pytest")
    if runs:
        parts.append("offline-sdk-roteirizado" if mode == "offline" else f"live ({settings.openai_model})")
    row.update(
        result="fail" if reasons else "pass",
        mode=" + ".join(parts),
        reason="; ".join(reasons) if reasons else "todas as invariantes satisfeitas",
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    if case.limitations:
        row["limitations"] = case.limitations
    return row


def _run_row(o: RunOutcome, fails: list[str]) -> dict:
    res = o.result
    chat_end = next(iter(o.events_named("chat.end")), {})
    return {
        "label": o.run.label,
        "profile": o.run.profile,
        "prompt": o.run.prompt,
        "result": "fail" if fails else "pass",
        "failures": fails,
        "duration_ms": o.duration_ms,
        "status": res.status if res else None,
        "answer": res.answer if res else None,
        "tools_used": res.tools_used if res else [],
        "sources": res.sources if res else [],
        "warnings": res.warnings if res else [],
        "tool_calls": [{"tool": e.get("tool"), "error_code": e.get("error_code")} for e in o.events_named("tool.call")],
        "http_gets": len(o.gets),
        "tokens": {k: chat_end.get(k) for k in ("llm_requests", "input_tokens", "output_tokens", "total_tokens")},
        "request_id": res.request_id if res else None,
    }


def _write_log(case: Case, mode: str, outcomes: list[RunOutcome]) -> Path:
    path = EVIDENCE / mode / f"{case.id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for o in outcomes:
            for event in o.events:
                fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return path


# --------------------------------------------------------------------------- #
# Relatório
# --------------------------------------------------------------------------- #
def _meta(mode: str) -> dict:
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": mode,
        "model": settings.openai_model if mode == "live" else "ScriptedModel (replay offline, sem LLM)",
        "pokeapi": "https://pokeapi.co (real)" if mode == "live" else "fixtures em evals/fixtures/pokeapi (não são consultas reais)",
        "openai_agents": version("openai-agents"),
        "openai": version("openai"),
        "python": platform.python_version(),
        "git_commit": commit or None,
    }


def write_report(mode: str, rows: list[dict]) -> tuple[Path, Path]:
    meta = _meta(mode)
    totals = {k: sum(r["result"] == k for r in rows) for k in ("pass", "fail", "not_run")}
    tokens = [r2["tokens"] for r in rows for r2 in r["runs"] if r2["tokens"].get("total_tokens") is not None]
    if mode == "live":
        meta["total_tokens"] = sum(t["total_tokens"] for t in tokens) if tokens else "indisponível"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    json_path = EVIDENCE / f"report-{mode}.json"
    json_path.write_text(json.dumps({"meta": meta, "totals": totals, "cases": rows}, ensure_ascii=False, indent=2, default=str) + "\n")

    lines = [
        f"# Relatório de avaliação — modo {mode}",
        "",
        *(f"- **{k}**: {v}" for k, v in meta.items()),
        f"- **resultado**: {totals['pass']} pass · {totals['fail']} fail · {totals['not_run']} not_run",
        "",
        "| Caso | Cenário | Resultado | Modo | Duração | Motivo | Evidências |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        evidence = "<br>".join(f"`{e}`" for e in r.get("evidence", []))
        reason = r["reason"].replace("|", "\\|")
        lines.append(f"| {r['id']} | {r['scenario']} | **{r['result']}** | {r['mode']} | {r['duration_ms']} ms | {reason} | {evidence} |")
    lines += ["", "## Detalhe por requisição", ""]
    for r in rows:
        for run in r["runs"]:
            label = f" ({run['label']})" if run["label"] else ""
            lines += [
                f"### {r['id']}{label} — {run['result']}",
                f"- prompt: {run['prompt']}",
                f"- perfil: {run['profile']} · status: `{run['status']}` · {run['duration_ms']} ms · GETs: {run['http_gets']}",
                f"- tools_used: {run['tools_used']} · tool.call: {run['tool_calls']}",
                f"- fontes: {[s['url'] for s in run['sources']]}",
                f"- answer: {run['answer']}",
                *([f"- falhas: {run['failures']}"] if run["failures"] else []),
                *([f"- tokens: {run['tokens']}"] if mode == "live" else []),
                "",
            ]
        if r.get("limitations"):
            lines += [f"> **Limitações ({r['id']})**: {r['limitations']}", ""]
    md_path = EVIDENCE / f"report-{mode}.md"
    md_path.write_text("\n".join(lines) + "\n")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avaliação do agente PokéGarden (seção 8).")
    parser.add_argument("--mode", choices=["offline", "live", "all"], default="offline")
    parser.add_argument("--cases", help="IDs separados por vírgula (prefixo: E12 casa E12a..E12d)")
    args = parser.parse_args(argv)

    selected = CASES
    if args.cases:
        wanted = [c.strip().upper() for c in args.cases.split(",")]
        selected = [c for c in CASES if any(c.id.upper().startswith(w) for w in wanted)]

    exit_code = 0
    for mode in ["offline", "live"] if args.mode == "all" else [args.mode]:
        pytest_results = run_pytest() if mode == "offline" else None
        rows = [evaluate(case, mode, pytest_results) for case in selected]
        json_path, md_path = write_report(mode, rows)
        print(f"\n== {mode} ==")
        for r in rows:
            print(f"  {r['id']:<5} {r['result']:<8} {r['duration_ms']:>6} ms  {r['reason'][:110]}")
        print(f"  relatório: {md_path.relative_to(ROOT)} · {json_path.relative_to(ROOT)}")
        if any(r["result"] == "fail" for r in rows):
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
