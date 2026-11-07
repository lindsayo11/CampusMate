"""A small, auditable needs questionnaire. Preferences are not eligibility facts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from .models import Path
from .data_catalog import catalog


class Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    stage: Literal["early", "junior", "senior", "graduate", "working"]
    direction: Literal["explore", "competition", "recommendation_exemption",
        "domestic_postgraduate_exam", "overseas_study", "national_civil_service",
        "employment", "entrepreneurship"]
    subject: str = Field(min_length=1, max_length=80)
    goal: Literal["research", "career", "skills", "startup", "unsure"]
    hours: int = Field(ge=2, le=40)
    experience: Literal["starting", "project", "award", "research"]
    collaboration: Literal["solo", "team", "either"]
    horizon: Literal["month", "semester", "year"]


NAMES = {
    "competition": "竞赛实践", "recommendation_exemption": "保研推免",
    "domestic_postgraduate_exam": "国内考研", "overseas_study": "境外留学",
    "national_civil_service": "考公考编", "employment": "实习就业",
    "entrepreneurship": "创新创业",
}
STAGES = {"early": "本科低年级", "junior": "本科三年级", "senior": "本科毕业年级",
          "graduate": "研究生", "working": "已毕业"}
EXPERIENCE = {"starting": "刚开始准备", "project": "有项目经历",
              "award": "有竞赛获奖", "research": "有科研经历"}
HORIZONS = {"month": "未来一个月", "semester": "本学期", "year": "未来一年"}


def evaluate(answers: Assessment, db):
    direction = answers.direction
    if direction == "explore":
        direction = {"career": "employment", "startup": "entrepreneurship",
                     "skills": "competition", "unsure": "competition"}.get(answers.goal,
            "recommendation_exemption" if answers.stage in {"early", "junior"} else "domestic_postgraduate_exam")
    name = NAMES[direction]
    path_code = "entrepreneurship" if direction == "competition" else direction
    path = db.scalar(select(Path).where(Path.code == path_code))
    phase = HORIZONS[answers.horizon]
    quota = max(1, round(answers.hours * .25))
    main_hours = answers.hours - quota
    first = {
        "competition": "对比两项竞赛的题目、赛制与报名条件",
        "recommendation_exemption": "核对本校推免办法与目标院校接收要求",
        "domestic_postgraduate_exam": "对比两所目标院校的科目、招生目录与复习范围",
        "overseas_study": "对比两个项目的语言、课程与申请材料",
        "national_civil_service": "核对岗位表中的学历、专业与应届身份要求",
        "employment": "筛选两类目标岗位并梳理技能差距",
        "entrepreneurship": "确定一个具体用户问题并准备访谈提纲",
    }[direction]
    output = ("完成一份小型练习与复盘记录" if answers.experience == "starting" else
              "将已有项目或成果整理成可展示的作品与证据")
    collaboration = ("明确分工、技能缺口与每周协作时间" if answers.collaboration == "team" else
        "划分可独立完成的任务，并预约一次外部反馈" if answers.collaboration == "solo" else
        "先完成一项小任务，再判断是否需要寻找队友")
    tasks = [
        {"title": first, "steps": [f"围绕{answers.subject}整理目标清单",
            "保存原文，逐项记录适用对象、时间、材料与尚未确认的条件"]},
        {"title": output, "steps": [f"每周安排 {main_hours} 小时开展主要准备",
            collaboration]},
        {"title": "每周回看进度，调整下一步", "steps": [
            f"每周预留 {quota} 小时核查来源与复盘（与主要准备合计 {answers.hours} 小时）",
            f"以{phase}为观察周期，保留成果、障碍与下一次行动"]},
    ]
    # Use the existing publication gate. No external call, invented notice or
    # automatic eligibility claim is made by this preference-based assessment.
    kwargs = dict(q="赛" if direction == "competition" else "", path=None if direction == "competition" else path_code,
                  region=None, offset=0, limit=6, school="", year=None, kind="all", sort="recent", db=db)
    matches = catalog(status="active", **kwargs)
    reference_only = False
    if not matches["items"]:
        matches = catalog(status="all", **kwargs)
        reference_only = bool(matches["items"])
    for row in matches["items"]:
        row["match_reason"] = "与所选竞赛方向相关" if direction == "competition" else f"属于{name}频道"
    rationale = [
        f"你的当前阶段是{STAGES[answers.stage]}，关注领域是{answers.subject}。",
        f"按你选择的方向安排{name}准备。" if answers.direction != "explore" else
        f"根据你的目标，先将{name}作为探索起点；你可以修改答案重新比较。",
        f"以{phase}为周期，每周共 {answers.hours} 小时；{EXPERIENCE[answers.experience]}。",
    ]
    return {"assessment": answers.model_dump(), "focus": name, "path_code": path_code,
        "path_id": path.id if path else None, "rationale": rationale, "tasks": tasks,
        "matches": matches["items"], "match_total": matches["total"], "reference_only": reference_only,
        "notice": "这是基于你的回答生成的准备方案，不代表通过报名资格。具体条件请进入公告核对原文。"}


def preparation_plans(answers: Assessment, db):
    result = evaluate(answers, db)
    return {"plans": [{"title": (result["focus"] + "：" + task["title"])[:160],
        "path_id": result["path_id"], "status": "todo", "due_date": None,
        "note": "依据本次需求问卷；个人准备建议，非官方截止日期。\n" + "\n".join(result["rationale"]),
        "steps": task["steps"]} for task in result["tasks"]],
        "note": "仅在确认后加入个人计划；不会覆盖个人画像。"}
