"""数据完整性与性能验收。"""

from __future__ import annotations

import random
import time
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import utcnow
from app.models import Activity, ActivityStatus, Checkin, Registration, RegistrationStatus, User
from app.security import hash_password
from app.services.lottery import run_lottery
from helpers import close_signup, create_activity, create_students, make_user, user_id


def test_unique_activity_user_blocks_duplicate_rows(client, db):
    """UNIQUE(activity_id, user_id) 是并发下的最终防线。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"])
    (student,) = create_students(client, 1)
    uid = user_id(db, student["username"])

    db.add(Registration(activity_id=activity["id"], user_id=uid, status=RegistrationStatus.PENDING))
    db.commit()

    with pytest.raises(IntegrityError):
        db.add(Registration(activity_id=activity["id"], user_id=uid, status=RegistrationStatus.PENDING))
        db.commit()
    db.rollback()


def test_checkin_unique_registration_blocks_double_row(client, db):
    """checkins.registration_id UNIQUE 拦截重复签到。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=1)
    (student,) = create_students(client, 1)
    student_uid = user_id(db, student["username"])

    client.post(
        f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"]
    )
    close_signup(client, org["headers"], activity["id"])
    client.post(f"/api/activities/{activity['id']}/lottery", headers=org["headers"])

    registration = db.scalar(
        select(Registration).where(
            Registration.activity_id == activity["id"],
            Registration.status == RegistrationStatus.WON,
        )
    )
    assert registration is not None and registration.user_id == student_uid

    def add_checkin() -> None:
        db.add(
            Checkin(
                registration_id=registration.id,
                activity_id=activity["id"],
                user_id=registration.user_id,
                checked_in_at=utcnow(),
            )
        )
        db.commit()

    add_checkin()
    with pytest.raises(IntegrityError):
        add_checkin()
    db.rollback()


def test_lottery_is_reproducible_from_seed(client, db):
    """用 lottery_seed 重建 shuffle 可复现同一份名单。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=4)
    students = create_students(client, 10)
    for student in students:
        client.post(
            f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"]
        )
    close_signup(client, org["headers"], activity["id"])

    run_lottery(db, activity["id"])

    db.expire_all()
    row = db.get(Activity, activity["id"])
    assert row.status == ActivityStatus.LOTTERY_DONE and row.lottery_seed
    assert str(row.status) == "LOTTERY_DONE"

    ordered_ids = list(
        db.scalars(
            select(Registration.id)
            .where(Registration.activity_id == activity["id"])
            .order_by(Registration.id)
        ).all()
    )
    rebuilt = list(ordered_ids)
    random.Random(row.lottery_seed).shuffle(rebuilt)

    by_rank = list(
        db.scalars(
            select(Registration.id)
            .where(Registration.activity_id == activity["id"])
            .order_by(Registration.lottery_rank)
        ).all()
    )
    assert by_rank == rebuilt

    ranks = list(
        db.scalars(
            select(Registration.lottery_rank).where(Registration.activity_id == activity["id"])
        ).all()
    )
    assert len(ranks) == len(set(ranks)) == 10


def test_lottery_1000_registrations_under_one_second(client, db):
    """性能验收：1000 条报名抽签 < 1s。"""
    org = make_user(client, "org1", "ORGANIZER")
    now = utcnow()
    activity = Activity(
        organizer_id=user_id(db, "org1"),
        title="性能测试活动",
        location="线上",
        start_time=now + timedelta(days=2),
        signup_deadline=now - timedelta(minutes=1),
        quota=100,
        status=ActivityStatus.PUBLISHED,
    )
    db.add(activity)
    db.flush()

    same_hash = hash_password("123456")
    users = [
        User(
            username=f"perf{index:05d}",
            password_hash=same_hash,
            real_name=f"压测用户{index}",
            role="STUDENT",
            is_active=1,
            created_at=now,
            updated_at=now,
        )
        for index in range(1000)
    ]
    db.add_all(users)
    db.flush()
    db.add_all(
        [
            Registration(
                activity_id=activity.id,
                user_id=user.id,
                accept_waitlist=index % 2 == 0,
            )
            for index, user in enumerate(users)
        ]
    )
    db.commit()

    started = time.perf_counter()
    result = run_lottery(db, activity.id)
    elapsed = time.perf_counter() - started

    assert result["executed"] is True
    assert result["won"] == 100
    assert result["waiting"] + result["lost"] == 900
    assert elapsed < 1.0, f"抽签耗时 {elapsed:.3f}s 超过 1s"
