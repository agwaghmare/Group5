"""Account-owned educational coin grants; only server-graded quizzes award coins."""
from sqlalchemy import select

from app.orm.models import LearnReward
from app.staff.store import now

PASS_SCORE = 0.8


def summary(store):
    grants = store.db.scalars(select(LearnReward).where(LearnReward.user_id == store.user.id)
                             .order_by(LearnReward.earned_at.desc())).all()
    return {"currency": "FIN coins", "balance": sum(g.amount_tenths for g in grants) / 10,
            "per_lesson": 0.1, "pass_score": PASS_SCORE,
            "description": "In-app learning points. No cash value or SOL transfer.",
            "earned_lessons": [{"lesson_id": g.lesson_id, "amount": g.amount_tenths / 10,
                                "earned_at": g.earned_at} for g in grants]}


def award_quiz(store, lesson_id, correct, total):
    existing = store.db.get(LearnReward, (store.user.id, lesson_id))
    awarded = False
    if not existing and total > 0 and correct / total >= PASS_SCORE:
        store.db.add(LearnReward(user_id=store.user.id, lesson_id=lesson_id, amount_tenths=1, earned_at=now()))
        store.db.flush()
        store.audit("learn_reward_earned", lesson_id, amount_tenths=1)
        awarded = True
    return {**summary(store), "awarded": 0.1 if awarded else 0, "already_earned": existing is not None}
