import json
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
RESULTS_PATH = REPO_ROOT / "eval" / "results_day3.json"

def image_path_for(label:dict) -> Path:
    stem = Path(label["filename"]).stem
    return IMAGES_DIR / f"{stem}.png"

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

def main()-> None:
    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))

    results = []
    for label in labels:
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
        "deadline_dates_accuracy": sum(r["deadline_dates_correct"] for r in results)/ n_total,
        "needs_human_review" : n_flagged,
        "false_confidence_rate": compute_false_confidence_rate(results),

    }
    output = {"summary": summary, "results": results}

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(summary,indent=2))
    print(f"\nfull results written to {RESULTS_PATH.relative_to(REPO_ROOT)}")

if __name__ == "__main__":
    main()