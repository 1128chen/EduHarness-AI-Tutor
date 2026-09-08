from __future__ import annotations

import argparse
import asyncio
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy import select

from eduharness.infrastructure.database import Database
from eduharness.infrastructure.models import (
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
)
from eduharness.settings import get_settings


@dataclass(frozen=True)
class GeneratedQuestion:
    subject: str
    stem: str
    question_type: str
    difficulty: float
    answer: dict[str, str]
    explanation: str
    knowledge_point_code: str

TOPIC_SPECS = [
    ("chinese.vocabulary.synonym", "chinese", "近义词"),
    ("chinese.vocabulary.antonym", "chinese", "反义词"),
    ("math.algebra.linear_equation", "math", "一元一次方程"),
    ("math.calculus.power_derivative", "math", "幂函数求导"),
    ("english.grammar.subject_verb_agreement", "english", "主谓一致"),
    ("english.grammar.irregular_past", "english", "不规则动词过去式"),
    ("physics.mechanics.speed", "physics", "速度路程时间"),
    ("physics.electricity.ohms_law", "physics", "欧姆定律"),
    ("chemistry.formula.atom_count", "chemistry", "化学式原子计数"),
    ("chemistry.amount.molar_mass", "chemistry", "摩尔质量"),
    ("biology.genetics.dna_pairing", "biology", "DNA碱基互补"),
    ("biology.ecology.energy_transfer", "biology", "生态能量传递"),
    ("history.calendar.century", "history", "年份与世纪"),
    ("history.calendar.elapsed_years", "history", "年代间隔"),
    ("geography.longitude.time_difference", "geography", "经度时差"),
    ("geography.map.scale", "geography", "地图比例尺"),
    ("computer.binary.to_decimal", "computer_science", "二进制转十进制"),
    ("computer.logic.boolean", "computer_science", "布尔逻辑"),
    ("economics.finance.simple_interest", "economics", "单利计算"),
    ("economics.market.discount", "economics", "折扣计算"),
]

KNOWLEDGE_POINTS = {
    code: {
        "subject": subject,
        "name": name,
        "description": f"{name}相关的基础概念与应用题。",
        "prerequisites": [],
    }
    for code, subject, name in TOPIC_SPECS
}



def format_linear_left(a: int, b: int) -> str:
    if a == 1:
        result = "x"
    elif a == -1:
        result = "-x"
    else:
        result = f"{a}x"

    if b > 0:
        result += f" + {b}"
    elif b < 0:
        result += f" - {abs(b)}"

    return result


def make_mcq(
    rng: random.Random,
    *,
    subject: str,
    prompt: str,
    correct: str,
    distractors: list[str],
    difficulty: float,
    explanation: str,
    knowledge_point_code: str,
) -> GeneratedQuestion:
    candidates = list(
        dict.fromkeys(
            value
            for value in distractors
            if value != correct
        )
    )

    if len(candidates) < 3:
        raise ValueError("选择题干扰项不足3个")

    options = [correct, *rng.sample(candidates, 3)]
    rng.shuffle(options)

    letters = ["A", "B", "C", "D"]
    correct_letter = letters[options.index(correct)]

    option_text = "\n".join(
        f"{letter}. {value}"
        for letter, value in zip(letters, options)
    )

    return GeneratedQuestion(
        subject=subject,
        stem=f"{prompt}\n{option_text}",
        question_type="multiple_choice",
        difficulty=difficulty,
        answer={"value": correct_letter},
        explanation=(
            f"正确选项是{correct_letter}。{explanation}"
        ),
        knowledge_point_code=knowledge_point_code,
    )


def unique_questions(
    count: int,
    factory: Callable[[], GeneratedQuestion],
) -> list[GeneratedQuestion]:
    result: list[GeneratedQuestion] = []
    stems: set[str] = set()
    attempts = 0

    while len(result) < count:
        attempts += 1

        if attempts > count * 200:
            raise RuntimeError("无法生成足够多的不重复题目")

        question = factory()

        if question.stem in stems:
            continue

        stems.add(question.stem)
        result.append(question)

    return result


def generate_math(
    rng: random.Random,
    count: int,
) -> list[GeneratedQuestion]:
    def factory() -> GeneratedQuestion:
        x = rng.randint(-20, 20)
        a = rng.choice(
            [value for value in range(-9, 10) if value != 0]
        )
        b = rng.randint(-30, 30)
        c = a * x + b
        left = format_linear_left(a, b)

        return GeneratedQuestion(
            subject="math",
            stem=f"解方程：{left} = {c}。只填写x的值。",
            question_type="short_answer",
            difficulty=round(rng.uniform(0.25, 0.65), 2),
            answer={"value": str(x)},
            explanation=(
                f"先将常数项移到等号右边，再除以"
                f"x的系数{a}，得到x = {x}。"
            ),
            knowledge_point_code=(
                "math.algebra.linear_equation"
            ),
        )

    return unique_questions(count, factory)


def generate_physics(
    rng: random.Random,
    count: int,
) -> list[GeneratedQuestion]:
    def factory() -> GeneratedQuestion:
        speed = rng.randint(4, 120)
        time = rng.randint(2, 12)
        distance = speed * time
        mode = rng.choice(["speed", "distance", "time"])

        if mode == "speed":
            stem = (
                f"某物体在{time}小时内行驶{distance}千米，"
                "平均速度是多少千米每小时？只填写数字。"
            )
            answer = speed
            explanation = (
                f"速度 = 路程 ÷ 时间 = "
                f"{distance} ÷ {time} = {speed}。"
            )
        elif mode == "distance":
            stem = (
                f"某物体以每小时{speed}千米的速度行驶"
                f"{time}小时，路程是多少千米？只填写数字。"
            )
            answer = distance
            explanation = (
                f"路程 = 速度 × 时间 = "
                f"{speed} × {time} = {distance}。"
            )
        else:
            stem = (
                f"某物体以每小时{speed}千米的速度行驶"
                f"{distance}千米，需要多少小时？只填写数字。"
            )
            answer = time
            explanation = (
                f"时间 = 路程 ÷ 速度 = "
                f"{distance} ÷ {speed} = {time}。"
            )

        return GeneratedQuestion(
            subject="physics",
            stem=stem,
            question_type="short_answer",
            difficulty=round(rng.uniform(0.2, 0.55), 2),
            answer={"value": str(answer)},
            explanation=explanation,
            knowledge_point_code="physics.mechanics.speed",
        )

    return unique_questions(count, factory)


CHEMISTRY_FACTS = [
    ("H2O", "H", 2),
    ("H2O", "O", 1),
    ("CO2", "O", 2),
    ("CO2", "C", 1),
    ("NH3", "H", 3),
    ("NH3", "N", 1),
    ("CH4", "H", 4),
    ("CH4", "C", 1),
    ("O2", "O", 2),
    ("N2", "N", 2),
    ("H2", "H", 2),
    ("SO2", "O", 2),
    ("SO3", "O", 3),
    ("H2S", "H", 2),
    ("NO2", "O", 2),
]


def generate_chemistry(
    rng: random.Random,
    count: int,
) -> list[GeneratedQuestion]:
    def factory() -> GeneratedQuestion:
        formula, element, per_molecule = rng.choice(
            CHEMISTRY_FACTS
        )
        molecules = rng.randint(2, 20)
        total = molecules * per_molecule

        return GeneratedQuestion(
            subject="chemistry",
            stem=(
                f"{molecules}个{formula}分子中一共有多少个"
                f"{element}原子？只填写数字。"
            ),
            question_type="short_answer",
            difficulty=round(rng.uniform(0.2, 0.5), 2),
            answer={"value": str(total)},
            explanation=(
                f"每个{formula}分子含有{per_molecule}个"
                f"{element}原子，因此总数为"
                f"{molecules} × {per_molecule} = {total}。"
            ),
            knowledge_point_code=(
                "chemistry.formula.atom_count"
            ),
        )

    return unique_questions(count, factory)


ENGLISH_SUBJECTS = [
    ("He", True),
    ("She", True),
    ("Tom", True),
    ("My teacher", True),
    ("The student", True),
    ("They", False),
    ("We", False),
    ("The students", False),
    ("Tom and Amy", False),
    ("My friends", False),
]

ENGLISH_VERBS = [
    ("go", "goes"),
    ("study", "studies"),
    ("play", "plays"),
    ("read", "reads"),
    ("write", "writes"),
    ("watch", "watches"),
    ("teach", "teaches"),
    ("work", "works"),
    ("run", "runs"),
    ("eat", "eats"),
]


def generate_english(
    rng: random.Random,
    count: int,
) -> list[GeneratedQuestion]:
    combinations = [
        (subject, singular, base, third)
        for subject, singular in ENGLISH_SUBJECTS
        for base, third in ENGLISH_VERBS
    ]
    rng.shuffle(combinations)

    questions = []

    for subject, singular, base, third in combinations[:count]:
        correct = third if singular else base
        wrong = base if singular else third

        questions.append(
            make_mcq(
                rng,
                subject="english",
                prompt=(
                    f"选择正确单词补全句子："
                    f"{subject} ___ English every day."
                ),
                correct=correct,
                distractors=[
                    wrong,
                    f"is {base}",
                    f"are {base}",
                    f"to {base}",
                ],
                difficulty=round(
                    rng.uniform(0.2, 0.55),
                    2,
                ),
                explanation=(
                    "一般现在时中，第三人称单数主语使用"
                    "动词第三人称单数形式；其他复数主语使用原形。"
                ),
                knowledge_point_code=(
                    "english.grammar.subject_verb_agreement"
                ),
            )
        )

    return questions


def generate_computer_science(
    rng: random.Random,
    count: int,
) -> list[GeneratedQuestion]:
    values = rng.sample(range(5, 256), count)

    return [
        GeneratedQuestion(
            subject="computer_science",
            stem=(
                f"将二进制数{value:b}转换为十进制数。"
                "只填写十进制数字。"
            ),
            question_type="short_answer",
            difficulty=round(rng.uniform(0.25, 0.65), 2),
            answer={"value": str(value)},
            explanation=(
                f"按照二进制位权展开，"
                f"{value:b}的十进制值是{value}。"
            ),
            knowledge_point_code="computer.binary.to_decimal",
        )
        for value in values
    ]


def generate_geography(
    rng: random.Random,
    count: int,
) -> list[GeneratedQuestion]:
    def factory() -> GeneratedQuestion:
        longitude_a = rng.randrange(0, 121, 15)
        longitude_b = rng.randrange(15, 181, 15)

        if longitude_a == longitude_b:
            longitude_b += 15

        difference = abs(longitude_b - longitude_a) // 15

        return GeneratedQuestion(
            subject="geography",
            stem=(
                f"A地位于东经{longitude_a}度，"
                f"B地位于东经{longitude_b}度。"
                "按照经度每相差15度约相差1小时计算，"
                "两地时差约为多少小时？只填写数字。"
            ),
            question_type="short_answer",
            difficulty=round(rng.uniform(0.3, 0.6), 2),
            answer={"value": str(difference)},
            explanation=(
                f"经度差为{abs(longitude_b - longitude_a)}度，"
                f"除以15得到{difference}小时。"
            ),
            knowledge_point_code=(
                "geography.longitude.time_difference"
            ),
        )

    return unique_questions(count, factory)


def generate_history(
    rng: random.Random,
    count: int,
) -> list[GeneratedQuestion]:
    years = rng.sample(range(101, 2001), count)

    return [
        GeneratedQuestion(
            subject="history",
            stem=(
                f"公元{year}年属于第几世纪？"
                "只填写阿拉伯数字。"
            ),
            question_type="short_answer",
            difficulty=round(rng.uniform(0.2, 0.45), 2),
            answer={
                "value": str((year - 1) // 100 + 1)
            },
            explanation=(
                f"用年份减1后除以100，再加1，"
                f"得到第{(year - 1) // 100 + 1}世纪。"
            ),
            knowledge_point_code="history.calendar.century",
        )
        for year in years
    ]

SYNONYM_PAIRS = [
    ("美丽", "漂亮"), ("著名", "有名"), ("迅速", "快速"),
    ("安静", "宁静"), ("高兴", "快乐"), ("坚固", "牢固"),
    ("珍贵", "宝贵"), ("宽广", "广阔"), ("观察", "察看"),
    ("困难", "艰难"), ("温暖", "暖和"), ("寒冷", "冰冷"),
    ("疲劳", "疲倦"), ("惊讶", "吃惊"), ("清楚", "明白"),
    ("保护", "爱护"), ("希望", "期望"), ("特别", "特殊"),
    ("赞扬", "表扬"), ("忽然", "突然"), ("仿佛", "好像"),
    ("聚集", "集合"), ("减少", "降低"), ("增加", "增添"),
    ("寻找", "查找"),
]

ANTONYM_PAIRS = [
    ("高", "低"), ("大", "小"), ("快", "慢"), ("远", "近"),
    ("冷", "热"), ("明", "暗"), ("开", "关"), ("早", "晚"),
    ("成功", "失败"), ("前进", "后退"), ("增加", "减少"),
    ("安全", "危险"), ("安静", "喧闹"), ("简单", "复杂"),
    ("坚强", "软弱"), ("诚实", "虚伪"), ("宽广", "狭窄"),
    ("清楚", "模糊"), ("赞成", "反对"), ("保护", "破坏"),
    ("积极", "消极"), ("熟悉", "陌生"), ("温暖", "寒冷"),
    ("认真", "马虎"), ("珍贵", "普通"),
]

IRREGULAR_VERBS = [
    ("go", "went"), ("see", "saw"), ("eat", "ate"),
    ("write", "wrote"), ("take", "took"), ("come", "came"),
    ("give", "gave"), ("speak", "spoke"), ("begin", "began"),
    ("drink", "drank"), ("sing", "sang"), ("run", "ran"),
    ("buy", "bought"), ("bring", "brought"), ("think", "thought"),
    ("teach", "taught"), ("catch", "caught"), ("find", "found"),
    ("make", "made"), ("have", "had"), ("do", "did"),
    ("get", "got"), ("know", "knew"), ("leave", "left"),
    ("feel", "felt"),
]

SUBJECT_VERBS = [
    ("He", "go", "goes"), ("She", "study", "studies"),
    ("Tom", "play", "plays"), ("My teacher", "teach", "teaches"),
    ("The student", "read", "reads"), ("They", "work", "works"),
    ("We", "write", "writes"), ("The students", "run", "runs"),
    ("Tom and Amy", "watch", "watches"), ("My friends", "eat", "eats"),
]

CHEMISTRY_ATOMS = [
    ("H2O", "H", 2), ("H2O", "O", 1), ("CO2", "O", 2),
    ("CO2", "C", 1), ("NH3", "H", 3), ("NH3", "N", 1),
    ("CH4", "H", 4), ("CH4", "C", 1), ("SO2", "O", 2),
    ("SO3", "O", 3), ("NO2", "O", 2), ("O2", "O", 2),
]

MOLAR_MASSES = [
    ("H2", 2), ("O2", 32), ("N2", 28), ("H2O", 18),
    ("CO2", 44), ("CH4", 16), ("NH3", 17), ("NaCl", 58.5),
    ("CaCO3", 100), ("SO2", 64),
]

def generate_topic_question(
    rng: random.Random,
    code: str,
    index: int,
) -> GeneratedQuestion:
    if code == "chinese.vocabulary.synonym":
        word, correct = SYNONYM_PAIRS[index]
        distractors = [
            value for _, value in SYNONYM_PAIRS
            if value != correct
        ]
        return make_mcq(
            rng,
            subject="chinese",
            prompt=f"选择“{word}”的近义词。",
            correct=correct,
            distractors=distractors,
            difficulty=0.25,
            explanation=f"“{word}”与“{correct}”意义相近。",
            knowledge_point_code=code,
        )

    if code == "chinese.vocabulary.antonym":
        word, correct = ANTONYM_PAIRS[index]
        distractors = [
            value for _, value in ANTONYM_PAIRS
            if value != correct
        ]
        return make_mcq(
            rng,
            subject="chinese",
            prompt=f"选择“{word}”的反义词。",
            correct=correct,
            distractors=distractors,
            difficulty=0.25,
            explanation=f"“{word}”与“{correct}”意义相反。",
            knowledge_point_code=code,
        )

    if code == "math.algebra.linear_equation":
        x = index - 12
        a = index % 8 + 2
        b = index * 3 % 29 - 14
        c = a * x + b
        left = format_linear_left(a, b)
        return GeneratedQuestion(
            subject="math",
            stem=f"解方程：{left} = {c}。只填写x的值。",
            question_type="short_answer",
            difficulty=round(0.3 + index / 100, 2),
            answer={"value": str(x)},
            explanation=f"移项并除以{a}，得到x = {x}。",
            knowledge_point_code=code,
        )

    if code == "math.calculus.power_derivative":
        coefficient = index % 7 + 1
        exponent = index % 5 + 1
        result_coefficient = coefficient * exponent
        result_exponent = exponent - 1

        if result_exponent == 0:
            answer = str(result_coefficient)
        elif result_exponent == 1:
            answer = f"{result_coefficient}x"
        else:
            answer = f"{result_coefficient}x^{result_exponent}"

        return GeneratedQuestion(
            subject="math",
            stem=(
                f"求函数f(x) = {coefficient}x^{exponent}的导数。"
                "使用普通文本填写。"
            ),
            question_type="short_answer",
            difficulty=round(0.45 + index / 200, 2),
            answer={"value": answer},
            explanation=(
                f"使用幂函数求导法则，得到f'(x) = {answer}。"
            ),
            knowledge_point_code=code,
        )

    if code == "english.grammar.subject_verb_agreement":
        subject, base, third = SUBJECT_VERBS[
            index % len(SUBJECT_VERBS)
        ]
        singular = subject not in {
            "They", "We", "The students",
            "Tom and Amy", "My friends",
        }
        correct = third if singular else base
        return make_mcq(
            rng,
            subject="english",
            prompt=f"{subject} ___ English every day.",
            correct=correct,
            distractors=[
                base if singular else third,
                f"is {base}",
                f"are {base}",
                f"to {base}",
            ],
            difficulty=0.35,
            explanation="根据主语单复数选择谓语形式。",
            knowledge_point_code=code,
        )

    if code == "english.grammar.irregular_past":
        base, correct = IRREGULAR_VERBS[index]
        distractors = [
            value for _, value in IRREGULAR_VERBS
            if value != correct
        ]
        return make_mcq(
            rng,
            subject="english",
            prompt=f"选择动词{base}的过去式。",
            correct=correct,
            distractors=distractors,
            difficulty=0.35,
            explanation=f"{base}的不规则过去式是{correct}。",
            knowledge_point_code=code,
        )

    if code == "physics.mechanics.speed":
        speed = index + 12
        time = index % 8 + 2
        distance = speed * time
        return GeneratedQuestion(
            subject="physics",
            stem=(
                f"物体在{time}小时内行驶{distance}千米，"
                "平均速度是多少千米每小时？只填写数字。"
            ),
            question_type="short_answer",
            difficulty=0.35,
            answer={"value": str(speed)},
            explanation=(
                f"速度 = 路程 ÷ 时间 = "
                f"{distance} ÷ {time} = {speed}。"
            ),
            knowledge_point_code=code,
        )

    if code == "physics.electricity.ohms_law":
        current = index % 10 + 1
        resistance = index + 2
        voltage = current * resistance
        return GeneratedQuestion(
            subject="physics",
            stem=(
                f"某电阻为{resistance}欧姆，通过的电流为"
                f"{current}安培，电压是多少伏？只填写数字。"
            ),
            question_type="short_answer",
            difficulty=0.45,
            answer={"value": str(voltage)},
            explanation=(
                f"根据U = IR，电压为"
                f"{current} × {resistance} = {voltage}伏。"
            ),
            knowledge_point_code=code,
        )

    if code == "chemistry.formula.atom_count":
        formula, element, per_molecule = CHEMISTRY_ATOMS[
            index % len(CHEMISTRY_ATOMS)
        ]
        molecules = index + 2
        total = molecules * per_molecule
        return GeneratedQuestion(
            subject="chemistry",
            stem=(
                f"{molecules}个{formula}分子中有多少个"
                f"{element}原子？只填写数字。"
            ),
            question_type="short_answer",
            difficulty=0.35,
            answer={"value": str(total)},
            explanation=(
                f"{molecules} × {per_molecule} = {total}。"
            ),
            knowledge_point_code=code,
        )

    if code == "chemistry.amount.molar_mass":
        formula, molar_mass = MOLAR_MASSES[
            index % len(MOLAR_MASSES)
        ]
        amount = index // len(MOLAR_MASSES) + 1
        total_mass = molar_mass * amount
        return GeneratedQuestion(
            subject="chemistry",
            stem=(
                f"{amount}摩尔{formula}的质量是多少克？"
                f"已知其摩尔质量为{molar_mass}克每摩尔。"
                "只填写数字。"
            ),
            question_type="short_answer",
            difficulty=0.45,
            answer={"value": str(total_mass)},
            explanation=(
                f"质量 = 物质的量 × 摩尔质量 = "
                f"{amount} × {molar_mass} = {total_mass}克。"
            ),
            knowledge_point_code=code,
        )

    if code == "biology.genetics.dna_pairing":
        bases = "ATCG"
        sequence = "".join(
            rng.choice(bases) for _ in range(6 + index % 5)
        )
        translation = str.maketrans("ATCG", "TAGC")
        complement = sequence.translate(translation)
        return GeneratedQuestion(
            subject="biology",
            stem=f"写出DNA序列{sequence}的互补链。",
            question_type="short_answer",
            difficulty=0.4,
            answer={"value": complement},
            explanation="DNA中A与T配对，C与G配对。",
            knowledge_point_code=code,
        )

    if code == "biology.ecology.energy_transfer":
        level = index % 4 + 1
        next_energy = (index + 10) * 100
        current_energy = next_energy * 10
        return GeneratedQuestion(
            subject="biology",
            stem=(
                f"某营养级具有{current_energy}千焦能量，"
                "按10%的传递效率，下一级约获得多少千焦？"
                "只填写数字。"
            ),
            question_type="short_answer",
            difficulty=round(0.35 + level / 20, 2),
            answer={"value": str(next_energy)},
            explanation=(
                f"{current_energy} × 10% = {next_energy}。"
            ),
            knowledge_point_code=code,
        )

    if code == "history.calendar.century":
        year = 101 + index * 73
        century = (year - 1) // 100 + 1
        return GeneratedQuestion(
            subject="history",
            stem=f"公元{year}年属于第几世纪？只填写数字。",
            question_type="short_answer",
            difficulty=0.3,
            answer={"value": str(century)},
            explanation=f"公元{year}年属于第{century}世纪。",
            knowledge_point_code=code,
        )

    if code == "history.calendar.elapsed_years":
        start = 1000 + index * 17
        interval = index % 80 + 20
        end = start + interval
        return GeneratedQuestion(
            subject="history",
            stem=(
                f"从公元{start}年到公元{end}年相隔多少年？"
                "只填写数字。"
            ),
            question_type="short_answer",
            difficulty=0.25,
            answer={"value": str(interval)},
            explanation=f"{end} - {start} = {interval}年。",
            knowledge_point_code=code,
        )

    if code == "geography.longitude.time_difference":
        longitude_a = index * 5
        difference = index % 6 + 1
        longitude_b = longitude_a + difference * 15
        return GeneratedQuestion(
            subject="geography",
            stem=(
                f"A地位于东经{longitude_a}度，B地位于东经"
                f"{longitude_b}度。两地时差约为多少小时？"
                "只填写数字。"
            ),
            question_type="short_answer",
            difficulty=0.4,
            answer={"value": str(difference)},
            explanation=(
                f"经度差除以15，得到{difference}小时。"
            ),
            knowledge_point_code=code,
        )

    if code == "geography.map.scale":
        scale_km = index % 8 + 1
        map_cm = index + 2
        real_km = scale_km * map_cm
        return GeneratedQuestion(
            subject="geography",
            stem=(
                f"某地图上1厘米代表{scale_km}千米，"
                f"两地相距{map_cm}厘米，实际距离是多少千米？"
                "只填写数字。"
            ),
            question_type="short_answer",
            difficulty=0.35,
            answer={"value": str(real_km)},
            explanation=(
                f"{scale_km} × {map_cm} = {real_km}千米。"
            ),
            knowledge_point_code=code,
        )

    if code == "computer.binary.to_decimal":
        value = index * 7 + 5
        return GeneratedQuestion(
            subject="computer_science",
            stem=(
                f"将二进制数{value:b}转换为十进制数。"
                "只填写数字。"
            ),
            question_type="short_answer",
            difficulty=0.4,
            answer={"value": str(value)},
            explanation=f"{value:b}的十进制值为{value}。",
            knowledge_point_code=code,
        )

    if code == "computer.logic.boolean":
        a = index % 2 == 0
        b = index % 3 == 0
        result = a and not b
        return GeneratedQuestion(
            subject="computer_science",
            stem=(
                f"已知A为{str(a)}，B为{str(b)}，"
                "表达式A and not B的结果是什么？"
                "填写True或False。"
            ),
            question_type="short_answer",
            difficulty=0.35,
            answer={"value": str(result)},
            explanation=(
                f"A and not B的结果为{str(result)}。"
            ),
            knowledge_point_code=code,
        )

    if code == "economics.finance.simple_interest":
        principal = 1000 + index * 200
        rate = index % 5 + 1
        years = index % 4 + 1
        interest = principal * rate * years // 100
        return GeneratedQuestion(
            subject="economics",
            stem=(
                f"本金{principal}元，年单利率{rate}%，"
                f"存{years}年，利息是多少元？只填写数字。"
            ),
            question_type="short_answer",
            difficulty=0.4,
            answer={"value": str(interest)},
            explanation=(
                f"利息 = 本金 × 利率 × 年数 = {interest}元。"
            ),
            knowledge_point_code=code,
        )

    if code == "economics.market.discount":
        original = 100 + index * 20
        discount = (index % 5 + 5) * 10
        sale_price = original * discount // 100
        return GeneratedQuestion(
            subject="economics",
            stem=(
                f"商品原价{original}元，按原价的{discount}%出售，"
                "售价是多少元？只填写数字。"
            ),
            question_type="short_answer",
            difficulty=0.3,
            answer={"value": str(sale_price)},
            explanation=(
                f"{original} × {discount}% = {sale_price}元。"
            ),
            knowledge_point_code=code,
        )

    raise ValueError(f"没有生成器：{code}")


def generate_all(seed: int) -> list[GeneratedQuestion]:
    rng = random.Random(seed)

    questions = [
        *generate_math(rng, 50),
        *generate_physics(rng, 50),
        *generate_chemistry(rng, 50),
        *generate_english(rng, 50),
        *generate_computer_science(rng, 50),
        *generate_geography(rng, 25),
        *generate_history(rng, 25),
    ]

    validate_questions(questions)
    return questions


def validate_questions(
    questions: list[GeneratedQuestion],
) -> None:
    if len(questions) != 300:
        raise ValueError(
            f"题目数量错误，预期300，实际{len(questions)}"
        )

    stems = set()

    for index, question in enumerate(questions, start=1):
        if not question.stem.strip():
            raise ValueError(f"第{index}题题干为空")

        if question.stem in stems:
            raise ValueError(
                f"发现重复题干：{question.stem}"
            )

        stems.add(question.stem)

        if not 0.0 <= question.difficulty <= 1.0:
            raise ValueError(
                f"第{index}题难度不合法"
            )

        if not question.answer.get("value", "").strip():
            raise ValueError(
                f"第{index}题答案为空"
            )

        if (
            question.knowledge_point_code
            not in KNOWLEDGE_POINTS
        ):
            raise ValueError(
                f"未知知识点："
                f"{question.knowledge_point_code}"
            )


def write_jsonl(
    questions: list[GeneratedQuestion],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        for question in questions:
            file.write(
                json.dumps(
                    asdict(question),
                    ensure_ascii=False,
                )
                + "\n"
            )


async def import_questions(
    questions: list[GeneratedQuestion],
) -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    await database.create_schema()

    inserted = 0
    existing = 0
    linked = 0

    async with database.session_factory() as db:
        point_by_code: dict[str, KnowledgePoint] = {}

        for code, definition in KNOWLEDGE_POINTS.items():
            result = await db.execute(
                select(KnowledgePoint)
                .where(
                    KnowledgePoint.subject
                    == definition["subject"],
                    KnowledgePoint.code == code,
                )
                .limit(1)
            )
            point = result.scalar_one_or_none()

            if point is None:
                point = KnowledgePoint(
                    subject=definition["subject"],
                    code=code,
                    name=definition["name"],
                    description=definition["description"],
                    prerequisites=definition[
                        "prerequisites"
                    ],
                )
                db.add(point)
                await db.flush()
            else:
                point.name = definition["name"]
                point.description = definition[
                    "description"
                ]
                point.prerequisites = definition[
                    "prerequisites"
                ]

            point_by_code[code] = point

        for generated in questions:
            result = await db.execute(
                select(Question)
                .where(
                    Question.subject
                    == generated.subject,
                    Question.stem
                    == generated.stem,
                )
                .limit(1)
            )
            question = result.scalar_one_or_none()

            if question is None:
                question = Question(
                    subject=generated.subject,
                    stem=generated.stem,
                    question_type=(
                        generated.question_type
                    ),
                    difficulty=generated.difficulty,
                    answer=generated.answer,
                    explanation=generated.explanation,
                    active=True,
                )
                db.add(question)
                await db.flush()
                inserted += 1
            else:
                existing += 1

            point = point_by_code[
                generated.knowledge_point_code
            ]

            link = await db.get(
                QuestionKnowledgePoint,
                {
                    "question_id": question.id,
                    "knowledge_point_id": point.id,
                },
            )

            if link is None:
                db.add(
                    QuestionKnowledgePoint(
                        question_id=question.id,
                        knowledge_point_id=point.id,
                        weight=1.0,
                    )
                )
                linked += 1

        await db.commit()

    await database.dispose()

    print(f"新增题目: {inserted}")
    print(f"已存在题目: {existing}")
    print(f"新增知识点关联: {linked}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seed",
        type=int,
        default=20260817,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/generated_questions.jsonl"
        ),
    )
    parser.add_argument(
        "--no-import",
        action="store_true",
    )
    args = parser.parse_args()

    questions = generate_all(args.seed)
    write_jsonl(questions, args.output)

    print(f"已生成 {len(questions)} 道题")
    print(f"JSONL文件: {args.output.resolve()}")

    if not args.no_import:
        await import_questions(questions)


if __name__ == "__main__":
    asyncio.run(main())