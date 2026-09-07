from rq import Worker
from app.db import SessionLocal
from app.models import Extraction, Job, Letter
from app.pipeline.classify_extract import classify_and_extract
from app.pipeline.self_check import self_check
from app.queue import letter_queue, redis_conn


# this is the actual worker-> background job body. RQ enqueue()/dequeue() pickles whatver arguments you pass it to store job in redis.
def process_letter_job(letter_id: int) -> None:
    db = SessionLocal()
    try:
        letter = db.get(Letter, letter_id)
        job = db.query(Job).filter(Job.letter_id == letter_id).first()
        if letter is None or job is None:
            return
        job.status = "processing"
        db.commit()

        try:
            extraction = classify_and_extract(letter.image_path)
        except Exception as exc:
            job.status = "failed"
            job.error_message = repr(exc)
            db.commit()
            return
        needs_human_review = False
        self_check_note = None
        field_confidence = None
        review_reasoning = []
        try:
            check = self_check(letter.image_path, extraction)
            needs_human_review = check.needs_human_review
            field_confidence = {
                "authority": check.authority_confidence.value,
                "letter_type": check.letter_type_confidence.value,
                "deadlines": check.deadline_confidence.value,
                "required_actions": check.required_actions_confidence.value,
                "required_documents": check.required_documents_confidence.value,
                "consequences": check.consequences_confidence.value,
                "contact_info": check.contact_info_confidence.value,
            }
            review_reasoning = check.reasoning
        except Exception as exc:
            needs_human_review = True
            self_check_note = f"self_check failed, unverified:  {exc!r}"

        db.add(
            Extraction(
                letter_id=letter.id,
                authority=extraction.authority.value,
                letter_type=extraction.letter_type.value,
                deadlines=[d.model_dump(mode="json") for d in extraction.deadlines],
                required_actions=extraction.required_actions,
                required_documents=extraction.required_documents,
                consequences=extraction.consequences,
                contact_info=extraction.contact_info,
                needs_human_review=needs_human_review,
                confidence_flags=extraction.confidence_flags,
                field_confidence=field_confidence,
                review_reasoning=review_reasoning,
            )
        )
        job.status = "done"
        job.error_message = self_check_note
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    worker = Worker([letter_queue], connection=redis_conn)
    worker.work()
