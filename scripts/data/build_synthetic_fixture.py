#!/usr/bin/env python3
"""Generate reproducible P1 schema and synthetic-post submission assets."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "data" / "schema" / "data_schema_v1.json"
DATASET_PATH = ROOT / "data" / "synthetic" / "simulated_posts_v1.json"

SCHEMA_VERSION = "1.0"
NOW = "2026-07-21T09:00:00+08:00"


def media(media_id: str, ocr_text: str | None = None, media_type: str = "image") -> list[dict]:
    return [{
        "media_id": media_id,
        "type": media_type,
        "local_ref": None,
        "sha256": None,
        "phash": None,
        "ocr_text": ocr_text,
    }]


def comment(comment_id: str, text: str, *, pinned: bool = False, likes: int = 0) -> dict:
    return {
        "comment_id": comment_id,
        "author_id": f"commenter_{comment_id}",
        "text": text,
        "like_count": likes,
        "is_pinned": pinned,
    }


def post(
    post_id: str,
    blogger_id: str,
    text: str,
    *,
    media_items: list[dict] | None = None,
    comments: list[dict] | None = None,
    history: list[str] | None = None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "post_id": post_id,
        "platform": "synthetic",
        "source_type": "synthetic",
        "blogger_id": blogger_id,
        "published_at": "2026-07-20T10:00:00+08:00",
        "text": text,
        "media": media_items or [],
        "comments": comments or [],
        "blogger_history_refs": history or [],
        "provenance": {
            "source_ref_hash": f"synthetic_case_{post_id}",
            "collected_at": NOW,
            "collector": "P1_team",
            "terms_checked_at": "2026-07-21",
        },
        "privacy": {
            "anonymized": True,
            "contains_sensitive_data": False,
        },
    }


def annotation(
    post_id: str,
    label: str,
    codes: list[str],
    evidence: list[str],
    *,
    confidence: float = 0.9,
    uncertain_reason: str | None = None,
) -> dict:
    return {
        "post_id": post_id,
        "annotator_id": "synthetic_reference",
        "guide_version": SCHEMA_VERSION,
        "label": label,
        "confidence": confidence,
        "evidence_codes": codes,
        "evidence": evidence,
        "uncertain_reason": uncertain_reason,
        "annotated_at": NOW,
    }


posts = [
    post("post_explicit_sponsor", "blogger_style_001", "本期穿搭内容由晴岚服饰赞助，下面展示三套新品搭配和购买入口。", media_items=media("media_001", "晴岚服饰新品合作")),
    post("post_platform_paid_label", "blogger_food_001", "周末去云巷咖啡体验新品，菜单和店铺地址整理在图里。", media_items=media("media_002", "平台标识：商业推广；云巷咖啡夏日新品")),
    post("post_gifted_product", "blogger_beauty_001", "感谢澄光品牌寄送试用套装。本文记录七天使用感受，并附产品信息。", media_items=media("media_003", "澄光品牌寄送")),
    post("post_invited_launch", "blogger_tech_001", "受邀参加星曜耳机新品发布会，现场试听和型号介绍如下。", media_items=media("media_004", "星曜耳机新品发布会")),
    post("post_disclosed_giveaway", "blogger_life_001", "与森野家居联合送福利：转发并留言可参与抽奖，奖品为本期合作产品。", comments=[comment("c005", "活动规则已置顶", pinned=True, likes=20)]),

    post("post_coupon_code", "blogger_beauty_002", "这支防晒我自费回购很多次，最近店铺给了我的专属码 ZY20，到手价更低。", media_items=media("media_006", "专属优惠码 ZY20")),
    post("post_link_in_comments", "blogger_style_002", "这双通勤鞋真的闭眼入，显腿长又不磨脚，想要同款的去评论区看链接。", comments=[comment("c007", "同款购买链接：示例店铺/鞋款", pinned=True, likes=65)]),
    post("post_qr_coupon_image", "blogger_home_001", "今天只分享厨房收纳的小变化。", media_items=media("media_008", "满199减80，扫码领券；清禾收纳盒")),
    post("post_restaurant_discount", "blogger_food_002", "这家店的套餐太值了，周末一定要冲！报我的暗号可领九折券，排队前先预约。"),
    post("post_comparison_one_link", "blogger_tech_002", "三款降噪耳机里我更推荐澜声 X2，续航和佩戴最好。购买页我放在置顶评论。", comments=[comment("c010", "澜声 X2 官方购买页", pinned=True, likes=31)]),
    post("post_pinned_store_entry", "blogger_mom_001", "宝宝餐椅选购做了很多功课，最后留下晨芽这款。尺寸、材质和店铺入口都在置顶。", comments=[comment("c011", "晨芽餐椅店铺入口与活动价", pinned=True, likes=42)]),
    post("post_scarcity_price", "blogger_life_002", "这个净水壶库存快没了，今天活动只剩最后两小时，低于这个价真的别等。", media_items=media("media_012", "限时2小时；到手价169元；清泉净水壶")),
    post("post_health_qr", "blogger_health_001", "最近熬夜多的朋友可以看看元气维 C 片，我连续吃一周精神好多了。图里有扫码领试用装。", media_items=media("media_013", "元气维C片；扫码领取试用装")),
    post("post_topic_drift_finance", "blogger_travel_001", "平时写旅行攻略，今天想认真推荐一个理财课程：零基础也能学，报名入口见评论。", comments=[comment("c014", "课程报名入口", pinned=True, likes=18)], history=["history_travel_101", "history_travel_102"]),
    post("post_image_only_sale", "blogger_home_002", "新品到了。", media_items=media("media_015", "北屿香薰机；新品首发；限时立减50元")),
    post("post_comment_anomaly", "blogger_beauty_003", "最近一直在用润泽精华，肤感轻薄又稳定，分享给需要的人。", comments=[comment("c016a", "已买，真的好用！", likes=12), comment("c016b", "已买，真的好用！", likes=11), comment("c016c", "已买，真的好用！", likes=9), comment("c016d", "已买，真的好用！", likes=8)]),
    post("post_direct_shop_route", "blogger_pet_001", "新手养猫先备这款除味豆腐砂，灰尘少、结团快。店铺直播间今天有赠品，直接搜‘轻爪猫砂’。", media_items=media("media_017", "轻爪猫砂；直播间赠品")),

    post("post_balanced_review", "blogger_tech_003", "自费买了风铃键盘，用一周后优点是手感稳定，缺点是声音偏大、配列不适合所有人；没有购买链接。"),
    post("post_logo_background", "blogger_life_003", "和朋友在公园野餐，记录一下天气和路线。", media_items=media("media_019", "远处饮料包装Logo，非内容主体")),
    post("post_negative_complaint", "blogger_food_003", "上周买的北湾酸奶口感发酸且客服处理慢，记录避雷过程，不建议购买。"),
    post("post_news_price", "blogger_news_001", "行业快讯：多家家电企业公布季度销量和原材料价格变化，本文只整理公开财报数据。"),
    post("post_science_multibrand", "blogger_science_001", "防晒成分科普：氧化锌、阿伏苯宗各有适用场景，列出多个品牌仅作成分示例，不提供购买渠道。"),
    post("post_restaurant_diary", "blogger_food_004", "下班和同事去巷口吃面，汤头偏咸但分量足，记录路线和当天心情，没有折扣或联络方式。"),
    post("post_objective_device_review", "blogger_tech_004", "对两台扫地机做了噪声、续航和避障测试：A 的避障好，B 的续航长；没有指定推荐，也没有链接。"),
    post("post_running_diary", "blogger_sport_001", "晨跑 5 公里打卡。脚上的鞋是去年买的旧款，今天只记录配速和心率。", media_items=media("media_025", "跑步数据截图，无价格或导流")),

    post("post_used_sale", "blogger_personal_001", "搬家出一台自用二手书桌，使用痕迹见图，有需要的本地自取。"),
    post("post_recruitment", "blogger_company_001", "工作室招聘剪辑实习生，岗位职责和投递邮箱见下方。"),
    post("post_charity", "blogger_public_001", "本周末为山区儿童开展公益图书募集，欢迎按活动说明捐赠闲置书籍。"),

    post("post_ambiguous_model", "blogger_style_003", "很多人问这件外套的同款，我先写下型号：M-27。其余信息之后再整理。"),
    post("post_blurry_image", "blogger_life_004", "朋友送来一份新品小礼物，先随手拍一下。", media_items=media("media_030", "图中文字模糊，疑似商品包装，无法识别品牌或价格")),
]

annotations = [
    annotation("post_explicit_sponsor", "明广", ["D", "C"], ["正文明确写明品牌赞助", "内容围绕单一服饰品牌展示"]),
    annotation("post_platform_paid_label", "明广", ["D", "C", "V"], ["图片中存在平台商业推广标识", "店铺和新品是内容核心"]),
    annotation("post_gifted_product", "明广", ["D", "C"], ["正文披露品牌寄送", "围绕单一产品套装展开"]),
    annotation("post_invited_launch", "明广", ["D", "C"], ["正文披露受邀参加发布会", "集中介绍单一品牌新品"]),
    annotation("post_disclosed_giveaway", "明广", ["D", "C", "A"], ["明确写明联合活动", "抽奖活动引导用户参与"]),

    annotation("post_coupon_code", "暗广", ["C", "A"], ["明确指向单一防晒产品", "提供专属优惠码形成直接转化动作"]),
    annotation("post_link_in_comments", "暗广", ["C", "P", "A"], ["围绕单一鞋款强推荐", "使用‘闭眼入’等促销话术", "置顶评论提供购买链接"]),
    annotation("post_qr_coupon_image", "暗广", ["C", "V", "A"], ["图片明确展示收纳盒品牌", "图内有满减与扫码领券信息"]),
    annotation("post_restaurant_discount", "暗广", ["C", "P", "A"], ["明确商业对象为餐厅套餐", "存在‘一定要冲’等促销话术", "提供暗号折扣和预约引导"]),
    annotation("post_comparison_one_link", "暗广", ["C", "A"], ["比较后只重点推荐一款耳机", "置顶评论提供该款购买页"]),
    annotation("post_pinned_store_entry", "暗广", ["C", "A", "M"], ["内容聚焦单一餐椅", "置顶评论提供店铺入口和活动价", "置顶导流属于评论异常证据"]),
    annotation("post_scarcity_price", "暗广", ["C", "P", "V", "A"], ["明确推广单一净水壶", "强调库存和限时稀缺", "图片展示到手价", "形成购买时机引导"]),
    annotation("post_health_qr", "暗广", ["C", "V", "A"], ["明确商业对象为维C片", "图内展示试用装扫码信息", "扫码领取构成转化动作"]),
    annotation("post_topic_drift_finance", "暗广", ["C", "A", "B"], ["明确推广理财课程", "评论区有报名入口", "旅行主题账号突然推广金融课程，存在可验证主题偏移"]),
    annotation("post_image_only_sale", "暗广", ["C", "V", "A"], ["正文虽短，但图片明确展示香薰机新品", "图内有首发立减等促销信息"]),
    annotation("post_comment_anomaly", "暗广", ["C", "P", "M"], ["内容聚焦单一精华产品", "存在正向推荐语气", "评论区出现集中重复的模板化赞美"]),
    annotation("post_direct_shop_route", "暗广", ["C", "P", "A"], ["内容聚焦单一猫砂品牌", "使用强推荐表达", "引导用户搜索直播间并提示赠品"]),

    annotation("post_balanced_review", "非广", ["C"], ["虽有明确产品对象，但同时给出缺点", "没有购买入口、优惠或促销话术"]),
    annotation("post_logo_background", "非广", [], ["品牌Logo仅作为生活照片背景，不是内容核心"]),
    annotation("post_negative_complaint", "非广", ["C"], ["对象是商品，但内容为负面投诉且没有推广导流"]),
    annotation("post_news_price", "非广", [], ["价格和销量属于新闻事实整理，不构成促销"]),
    annotation("post_science_multibrand", "非广", [], ["多品牌仅作科普示例，没有购买渠道或导流"]),
    annotation("post_restaurant_diary", "非广", ["C"], ["餐厅仅是日常记录对象，没有折扣、链接或促销引导"]),
    annotation("post_objective_device_review", "非广", ["C"], ["客观比较两台设备，没有偏向单一购买入口或促销动作"]),
    annotation("post_running_diary", "非广", [], ["鞋子不是内容核心，图片仅展示跑步数据"]),

    annotation("post_used_sale", "out_of_scope", [], ["个人二手转卖不属于本项目定义的内容营销"], confidence=1.0),
    annotation("post_recruitment", "out_of_scope", [], ["招聘信息不属于商业产品推广帖"], confidence=1.0),
    annotation("post_charity", "out_of_scope", [], ["公益募集不是商业广告，需单独统计"], confidence=1.0),

    annotation("post_ambiguous_model", "uncertain", ["C"], ["出现服装型号，但没有价格、店铺、链接或明确导购"], confidence=0.45, uncertain_reason="需要结合后续内容或博主历史判断是否存在转化意图"),
    annotation("post_blurry_image", "uncertain", ["V"], ["图片疑似商品包装但关键信息无法识别", "正文没有品牌、价格或导流"], confidence=0.35, uncertain_reason="图片证据不清晰且上下文不足"),
]

content_properties = {
    "schema_version": {"const": SCHEMA_VERSION, "description": "Schema 版本。"},
    "post_id": {"type": "string", "pattern": "^post_[A-Za-z0-9_-]+$", "description": "去标识化且全局唯一的帖子 ID。"},
    "platform": {"type": "string", "enum": ["wechat_official_account", "weibo", "xiaohongshu", "douyin", "synthetic", "other"], "description": "内容来源平台。"},
    "source_type": {"type": "string", "enum": ["public_dataset", "manual_public_collection", "authorized_export", "synthetic"], "description": "数据取得方式；模拟数据必须填 synthetic。"},
    "blogger_id": {"type": "string", "pattern": "^blogger_[A-Za-z0-9_-]+$", "description": "经项目私有盐处理的稳定哈希/匿名 ID。"},
    "published_at": {"type": ["string", "null"], "format": "date-time", "description": "发布时间；未知时为 null。"},
    "text": {"type": "string", "description": "经脱敏后的正文；图像为主的帖子可为空字符串。"},
    "media": {"type": "array", "items": {"$ref": "#/$defs/media_item"}, "description": "媒体元数据，不在 Git 中提交未审查的原始媒体。"},
    "comments": {"type": "array", "items": {"$ref": "#/$defs/comment_item"}, "description": "可获得时的匿名化评论。"},
    "blogger_history_refs": {"type": "array", "items": {"type": "string"}, "description": "用于主题漂移判断的去标识化历史帖子引用。"},
    "provenance": {"$ref": "#/$defs/provenance", "description": "来源和采集审计信息。"},
    "privacy": {"$ref": "#/$defs/privacy", "description": "脱敏与敏感信息检查结果。"},
}

schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.invalid/implicit-ad/data_schema_v1.json",
    "title": "隐性广告识别 P1 数据 Schema v1.0",
    "description": "标准帖子输入和独立标注记录定义。内容记录不包含最终人工标签。",
    "$ref": "#/$defs/content_record",
    "$defs": {
        "content_record": {
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "post_id", "platform", "source_type", "blogger_id", "text", "media", "provenance", "privacy"],
            "properties": content_properties,
        },
        "media_item": {
            "type": "object",
            "additionalProperties": False,
            "required": ["media_id", "type", "local_ref", "sha256", "phash", "ocr_text"],
            "properties": {
                "media_id": {"type": "string"},
                "type": {"type": "string", "enum": ["image", "video", "audio", "link", "other"]},
                "local_ref": {"type": ["string", "null"]},
                "sha256": {"type": ["string", "null"], "pattern": "^[A-Fa-f0-9]{64}$"},
                "phash": {"type": ["string", "null"]},
                "ocr_text": {"type": ["string", "null"]},
            },
        },
        "comment_item": {
            "type": "object",
            "additionalProperties": False,
            "required": ["comment_id", "author_id", "text", "like_count", "is_pinned"],
            "properties": {
                "comment_id": {"type": "string"},
                "author_id": {"type": "string", "description": "匿名评论者 ID。"},
                "text": {"type": "string"},
                "like_count": {"type": "integer", "minimum": 0},
                "is_pinned": {"type": "boolean"},
            },
        },
        "provenance": {
            "type": "object",
            "additionalProperties": False,
            "required": ["source_ref_hash", "collected_at", "collector", "terms_checked_at"],
            "properties": {
                "source_ref_hash": {"type": "string"},
                "collected_at": {"type": "string", "format": "date-time"},
                "collector": {"type": "string"},
                "terms_checked_at": {"type": ["string", "null"], "format": "date"},
            },
        },
        "privacy": {
            "type": "object",
            "additionalProperties": False,
            "required": ["anonymized", "contains_sensitive_data"],
            "properties": {
                "anonymized": {"type": "boolean"},
                "contains_sensitive_data": {"type": "boolean"},
            },
        },
        "annotation_record": {
            "type": "object",
            "additionalProperties": False,
            "required": ["post_id", "annotator_id", "guide_version", "label", "confidence", "evidence_codes", "evidence", "uncertain_reason", "annotated_at"],
            "properties": {
                "post_id": {"type": "string", "pattern": "^post_[A-Za-z0-9_-]+$"},
                "annotator_id": {"type": "string", "description": "正式双标时使用 D 或 N；本模拟集使用 synthetic_reference。"},
                "guide_version": {"const": SCHEMA_VERSION},
                "label": {"type": "string", "enum": ["明广", "暗广", "非广", "out_of_scope", "uncertain"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "evidence_codes": {"type": "array", "uniqueItems": True, "items": {"type": "string", "enum": ["D", "C", "P", "A", "V", "B", "M"]}},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "uncertain_reason": {"type": ["string", "null"]},
                "annotated_at": {"type": "string", "format": "date-time"},
            },
        },
    },
    "x_field_reference": [
        {"field": "post_id", "required": True, "purpose": "内容和标注记录的唯一关联键。"},
        {"field": "blogger_id", "required": True, "purpose": "按博主分组切分、防泄漏；不得存真实昵称。"},
        {"field": "media/comments/blogger_history_refs", "required": False, "purpose": "支撑视觉、评论异常和主题漂移证据。"},
        {"field": "provenance", "required": True, "purpose": "确保来源、采集时间、责任人和条款检查可追溯。"},
        {"field": "privacy", "required": True, "purpose": "保证数据已脱敏并标记敏感风险。"},
        {"field": "annotation_record", "required": "separate file", "purpose": "保存独立标注，不与模型输入内容混放。"},
    ],
    "examples": [posts[0], annotations[0]],
}

dataset = {
    "dataset_metadata": {
        "dataset_name": "隐性广告识别 P1 模拟帖子集",
        "dataset_version": "synthetic_v1.0",
        "schema_version": SCHEMA_VERSION,
        "schema_file": "data/schema/data_schema_v1.json",
        "created_at": NOW,
        "purpose": "Schema 校验、标注规范试跑和数据处理流程冒烟测试。全部为团队生成的合成数据，不可作为真实金标训练集。",
        "synthetic_only": True,
        "contains_real_personal_data": False,
    },
    "content_records": posts,
    "reference_annotations": annotations,
    "coverage_matrix": {
        "明广": ["post_explicit_sponsor", "post_platform_paid_label", "post_gifted_product", "post_invited_launch", "post_disclosed_giveaway"],
        "暗广": ["post_coupon_code", "post_link_in_comments", "post_qr_coupon_image", "post_restaurant_discount", "post_comparison_one_link", "post_pinned_store_entry", "post_scarcity_price", "post_health_qr", "post_topic_drift_finance", "post_image_only_sale", "post_comment_anomaly", "post_direct_shop_route"],
        "非广": ["post_balanced_review", "post_logo_background", "post_negative_complaint", "post_news_price", "post_science_multibrand", "post_restaurant_diary", "post_objective_device_review", "post_running_diary"],
        "范围外": ["post_used_sale", "post_recruitment", "post_charity"],
        "不确定/复核": ["post_ambiguous_model", "post_blurry_image"],
        "模态覆盖": {
            "纯文本": ["post_restaurant_discount", "post_balanced_review", "post_used_sale"],
            "图片/图中文字": ["post_qr_coupon_image", "post_scarcity_price", "post_image_only_sale", "post_blurry_image"],
            "评论/置顶导流": ["post_link_in_comments", "post_pinned_store_entry", "post_comment_anomaly"],
            "历史主题": ["post_topic_drift_finance"],
            "缺失或不清晰上下文": ["post_ambiguous_model", "post_blurry_image"],
        },
    },
}

SCHEMA_PATH.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
DATASET_PATH.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {SCHEMA_PATH.relative_to(ROOT)}")
print(f"wrote {DATASET_PATH.relative_to(ROOT)}")
print(f"records: {len(posts)}, annotations: {len(annotations)}")
