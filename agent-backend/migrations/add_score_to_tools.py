"""
为工具相关表添加 score 字段的迁移脚本：
- mcp_tools.score
- temporary_tools.score
- tool_configs.score
"""

from sqlalchemy import create_engine, text
import os

# 数据库连接配置（与 add_content_to_chat_messages 保持一致）
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chat_agent.db")


def _has_column_sqlite(conn, table: str, column: str) -> bool:
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    columns = [row[1] for row in result.fetchall()]
    return column in columns


def upgrade():
    """升级数据库结构：为工具表添加 score 字段"""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        try:
            # SQLite 分支
            if "sqlite" in DATABASE_URL:
                # mcp_tools.score
                if not _has_column_sqlite(conn, "mcp_tools", "score"):
                    conn.execute(
                        text(
                            """
                            ALTER TABLE mcp_tools
                            ADD COLUMN score REAL DEFAULT 3.0
                            """
                        )
                    )
                    print("✅ 已为 mcp_tools 表添加 score 字段")
                else:
                    print("ℹ️ mcp_tools.score 字段已存在，跳过")

                # temporary_tools.score
                if not _has_column_sqlite(conn, "temporary_tools", "score"):
                    conn.execute(
                        text(
                            """
                            ALTER TABLE temporary_tools
                            ADD COLUMN score REAL DEFAULT 3.0
                            """
                        )
                    )
                    print("✅ 已为 temporary_tools 表添加 score 字段")
                else:
                    print("ℹ️ temporary_tools.score 字段已存在，跳过")

                # tool_configs.score
                if not _has_column_sqlite(conn, "tool_configs", "score"):
                    conn.execute(
                        text(
                            """
                            ALTER TABLE tool_configs
                            ADD COLUMN score REAL DEFAULT 3.0
                            """
                        )
                    )
                    print("✅ 已为 tool_configs 表添加 score 字段")
                else:
                    print("ℹ️ tool_configs.score 字段已存在，跳过")
            else:
                # 其他数据库（Postgres 等），不做复杂兼容，简单尝试添加列
                for table in ("mcp_tools", "temporary_tools", "tool_configs"):
                    try:
                        conn.execute(
                            text(
                                f"""
                                ALTER TABLE {table}
                                ADD COLUMN score FLOAT DEFAULT 3.0
                                """
                            )
                        )
                        print(f"✅ 已为 {table} 表添加 score 字段")
                    except Exception as e:
                        # 如果字段已存在则忽略
                        msg = str(e).lower()
                        if "already exists" in msg or "duplicate column" in msg:
                            print(f"ℹ️ {table}.score 字段已存在，跳过")
                        else:
                            raise

            conn.commit()
        except Exception as e:
            print(f"❌ 添加 score 字段失败: {e}")
            return False

    return True


def downgrade():
    """回滚数据库结构（仅对非 SQLite 数据库尝试删除列）"""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        try:
            if "sqlite" in DATABASE_URL:
                print("⚠️ SQLite 不支持 DROP COLUMN，请手动处理 score 字段的回滚（如需）")
                return False

            for table in ("mcp_tools", "temporary_tools", "tool_configs"):
                try:
                    conn.execute(
                        text(
                            f"""
                            ALTER TABLE {table}
                            DROP COLUMN score
                            """
                        )
                    )
                    print(f"✅ 已从 {table} 表删除 score 字段")
                except Exception as e:
                    print(f"❌ 删除 {table}.score 字段失败: {e}")

            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 回滚 score 字段失败: {e}")
            return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "down":
        downgrade()
    else:
        upgrade()


