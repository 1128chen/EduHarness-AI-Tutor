##给 EduHarness 灌入一门"真实可演示"的种子课程：Python 程序设计入门。
##内容 = 章节知识点DAG(带先修) + 每知识点确定性短答两道 + 每章知识文档chunk，
##再加一套演示班级：教师账号、一门课、三名学生及其作答轨迹(故意制造弱知识点)。
##幂等：已存在 python 课程内容时直接报告现状并跳过，不会重复灌入。
##用法：
##    python -m eduharness.scripts.seed_python_course          # 灌入默认数据库
##    EDUHARNESS_DATABASE_URL=... python -m ...                # 指定数据库
from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import func, select

from eduharness.application.auth import hash_password
from eduharness.infrastructure.database import Database
from eduharness.infrastructure.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePoint,
    LearningAttempt,
    Question,
    QuestionKnowledgePoint,
)
from eduharness.infrastructure.repositories import EduRepository
from eduharness.settings import get_settings

SUBJECT = "python"
DEMO_TEACHER_USERNAME = "demo"
DEMO_TEACHER_PASSWORD = "demo1234"
DEMO_COURSE_NAME = "Python 程序设计入门"

##--------------------------------------------------------------------------
## 课程内容定义
##--------------------------------------------------------------------------
## 章节 -> 知识点列表；prerequisites 用知识点 code 表示（先修关系构成 DAG）
CHAPTERS: list[dict[str, Any]] = [
    {
        "title": "基础语法",
        "knowledge_points": [
            {
                "code": "python.ch1.hello",
                "name": "输出与注释",
                "description": "print 输出、单行/多行注释",
                "prerequisites": [],
            },
            {
                "code": "python.ch1.variables",
                "name": "变量与赋值",
                "description": "变量命名、= 赋值、type() 类型",
                "prerequisites": [],
            },
            {
                "code": "python.ch1.input",
                "name": "输入与类型转换",
                "description": "input() 返回字符串，需 int()/float() 转换",
                "prerequisites": ["python.ch1.variables"],
            },
        ],
    },
    {
        "title": "运算符与内建类型",
        "knowledge_points": [
            {
                "code": "python.ch2.numeric",
                "name": "数值与算术运算符",
                "description": "整型/浮点、+ - * / // % **",
                "prerequisites": ["python.ch1.variables"],
            },
            {
                "code": "python.ch2.string",
                "name": "字符串常用操作",
                "description": "拼接、len()、索引与切片入口",
                "prerequisites": ["python.ch1.variables"],
            },
            {
                "code": "python.ch2.bool",
                "name": "布尔与逻辑运算",
                "description": "== != < >、and or not",
                "prerequisites": ["python.ch2.numeric"],
            },
        ],
    },
    {
        "title": "流程控制",
        "knowledge_points": [
            {
                "code": "python.ch3.if",
                "name": "if/elif/else 分支",
                "description": "条件分支与缩进块",
                "prerequisites": ["python.ch2.bool"],
            },
            {
                "code": "python.ch3.for",
                "name": "for 循环与 range",
                "description": "遍历与 range() 序列",
                "prerequisites": ["python.ch2.bool"],
            },
            {
                "code": "python.ch3.while",
                "name": "while 与 break/continue",
                "description": "条件循环与跳转关键字",
                "prerequisites": ["python.ch3.if"],
            },
        ],
    },
    {
        "title": "函数",
        "knowledge_points": [
            {
                "code": "python.ch4.func",
                "name": "def 与 return",
                "description": "函数定义与返回值",
                "prerequisites": ["python.ch1.variables"],
            },
            {
                "code": "python.ch4.params",
                "name": "参数与默认值",
                "description": "位置/关键字参数、默认参数、*args",
                "prerequisites": ["python.ch4.func"],
            },
            {
                "code": "python.ch4.scope",
                "name": "作用域",
                "description": "局部/全局变量与 global 声明",
                "prerequisites": ["python.ch4.func"],
            },
        ],
    },
    {
        "title": "常用数据结构",
        "knowledge_points": [
            {
                "code": "python.ch5.list",
                "name": "列表常用方法",
                "description": "append/pop/sorted 等",
                "prerequisites": ["python.ch2.string"],
            },
            {
                "code": "python.ch5.dict",
                "name": "字典",
                "description": "键值对、d[key]、.get()",
                "prerequisites": ["python.ch5.list"],
            },
            {
                "code": "python.ch5.slice",
                "name": "切片",
                "description": "lst[start:stop:step] 负索引",
                "prerequisites": ["python.ch5.list"],
            },
        ],
    },
    {
        "title": "文件 / 异常 / 模块",
        "knowledge_points": [
            {
                "code": "python.ch6.file",
                "name": "文件读写",
                "description": "open() 与 with 语句、read()",
                "prerequisites": ["python.ch1.variables"],
            },
            {
                "code": "python.ch6.exception",
                "name": "异常处理",
                "description": "try/except 捕获运行时错误",
                "prerequisites": ["python.ch3.if"],
            },
            {
                "code": "python.ch6.module",
                "name": "模块导入",
                "description": "import / from ... import / as 别名",
                "prerequisites": ["python.ch4.func"],
            },
        ],
    },
]

##每知识点恰好两道确定性短答：(stem, answer, difficulty, explanation)
QUESTIONS_BY_KP: dict[str, list[tuple[str, str, float, str]]] = {
    "python.ch1.hello": [
        ("Python 中把内容输出到控制台的内置函数是？", "print", 0.2, "print() 是最常用的输出函数。"),
        ("Python 单行注释使用的符号是？", "#", 0.15, "以 # 开头到行尾为注释。"),
    ],
    "python.ch1.variables": [
        ("把数值 5 赋给变量 x 的语句是？", "x = 5", 0.25, "使用单个 = 赋值。"),
        ("返回变量 x 数据类型的函数是？", "type", 0.3, "type(x) 返回类型对象。"),
    ],
    "python.ch1.input": [
        ("读取用户键盘输入并返回字符串的内置函数是？", "input", 0.35, "input() 的结果默认是字符串。"),
        ("把字符串 '10' 转成整数的函数是？", "int", 0.3, "int('10') 得到整数 10。"),
    ],
    "python.ch2.numeric": [
        ("Python 中执行整除（向下取整）的运算符是？", "//", 0.35, "7 // 2 == 3。"),
        ("计算 x 的 y 次方使用的运算符是？", "**", 0.35, "2 ** 3 == 8。"),
    ],
    "python.ch2.string": [
        ("把两个字符串 a 和 b 拼接成一个字符串的运算符是？", "+", 0.3, "'a' + 'b' == 'ab'。"),
        ("返回字符串 s 字符个数的内置函数是？", "len", 0.35, "len(s) 返回长度。"),
    ],
    "python.ch2.bool": [
        ("判断 a 与 b 是否相等的比较运算符是？", "==", 0.25, "单个 = 是赋值，== 才是比较。"),
        ("Python 中表示逻辑'与'的关键字是？", "and", 0.3, "and / or / not 组成逻辑表达式。"),
    ],
    "python.ch3.if": [
        ("if 多分支判断中，对应'否则如果'的关键字是？", "elif", 0.35, "elif 是 else if 的缩写。"),
        ("'如果条件成立则执行分支'使用的语句关键字是？", "if", 0.2, "if 引导条件块。"),
    ],
    "python.ch3.for": [
        ("for 循环要生成 0 到 9 的整数序列，使用的内置函数是？", "range", 0.4, "range(10) 生成 0..9。"),
        ("循环中立即终止整个循环的关键字是？", "break", 0.3, "break 跳出当前循环。"),
    ],
    "python.ch3.while": [
        ("只要条件为真就反复执行循环体的关键字是？", "while", 0.3, "while 判断条件循环。"),
        ("循环体中跳过本次、进入下一次迭代的关键字是？", "continue", 0.35, "continue 结束本轮。"),
    ],
    "python.ch4.func": [
        ("Python 定义函数使用的关键字是？", "def", 0.3, "def 函数名(参数): 定义函数。"),
        ("函数把计算结果交还给调用者的关键字是？", "return", 0.25, "return 语句返回结果。"),
    ],
    "python.ch4.params": [
        ("函数定义 def f(a=1) 中，不传参调用 f() 时 a 的值是？", "1", 0.45, "默认参数缺省取 1。"),
        ("可变位置参数在形参前加的前缀符号是？", "*", 0.55, "def f(*args) 收集成元组。"),
    ],
    "python.ch4.scope": [
        ("函数内要修改全局变量 x，需先用哪个关键字声明？", "global", 0.5, "global x 声明为全局。"),
        ("只在函数体内可见的变量属于哪种作用域？", "local", 0.55, "函数内局部作用域。"),
    ],
    "python.ch5.list": [
        ("把列表 lst 排序并返回新列表的内置函数是？", "sorted", 0.5, "sorted(lst) 不改原列表。"),
        ("删除并返回列表 lst 末尾元素的方法名是？", "pop", 0.4, "lst.pop() 弹出末尾元素。"),
    ],
    "python.ch5.dict": [
        ("创建空字典使用的字面量写法是？", "{}", 0.35, "花括号空对即空字典。"),
        ("dict d 取键 'k'，键不存在时返回默认值而不报错的方法是？", "get", 0.45, "d.get('k') 安全取键。"),
    ],
    "python.ch5.slice": [
        ("取列表 lst 索引 0 到 1（不含 2）两个元素的切片写法是？", "lst[0:2]", 0.55, "lst[start:stop] 左闭右开。"),
        ("取列表 lst 最后三个元素的切片写法是？", "lst[-3:]", 0.6, "负索引从末尾倒数。"),
    ],
    "python.ch6.file": [
        ("Python 打开文件的内置函数是？", "open", 0.3, "open(path, mode) 返回文件对象。"),
        ("读取文件对象 fp 的全部内容到字符串的方法名是？", "read", 0.4, "fp.read() 读全量文本。"),
    ],
    "python.ch6.exception": [
        ("捕获可能抛出异常代码块的语句关键字是？", "try", 0.35, "try 包住可能出错的代码。"),
        ("捕获异常后处理异常的分支关键字是？", "except", 0.3, "except 分支处理错误。"),
    ],
    "python.ch6.module": [
        ("导入名为 math 的模块，使用的语句关键字是？", "import", 0.25, "import math 后可用 math.sqrt。"),
        ("给导入的模块起别名使用的关键字是？", "as", 0.35, "import math as m 之后用 m。"),
    ],
}

##每章一张知识文档，两条 chunk，收录该章关键结论供 agent 引用
DOC_SUMMARIES: list[tuple[str, list[str]]] = [
    (
        "Python 基础语法速览",
        [
            "print() 输出到控制台；# 开头是注释。变量用 = 赋值，命名须遵守标识符规则。",
            "input() 读入的都是字符串，需要运算前用 int()/float() 转型。",
        ],
    ),
    (
        "运算符与内建类型速览",
        [
            "整除用 //、乘方用 **；字符串可用 + 拼接、len() 求长度。",
            "比较用 == != < > 得到布尔值；and/or/not 组合逻辑。",
        ],
    ),
    (
        "流程控制速览",
        [
            "if/elif/else 按条件走分支；缩进决定代码块归属。",
            "for 通常配合 range() 遍历固定次数；while 依赖条件；break/continue 控制跳转。",
        ],
    ),
    (
        "函数速览",
        [
            "def 定义函数，return 返回值；调用即执行函数体。",
            "形参可带默认值；可变参数 *args 收集元组；函数内改全局变量要先 global 声明。",
        ],
    ),
    (
        "常用数据结构速览",
        [
            "列表可变有序：append/pop/sorted；列表从 0 开始索引。",
            "字典用键取值：d[key] 或 d.get(key)；切片 lst[start:stop:step] 左闭右开、支持负索引。",
        ],
    ),
    (
        "文件/异常/模块速览",
        [
            "open() 打开文件，推荐 with 语句自动释放；read() 读取内容。",
            "try/except 捕获运行时异常；import 引入模块，as 可起别名。",
        ],
    ),
]


##--------------------------------------------------------------------------
## 灌入逻辑
##--------------------------------------------------------------------------

async def _existing_python_counts(database: Database) -> tuple[int, int]:
    async with database.session_factory() as db:
        kp_count = int(
            (
                await db.execute(
                    select(func.count(KnowledgePoint.id)).where(
                        KnowledgePoint.subject == SUBJECT
                    )
                )
            ).scalar_one()
        )
        q_count = int(
            (
                await db.execute(
                    select(func.count(Question.id)).where(
                        Question.subject == SUBJECT
                    )
                )
            ).scalar_one()
        )
        return kp_count, q_count


async def _seed_content(database: Database) -> None:
    """知识点 + 题目 + 知识文档。返回后 code->kp.id 由调用方另行查询即可。"""
    async with database.session_factory() as db:
        for chapter in CHAPTERS:
            points = chapter["knowledge_points"]
            for point in points:
                db.add(
                    KnowledgePoint(
                        subject=SUBJECT,
                        code=point["code"],
                        name=point["name"],
                        description=point["description"],
                        prerequisites=point["prerequisites"],
                    )
                )
        await db.flush()

        # code -> id
        rows = (
            await db.execute(
                select(KnowledgePoint.code, KnowledgePoint.id).where(
                    KnowledgePoint.subject == SUBJECT
                )
            )
        ).all()
        code_to_id = {code: kp_id for code, kp_id in rows}

        for code, question_list in QUESTIONS_BY_KP.items():
            kp_id = code_to_id[code]
            for stem, answer, difficulty, explanation in question_list:
                question = Question(
                    subject=SUBJECT,
                    stem=stem,
                    question_type="short_answer",
                    difficulty=difficulty,
                    answer={"value": answer},
                    explanation=explanation,
                )
                db.add(question)
                await db.flush()
                db.add(
                    QuestionKnowledgePoint(
                        question_id=question.id,
                        knowledge_point_id=kp_id,
                        weight=1.0,
                    )
                )

        for idx, (title, chunk_texts) in enumerate(DOC_SUMMARIES):
            chapter_points = CHAPTERS[idx]["knowledge_points"]
            codes = [p["code"] for p in chapter_points]
            document = KnowledgeDocument(
                subject=SUBJECT,
                title=title,
                source_uri=f"seed://python-course/chapter-{idx + 1}",
            )
            db.add(document)
            await db.flush()
            for ordinal, text in enumerate(chunk_texts):
                db.add(
                    KnowledgeChunk(
                        document_id=document.id,
                        ordinal=ordinal,
                        content=text,
                        metadata_json={"knowledge_codes": codes},
                    )
                )

        await db.commit()


async def _seed_demo(
    repository: EduRepository,
    database: Database,
) -> None:
    """演示班级：教师 + 课程 + 3 名学生 + 合成作答轨迹。"""
    teacher = await repository.get_or_create_teacher(
        username=DEMO_TEACHER_USERNAME,
        password_hash=hash_password(DEMO_TEACHER_PASSWORD),
        display_name="王老师",
    )
    courses = await repository.list_teacher_courses(teacher.id)
    course = next(
        (c for c in courses if c["subject"] == SUBJECT),
        None,
    )
    if course is None:
        course_obj = await repository.create_course(
            teacher_id=teacher.id,
            name=DEMO_COURSE_NAME,
            subject=SUBJECT,
            description="种子演示课程：Python 程序设计入门",
        )
        course_id = course_obj.id
    else:
        course_id = course["id"]

    # 学生与作答模式
    demo_students = [
        ("demo.stu01", "小明"),
        ("demo.stu02", "小红"),
        ("demo.stu03", "小刚"),
    ]
    # (知识点code, 是否正确)：刻意让 func / for / slice 偏低
    attempt_pattern = [
        ("python.ch1.hello", True),
        ("python.ch1.variables", True),
        ("python.ch2.string", True),
        ("python.ch5.dict", True),
        ("python.ch4.func", False),
        ("python.ch4.func", False),
        ("python.ch3.for", False),
        ("python.ch3.for", False),
        ("python.ch5.slice", False),
    ]

    async with database.session_factory() as db:
        # 每知识点取第一道题的 id 用于作答
        question_rows = (
            await db.execute(
                select(
                    Question.id,
                    QuestionKnowledgePoint.knowledge_point_id,
                    Question.answer,
                )
                .join(
                    QuestionKnowledgePoint,
                    QuestionKnowledgePoint.question_id == Question.id,
                )
                .where(Question.subject == SUBJECT)
            )
        ).all()
        q_by_kp: dict[str, list[dict[str, Any]]] = {}
        for qid, kp_id, answer in question_rows:
            q_by_kp.setdefault(kp_id, []).append(
                {"id": qid, "answer": answer}
            )

        for external_id, display_name in demo_students:
            student = await repository.get_or_create_student(
                external_id, display_name
            )
            await repository.enroll_student(
                course_id=course_id,
                student_id=student.id,
            )

            # 幂等：该学生名下已有作答则跳过整段演示轨迹
            existing_attempts = int(
                (
                    await db.execute(
                        select(func.count()).select_from(
                            LearningAttempt
                        ).where(
                            LearningAttempt.student_id == student.id
                        )
                    )
                ).scalar_one()
            )
            if existing_attempts > 0:
                continue

            for ordinal, (code, correct) in enumerate(
                attempt_pattern
            ):
                kp_row = (
                    await db.execute(
                        select(KnowledgePoint.id).where(
                            KnowledgePoint.code == code,
                            KnowledgePoint.subject == SUBJECT,
                        )
                    )
                ).scalar_one()
                question = q_by_kp.get(kp_row)
                if not question:
                    continue
                chosen = question[ordinal % len(question)]
                wrong_answer = (
                    "不确定"
                    if correct
                    else ("错误答案" if ordinal % 2 == 0 else "记不清了")
                )
                # 通过 repository 走完整记录流程（含掌握度增量），保证演示轨迹与线上路径一致
                await repository.record_attempt(
                    student_id=student.id,
                    session_id=None,
                    turn_id=None,
                    question_id=chosen["id"],
                    answer=(
                        chosen["answer"]
                        if correct
                        else {"value": wrong_answer}
                    ),
                    score=1.0 if correct else 0.0,
                    max_score=1.0,
                    knowledge_evidence=[
                        {
                            "knowledge_point_id": kp_row,
                            "weight": 1.0,
                        }
                    ],
                    duration_seconds=8 + ordinal,
                )


async def main() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    await database.create_schema()
    repository = EduRepository(database.session_factory)

    kp_count, q_count = await _existing_python_counts(database)
    if kp_count or q_count:
        print(
            f"[seed] python 课程已存在，跳过内容灌入："
            f"{kp_count} 知识点 / {q_count} 题"
        )
    else:
        await _seed_content(database)
        kp_count, q_count = await _existing_python_counts(database)
        print(f"[seed] 课程内容已灌入：{kp_count} 知识点 / {q_count} 题")

    await _seed_demo(repository, database)

    # 覆盖指标
    async with database.session_factory() as db:
        docs = int(
            (
                await db.execute(
                    select(func.count(KnowledgeDocument.id)).where(
                        KnowledgeDocument.subject == SUBJECT
                    )
                )
            ).scalar_one()
        )
        chunks = int(
            (
                await db.execute(
                    select(func.count(KnowledgeChunk.id)).where(
                        KnowledgeChunk.document_id.in_(
                            select(KnowledgeDocument.id).where(
                                KnowledgeDocument.subject == SUBJECT
                            )
                        )
                    )
                )
            ).scalar_one()
        )
        per_kp = (
            await db.execute(
                select(
                    QuestionKnowledgePoint.knowledge_point_id,
                    func.count(QuestionKnowledgePoint.question_id),
                )
                .join(
                    Question,
                    Question.id
                    == QuestionKnowledgePoint.question_id,
                )
                .where(Question.subject == SUBJECT)
                .group_by(QuestionKnowledgePoint.knowledge_point_id)
            )
        ).all()
        counts = [int(count) for _, count in per_kp]

    students = [
        f"{external_id}({name})"
        for external_id, name in [
            ("demo.stu01", "小明"),
            ("demo.stu02", "小红"),
            ("demo.stu03", "小刚"),
        ]
    ]
    print(
        f"[seed] 演示班级就绪：教师 {DEMO_TEACHER_USERNAME} / "
        f"课程 {DEMO_COURSE_NAME} / 学生 {', '.join(students)}"
    )
    print(
        f"[seed] 覆盖指标：知识点 {len(counts)} | "
        f"每知识点题数 min={min(counts) if counts else 0} "
        f"max={max(counts) if counts else 0} "
        f"avg={sum(counts) / len(counts) if counts else 0:.1f} | "
        f"文档 {docs} 篇 / {chunks} 段"
    )
    await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
