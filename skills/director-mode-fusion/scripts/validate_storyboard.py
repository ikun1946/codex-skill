#!/usr/bin/env python3
"""Validate director-mode-fusion structure and timing; not story semantics or audio quality."""
import argparse
from decimal import Decimal
from pathlib import Path
import re
import sys

NUMBER = r"[0-9]+\.[0-9]"
PARAGRAPH = re.compile(rf"段落([0-9]+)｜总时长：({NUMBER})s")
SHOT = re.compile(rf"镜([0-9]+)｜({NUMBER})s｜([^/\n]+/[^/\n]+/[^/\n]+)")
VOICE_TOKEN = re.compile(r"【(V[0-9]{3,})｜([^】\n]+)】")
VOICE_CARD = re.compile(r"^\s*(?:[-*]\s*)?(V[0-9]{3,})｜([^｜\n]+)｜([^\n]+?)\s*$", re.MULTILINE)
DIALOGUE_QUOTE = re.compile(r"[“「][^”」]+[”」]")
TEMPORARY_VOICE_WORDS = ("当前", "此刻", "愤怒", "悲伤", "哭腔", "哽咽", "嘶吼", "尖叫", "醉酒", "喘息")
SPEAKER_PREFIXES = ("画外", "电话中", "电话", "隔门", "OS", "VO")


SCENE_FIELDS = ("本段场景布局：", "本段统一光影/质感：", "本场光影/质感：")

STANCE_VERB = re.compile(
    r"(?:坐|站|躺|靠|蹲|跪|伏|倚|停|挡|走|跑|退|挤|并排|位于|留在|守在|来到|回到|抱|背|扶|牵|趴)"
    r"(?:在|于|到|向|着|回|进|起)[^，。；]{0,20}")
STANCE_PREP = re.compile(
    r"(?:在|于|从|到|向)[^，。；]{1,14}"
    r"(?:上|下|里|外|内|中|处|侧|旁|边|间|口|前|后|端)")
STANCE_LANDMARK = re.compile(
    r"门口|门外|门内|门槛|门框|门前|门边|正门|台阶|楼梯|栏杆|桌沿|桌尾|桌首|桌边|桌前|桌面"
    r"|沙发|茶几|床边|床沿|床头|床尾|窗边|窗前|吧台|柜台|台面|玄关|走廊|通道|池边|池沿"
    r"|镜前|车位|甲板|码头|烤架|展台|工位|书架|墙边|角落|院中|树下|驾驶位|副驾驶|后座"
    r"|地毯|地板|地面|地上|台前|台后|座椅|椅子|椅背|凳子|炕沿|炕上|回廊|廊下|车里|车内|栈桥|站台|大厅|门口")
STANCE_REMAIN = re.compile(r"(?:仍在|还在|留在|停在|守在)[^，。；]{1,16}")
COMPASS = re.compile(r"[东南西北](?:侧|边|面|方)")
PERSON_PRONOUN = re.compile(r"(?<![它其])[她他](?!的)|两人(?!的)|三人(?!的)|众人|二人(?!的)")
SCREEN_CONTENT = re.compile(r"屏幕|手机屏|手机上|聊天界面|照片|影像|回放|记录|名单|报告单")

EXPRESSION_STATE = re.compile(
    r"眉心|眉头|眉梢|眉峰|眉毛|眉眼|眼眶|眼睑|眼帘|眼皮|睫毛|瞳孔|眼睛|眼角|眼尾|脸颊|面颊|额头"
    r"|嘴角|唇角|唇线|嘴唇|下唇|双唇|下颌|下巴|喉结|喉头|喉间|鼻息|鼻翼|鼻尖|鼻梁|脸色|神情|表情|面色"
    r"|牙关|腮|神色|脖颈|颈侧|呼吸|吸气|屏息|肩线|肩背|肩膀|脊背|胸口|手心|手背|指节|指尖")
ADDRESS_GAZE = re.compile(
    r"视线|目光|看向|看着|望向|盯着|盯住|瞟|瞥|抬眼|垂眼|朝向|面向|背对|侧对|转头|侧头"
    r"|回头|冲着|朝着|对上|迎上|眼睛[^，。；]{0,10}(?:画左|画右|看|望|移|挪|扫|躲|盯|对)")
OFFSCREEN_MARK = re.compile(r"画外|电话中|电话声|语音声|隔门|OS|旁白")
ADDRESS_OBJECT = re.compile(
    r"(?:对|问|跟|冲|朝)([^，。；：、“”「」]{1,10}?)(?:说|问|答|喊|道|讲|回)")
CONTACT_VERB = re.compile(
    r"递给|递到|塞给|塞到|推到|推向|递还|拉过|拉住|拽住|扯住|扶住|按住|抱住|揽住|抱紧"
    r"|搂住|拍在|拍向|扇了|扇在|扇向|扇耳光|吻上|吻住|抵住")
CONTACT_PART = re.compile(r"手|手指|指尖|指节|掌|腕|臂|肩|腰|背|胸|脸|唇|颈|衣领|袖口")
CONTACT_FEEDBACK = re.compile(
    r"贴|扣|握|压|拉|推|抵|陷|回弹|收紧|松开|滑|擦|碰|晃|垂|回缩|带住|托")
CLOSE_MEDIUM_SCALE = {"特写", "近景", "中近景", "中景"}


def _base_names(line):
    """Split 出场人物 into base character names, dropping markers and costume suffixes."""
    value = line.split("：", 1)[1] if "：" in line else ""
    names = []
    for item in re.split(r"[；;]", value):
        item = re.sub(r"[（(][^）)]*[）)]", "", item).strip()
        item = item.split("-")[0].strip()
        if not item or item in ("无", "群演"):
            continue
        names.append(item)
    return names


def _has_stance(pic):
    return bool(STANCE_VERB.search(pic) or STANCE_PREP.search(pic) or STANCE_REMAIN.search(pic)
                or STANCE_LANDMARK.search(pic))


def _stance_clauses(pic):
    return [c for c in re.split(r"[，；]", pic) if len(c) >= 6 and _has_stance(c)]
EXTERNAL_SCENE_REFERENCE = re.compile(r"同前|(?<!相)同上(?![方悬])(?:段|场|镜)?|沿用(?:上|前)(?:一)?(?:段|场|镜)|参见(?:上|前)(?:一)?(?:段|场|镜)")


def _read_scene_fields(lines, cursor, errors, label, initial, strict):
    """Consume ordered scene metadata; absent legacy fields remain compatible."""
    expected = [("本段场景布局：", strict)]
    if initial:
        expected += [("出场人物：", True), ("本段统一光影/质感：", True)]
    else:
        expected += [("本场光影/质感：", strict)]
    for prefix, required in expected:
        if cursor < len(lines) and lines[cursor].startswith(prefix):
            value = lines[cursor][len(prefix):].strip()
            if not value:
                errors.append(f"{label}：{prefix}不能为空")
            elif strict and prefix != "出场人物：" and EXTERNAL_SCENE_REFERENCE.search(value):
                errors.append(f"{label}：{prefix}含外部依赖，需独立写全布局或光影")
            cursor += 1
        elif required:
            errors.append(f"{label}：缺少或错置{prefix}")
    return cursor


def validate(text, start_shot=1, start_paragraph=1, check_scenes=False):
    errors = []
    stripped = text.strip()
    if stripped.startswith('```') and stripped.endswith('```'):
        stripped = '\n'.join(stripped.splitlines()[1:-1]).strip()
    if not stripped:
        return ["输入为空"]
    blocks = re.split(r"(?m)^\s*@\s*$", stripped)
    next_shot = start_shot
    for index, block in enumerate(blocks):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        label = f"第{index + 1}段块"
        if len(lines) < 5:
            errors.append(f"{label}：缺少段落信息或镜头（也请检查多余@）")
            continue
        header = PARAGRAPH.fullmatch(lines[0])
        if not header:
            errors.append(f"{label}：段落标题格式错误")
            continue
        number, declared = int(header[1]), Decimal(header[2])
        label = f"段落{number}"
        if number != start_paragraph + index:
            errors.append(f"{label}：段落编号不连续")
        if not lines[1].startswith("场景：") or not lines[1][len("场景："):].strip():
            errors.append(f"{label}：缺少或错置场景：")
        cursor = _read_scene_fields(lines, 2, errors, label, True, check_scenes)
        char_names = []
        if check_scenes:
            staff = [l for l in lines if l.startswith("出场人物：")]
            if staff:
                char_names = _base_names(staff[0])
            if char_names:
                for layout_line in [l for l in lines if l.startswith("本段场景布局：")]:
                    hit = [n for n in char_names if n in layout_line]
                    if hit:
                        errors.append(
                            f"{label}：本段场景布局含人物姓名（{'、'.join(hit)}），应只写环境")
        prev_stance = []
        total = Decimal("0")
        count = 0
        pending_scene = True
        while cursor < len(lines):
            line = lines[cursor]
            if line == "制作控制卡":
                cursor += 1
                while cursor < len(lines) and not lines[cursor].startswith(("镜", "场景：", "段落") + SCENE_FIELDS):
                    cursor += 1
                continue
            if line.startswith("场景："):
                if pending_scene or not line[len("场景："):].strip():
                    errors.append(f"{label}：场景切换重复或为空")
                pending_scene = True
                cursor += 1
                cursor = _read_scene_fields(lines, cursor, errors, f"{label}换场", False, check_scenes)
                continue
            match = SHOT.fullmatch(line)
            if not match:
                errors.append(f"{label}：预期镜头标题，实际为 {line[:55]}")
                cursor += 1
                continue
            pending_scene = False
            count += 1
            shot_no, duration = int(match[1]), Decimal(match[2])
            if shot_no != next_shot:
                errors.append(f"镜{shot_no}：编号应为{next_shot}")
            next_shot = shot_no + 1
            if duration <= 0:
                errors.append(f"镜{shot_no}：时长必须大于0")
            total += duration
            cursor += 1
            body = []
            while cursor < len(lines) and not lines[cursor].startswith(("镜", "场景：", "段落")):
                body.append(lines[cursor])
                cursor += 1
            fields = [part.split("：", 1)[0] for part in body]
            allowed = [["画面", "台词/声音", "运镜"], ["画面", "本镜光影", "台词/声音", "运镜"]]
            if fields not in allowed:
                errors.append(f"镜{shot_no}：字段缺失、重复、错序或存在额外字段")
            for part in body:
                if "：" not in part or not part.split("：", 1)[1].strip():
                    errors.append(f"镜{shot_no}：空字段")
            if check_scenes and char_names:
                pic = next((part for part in body if part.startswith("画面：")), "")
                pic_text = pic.split("：", 1)[1].strip() if "：" in pic else ""
                if pic_text:
                    if COMPASS.search(pic_text):
                        errors.append(f"镜{shot_no}：画面使用罗盘方位，请改用地标或机位基准")
                    on_screen = bool(SCREEN_CONTENT.search(pic_text))
                    is_person = any(
                        re.search(rf"{re.escape(name)}(?!的)", pic_text) for name in char_names
                    ) or bool(PERSON_PRONOUN.search(pic_text))
                    if is_person and not on_screen and not _has_stance(pic_text):
                        errors.append(f"镜{shot_no}：画面未见可见角色的站位（地标＋相对方位）")
                    clauses = _stance_clauses(pic_text)
                    if prev_stance:
                        dup = sorted(set(clauses) & set(prev_stance))
                        if dup:
                            errors.append(
                                f"镜{shot_no}：站位整块重复（{dup[0][:24]}），应改为写变化")
                    prev_stance = clauses
            moves = [part for part in body if part.startswith("运镜：")]
            if len(moves) == 1:
                move_text = moves[0]
                if "摄影机" not in move_text:
                    errors.append(f"镜{shot_no}：运镜需含“摄影机”明确机位指令")
                if "焦点" not in move_text:
                    errors.append(f"镜{shot_no}：运镜需含“焦点”轨迹")
                if "结束于" not in move_text and "结束" not in move_text:
                    errors.append(f"镜{shot_no}：运镜需含“结束于”说明结束构图")
                motion_verbs = ["推", "拉", "摇", "移", "升", "降", "环绕", "固定", "复合"]
                if not any(v in move_text for v in motion_verbs):
                    errors.append(f"镜{shot_no}：运镜需用标准运动动词之一（推/拉/摇/移/升/降/环绕/固定/复合）")
                if re.search(r"\d+(?:\.\d+)?\s*步", move_text):
                    errors.append(f"镜{shot_no}：机位距离请使用公制单位（米/厘米），不得使用“步”")
                if re.search(r"\d+(?:\.\d+)?\s*(?:s\b|秒|%|％)|\d+:\d+|第[一二三四五六七八九十\d]+秒", move_text):
                    errors.append(f"镜{shot_no}：运镜内部含时间或百分比")
                if any(word in move_text for word in ["继续推进", "接上个", "同前", "状态不变", "保持不变"]):
                    errors.append(f"镜{shot_no}：运镜使用抽象依赖表达")
        if pending_scene:
            errors.append(f"{label}：场景标注后没有镜头")
        if not count:
            errors.append(f"{label}：没有有效镜头")
        if total != declared:
            errors.append(f"{label}：标题{declared}s，实际加总{total}s")
        if declared <= 0:
            errors.append(f"{label}：总时长必须大于0")
        if not Decimal("10.0") <= total <= Decimal("15.0"):
            errors.append(f"{label}：实际时长{total}s，不在10.0–15.0s")
    return errors


def _normalize_voice_description(value):
    return re.sub(r"\s+", "", value).replace("，", "·").replace("/", "·")


def _voice_speaker(line, position):
    prefix = line[:position]
    if prefix.startswith("台词/声音："):
        prefix = prefix.split("：", 1)[1]
    chunk = re.split(r"[，。；：:！？!?、\s]", prefix)[-1].strip("“”「」『』()（）")
    for marker in SPEAKER_PREFIXES:
        if chunk.startswith(marker) and len(chunk) > len(marker):
            chunk = chunk[len(marker):]
            break
    if not chunk:
        return None
    return chunk[-20:]


def validate_address(text):
    """Check on-screen speakers and actors carry visible state, gaze and contact.

    Keyword-level only: cannot judge whether the expression suits the beat or
    whether the gaze target is correct.
    """
    errors = []
    for block in re.split(r"(?m)^\s*@\s*$", text.strip()):
        if not re.search(r"段落[0-9]+｜总时长：", block):
            continue
        matches = list(re.finditer(r"(?m)^镜([0-9]+)｜([0-9]+\.[0-9])s｜([^\n]+)", block))
        for index, match in enumerate(matches):
            shot_no = int(match[1])
            scale = match[3].split("/")[0].strip()
            body = block[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(block)]
            lines = body.splitlines()
            pic = next((line[len("画面："):] for line in lines if line.startswith("画面：")), "")
            say_line = next((line for line in lines if line.startswith("台词/声音：")), "")
            if not pic:
                continue
            say_text = say_line[len("台词/声音："):] if say_line else ""
            if say_text and DIALOGUE_QUOTE.search(say_text):
                visible = []
                for anchor in VOICE_TOKEN.finditer(say_line):
                    speaker = _voice_speaker(say_line, anchor.start())
                    if not speaker:
                        continue
                    prefix = say_line[len("台词/声音："):anchor.start()]
                    clause = re.split(r"[，。；]", prefix)[-1]
                    if OFFSCREEN_MARK.search(clause):
                        continue
                    if speaker in pic:
                        visible.append(speaker)
                if visible:
                    who = "、".join(dict.fromkeys(visible))
                    if scale in CLOSE_MEDIUM_SCALE and not EXPRESSION_STATE.search(pic):
                        errors.append(f"镜{shot_no}：说话者{who}在画内，画面缺少可见神情或身体状态")
                    if not ADDRESS_GAZE.search(pic):
                        errors.append(f"镜{shot_no}：说话者{who}在画内，画面缺少投向对话对象的视线或朝向")
            if CONTACT_VERB.search(pic) and not (
                CONTACT_PART.search(pic) and CONTACT_FEEDBACK.search(pic)
            ):
                errors.append(f"镜{shot_no}：角色对角色做动作，画面缺少身体部位或接触/受力反馈")
    return errors


def validate_voices(text):
    """Validate structural voice anchors and cross-shot identity mappings."""
    errors = []
    id_to_desc = {}
    id_to_name = {}
    name_to_ids = {}
    name_to_desc = {}

    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        matches = list(VOICE_TOKEN.finditer(stripped))
        for match in matches:
            voice_id, desc = match.group(1), match.group(2).strip()
            if not stripped.startswith("台词/声音："):
                errors.append(f"第{line_no}行：音色锚点必须写在“台词/声音”字段内")
                continue
            speaker = _voice_speaker(stripped, match.start())
            if not speaker:
                errors.append(f"第{line_no}行：音色锚点前必须紧接标准资产名")
                continue
            parts = [part.strip() for part in re.split(r"[·/，,]", desc) if part.strip()]
            if not 3 <= len(parts) <= 5:
                errors.append(f"第{line_no}行：{voice_id}基础音色必须含3–5项稳定描述，当前{len(parts)}项")
            if any(word in desc for word in TEMPORARY_VOICE_WORDS):
                errors.append(f"第{line_no}行：{voice_id}基础音色含临时情绪或发声状态，应移到锚点外")
            if "待定" in desc or "TBD" in desc.upper():
                errors.append(f"第{line_no}行：{voice_id}基础音色不能使用待定占位")

            normalized_desc = _normalize_voice_description(desc)
            if voice_id in id_to_desc and id_to_desc[voice_id] != normalized_desc:
                errors.append(f"第{line_no}行：{voice_id}的基础音色描述与先前镜头不一致")
            id_to_desc.setdefault(voice_id, normalized_desc)
            if voice_id in id_to_name and id_to_name[voice_id] != speaker:
                errors.append(f"第{line_no}行：{voice_id}同时绑定到“{id_to_name[voice_id]}”和“{speaker}”")
            id_to_name.setdefault(voice_id, speaker)
            name_to_ids.setdefault(speaker, set()).add(voice_id)
            if speaker in name_to_desc and name_to_desc[speaker] != normalized_desc:
                errors.append(f"第{line_no}行：角色“{speaker}”的基础音色描述跨镜不一致")
            name_to_desc.setdefault(speaker, normalized_desc)

        if stripped.startswith("台词/声音：") and DIALOGUE_QUOTE.search(stripped) and not matches:
            errors.append(f"第{line_no}行：含对白但缺少音色锚点【Vxxx｜基础音色描述】")

    for name, ids in name_to_ids.items():
        if len(ids) > 1:
            errors.append(f"角色“{name}”使用了多个V-ID：{'、'.join(sorted(ids))}")
    cards = {}
    card_names = {}
    for match in VOICE_CARD.finditer(text):
        voice_id, name, desc = match.group(1), match.group(2).strip(), match.group(3).strip()
        if voice_id in cards:
            errors.append(f"角色音色卡：{voice_id}重复")
            continue
        cards[voice_id] = (name, _normalize_voice_description(desc))
        if name in card_names and card_names[name] != voice_id:
            errors.append(f"角色音色卡：角色“{name}”出现多个V-ID")
        card_names[name] = voice_id
        if voice_id in id_to_name and id_to_name[voice_id] != name:
            errors.append(f"角色音色卡：{voice_id}写为“{name}”，分镜绑定为“{id_to_name[voice_id]}”")
        if voice_id in id_to_desc and id_to_desc[voice_id] != _normalize_voice_description(desc):
            errors.append(f"角色音色卡：{voice_id}基础描述与分镜锚点不一致")

    return errors


def _parse_count(line):
    match = re.search(r"(\d+)\s*张", line)
    return int(match.group(1)) if match else None


def _names_after_bar(line):
    value = line.split("：", 1)[1]
    had_bar = False
    for bar in ("｜", "|"):
        if bar in value:
            value = value.split(bar, 1)[1]
            had_bar = True
            break
    if not had_bar and re.fullmatch(r"\d+\s*张", value.strip()):
        return []
    return [item.strip() for item in re.split(r"[、,，]", value) if item.strip()]


def validate_controls(text, allow_frame_anchors=False):
    """Validate optional production-control lines when explicitly requested."""
    errors = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    control_prefixes = (
        "景别策略：", "参考素材：", "复杂度：", "起始状态：", "结束状态：",
        "声音槽位：", "负面约束：", "场景人物名册：", "场景在场：", "本段入画：",
        "本段出场：", "画外在场：", "入退场：", "座位图：", "本段可见范围：",
        "参考图预算：", "场景参考：", "角色参考：", "其他参考：",
        "角色音色卡：", "音色绑定：",
    )
    present = [line for line in lines if line.startswith(control_prefixes)]
    if not present:
        return ["未找到制作控制卡（景别策略/参考素材/复杂度/起始状态/结束状态/声音槽位/负面约束）"]

    profiles = {"对话表演型", "空间叙事型", "动作奇观型"}
    has_start = any(line.startswith("起始状态：") for line in lines)
    has_end = any(line.startswith("结束状态：") for line in lines)
    if has_start != has_end:
        errors.append("制作控制卡：起始状态与结束状态必须同时存在")

    def get_line(prefix):
        return next((line for line in lines if line.startswith(prefix)), None)

    # Group-scene continuity fields.
    group_prefixes = ("场景在场：", "本段入画：", "本段出场：", "画外在场：", "入退场：", "本段可见范围：", "座位图：")
    if any(line.startswith(group_prefixes) for line in lines):
        for required in ("场景在场：", "本段入画：", "本段出场：", "入退场："):
            if get_line(required) is None:
                errors.append(f"制作控制卡：群像场景缺少{required[:-1]}")
        visible = get_line("本段可见范围：")
        if visible:
            visible_value = visible.split("：", 1)[1].strip()
            if visible_value not in {"整桌", "局部"}:
                errors.append("制作控制卡：本段可见范围只能为“整桌”或“局部”")
            if visible_value == "整桌":
                on_scene = get_line("场景在场：")
                in_frame = get_line("本段入画：")
                if on_scene and in_frame:
                    if len(_names_after_bar(on_scene)) != len(_names_after_bar(in_frame)):
                        errors.append("制作控制卡：整桌可见时，本段入画人数必须等于场景在场人数")
        on_scene = get_line("场景在场：")
        in_frame = get_line("本段入画：")
        if on_scene and in_frame and len(_names_after_bar(in_frame)) > len(_names_after_bar(on_scene)):
            errors.append("制作控制卡：本段入画人物不能多于场景在场人物")

    # Nine-image reference budget.
    budget_line = get_line("参考图预算：")
    scene_line = get_line("场景参考：")
    role_line = get_line("角色参考：")
    other_line = get_line("其他参考：")
    if budget_line is None or scene_line is None or role_line is None:
        errors.append("制作控制卡：必须写明参考图预算、场景参考和角色参考")
    else:
        budget = _parse_count(budget_line)
        scene_count = _parse_count(scene_line)
        role_count = _parse_count(role_line)
        other_count = _parse_count(other_line) if other_line else 0
        if budget is None or scene_count is None or role_count is None:
            errors.append("制作控制卡：参考图预算、场景参考和角色参考必须写明“N张”")
        else:
            if scene_count < 1:
                errors.append("制作控制卡：场景参考至少1张，多场景按实际图片计数")
            if role_count > 8:
                errors.append("制作控制卡：角色参考最多8张")
            if other_count is None:
                errors.append("制作控制卡：其他参考必须写明“N张”")
                other_count = 0
            total = scene_count + role_count + other_count
            if total > 9:
                errors.append(f"制作控制卡：参考图总数{total}张，超过9张上限")
            if budget != total:
                errors.append(f"制作控制卡：参考图预算{budget}张与实际合计{total}张不一致")
            for prefix in ("场景参考：", "角色参考：", "其他参考："):
                line = get_line(prefix)
                if line:
                    declared = _parse_count(line)
                    names = _names_after_bar(line)
                    if declared is not None and names and declared != len(names):
                        errors.append(f"制作控制卡：{prefix[:-1]}写{declared}张，但列出了{len(names)}项")

    for line in lines:
        if line.startswith("景别策略："):
            value = line.split("：", 1)[1].strip()
            if value not in profiles:
                errors.append(f"制作控制卡：景别策略必须为{ '、'.join(sorted(profiles)) }之一")
        if line.startswith("参考素材："):
            value = line.split("：", 1)[1].strip()
            if not value:
                errors.append("制作控制卡：参考素材不能为空")
            if re.search(r"@\s*[\[［]", value):
                errors.append("制作控制卡：参考素材默认不得使用 @[...] 引用")
        if line.startswith(("起始状态：", "结束状态：", "复杂度：", "声音槽位：", "场景人物名册：", "座位图：", "角色音色卡：", "音色绑定：")):
            if not line.split("：", 1)[1].strip():
                errors.append(f"制作控制卡：{line.split('：', 1)[0]}不能为空")
        if line.startswith("负面约束："):
            value = line.split("：", 1)[1].strip()
            if not value:
                errors.append("制作控制卡：负面约束不能为空")
            items = [x for x in re.split(r"[；;]", value) if x.strip()]
            if len(items) > 8:
                errors.append("制作控制卡：负面约束建议不超过8条")
        if not allow_frame_anchors and ("首帧锚定" in line or "首帧锁定" in line):
            errors.append("制作控制卡：默认不使用首帧锚定/首帧锁定")
        if "STYLE LOCK" in line.upper() or line.startswith("项目级风格锁："):
            errors.append("制作控制卡：默认不新增项目级风格锁")
    return errors


def check_editing(text):
    """Return explicit editing violations and heuristic review items separately.

    Timing and repetition cannot establish dramatic value; never fail them alone.
    Inspect visual instructions, not dialogue or diegetic sound descriptions.
    """
    errors, reviews = [], []
    shots = []
    for block in re.split(r"(?m)^\s*@\s*$", text.strip()):
        header = re.search(r"段落([0-9]+)｜总时长：([0-9]+\.[0-9])s", block)
        if not header:
            continue
        paragraph_shots = []
        matches = list(re.finditer(r"(?m)^镜([0-9]+)｜([0-9]+\.[0-9])s｜([^\n]+)", block))
        for i, match in enumerate(matches):
            body = block[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(block)]
            visual = "\n".join(line for line in body.splitlines() if line.startswith(("画面：", "运镜：")))
            # Quoted text can be signs or source dialogue, not camera directions.
            visual = re.sub(r"[“「][^”」]*[”」]", "", visual)
            move = next((line for line in body.splitlines() if line.startswith("运镜：")), "")
            shot = (int(match[1]), Decimal(match[2]), match[3].strip(), move)
            shots.append(shot)
            paragraph_shots.append(shot)
            for clause in re.split(r"[，。；;\n]", visual):
                if re.search(r"(?:禁止|不要|不得|不使用|不用|无|不加|避免)[^，。；;]*$", clause):
                    continue
                if re.search(r"叠化|淡入|淡出|(?:溶解|闪白|黑场|遮罩|遮挡|甩镜|变形|画框|擦除)(?:过渡|转场)|(?:转场|过渡)(?:效果|特效)|(?:渐隐|渐显|渐变)至|切(?:入|至)黑场|画框穿越|cross.?fade|dissolve|fade.?out|fade.?in", clause, re.I):
                    errors.append(f"镜{shot[0]}：含转场特效指令，镜间只能硬切：{clause.strip()}")
            if shot[1] > Decimal('4.0'):
                reviews.append(f"镜{shot[0]}：{shot[1]}秒，复核切点及持续观看依据；多节点固定对白长于6秒原则上拆镜")
        if Decimal('10.0') <= Decimal(header[2]) <= Decimal('15.0') and 1 <= len(paragraph_shots) <= 2:
            reviews.append(f"段落{header[1]}：仅{len(paragraph_shots)}镜，复核是否遗漏有效切点")
        pushes = [shot for shot in paragraph_shots if has_push_pull(shot[3])]
        if paragraph_shots and len(pushes) * 2 > len(paragraph_shots):
            reviews.append(f"段落{header[1]}：推拉/变焦超过半数，优先重排为固定机位之间硬切")
    for i, shot in enumerate(shots):
        if i + 1 < len(shots) and not re.search(r"(?:[，；;]\s*|\s)硬切\s*[。.]?$", shot[3]):
            errors.append(f"镜{shot[0]}：有后继镜头，运镜末尾须明确写硬切")
        if i and shot[2] == shots[i - 1][2]:
            reviews.append(f"镜{shots[i - 1][0]}–镜{shot[0]}：标题取景相同，核对真实观察对象/角度变化，勿仅改标签")
        if i and has_push_pull(shot[3]) and has_push_pull(shots[i - 1][3]):
            reviews.append(f"镜{shots[i - 1][0]}–镜{shot[0]}：连续推拉/变焦，核对是否应硬切换取景")
    return errors, reviews


def has_push_pull(move):
    # Avoid matching position phrases such as “距拉车人” or action subjects.
    return bool(re.search(r"[，；;]\s*(?:缓慢|缓缓|快速|轻微|轻|快|慢)?(?:推近|推进|推镜|推远|拉远|拉近|拉镜|推拉|变焦|光学推|光学拉|快推|复合[^；\n]*(?:推|拉))", move))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--start-shot", type=int, default=1)
    parser.add_argument("--start-paragraph", type=int, default=1)
    parser.add_argument("--check-controls", action="store_true", help="检查可选制作控制卡")
    parser.add_argument("--check-voices", action="store_true", help="检查音色锚点、跨镜绑定及对白/动作指向（画内说话者的神情与视线、动作的接触与反馈）")
    parser.add_argument("--check-editing", action="store_true", help="检查硬切与转场特效，列出长镜/低镜数/推拉密集待复核项")
    parser.add_argument("--check-scenes", action="store_true", help="严格检查每场布局、段内换场光影及环境字段外部依赖；不判断空间语义")
    parser.add_argument("--allow-frame-anchors", action="store_true", help="允许控制卡出现首帧锚定/首帧锁定")
    args = parser.parse_args()
    if args.start_shot < 1 or args.start_paragraph < 1:
        parser.error("起始编号必须大于0")
    try:
        content = args.file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        print(f"无法读取UTF-8分镜文件：{exc}", file=sys.stderr)
        return 2
    errors = validate(content, args.start_shot, args.start_paragraph, check_scenes=args.check_scenes)
    if args.check_controls:
        errors.extend(validate_controls(content, allow_frame_anchors=args.allow_frame_anchors))
    if args.check_voices:
        errors.extend(validate_voices(content))
        errors.extend(validate_address(content))
    if args.check_editing:
        editing_errors, reviews = check_editing(content)
        errors.extend(editing_errors)
        for review in reviews:
            print(f"REVIEW: {review}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("PASS: 结构检查通过；仍需人工核对剧情、对白、连续性、可执行性和实际音色绑定。")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
