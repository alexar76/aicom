"""
Feedback API
============
Endpoints for collecting, classifying, and routing user feedback.
Feedback is evaluated for usefulness, classified by type, and routed
to the appropriate agent (QA, PM, Marketing, etc.).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


# ── Classification taxonomy ─────────────────────────────────────────────────

FEEDBACK_CLASSES = {
    "bug": {
        "label": "Bug Report",
        "description": "Something is broken or not working correctly",
        "priority": 1,
        "route_to": "qa",
    },
    "feature_request": {
        "label": "Feature Request",
        "description": "User wants a new capability or improvement",
        "priority": 2,
        "route_to": "pm",
    },
    "praise": {
        "label": "Praise / Testimonial",
        "description": "Positive feedback, compliment, or testimonial",
        "priority": 4,
        "route_to": "marketing",
    },
    "question": {
        "label": "Question / Support",
        "description": "User has a question about the product",
        "priority": 3,
        "route_to": "general",
    },
    "garbage": {
        "label": "Garbage / Spam",
        "description": "Irrelevant, spam, nonsensical content",
        "priority": 5,
        "route_to": "discard",
    },
    "improvement": {
        "label": "Improvement Suggestion",
        "description": "Constructive suggestion that is not a feature request per se",
        "priority": 2,
        "route_to": "pm",
    },
}

# ── Models ──────────────────────────────────────────────────────────────────


class FeedbackSubmitRequest(BaseModel):
    product_id: str = Field(..., min_length=5, max_length=80)
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=1, max_length=4000)
    # Optional structured context (no PII)
    source: str = Field("product_page", max_length=40)  # product_page | widget | sandbox | other
    page_url: Optional[str] = Field(None, max_length=500)
    journey_step: Optional[str] = Field(None, max_length=80)  # onboarding | core_action | checkout | etc
    tags: list[str] = Field(default_factory=list, max_length=32)
    locale: Optional[str] = Field(None, max_length=16)
    session_id: Optional[str] = Field(None, max_length=80)
    # Optional contact (stored as hash only)
    contact_email: Optional[str] = Field(None, max_length=254)


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/submit")
async def submit_feedback(body: FeedbackSubmitRequest):
    """Submit feedback for a product.

    Feedback is automatically:
    1. Classified by type (bug, feature_request, praise, question, garbage, improvement)
    2. Scored for usefulness (0.0 – 1.0)
    3. Routed to the appropriate agent or discarded
    """
    feedback_id = f"fb-{uuid.uuid4().hex[:12]}"

    feedback = {
        "id": feedback_id,
        "product_id": body.product_id,
        "rating": body.rating,
        "comment": body.comment,
        "source": body.source,
        "page_url": body.page_url,
        "journey_step": body.journey_step,
        "tags": body.tags[:32],
        "locale": body.locale,
        "session_id": body.session_id,
        "status": "received",
        "created_at": time.time(),
    }
    if body.contact_email:
        norm = body.contact_email.strip().lower()
        feedback["contact_email_hash"] = hashlib.sha256(norm.encode("utf-8")).hexdigest()

    # Save raw feedback first
    feedback_dir = Path("/app/data/feedback")
    feedback_dir.mkdir(parents=True, exist_ok=True)

    with open(feedback_dir / f"{feedback_id}.json", "w", encoding="utf-8") as f:
        json.dump(feedback, f, indent=2, ensure_ascii=False)

    # Classify and evaluate
    classification = _classify_feedback(body.rating, body.comment)
    usefulness_score = _evaluate_usefulness(body.comment, classification)
    feedback["classification"] = classification
    feedback["usefulness_score"] = round(usefulness_score, 2)

    # Update saved file with classification
    with open(feedback_dir / f"{feedback_id}.json", "w", encoding="utf-8") as f:
        json.dump(feedback, f, indent=2, ensure_ascii=False)

    # Route based on classification
    route_result = _route_feedback(
        product_id=body.product_id,
        feedback_id=feedback_id,
        classification=classification,
        comment=body.comment,
    )

    logger.info(
        f"Feedback {feedback_id} received: rating={body.rating}, "
        f"class={classification}, usefulness={usefulness_score:.2f}, "
        f"routed_to={route_result['routed_to']}"
    )

    return {
        "feedback_id": feedback_id,
        "status": "received",
        "classification": classification,
        "usefulness_score": round(usefulness_score, 2),
        "routed_to": route_result["routed_to"],
        "message": _response_message(classification, usefulness_score),
    }


@router.get("/product/{product_id}")
async def get_product_feedback(product_id: str):
    """Get all feedback for a product, classified and scored."""
    feedback_dir = Path("/app/data/feedback")
    if not feedback_dir.exists():
        return {"feedback": [], "count": 0}

    feedback_list = []
    for fb_file in sorted(feedback_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(fb_file, "r") as f:
                fb = json.load(f)
            if fb.get("product_id") == product_id:
                feedback_list.append(fb)
        except Exception:
            pass

    ratings = [fb.get("rating", 0) for fb in feedback_list]
    avg_rating = sum(ratings) / max(len(ratings), 1) if ratings else 0

    return {
        "feedback": feedback_list,
        "count": len(feedback_list),
        "average_rating": round(avg_rating, 1),
    }


# ── Classification logic ────────────────────────────────────────────────────


def _classify_feedback(rating: int, comment: str) -> str:
    """Classify feedback using keyword scoring with multiple dimensions.

    Returns one of: bug, feature_request, praise, question, garbage, improvement
    """
    if not comment or not comment.strip():
        return "garbage"

    comment_lower = comment.lower().strip()

    # ── Score each class ──────────────────────────────────────────────────
    scores = {
        "bug": 0,
        "feature_request": 0,
        "praise": 0,
        "question": 0,
        "garbage": 0,
        "improvement": 0,
    }

    # Bug indicators
    bug_signals = [
        "bug", "error", "crash", "broken", "not working", "fail", "issue",
        "problem", "doesn't work", "does not work", "buggy", "glitch",
        "wrong", "incorrect", "fix", "repair", "error message",
        "exception", "stack trace", "typo", "missing", "failed",
    ]
    for kw in bug_signals:
        if kw in comment_lower:
            scores["bug"] += 3

    # Feature request indicators
    feature_signals = [
        "feature", "would like", "suggestion", "add", "wish",
        "could you", "please add", "i need", "would be great if",
        "it would be nice", "idea:", "propose", "enhancement",
        "request", "missing feature", "should have", "why not",
    ]
    for kw in feature_signals:
        if kw in comment_lower:
            scores["feature_request"] += 3

    # Improvement indicators
    improvement_signals = [
        "improve", "better", "optimize", "usability", "ux",
        "make it", "easier", "simplify", "redesign", "update",
        "refresh", "modernize", "clean up", "polish",
    ]
    for kw in improvement_signals:
        if kw in comment_lower:
            scores["improvement"] += 2

    # Praise indicators
    praise_signals = [
        "great", "awesome", "amazing", "love", "excellent",
        "fantastic", "wonderful", "best", "perfect", "nice",
        "good", "useful", "helpful", "thank", "thanks",
        "works great", "impressed", "brilliant", "superb",
    ]
    for kw in praise_signals:
        if kw in comment_lower:
            scores["praise"] += 2

    # Rating boost: high rating with praise keywords
    if rating >= 4:
        scores["praise"] += 1
    elif rating >= 3 and scores["praise"] > 0:
        scores["praise"] += 1

    # Question indicators
    question_signals = [
        "how", "what", "where", "when", "why", "which",
        "?", "how to", "does this", "can i", "is there",
        "explain", "tutorial", "guide", "help me",
    ]
    for kw in question_signals:
        if kw in comment_lower:
            scores["question"] += 2

    # Low rating with no specific bug keywords → likely bug
    if rating <= 2 and scores["bug"] == 0:
        scores["bug"] += 2

    # Garbage indicators
    if len(comment.strip()) < 3:
        scores["garbage"] += 10
    garbage_signals = [
        "asdf", "test", "spam", "click here", "buy now",
        "free money", "!!!", "???"
    ]
    for kw in garbage_signals:
        if kw in comment_lower:
            scores["garbage"] += 5

    # Empty or single-word comments
    if len(comment.split()) <= 1 and len(comment.strip()) < 10:
        scores["garbage"] += 3

    # Boost for questions that contain question marks
    if "?" in comment and scores["question"] > 0:
        scores["question"] += 1

    # ── Select best class ─────────────────────────────────────────────────
    best_class = max(scores, key=scores.get)
    best_score = scores[best_class]

    # If garbage is not clearly dominant but score is low, default to general
    if best_score == 0:
        return "improvement"

    # Spam/garbage needs high confidence
    if best_class == "garbage" and best_score < 8:
        # Fall through to next best
        scores["garbage"] = 0
        best_class = max(scores, key=scores.get)

    return best_class


def _evaluate_usefulness(comment: str, classification: str) -> float:
    """Score how useful the feedback is (0.0 – 1.0)."""
    if classification == "garbage":
        return 0.0

    score = 0.3  # baseline for any real feedback

    comment_stripped = comment.strip()

    # Longer, detailed comments are more useful
    word_count = len(comment_stripped.split())
    if word_count >= 20:
        score += 0.3
    elif word_count >= 10:
        score += 0.2
    elif word_count >= 5:
        score += 0.1

    # Contains specific technical terms → more useful
    technical_terms = [
        "api", "endpoint", "ui", "ux", "button", "page", "load",
        "speed", "price", "pricing", "integration", "sync",
        "login", "auth", "error", "code", "data", "export",
        "import", "config", "setting", "dashboard",
    ]
    for term in technical_terms:
        if term in comment_stripped.lower():
            score += 0.05
            break  # only bonus once

    # Contains specific reproduction steps → very useful
    if any(phrase in comment_stripped.lower() for phrase in ["step", "when i", "click", "scroll", "type"]):
        score += 0.2

    # Bug reports with error messages → extremely useful
    if classification == "bug" and any(kw in comment_stripped.lower() for kw in ["error", "exception", "instead of"]):
        score += 0.15

    # Feature requests with clear use-case
    if classification == "feature_request" and any(kw in comment_stripped.lower() for kw in ["because", "for", "use case"]):
        score += 0.1

    return min(score, 1.0)


def _route_feedback(product_id: str, feedback_id: str, classification: str, comment: str) -> dict:
    """Route feedback to the appropriate agent based on classification."""
    class_info = FEEDBACK_CLASSES.get(classification, FEEDBACK_CLASSES["improvement"])
    route_to = class_info["route_to"]
    result = {
        "routed_to": route_to,
        "action": None,
    }

    if classification == "bug":
        # Create a bug ticket for QA
        _create_bug_task(product_id, feedback_id, comment, route_to)
        result["action"] = "bug_task_created"
        logger.info(f"Feedback {feedback_id}: Bug task created for QA (product={product_id})")

    elif classification == "feature_request":
        # Create a feature suggestion for PM
        _create_feature_suggestion(product_id, feedback_id, comment)
        result["action"] = "feature_suggestion_created"
        logger.info(f"Feedback {feedback_id}: Feature suggestion created for PM (product={product_id})")

    elif classification == "praise":
        # Log for marketing — store in a dedicated file
        _log_praise(product_id, feedback_id, comment)
        result["action"] = "praise_logged"
        logger.info(f"Feedback {feedback_id}: Praise logged for marketing (product={product_id})")

    elif classification == "garbage":
        # Mark as discarded — no further action
        result["action"] = "discarded"
        logger.info(f"Feedback {feedback_id}: Discarded as garbage")

    elif classification == "question":
        # Log as support inquiry
        _log_question(product_id, feedback_id, comment)
        result["action"] = "question_logged"
        logger.info(f"Feedback {feedback_id}: Question logged for support (product={product_id})")

    else:  # improvement
        # Log for PM consideration
        _create_feature_suggestion(product_id, feedback_id, comment, is_improvement=True)
        result["action"] = "improvement_logged"
        logger.info(f"Feedback {feedback_id}: Improvement suggestion logged (product={product_id})")

    return result


def _response_message(classification: str, usefulness: float) -> str:
    """Generate a human-friendly response message based on classification."""
    messages = {
        "bug": "Thank you for reporting this issue. Our QA team will investigate and fix it.",
        "feature_request": "Thanks for your suggestion! Our product team will review it.",
        "praise": "Thank you so much! We're glad you're enjoying the product.",
        "question": "Thanks for reaching out. We'll get back to you with an answer.",
        "garbage": "Thank you for your feedback.",
        "improvement": "Thanks for the suggestion! We'll consider it for future improvements.",
    }
    msg = messages.get(classification, "Thank you for your feedback!")
    if usefulness >= 0.7:
        msg += " Your detailed feedback is especially valuable."
    return msg


# ── Action helpers ──────────────────────────────────────────────────────────


def _create_bug_task(product_id: str, feedback_id: str, description: str, route_to: str = "qa"):
    """Create a bug task that QA can pick up."""
    bug_data = {
        "id": f"bug-{uuid.uuid4().hex[:12]}",
        "product_id": product_id,
        "feedback_id": feedback_id,
        "description": description,
        "source": "user_feedback",
        "classification": "bug",
        "status": "open",
        "assigned_to": route_to,
        "created_at": time.time(),
    }

    bugs_dir = Path(f"/app/data/bugs/{product_id}")
    bugs_dir.mkdir(parents=True, exist_ok=True)

    with open(bugs_dir / f"feedback_bug_{feedback_id}.json", "w") as f:
        json.dump(bug_data, f, indent=2)


def _create_feature_suggestion(product_id: str, feedback_id: str, description: str, is_improvement: bool = False):
    """Create a feature suggestion document for PM review."""
    suggestion_dir = Path(f"/app/data/state/{product_id}")
    suggestion_dir.mkdir(parents=True, exist_ok=True)

    suggestion_file = suggestion_dir / "feedback_suggestions.json"
    suggestions = []
    if suggestion_file.exists():
        try:
            with open(suggestion_file) as f:
                suggestions = json.load(f)
        except Exception:
            pass

    suggestions.append({
        "id": f"sug-{uuid.uuid4().hex[:8]}",
        "feedback_id": feedback_id,
        "description": description,
        "type": "improvement" if is_improvement else "feature_request",
        "status": "pending_review",
        "created_at": time.time(),
    })

    # Keep only last 50
    suggestions = suggestions[-50:]

    with open(suggestion_file, "w") as f:
        json.dump(suggestions, f, indent=2)


def _log_praise(product_id: str, feedback_id: str, comment: str):
    """Log positive feedback for marketing use."""
    praise_dir = Path("/app/data/marketing")
    praise_dir.mkdir(parents=True, exist_ok=True)

    praise_file = praise_dir / "testimonials.json"
    testimonials = []
    if praise_file.exists():
        try:
            with open(praise_file) as f:
                testimonials = json.load(f)
        except Exception:
            pass

    testimonials.append({
        "id": f"test-{uuid.uuid4().hex[:8]}",
        "feedback_id": feedback_id,
        "product_id": product_id,
        "text": comment,
        "source": "user_feedback",
        "created_at": time.time(),
    })

    with open(praise_file, "w") as f:
        json.dump(testimonials, f, indent=2)


def _log_question(product_id: str, feedback_id: str, comment: str):
    """Log a support question for follow-up."""
    support_dir = Path("/app/data/support")
    support_dir.mkdir(parents=True, exist_ok=True)

    question_file = support_dir / "questions.jsonl"
    entry = json.dumps({
        "id": feedback_id,
        "product_id": product_id,
        "question": comment,
        "status": "unanswered",
        "created_at": time.time(),
    })

    with open(question_file, "a") as f:
        f.write(entry + "\n")
