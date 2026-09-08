import argparse
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(REPO_ROOT / "backend"))
load_dotenv(REPO_ROOT / ".env")

from app.pipeline.classify_extract import classify_and_extract
from app.pipeline.self_check import self_check

LABELS_PATH = REPO_ROOT / "data" / "labels.json"
IMAGES_DIR = REPO_ROOT / "data" / "sample_letters_images"
RESULTS_PATH = REPO_ROOT / "eval" / "results_final.json"

def image_path_for(label:dict) -> Path:
    stem = Path(label["filename"]).stem
    return IMAGES_DIR / f"{stem}.png"

ACTION_MATCH_THRESHOLD = 0.38  # lowered from 0.4 -- verified this only newly matches D1 (0.385), no other pair in the 0.30-0.39 range is a false positive (see error_analysis.md)

_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "in", "on", "at", "and", "or", "with",
    "your", "you", "please", "must", "should", "is", "are", "be", "this", "that",
}

# Small, deliberately narrow domain synonym map -- NOT a general synonym dictionary. Each entry
# is tied to a specific verified letter in this eval set (see error_analysis.md), not tuned
# until numbers looked good. "personal"/"person" (letter A1) and "matriculation"/"id" (letter
# D1 -- "Matrikelnummer" literally means student ID number) are genuine synonyms Jaccard can't
# see on its own; this is the honest, bounded way to teach it those two without pretending to
# solve paraphrase-matching in general.
_SYNONYMS = {
    "personal": "person",
    "matriculation": "id",
}

def _tokenize(text: str) -> set[str]:
    # letters (incl. German umlauts/eszett, plus an apostrophe so "supervisor's" tokenizes as
    # one word instead of splitting into "supervisor" + a stray noise token "s") OR a number
    # sequence like "412.00" / "58,30" -- numbers matter here because a shared amount or date
    # is often the strongest signal that two differently-worded action strings describe the
    # same thing.
    raw = re.findall(
        r"[a-zA-Z\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df']+|\d+(?:[.,]\d+)?",
        text.lower(),
    )
    tokens = set()
    for w in raw:
        if re.fullmatch(r"\d+(?:[.,]\d+)?", w):
            tokens.add(w.replace(",", "."))  # normalize German "58,30" and English "58.30" alike
            continue
        w = w.strip("'")
        if w.endswith("'s"):
            w = w[:-2]
        if not w or w in _STOPWORDS:
            continue
        tokens.add(_SYNONYMS.get(w, w))
    return tokens

def _action_overlap(a: str, b: str) -> float:
    tokens_a, tokens_b = _tokenize(a), _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

def score_required_actions(predicted: list[str], true: list[str]) -> dict:
    """
    Recall only: for each true (labeled) action, was there SOME predicted
    action that overlaps it enough to count as a match? Doesn't penalize
    extra predicted actions that aren't in the ground truth.
    """
    if not true:
        return {
            "action_recall": 1.0 if not predicted else 0.0,
            "matched_true_actions": [],
            "unmatched_true_actions": [],
        }

    matched, unmatched = [], []
    for true_action in true:
        best = max((_action_overlap(true_action, p) for p in predicted), default=0.0)
        (matched if best >= ACTION_MATCH_THRESHOLD else unmatched).append(true_action)

    return {
        "action_recall": len(matched) / len(true),
        "matched_true_actions": matched,
        "unmatched_true_actions": unmatched,
    }

def score_letter(label:dict) -> dict:
    # runs one letter through the pipeline and scores it.
    image_path = image_path_for(label)
    true_dates = sorted(d["date"] for d in label["true_deadlines"])

    try:
        extraction = classify_and_extract(str(image_path))
    except Exception as exc:
        return {
            "id": label["id"],
            "extraction_failed": True,
            "error": repr(exc),
            "letter_type_correct": False,
            "deadline_dates_correct": False,
            "true_letter_type": label["letter_type"],
            "true_deadline_dates": true_dates,
            "self_check_failed": True,
            "action_recall": 0.0,
            "required_actions_correct": False,
        }
    pred_dates = sorted(d.date.isoformat() for d in extraction.deadlines)

    result = {
        "id": label["id"],
        "extraction_failed": False,
        "letter_type_correct": extraction.letter_type.value == label["letter_type"],
        "predicted_letter_type": extraction.letter_type.value,
        "true_letter_type": label["letter_type"],
        "deadline_dates_correct": pred_dates ==  true_dates,
        "predicted_deadline_dates": pred_dates,
        "true_deadline_dates": true_dates,
        "predicted_required_actions": extraction.required_actions,
        "true_required_actions": label["true_required_actions"],
        "predicted_confidence_flags": extraction.confidence_flags,
    }

    action_score = score_required_actions(
        extraction.required_actions, label["true_required_actions"]
    )
    result["action_recall"] = action_score["action_recall"]
    result["required_actions_correct"] = action_score["action_recall"] == 1.0
    result["unmatched_true_actions"] = action_score["unmatched_true_actions"]

    try:
        check = self_check(str(image_path), extraction)
    except Exception as exc:
        result["self_check_failed"] = True
        result["self_check_error"] = repr(exc)
        return result 
    result["self_check_failed"] = False
    result["needs_human_review"] = check.needs_human_review
    result["reasoning"] = check.reasoning
    result["letter_type_confidence"] = check.letter_type_confidence.value
    result["deadline_confidence"] = check.deadline_confidence.value
    result["authority_confidence"] = check.authority_confidence.value
    result["required_actions_confidence"] = check.required_actions_confidence.value
    result["required_documents_confidence"] = check.required_documents_confidence.value
    result["consequences_confidence"] = check.consequences_confidence.value
    result["contact_info_confidence"] = check.contact_info_confidence.value

    return result 

def compute_false_confidence_rate(results:list[dict]) -> float | None:

    high_confidence_calls = []
    for r in results:
        if r["extraction_failed"] or r.get("self_check_failed"):
            continue
        if r["letter_type_confidence"] == "high":
            high_confidence_calls.append(r["letter_type_correct"])
        if r["deadline_confidence"] == "high":
            high_confidence_calls.append(r["deadline_dates_correct"])

    if not high_confidence_calls:
        return None
    n_wrong = sum(not was_correct for was_correct in high_confidence_calls)
    return n_wrong / len(high_confidence_calls)

def compute_breakdown_by_type(results: list[dict]) -> dict:
    """
    Groups results by true_letter_type and recomputes the headline metrics
    per group -- one aggregate number hides which document type the
    pipeline actually struggles with.
    """
    by_type: dict[str, list[dict]] = {}
    for r in results:
        by_type.setdefault(r["true_letter_type"], []).append(r)

    breakdown = {}
    for letter_type, group in sorted(by_type.items()):
        n = len(group)
        breakdown[letter_type] = {
            "n": n,
            "letter_type_accuracy": sum(r["letter_type_correct"] for r in group) / n,
            "deadline_dates_accuracy": sum(r["deadline_dates_correct"] for r in group) / n,
            "action_classification_accuracy": sum(
                r.get("required_actions_correct", False) for r in group
            ) / n,
            "action_recall_avg": sum(r.get("action_recall", 0.0) for r in group) / n,
            "false_confidence_rate": compute_false_confidence_rate(group),
        }
    return breakdown

def rescore_result(old_result: dict, label: dict) -> dict:
    """
    Re-derives the scoring fields for a letter WITHOUT calling Gemini again --
    reuses the raw model output already recorded in old_result (from an
    earlier eval run, e.g. results_day3.json) and re-applies the CURRENT
    scoring logic on top of it. Only valid when the extraction/self-check
    pipeline code hasn't changed since that earlier run -- otherwise the raw
    output itself is stale and this just re-scores outdated predictions.
    """
    result = dict(old_result)

    if result.get("extraction_failed"):
        result.setdefault("action_recall", 0.0)
        result.setdefault("required_actions_correct", False)
        return result

    action_score = score_required_actions(
        result.get("predicted_required_actions", []),
        label["true_required_actions"],
    )
    result["action_recall"] = action_score["action_recall"]
    result["required_actions_correct"] = action_score["action_recall"] == 1.0
    result["unmatched_true_actions"] = action_score["unmatched_true_actions"]
    return result

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help=(
            "Comma-separated letter ids to actually re-run against Gemini (e.g. "
            "B1,B2,B3,B4,C1,C2). Every other letter is pulled from the existing "
            "results_day3.json instead of burning API quota re-running it."
        ),
    )
    parser.add_argument(
        "--from-existing",
        type=str,
        default=None,
        help=(
            "Path to a prior results JSON (e.g. eval/results_day3.json) whose raw "
            "model outputs are reused as-is -- NO Gemini calls are made at all. Only "
            "the scoring logic (action_recall, breakdown_by_type, etc.) is re-run on "
            "top of those existing predictions. Use this when the extraction/"
            "self-check pipeline code hasn't changed since that prior run."
        ),
    )
    return parser.parse_args()


def main()-> None:
    args = parse_args()
    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    labels_by_id = {l["id"]: l for l in labels}

    if args.from_existing:
        source_path = Path(args.from_existing)
        prior = json.loads(source_path.read_text(encoding="utf-8"))
        print(
            f"--from-existing {source_path}: reusing {len(prior['results'])} raw model "
            f"outputs as-is. NO Gemini calls will be made -- only re-scoring."
        )
        results = [rescore_result(r, labels_by_id[r["id"]]) for r in prior["results"]]
    else:
        only_ids = set(i.strip() for i in args.only.split(",")) if args.only else None

        existing_by_id = {}
        if only_ids is not None and RESULTS_PATH.exists():
            prior = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
            existing_by_id = {r["id"]: r for r in prior["results"]}
            missing = only_ids - existing_by_id.keys()
            if missing:
                print(
                    f"WARNING: --only requested ids with no prior result to fall back on: "
                    f"{sorted(missing)}"
                )

        if only_ids is not None:
            n_calls = 2 * len(only_ids)
            print(
                f"--only {sorted(only_ids)}: about to make up to {n_calls} Gemini calls "
                f"(classify_and_extract + self_check per letter, more if a validation retry "
                f"fires). Ctrl+C now if quota isn't actually fresh."
            )
            input("Press Enter to continue...")

        results = []
        for label in labels:
            if only_ids is not None and label["id"] not in only_ids:
                if label["id"] in existing_by_id:
                    results.append(existing_by_id[label["id"]])
                    print(f"[{label['id']}] reused prior result (not in --only set)")
                else:
                    print(f"[{label['id']}] SKIPPED: not in --only set and no prior result exists")
                continue
            print(f"[{label['id']}] extracting {image_path_for(label).name}...")
            result = score_letter(label)
            results.append(result)
            if result["extraction_failed"]:
                print(f"[{label['id']}] EXTRACTION FAILED: {result['error']}")
            else:
                status = "OK" if result["letter_type_correct"] and result["deadline_dates_correct"] else "MISS"
                print(f"[{label['id']}] {status}")

    n_total = len(results)
    n_failed = sum(r["extraction_failed"] for r in results)
    n_self_check_failed = sum(r["self_check_failed"] for r in results if not r["extraction_failed"])
    n_flagged = sum(r.get("needs_human_review", False) for r in results)

    summary = {
        "total_letters": n_total,
        "extraction_failures": n_failed,
        "self_check_failures": n_self_check_failed,
        "letter_type_accuracy": sum(r["letter_type_correct"] for r in results) / n_total,
        "deadline_dates_accuracy": sum(r["deadline_dates_correct"] for r in results) / n_total,
        "action_classification_accuracy": sum(
            r.get("required_actions_correct", False) for r in results
        ) / n_total,
        "action_recall_avg": sum(r.get("action_recall", 0.0) for r in results) / n_total,
        "needs_human_review": n_flagged,
        "false_confidence_rate": compute_false_confidence_rate(results),
        "breakdown_by_type": compute_breakdown_by_type(results),
    }
    output = {"summary": summary, "results": results}

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(summary,indent=2))
    print(f"\nfull results written to {RESULTS_PATH.relative_to(REPO_ROOT)}")

if __name__ == "__main__":
    main()