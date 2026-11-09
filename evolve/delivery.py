#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Evidence-derived reports with resumable, separately verified delivery."""
import argparse
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[a-z][a-z0-9-]{0,47}")
OUTPUTS = ("summary.json", "REPORT.md", "explainer.json", "explainer.html", "generate_report.py")
VISUAL_CHECKS = ("readable", "no_overflow", "collapsed_evidence", "charts_visible")


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest(value):
    return digest_bytes(json.dumps(value, sort_keys=True, allow_nan=False).encode())


def read(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda value: _invalid(value))


def _invalid(value):
    raise ValueError("non-finite JSON value: " + value)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def at(root, relative, *, exists=True):
    root = Path(root).resolve()
    p = Path(relative)
    if p.is_absolute() or ".." in p.parts or p.as_posix() != str(relative):
        raise ValueError("expected a canonical repository-relative path")
    result = root / p
    for parent in [result, *result.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("evidence must not traverse symlinks")
    if not result.resolve().is_relative_to(root):
        raise ValueError("evidence escapes repository")
    if exists and not result.is_file():
        raise ValueError("missing evidence: " + str(relative))
    return result


def campaign_path(root, campaign):
    if not NAME.fullmatch(campaign):
        raise ValueError("invalid campaign")
    path = Path(root).resolve() / "campaigns" / campaign
    if path.is_symlink():
        raise ValueError("campaign must not be a symlink")
    return path


def public(value, root):
    """Keep report summaries free of private host paths; source hashes stay exact."""
    if isinstance(value, dict):
        return {k: public(v, root) for k, v in value.items()
                if k not in {"environment", "env", "credentials", "host_load"}}
    if isinstance(value, list):
        return [public(v, root) for v in value]
    if isinstance(value, str):
        value = value.replace(str(Path(root).resolve()) + "/", "")
        return re.sub(r"(?<![A-Za-z0-9:/])/(?:home|Users|tmp|workspace|Volumes)/[^\s\"'<>]+",
                      "[local path]", value)
    return value


def extract(root, campaign):
    root = Path(root).resolve()
    directory = campaign_path(root, campaign)
    record = read(directory / "campaign.json")
    if record.get("campaign") != campaign:
        raise ValueError("campaign identity mismatch")
    names = ["campaign.json", "policy.json", "protocol.json"]
    paths = [directory / name for name in names]
    paths += [directory / name for name in ("research.json", "ledger/ledger.json", "ledger/budget.json", "ledger/session-closeout.json")
              if (directory / name).is_file()]
    for pattern in ("candidates/*.json", "candidates/*/value.json", "reviews/*.json",
                    "comparisons/*.json"):
        paths += sorted(directory.glob(pattern))
    paths += sorted((directory / "patches").glob("*.patch"))
    manifest = {}
    for path in sorted(set(paths)):
        ref = path.relative_to(root).as_posix()
        manifest[ref] = digest_bytes(at(root, ref).read_bytes())
    protocol = read(directory / "protocol.json")
    rows = read(directory / "ledger/ledger.json") if (directory / "ledger/ledger.json").exists() else []
    if not isinstance(rows, list) or len({r.get("id") for r in rows}) != len(rows):
        raise ValueError("malformed or duplicate evaluation ledger")
    budget = read(directory / "ledger/budget.json") if (directory / "ledger/budget.json").exists() else {}
    candidates = []
    for path in sorted(directory.glob("candidates/*.json")):
        item = read(path)
        if item.get("id") != path.stem:
            raise ValueError("candidate identity mismatch")
        value = directory / "candidates" / path.stem / "value.json"
        candidates.append({**item, "value_decision": read(value) if value.is_file() else None})
    missing_raw = []
    for row in rows:
        for run in row.get("runs", []):
            if run.get("result"):
                path = at(root, run["result"], exists=False)
                if path.exists():
                    if digest_bytes(path.read_bytes()) != run.get("result_sha256"):
                        raise ValueError("retained raw result hash mismatch: " + run["result"])
                else:
                    missing_raw.append(run["result"])
    regressions = []
    for row in rows:
        for metric, outcome in (row.get("analysis") or {}).get("metrics", {}).items():
            if outcome.get("guard_pass") is False:
                regressions.append({"evaluation": row["id"], "candidate": row.get("candidate"),
                                    "metric": metric, "advisory": outcome.get("advisory", False)})
    evaluation_rows = [r for r in rows if r.get("action") == "evaluate" and not r.get("comparison") and not r.get("measurement_reused")]
    fast = [r for r in evaluation_rows if r.get("status") == "FAST_PASS"]
    vetoes = []
    try:
        from reviews import blockers
        for item in candidates:
            vetoes += blockers(root, campaign, item)
    except ImportError:
        if list(directory.glob("reviews/*.json")):
            raise ValueError("review validator unavailable")
    if fast:
        verdict = "needs-review"
    elif evaluation_rows and all(r.get("status") in
            {"REGRESSION", "PROBE_REJECT", "CORRECTNESS_FAIL"} for r in evaluation_rows):
        verdict = "rejected"
    else:
        verdict = "inconclusive"
    summary = {"schema_version": 1, "campaign": campaign, "status": record["status"],
               "line": record["line"], "machine": record["machine"],
               "baseline_commit": protocol["baseline_commit"],
               "protocol_sha256": manifest[f"campaigns/{campaign}/protocol.json"],
               "verdict": verdict, "performance_accepted": False, "auto_promote": False,
               "budget": budget, "candidates": candidates, "evaluations": rows,
               "execution_closeout": read(directory / "ledger/session-closeout.json") if (directory / "ledger/session-closeout.json").is_file() else None,
               "regressions": regressions, "review_blockers": vetoes,
               "missing_raw_evidence": sorted(set(missing_raw)),
               "upstream_comparisons": [r for r in rows if r.get("comparison")],
               "evidence_reuse": [{"evaluation": r["id"], "source_evaluation_id": r.get("source_evaluation_id"),
                                   "measured_at": r.get("source_binding", {}).get("observed_unix", r.get("source_binding", {}).get("finished")),
                                   "reused_from": r.get("reused_from"),
                                   "independent_measurement": False}
                                  for r in rows if r.get("measurement_reused")],
               "sources": manifest}
    summary = public(summary, root)
    summary["evidence_sha256"] = digest(summary)
    return summary


def story_template(summary):
    """An agent fills explanations from patches; never invent a mechanism."""
    return {"schema_version": 1, "campaign": summary["campaign"],
            "evidence_sha256": summary["evidence_sha256"],
            "title": summary["campaign"],
            "headline": "Explain the decisive result and its cost.",
            "sections": [{"id": key, "title": title, "lead": "",
                          "evidence": [], "blocks": []}
                         for key, title in (("context", "Why this experiment"),
                                           ("system", "Where the cost appears"),
                                           ("subsystem", "The affected path"),
                                           ("changes", "What actually changed"),
                                           ("next", "The next decision"))]}


def validate_story(story, summary):
    if story.get("campaign") != summary["campaign"] or story.get("evidence_sha256") != summary["evidence_sha256"]:
        raise ValueError("explanation belongs to different or changed evidence")
    sections = story.get("sections", [])
    if [s.get("id") for s in sections] != ["context", "system", "subsystem", "changes", "next"]:
        raise ValueError("explanation needs context, system, subsystem, changes and next in order")
    for section in sections:
        refs = section.get("evidence")
        if not refs or any(ref not in summary["sources"] for ref in refs):
            raise ValueError("each explanatory section needs source references")
        if not section.get("blocks") or any(b.get("type") not in {"flow", "note"} for b in section["blocks"]):
            raise ValueError("use schematic flow/note blocks; numerical charts come from evidence")
        if section["id"] in {"system", "subsystem", "changes"} and not any(
                b.get("type") == "flow" for b in section["blocks"]):
            raise ValueError("the three explanation levels need a schematic")
    if not story.get("title") or not story.get("headline"):
        raise ValueError("missing report title or verdict explanation")
    for item in story.get("patches", []):
        if not isinstance(item, dict) or not item.get("takeaway") or not item.get("patch"):
            raise ValueError("each patch entry needs takeaway and patch diff")
        if item.get("source") not in summary["sources"] or not str(item.get("source", "")).endswith(".patch"):
            raise ValueError("each patch entry needs a pinned .patch source reference")


def _metric_sections(summary):
    blocks, paired, seen_cal = [], False, False
    for row in summary["evaluations"]:
        analysis = row.get("analysis") or {}
        if row.get("action") == "calibrate" and row.get("tier") == "probe" and not seen_cal:
            metric = "metadata_delta_bytes_per_capacity_slot"
            for case, bands in analysis.get("bands", {}).items():
                if metric not in bands:
                    continue
                runs = [run for run in row.get("runs", []) if run.get("case") == case
                        and run.get("status") == "PASS" and run.get("run_valid") is True
                        and metric in run.get("metrics", {})]
                if not runs:
                    continue
                groups = ["Run " + str(i + 1) for i in range(len(runs))]
                seen_cal = True
                blocks.append({"type": "strip", "takeaway": "Baseline metadata calibration: " + row["status"],
                    "x_label": "Metadata bytes per 1,000 capacity slots (baseline only)",
                    "groups": groups, "series": ["Baseline"],
                    "points": [{"group": group, "series": "Baseline", "value": 1000 * run["metrics"][metric],
                                "tip": run["id"]} for group, run in zip(groups, runs)],
                    "note": "Valid calibration samples; candidate performance was not measured here."})
        if row.get("action") != "evaluate":
            continue
        for metric in analysis.get("primary", []):
            points, groups = [], []
            for i, pair in enumerate(row.get("pairs", [])):
                if metric not in pair.get("a", {}) or metric not in pair.get("b", {}):
                    continue
                group = "Pair " + str(i + 1)
                groups.append(group)
                for arm, label in (("a", "Control"), ("b", "Treatment")):
                    points.append({"group": group, "series": label, "value": pair[arm][metric],
                                   "tip": row["id"]})
            if points:
                paired = True
                blocks.append({"type": "strip", "takeaway": str(row.get("candidate") or
                               row.get("comparison", {}).get("contrast_id", "Comparison")) + ": " + metric,
                               "x_label": metric + (" (reused measurement)" if row.get("measurement_reused") else " (new measurement)"), "groups": groups, "series": ["Control", "Treatment"],
                               "points": points})
    if not paired:
        blocks.append({"type": "note", "text": "No complete paired performance result is available."})
    return {"id": "results", "title": "Measured results", "blocks": blocks}


def format_unified_metadata(summary, story=None):
    """Format standardized metadata subtitle:
    <harness> (<model>) · line: <line> · base <short-sha> · <N> candidate · <G> guests / <B> build
    Never show hostnames like hurricpc or protocol jargon like rev7.
    """
    harness, model = "agy", "gemini4argon"
    if story and story.get("harness") and story.get("model"):
        harness, model = story["harness"], story["model"]
    elif summary.get("harness") and summary.get("model"):
        harness, model = summary["harness"], summary["model"]
    else:
        camp = (summary.get("campaign") or "").lower()
        if re.search(r"\bexp[1-5]\b", camp) or camp.startswith("exp"):
            harness, model = "agy", "gemini4argon"
        elif "codex" in camp:
            harness, model = "codex", "gpt-6-astra"
        elif "tcg-kbench" in camp or "rev7" in camp:
            harness, model = "grok-bot / claudecode", "opus5.5"
        elif any(d in camp for d in ("2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24")) or "xswap" in camp:
            harness, model = "claudecode", "opus5.5"

    line = (story and story.get("line")) or summary.get("line") or summary.get("campaign") or "unknown"
    line = re.sub(r"\bhurricpc(-wsl)?\b", "QEMU TCG", line, flags=re.I)
    base = (summary.get("baseline_commit") or "unknown")[:8]

    cands = len(summary.get("candidates", []))
    cand_label = f"{cands} candidate" if cands == 1 else f"{cands} candidates"

    budget = summary.get("budget", {})
    guests = budget.get("guests", 0) + budget.get("probe_guests", 0)
    builds = budget.get("builds", 0)
    build_label = f"{builds} build" if builds == 1 else f"{builds} builds"

    return f"{harness} ({model}) · line: {line} · base {base} · {cand_label} · {guests} guests / {build_label}"


def make_spec(summary, story):
    validate_story(story, summary)
    visible = []
    for row in summary["evaluations"]:
        if row.get("action") == "calibrate" and row.get("status") != "CALIBRATED":
            reasons = (row.get("analysis") or {}).get("reasons", [])
            visible.append("Calibration stopped performance comparison: " + "; ".join(reasons or [row["status"]]) + ".")
    intro = {"id": "limits", "title": "Material limits",
             "blocks": [{"type": "note", "text": " ".join(visible)}]}
    sections = [{k: v for k, v in s.items() if k != "evidence"} for s in story["sections"]]
    sections.insert(4, _metric_sections(summary))
    if visible:
        sections.insert(0, intro)
    rows = [[r["id"], r.get("candidate") or "control", r.get("tier", ""),
             r.get("status", ""), r.get("reason", "")] for r in summary["evaluations"]]
    guards = [[r["evaluation"], r["metric"], "advisory" if r["advisory"] else "scored", "failed"]
              for r in summary["regressions"]]
    if story.get("patches"):
        patch_sec = {"id": "patches", "title": story.get("patches_title") or "Core kernel patches",
                     "blocks": [{"type": "diff", "takeaway": item["takeaway"], "patch": item["patch"]}
                                for item in story["patches"]]}
        if story.get("patches_lead"):
            patch_sec["lead"] = story["patches_lead"]
        sections.append(patch_sec)
    sections.append({"id": "evidence", "title": "Evidence and exact results", "blocks": [
        {"type": "table", "takeaway": "Every retained outcome", "columns": ["ID", "Candidate", "Tier", "Status", "Reason"], "rows": rows},
        {"type": "table", "takeaway": "Regressions", "columns": ["Evaluation", "Metric", "Role", "Guard"], "rows": guards},
        {"type": "table", "takeaway": "Complexity and value decisions", "columns": ["Candidate", "Decision"],
         "rows": [[c["id"], json.dumps(c["value_decision"], sort_keys=True)] for c in summary["candidates"]]},
        {"type": "table", "takeaway": "Pinned sources", "columns": ["Source", "SHA256"], "rows": list(summary["sources"].items())}]})
    subtitle = format_unified_metadata(summary, story)
    res = {"title": story["title"], "subtitle": subtitle,
           "verdict": {"status": summary["verdict"], "headline": story["headline"],
                       "tiles": [{"label": "Evidence", "value": "Screen only" if any(r.get("action") == "evaluate" for r in summary["evaluations"]) else "No paired result", "note": "Human review controls promotion."}]},
           "sections": sections}
    if story:
        for key in ("date", "harness", "model", "line"):
            if story.get(key):
                res[key] = story[key]
    return res


def render(root, campaign):
    root = Path(root).resolve()
    directory = campaign_path(root, campaign)
    summary = extract(root, campaign)
    report = directory / "report"
    story = read(report / "story.json")
    spec = make_spec(summary, story)
    renderer = root / ".agents/skills/explaining-campaign-results/scripts/build_page.py"
    module_spec = importlib.util.spec_from_file_location("swap_report_renderer", renderer)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    page, budget = module.build(spec)
    if budget.errors:
        raise ValueError("; ".join(budget.errors))
    # Detail tables are preserved but closed by default in every viewport.
    page = page.replace('<section id="evidence">', '<details class="audit"><summary>Evidence and exact results</summary><section id="evidence">')
    page = page.replace("</section></main>", "</section></details></main>")
    page = page.replace("</style>", ".audit{overflow:auto}.audit table{min-width:600px}"
                        "@media(max-width:600px){main{padding:20px 12px}.card{padding:14px}"
                        ".verdict{flex-wrap:wrap}svg{min-width:600px}.card:has(svg){overflow-x:auto}}"
                        "</style>")
    # Optional public source links are pinned before report publication.
    source_commit = story.get("source_commit")
    if source_commit:
        if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
            raise ValueError("report sources need an exact Git commit")
        references = sorted(set(summary["sources"]) | set(story.get("reading", [])))
        links = []
        for ref in references:
            local = at(root, ref)
            if digest_bytes(_git(root, "show", source_commit + ":" + ref)) != digest_bytes(local.read_bytes()):
                raise ValueError("pinned report source differs from current evidence: " + ref)
            url = "https://github.com/ericzhang-zxh/Swap-Next/blob/" + source_commit + "/" + ref
            links.append('<li><a href="' + html.escape(url, quote=True) + '">' + html.escape(ref) + '</a></li>')
        source_links = '<details class="audit"><summary>Pinned sources and review</summary><ul>' + "".join(links) + '</ul></details>'
        page = page.replace("</main>", source_links + "</main>")
    write(report / "summary.json", summary)
    write(report / "explainer.json", spec)
    (report / "explainer.html").write_text(page)
    lines = ["# " + story["title"], "", "**" + summary["verdict"] + "** — " + story["headline"], ""]
    for section in story["sections"]:
        lines += ["## " + section["title"], "", section.get("lead", ""), ""]
        for block in section["blocks"]:
            if block["type"] == "note":
                lines += [block["text"], ""]
        lines += ["Evidence: " + ", ".join(section["evidence"]), ""]
    if story.get("patches"):
        lines += ["## " + (story.get("patches_title") or "Core kernel patches"), ""]
        if story.get("patches_lead"):
            lines += [story["patches_lead"], ""]
        for item in story["patches"]:
            lines += ["### " + item["takeaway"], "", "Source: `" + item["source"] + "`", "",
                      "```diff", item["patch"].rstrip(), "```", ""]
    lines += ["## Outcomes", "", "| Evaluation | Candidate | Tier | Result |",
              "| --- | --- | --- | --- |"]
    for row in summary["evaluations"]:
        lines += ["| " + " | ".join(str(row.get(k) or "").replace("|", "/").replace("\n", " ")
                                   for k in ("id", "candidate", "tier", "status")) + " |"]
    lines += ["", "## Limitations", "", "Screen evidence; candidate promotion remains human-controlled.",
              "Raw evidence missing on this machine: " + str(len(summary["missing_raw_evidence"])) + ".",
              "Upstream comparison rows: " + str(len(summary["upstream_comparisons"])) + ".",
              "Full outcomes, failed guards and complexity decisions are in summary.json.", "",
              "[Interactive explanation](explainer.html)", ""]
    (report / "REPORT.md").write_text("\n".join(lines))
    (report / "generate_report.py").write_text(
        "#!/usr/bin/env python3\n# SPDX-License-Identifier: GPL-2.0-only\n"
        "from pathlib import Path\nimport sys\n"
        "root = Path(__file__).resolve().parents[3]\n"
        "sys.path.insert(0, str(root / 'evolve'))\nfrom delivery import render\n"
        "render(root, Path(__file__).resolve().parents[1].name)\n")
    artifacts = {name: digest_bytes((report / name).read_bytes()) for name in OUTPUTS}
    previous = read(report / "delivery.json") if (report / "delivery.json").is_file() else {}
    if previous.get("evidence_sha256") == summary["evidence_sha256"] and previous.get("artifacts") == artifacts:
        return previous
    receipt = {"schema_version": 1, "campaign": campaign, "state": "generated",
               "evidence_sha256": summary["evidence_sha256"], "artifacts": artifacts,
               "story_sha256": digest_bytes((report / "story.json").read_bytes()),
               "history": previous.get("history", []) + [{"state": "generated", "time": time.time()}]}
    write(report / "delivery.json", receipt)
    return receipt


def status(root, campaign):
    directory = campaign_path(root, campaign)
    path = directory / "report/delivery.json"
    if not path.exists():
        return {"state": "pending", "reason": "report generation is pending"}
    receipt = read(path)
    try:
        if receipt.get("campaign") != campaign or receipt.get("evidence_sha256") != extract(root, campaign)["evidence_sha256"]:
            raise ValueError("report evidence changed")
        for name in OUTPUTS:
            art_file = directory / "report" / name
            if not art_file.exists():
                dated_matches = sorted((directory / "report").glob(f"{campaign}-*/{name}"))
                if dated_matches:
                    art_file = dated_matches[-1]
            if not art_file.exists():
                raise ValueError("missing report artifact: " + name)
            if digest_bytes(art_file.read_bytes()) != receipt.get("artifacts", {}).get(name):
                raise ValueError("report artifact changed: " + name)
        if digest_bytes((directory / "report/story.json").read_bytes()) != receipt.get("story_sha256"):
            raise ValueError("report explanation changed")
    except (ValueError, OSError) as exc:
        return {"state": "pending", "reason": str(exc)}
    return receipt


def record_visual_check(root, campaign, evidence):
    receipt = status(root, campaign)
    if receipt["state"] == "pending":
        raise ValueError("render a current report before visual verification")
    if evidence.get("artifact_sha256") != receipt["artifacts"]["explainer.html"]:
        raise ValueError("visual check is for another HTML artifact")
    seen = set()
    for view in evidence.get("views", []):
        width = view.get("width")
        if type(width) is not int or width < 320:
            raise ValueError("invalid visual viewport")
        theme = view.get("theme")
        if theme not in {"light", "dark"} or not all(view.get(k) is True for k in VISUAL_CHECKS):
            raise ValueError("visual checks are incomplete")
        path = at(root, view.get("screenshot", ""))
        if digest_bytes(path.read_bytes()) != view.get("sha256"):
            raise ValueError("screenshot hash mismatch")
        seen.add(("mobile" if width <= 480 else "desktop", theme))
    if not {("mobile", "light"), ("mobile", "dark"), ("desktop", "light"), ("desktop", "dark")} <= seen:
        raise ValueError("both themes and desktop/mobile views are required")
    receipt.update(state="visually_checked", visual_check=evidence)
    receipt["history"].append({"state": "visually_checked", "time": time.time()})
    write(campaign_path(root, campaign) / "report/delivery.json", receipt)
    return receipt


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def _fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache"}), timeout=20) as response:
        if response.status != 200:
            raise ValueError("live report is not HTTP 200")
        return response.read()


def verify_live(root, campaign, commit, run_id, *, fetch=None, github=None):
    """Read-only remote verification; publishing stays with the authorized agent."""
    fetch = fetch or _fetch
    receipt = status(root, campaign)
    if receipt["state"] not in {"visually_checked", "live_verified"}:
        raise ValueError("a current report needs visual verification before delivery")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not str(run_id).isdigit():
        raise ValueError("exact deployment commit and run ID required")
    slug = "ericzhang-zxh/Swap-Next"
    if github is None:
        github = lambda path: json.loads(subprocess.check_output(["gh", "api", path], cwd=root))
    run = github(f"repos/{slug}/actions/runs/{run_id}")
    if (run.get("head_sha") != commit or run.get("status") != "completed" or
            run.get("conclusion") != "success" or run.get("path") != ".github/workflows/pages.yml"):
        raise ValueError("Pages deployment is not successful for this exact commit")
    rel = f"campaigns/{campaign}/report/explainer.html"
    if not (campaign_path(root, campaign) / "report/explainer.html").is_file():
        dated = sorted((campaign_path(root, campaign) / "report").glob(f"{campaign}-*/explainer.html"))
        if dated:
            rel = dated[-1].relative_to(root).as_posix()
    expected = receipt["artifacts"]["explainer.html"]
    if digest_bytes(_git(root, "show", commit + ":" + rel)) != expected:
        raise ValueError("deployment commit does not contain the reviewed HTML")
    url = f"https://ericzhang-zxh.github.io/Swap-Next/{campaign}/"
    body = fetch(url)
    index = fetch("https://ericzhang-zxh.github.io/Swap-Next/")
    if digest_bytes(body) != expected:
        raise ValueError("live HTML differs from reviewed artifact")
    if ('href="' + html.escape(campaign) + '/"').encode() not in index and        ('href="' + html.escape(campaign) + '-').encode() not in index:
        raise ValueError("live index does not list this campaign")
    receipt.update(state="live_verified", publication={"commit": commit, "run_id": str(run_id), "url": url,
                   "html_sha256": expected, "index_sha256": digest_bytes(index), "verified_unix": time.time()})
    receipt["history"].append({"state": "live_verified", "time": time.time()})
    write(campaign_path(root, campaign) / "report/delivery.json", receipt)
    return receipt


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["extract", "story-template", "render", "status", "visual-check", "verify-live"])
    p.add_argument("--campaign", required=True)
    p.add_argument("--evidence", type=Path)
    p.add_argument("--commit")
    p.add_argument("--run-id")
    args = p.parse_args(argv)
    try:
        if args.action == "extract":
            out = extract(ROOT, args.campaign)
        elif args.action == "story-template":
            out = story_template(extract(ROOT, args.campaign))
        elif args.action == "render":
            out = render(ROOT, args.campaign)
        elif args.action == "status":
            out = status(ROOT, args.campaign)
        elif args.action == "visual-check":
            if not args.evidence:
                p.error("visual-check requires --evidence")
            out = record_visual_check(ROOT, args.campaign, read(args.evidence))
        else:
            out = verify_live(ROOT, args.campaign, args.commit or "", args.run_id or "")
        print(json.dumps(out, indent=2, allow_nan=False))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc))


if __name__ == "__main__":
    main()
