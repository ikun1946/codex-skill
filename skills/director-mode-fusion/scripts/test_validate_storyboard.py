"""Regression tests for scene metadata and existing storyboard invariants."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from validate_storyboard import (
    validate, validate_voices, validate_address, check_editing, validate_controls
)


def shot(number, duration='4.0', last=False):
    stances = (
        '林晚站在柜台前，右手放下信封，视线投向画右。',
        '林晚仍在柜台外侧半步处，身体侧向画左，指尖搭在台沿。',
        '林晚退到柜台与门口的通道中段，肩膀转向入口。',
    )
    picture = stances[(number - 1) % len(stances)]
    return (
        f'镜{number}｜{duration}s｜中景/平视/三分构图\n'
        f'画面：{picture}\n'
        '台词/声音：无台词；闭口，纸张落台轻响。\n'
        '运镜：摄影机在柜台外侧·距地1.5米·平视·中景·距林晚2米看林晚，固定机位；'
        f'焦点稳定在信封与手部；结束于信封落台的中景构图，{"结束" if last else "硬切"}\n'
    )


def blocking_paragraph(pics, layout='本段场景布局：柜台与入口相对，柜台前留有通道。\n', names='林晚'):
    """Paragraph built from explicit 画面 texts, for blocking-rule tests."""
    header = (
        f'段落1｜总时长：{4.0 * len(pics):.1f}s\n场景：店铺 夜 内\n'
        f'{layout}出场人物：{names}\n本段统一光影/质感：柜台顶灯照亮台面，入口较暗。\n'
    )
    body = ''
    for index, picture in enumerate(pics, 1):
        tail = '结束' if index == len(pics) else '硬切'
        body += (
            f'镜{index}｜4.0s｜中景/平视/三分构图\n'
            f'画面：{picture}\n'
            '台词/声音：无台词；闭口。\n'
            '运镜：摄影机在柜台外侧·距地1.5米·平视·中景·距林晚2米看林晚，固定机位；'
            f'焦点稳定在手部；结束于中景构图，{tail}\n'
        )
    return header + body


def paragraph(new=True, switch=False, number=1, first=1):
    layout = '本段场景布局：柜台与入口相对，柜台前留有通道。\n'
    header = (
        f'段落{number}｜总时长：12.0s\n场景：店铺 夜 内\n'
        + (layout if new else '')
        + '出场人物：林晚\n本段统一光影/质感：柜台顶灯照亮台面，入口较暗。\n'
    )
    transition = ''
    if switch:
        transition = '场景：店铺-门前 夜 外\n'
        if new:
            transition += ('本段场景布局：入口门槛外连接平坦步道。\n'
                           '本场光影/质感：门灯照亮门槛，步道向远处渐暗。\n')
    return header + shot(first) + transition + shot(first + 1) + shot(first + 2, last=True)


class SceneFormatTests(unittest.TestCase):
    def test_legacy_without_strict_mode(self):
        self.assertEqual(validate(paragraph(False)), [])
        self.assertEqual(validate(paragraph(False, True)), [])

    def test_legacy_requires_layout_in_strict_mode(self):
        self.assertTrue(validate(paragraph(False), check_scenes=True))

    def test_new_single_scene_and_switch(self):
        for switch in (False, True):
            with self.subTest(switch=switch):
                self.assertEqual(validate(paragraph(switch=switch)), [])
                self.assertEqual(validate(paragraph(switch=switch), check_scenes=True), [])

    def test_missing_switch_layout_and_light(self):
        text = paragraph(switch=True)
        for line in ('本段场景布局：入口门槛外连接平坦步道。\n',
                     '本场光影/质感：门灯照亮门槛，步道向远处渐暗。\n'):
            with self.subTest(line=line):
                self.assertTrue(validate(text.replace(line, ''), check_scenes=True))

    def test_duplicate_empty_misordered_and_orphan_fields(self):
        text = paragraph(switch=True)
        layout = '本段场景布局：柜台与入口相对，柜台前留有通道。\n'
        switch_layout = '本段场景布局：入口门槛外连接平坦步道。\n'
        light = '本场光影/质感：门灯照亮门槛，步道向远处渐暗。\n'
        broken = [
            text.replace(layout, layout + layout),
            text.replace(layout, '本段场景布局：\n'),
            text.replace(layout + '出场人物：林晚\n', '出场人物：林晚\n' + layout),
            text.replace(switch_layout + light, light + switch_layout),
            text.replace(light, light + light),
            text.replace(light, '本场光影/质感：\n'),
            text.replace('镜3｜', light + '镜3｜'),
            text.replace('镜3｜', '未知场景字段：冗余\n镜3｜'),
        ]
        for i, value in enumerate(broken):
            for strict in (False, True):
                with self.subTest(case=i, strict=strict):
                    self.assertTrue(validate(value, check_scenes=strict))

    def test_initial_scene_light_cannot_use_switch_field(self):
        self.assertTrue(validate(paragraph().replace('本段统一光影/质感：', '本场光影/质感：')))

    def test_switched_scene_cannot_use_initial_field(self):
        self.assertTrue(validate(paragraph(switch=True).replace('本场光影/质感：', '本段统一光影/质感：')))

    def test_external_dependencies_and_ordinary_continue(self):
        text = paragraph()
        for value in ('同前', '同上段', '沿用上一段', '参见前场'):
            with self.subTest(value=value):
                self.assertTrue(validate(text.replace('柜台与入口相对，柜台前留有通道。', value), check_scenes=True))
        self.assertEqual(validate(text.replace('柜台前留有通道', '通道继续延伸至入口'), check_scenes=True), [])
        self.assertEqual(validate(text.replace('柜台前留有通道', '相同上悬窗位于柜台后方墙上'), check_scenes=True), [])

    def test_light_dependency_in_new_scope(self):
        self.assertTrue(validate(paragraph(switch=True).replace('门灯照亮门槛，步道向远处渐暗。', '同前'), check_scenes=True))

    def test_consecutive_empty_switch_and_trailing_switch(self):
        text = paragraph(switch=True)
        self.assertTrue(validate(text.replace('场景：店铺-门前', '场景：店铺-侧门 夜 外\n场景：店铺-门前')))
        self.assertTrue(validate(text + '场景：巷口 夜 外\n'))

    def test_switch_before_any_shot_rejected(self):
        self.assertTrue(validate(paragraph().replace('镜1｜', '场景：巷口 夜 外\n镜1｜')))

    def test_code_fence_multiple_paragraphs_and_nondefault_numbers(self):
        text = paragraph(number=8, first=31) + '@\n' + paragraph(number=9, first=34)
        self.assertEqual(validate('```text\n' + text + '```', 31, 8, check_scenes=True), [])

    def test_total_duration_and_numbering_remain_enforced(self):
        for old, new in [('12.0s', '11.0s'), ('镜2｜', '镜4｜'), ('段落1｜', '段落2｜'), ('4.0s', '0.0s')]:
            with self.subTest(old=old):
                self.assertTrue(validate(paragraph().replace(old, new), check_scenes=True))

    def test_shot_fields_remain_strict(self):
        for old, new in [('画面：', '描述：'), ('台词/声音：无台词；闭口，纸张落台轻响。\n', ''), ('焦点', '观察位置')]:
            with self.subTest(old=old):
                self.assertTrue(validate(paragraph().replace(old, new), check_scenes=True))

    def test_voice_checks_unchanged(self):
        text = paragraph().replace('无台词；闭口，纸张落台轻响。', '林晚【V001｜成年女声·中音·清亮】对门口说：“请进。”')
        self.assertEqual(validate_voices(text), [])
        self.assertTrue(validate_voices(text.replace('V001｜成年女声·中音·清亮', 'V001｜成年女声·中音·沙哑', 1)))

    def test_editing_errors_still_detected_with_new_metadata(self):
        self.assertEqual(check_editing(paragraph(switch=True))[0], [])
        self.assertTrue(check_editing(paragraph().replace('，硬切', '，叠化', 1))[0])

    def test_blocking_requires_stance_for_person_shot(self):
        text = blocking_paragraph(['她抬手按住他的肩。',
                                   '林晚站在柜台前，右手放下信封。',
                                   '林晚退到通道中段，肩膀转向入口。'])
        errors = validate(text, check_scenes=True)
        self.assertEqual(len([e for e in errors if '站位' in e]), 1, errors)
        self.assertEqual(validate(text), [])

    def test_blocking_rejects_compass_direction(self):
        text = blocking_paragraph(['林晚站在门东侧的柜台前，右手放下信封。',
                                   '林晚仍在柜台外侧半步处，指尖搭在台沿。',
                                   '林晚退到通道中段，肩膀转向入口。'])
        errors = validate(text, check_scenes=True)
        self.assertEqual(len([e for e in errors if '罗盘' in e]), 1, errors)

    def test_blocking_rejects_layout_with_character_name(self):
        text = blocking_paragraph(['林晚站在柜台前，右手放下信封。',
                                   '林晚仍在柜台外侧半步处，指尖搭在台沿。',
                                   '林晚退到通道中段，肩膀转向入口。'],
                                  layout='本段场景布局：柜台与入口相对，林晚惯常的位置前留有通道。\n')
        errors = validate(text, check_scenes=True)
        self.assertEqual(len([e for e in errors if '布局含人物姓名' in e]), 1, errors)

    def test_blocking_rejects_duplicated_stance(self):
        text = blocking_paragraph(['林晚站在柜台前，右手放下信封。',
                                   '林晚站在柜台前，指节停在信封边缘。',
                                   '林晚退到通道中段，肩膀转向入口。'])
        errors = validate(text, check_scenes=True)
        self.assertEqual(len([e for e in errors if '整块重复' in e]), 1, errors)

    def test_unregistered_character_in_picture_is_rejected(self):
        first = blocking_paragraph(['林晚站在柜台前，视线落在周砚脸上。',
                                    '林晚退到通道中段，肩膀转向入口。',
                                    '林晚站在柜台前，指节抵着信封边缘。'],
                                   names='林晚')
        second = blocking_paragraph(['周砚站在柜台前，视线落向门外。',
                                     '周砚退到通道中段，肩膀转向入口。',
                                     '周砚站在柜台前，指节抵着信封边缘。'],
                                    names='周砚').replace('段落1｜', '段落2｜')
        text = first + '\n@\n' + second
        errors = validate(text, check_scenes=True)
        self.assertTrue(any('未登记角色' in e for e in errors), errors)

    def test_image_budget_still_enforced(self):
        card = '制作控制卡\n参考图预算：10张\n场景参考：2张｜店内、门前\n角色参考：8张\n'
        self.assertTrue(validate_controls(paragraph() + card))

    def test_cli_strict_mode_and_legacy_exit_codes(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            path = Path(tmp) / 'story.md'
            for text, flags, expected in [(paragraph(), ['--check-scenes', '--check-editing', '--check-voices'], 0),
                                           (paragraph(False), [], 0),
                                           (paragraph(False), ['--check-scenes'], 1)]:
                path.write_text(text, encoding='utf-8-sig')
                result = subprocess.run([sys.executable, str(Path(__file__).with_name('validate_storyboard.py')), str(path)] + flags,
                                        capture_output=True)
                self.assertEqual(result.returncode, expected, result.stdout.decode('utf-8', errors='replace'))


class AddressChecks(unittest.TestCase):
    def _text(self, picture, say, scale='中近景'):
        return (
            '段落1｜总时长：12.0s\n场景：餐厅 夜 内\n'
            '本段场景布局：长桌居中，四椅分列。\n'
            '出场人物：林晚；周砚\n'
            '本段统一光影/质感：吊灯暖黄。\n'
            f'镜1｜12.0s｜{scale}/平视/三分构图\n'
            f'画面：{picture}\n'
            f'台词/声音：{say}\n'
            '运镜：摄影机在林晚右前方·距地1.4米·平视·中近景·距林晚1.2米看林晚，固定机位；'
            '焦点稳定在她的眼睛；结束于胸口以上，结束\n'
        )

    VOICE = '林晚【V001｜成年女声·中音·清亮·语速适中】对周砚说：“先坐。”'

    def test_missing_expression_is_rejected(self):
        text = self._text('林晚坐在桌边，双手放在膝上，视线钉在周砚脸上。', self.VOICE)
        errors = validate_address(text)
        self.assertEqual(len([e for e in errors if '缺少可见神情' in e]), 1, errors)

    def test_missing_gaze_is_rejected(self):
        text = self._text('林晚坐在桌边，眉心压低，双手放在膝上。', self.VOICE)
        errors = validate_address(text)
        self.assertEqual(len([e for e in errors if '缺少投向' in e]), 1, errors)

    def test_complete_address_passes(self):
        text = self._text('林晚坐在桌边，眉心压低，视线钉在周砚脸上。', self.VOICE)
        self.assertEqual(validate_address(text), [])

    def test_offscreen_speaker_not_required_on_screen(self):
        text = self._text('周砚坐在桌边，眉心压低，视线投向画左。',
                          '林晚（画外）【V001｜成年女声·中音·清亮·语速适中】对周砚说：“先坐。”')
        self.assertEqual(validate_address(text), [])

    def test_contact_action_requires_hand_and_feedback(self):
        text = self._text('周砚把外套递给林晚。', '无台词。')
        errors = validate_address(text)
        self.assertEqual(len([e for e in errors if '动作' in e]), 1, errors)
        fixed = self._text('周砚把外套递到林晚手边，掌心托着衣领，等她抬手才松开。', '无台词。')
        self.assertEqual(validate_address(fixed), [])


class RepetitionChecks(unittest.TestCase):
    def _shot(self, number, picture, last=False):
        return (
            f'镜{number}｜4.0s｜中近景/平视/三分构图\n'
            f'画面：{picture}\n'
            '台词/声音：无台词。\n'
            '运镜：摄影机在柜台外侧·距地1.5米·平视·中近景·距林晚2米看林晚，固定机位；'
            f'焦点稳定在手部；结束于中景构图，{"结束" if last else "硬切"}\n'
        )

    def _paragraph(self, pictures, number=1):
        body = ''.join(self._shot(i, pic, i == len(pictures)) for i, pic in enumerate(pictures, 1))
        return (
            f'段落{number}｜总时长：{4.0 * len(pictures):.1f}s\n场景：店铺 夜 内\n'
            '本段场景布局：柜台与入口相对，柜台前留有通道。\n'
            '出场人物：林晚\n本段统一光影/质感：柜台顶灯照亮台面。\n' + body
        )

    def test_same_clause_in_one_paragraph_is_flagged(self):
        text = self._paragraph(['林晚站在柜台前，眉心压着，视线钉在来人脸上。',
                                '林晚仍站在柜台前，眉心压着，视线钉在来人脸上。'])
        _, reviews = check_editing(text)
        self.assertTrue(any('相同描写' in r for r in reviews), reviews)

    def test_global_repetition_is_flagged(self):
        text = '\n@\n'.join(
            self._paragraph([f'林晚站在柜台前第{n}步处，眉心平着，手指搭在台沿。'], number=n)
            for n in range(1, 10))
        _, reviews = check_editing(text)
        self.assertTrue(any('机械重复' in r and '眉心平着' in r for r in reviews), reviews)

    def test_distinct_descriptions_are_not_flagged(self):
        text = self._paragraph(['林晚站在柜台前，眉心压着，视线钉在来人脸上。',
                                '林晚退到门口，肩膀转向入口，指节抵着信封边缘。'])
        _, reviews = check_editing(text)
        self.assertFalse(any('相同描写' in r for r in reviews), reviews)


class DirectorEvolutionTests(unittest.TestCase):
    def test_pacing_profiles_burst_lingering_outro(self):
        # 1. Burst 档位 (6.0 - 9.0s)
        burst_text = (
            '段落1 [Burst]｜总时长：7.5s\n场景：客厅 夜 内\n'
            '本段场景布局：正门进来是玄关，茶几在沙发前。\n'
            '出场人物：林晚；周砚\n'
            '本段统一光影/质感：吊灯暖黄。\n'
            '镜1｜3.5s｜中景/平视/双人构图\n'
            '画面：站在茶几前的林晚把日记本放下，周砚自玄关走入，两人视线对上。\n'
            '台词/声音：无台词；闭口。\n'
            '运镜：摄影机在两人侧方·距地1.4米·平视·中景·距主体2米看两人，固定；焦点稳定在桌面；结束于两人，硬切\n'
            '镜2｜4.0s｜近景/平视/画右构图\n'
            '画面：周砚跨步来到茶几前，目光直视林晚，喉结极慢滚动，手指压在封皮上。\n'
            '台词/声音：无台词；闭口。\n'
            '运镜：摄影机在周砚正面·距地1.4米·平视·近景·距主体1米看周砚，固定；焦点稳定在他的眼睛；结束于锁骨以上，结束\n'
        )
        self.assertEqual(validate(burst_text, check_scenes=True), [])
        # 超出 Burst 范围应拦截
        self.assertTrue(validate(burst_text.replace('7.5s', '10.5s').replace('4.0s', '7.0s'), check_scenes=True))

        # 2. Lingering 档位 (15.0 - 20.0s)
        lingering_text = burst_text.replace('段落1 [Burst]｜总时长：7.5s', '段落1 [Lingering]｜总时长：16.0s').replace('3.5s', '8.0s').replace('4.0s', '8.0s')
        self.assertEqual(validate(lingering_text, check_scenes=True), [])

        # 3. Outro 档位 (>=5.0s)
        outro_text = burst_text.replace('段落1 [Burst]｜总时长：7.5s', '段落1 [Outro]｜总时长：5.5s').replace('3.5s', '2.5s').replace('4.0s', '3.0s')
        self.assertEqual(validate(outro_text, check_scenes=True), [])

    def test_closeup_stance_inheritance(self):
        # 首镜已建立站位，特写镜头聚焦局部表演，无需强行重复地标打卡
        inherit_text = (
            '段落1｜总时长：11.0s\n场景：客厅 夜 内\n'
            '本段场景布局：正门进来是玄关，茶几在沙发前。\n'
            '出场人物：林晚\n'
            '本段统一光影/质感：吊灯暖黄。\n'
            '镜1｜3.5s｜中景/平视/三分构图\n'
            '画面：站在茶几前的林晚放下玻璃杯，目光看向门外。\n'
            '台词/声音：无台词；闭口。\n'
            '运镜：摄影机在茶几侧方·距地1.4米·平视·中景·距主体2米看林晚，固定；焦点稳定在水杯；结束于中景，硬切\n'
            '镜2｜3.5s｜特写/平视/局部构图\n'
            '画面：林晚发颤的指尖死死扣紧泛黄纸页边缘，指节泛白，微颤的唇线泄露内心的动摇。\n'
            '台词/声音：无台词；闭口。\n'
            '运镜：摄影机在桌面正上方·距地1.2米·平视·特写·距主体0.6米看手部，固定；焦点稳定在指尖；结束于特写，硬切\n'
            '镜3｜4.0s｜近景/平视/画右构图\n'
            '画面：林晚靠在沙发靠背上，深沉的视线投向虚空，长睫微垂。\n'
            '台词/声音：无台词；闭口。\n'
            '运镜：摄影机在林晚正前方·距地1.4米·平视·近景·距主体1米看林晚，固定；焦点稳定在她的双眼；结束于锁骨以上，结束\n'
        )
        self.assertEqual(validate(inherit_text, check_scenes=True), [])

    def test_enhanced_expression_and_gaze_semantics(self):
        # 测试扩展后的丰富视听动词（如直视、凝视、眼眸、下唇颤抖、屏息等）
        dialogue_text = (
            '段落1｜总时长：11.0s\n场景：客厅 夜 内\n'
            '本段场景布局：正门进来是玄关，茶几在沙发前。\n'
            '出场人物：林晚；周砚\n'
            '本段统一光影/质感：吊灯暖黄。\n'
            '镜1｜5.5s｜近景/平视/画右构图\n'
            '画面：坐在茶几旁沙发上的林晚目光直视周砚，下唇微微发颤，清澈的眼眸里蓄满泪水。\n'
            '台词/声音：林晚【V001｜成年女声·中音·清亮·语速适中】对周砚说：“这就是全部真相。”\n'
            '运镜：摄影机在林晚正前方·距地1.4米·平视·近景·距主体1米看林晚，固定；焦点稳定在她的眼睛；结束于锁骨以上，硬切\n'
            '镜2｜5.5s｜近景/平视/画左构图\n'
            '画面：站在茶几前一步处的周砚目光凝视着林晚，喉结极其缓慢地滑动，屏息听着她的一字一句。\n'
            '台词/声音：周砚【V002｜成年男声·中低音·音质清晰·语速适中】看着林晚低声道：“我知道了。”\n'
            '运镜：摄影机在周砚正前方·距地1.4米·平视·近景·距主体1米看周砚，固定；焦点稳定在他的眼睛；结束于锁骨以上，结束\n'
        )
        self.assertEqual(validate(dialogue_text, check_scenes=True), [])
        self.assertEqual(validate_address(dialogue_text), [])


if __name__ == '__main__':
    unittest.main()
