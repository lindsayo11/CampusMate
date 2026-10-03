"""Channel classification must place facts where the student actually looks.

A DevelopmentItem on the parent `domestic_study` path is visible in the generic
catalog but invisible inside all six development channels, because filtering walks
from a channel code down to descendants only. These tests protect the leaf-path
classifier from silently regressing to that behaviour.
"""
from app.adapters.education import classify_path


def test_classifies_postgraduate_items_before_generic_employment_terms():
    assert classify_path("江苏省2027年硕士研究生报考点设置") == "domestic_postgraduate_exam"
    # "招生" appears in the title, but it is postgraduate admission - not a job.
    assert classify_path("2027年全国硕士研究生招生工作管理规定") == "domestic_postgraduate_exam"


def test_classifies_certificates_into_employment_channel():
    assert classify_path("2026年下半年全国大学英语四、六级考试报名通告") == "employment"
    assert classify_path("2026年9月全国计算机等级考试考前提醒") == "employment"


def test_classifies_source_specific_overseas_and_entrepreneurship_text():
    assert classify_path("教育部发布留学回国人员有关规定") == "overseas_study"
    assert classify_path("挑战杯大学生创新创业项目孵化基地通知") == "entrepreneurship"


def test_unknown_content_is_not_forced_into_a_channel():
    # A generic education notice has no defensible six-channel placement.
    assert classify_path("我省公布普通高中学业水平合格性考试时间") is None
