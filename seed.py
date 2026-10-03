"""演示数据初始化：python seed.py

幂等（先查后插），可重复执行。默认写入：
1 个 ADMIN（.env 注入）+ 1 个 ORGANIZER（org1/123456）+ 20 个 STUDENT（stu001~stu020/123456）；
3 个 PUBLISHED 活动（名额 10、截止 = 运行时刻 + 2 分钟），每个活动 20 条报名（前 15 人接受候补）。

改造成自己的项目时，替换下面的 DEMO_ACTIVITIES 与账号即可。
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal, create_all, utcnow
from app.models import Activity, ActivityStatus, Registration, RegistrationStatus, Role, User
from app.security import hash_password

DEMO_PASSWORD = "123456"

DEMO_ACTIVITIES = [
    ("技术分享会", "邀请讲师分享工程实践经验", "报告厅 A", 10),
    ("城市徒步", "5 公里健步走，完赛发放纪念品", "中心广场集合", 10),
    ("摄影采风", "外景拍摄，可借用器材", "南门集合", 10),
]


def ensure_user(db, username: str, real_name: str, role: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is not None:
        return user
    user = User(
        username=username,
        password_hash=hash_password(DEMO_PASSWORD),
        real_name=real_name,
        role=role,
        is_active=1,
    )
    db.add(user)
    db.flush()
    return user


def main() -> None:
    create_all()
    settings = get_settings()
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.username == settings.ADMIN_USERNAME))
        if admin is None:
            admin = User(
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                real_name="系统管理员",
                role=Role.ADMIN.value,
                is_active=1,
            )
            db.add(admin)
        else:
            admin.role = Role.ADMIN.value
            admin.is_active = 1

        organizer = ensure_user(db, "org1", "演示组织者", Role.ORGANIZER.value)
        members = [
            ensure_user(db, f"stu{i:03d}", f"成员{i:03d}", Role.STUDENT.value) for i in range(1, 21)
        ]
        db.flush()

        now = utcnow()
        for offset, (title, description, location, quota) in enumerate(DEMO_ACTIVITIES, start=1):
            if db.scalar(select(Activity).where(Activity.title == title)):
                continue
            activity = Activity(
                organizer_id=organizer.id,
                title=title,
                description=description,
                location=location,
                start_time=now + timedelta(days=1, hours=offset),
                end_time=now + timedelta(days=1, hours=offset + 2),
                signup_deadline=now + timedelta(minutes=2),
                quota=quota,
                status=ActivityStatus.PUBLISHED,
            )
            db.add(activity)
            db.flush()

            for index, member in enumerate(members):
                if db.scalar(
                    select(Registration).where(
                        Registration.activity_id == activity.id, Registration.user_id == member.id
                    )
                ):
                    continue
                db.add(
                    Registration(
                        activity_id=activity.id,
                        user_id=member.id,
                        status=RegistrationStatus.PENDING,
                        accept_waitlist=index < 15,
                    )
                )
        db.commit()
    finally:
        db.close()

    print(
        "演示数据就绪：\n"
        f"  管理员      {settings.ADMIN_USERNAME} / {settings.ADMIN_PASSWORD}\n"
        "  组织者      org1 / 123456\n"
        "  学生        stu001 ~ stu020 / 123456\n"
        "  活动        3 个（名额 10，报名截止 = 运行时刻 + 2 分钟，各 20 条报名）"
    )


if __name__ == "__main__":
    main()
