"""建表脚本：python init_db.py（也可由 main lifespan 自动执行）。"""

from app.database import create_all


def main() -> None:
    create_all()
    print("数据表已创建：users / activities / registrations / checkins")


if __name__ == "__main__":
    main()
