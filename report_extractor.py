import re
from datetime import datetime
import pandas as pd

# 채팅 라인 정규표현식
chat_line_pattern = re.compile(
    r"^((?:\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.)|(?:\d{4}년\s*\d{1,2}월\s*\d{1,2}일))"
    r"\s*(오전|오후)\s*(\d{1,2}:\d{2}),?\s*(.+?)\s*[:：]\s*(.+)$"
)
# 알림/입장 통보 패턴
notification_pattern = re.compile(r"^\d{4}년?\.? .*?\d{1,2}월.*?:$")
# 리포트 시작 패턴
report_pattern = re.compile(r"부동\s*&\s*작업\s*(보고|공유)", re.IGNORECASE)

# 내부 알림성 날짜-시간 패턴 (메시지 내부)
skip_inner_pattern = re.compile(
    r"^(?:\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.)\s*(?:오전|오후)\s*\d{1,2}:\d{2}:."
)

def convert_to_24h(time_str, period):
    """오전/오후 + HH:MM -> 24시간 HH:MM"""
    hour, minute = map(int, time_str.split(':'))
    if period == '오후' and hour != 12:
        hour += 12
    if period == '오전' and hour == 12:
        hour = 0
    return f"{hour:02}:{minute:02}"


def parse_chat_lines(lines):
    """
    리스트 형태의 채팅 텍스트(한 줄씩)에서 메시지 dict 리스트 생성
    각 dict: {'date': date, 'sender': str, 'time': 'HH:MM', 'message': str}
    """
    results = []
    current_date = None
    current_sender = None
    current_time = None
    current_message = ""

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r'^\d{4}년', line):
            continue
        if notification_pattern.match(line):
            continue

        m = chat_line_pattern.match(line)
        if m:
            # 이전 메시지 저장
            if current_message:
                results.append({
                    'date': current_date,
                    'sender': current_sender,
                    'time': current_time,
                    'message': current_message.strip()
                })
            date_str, period, time_str, sender, message = m.groups()
            # 날짜 파싱
            if '년' in date_str:
                current_date = datetime.strptime(date_str, "%Y년 %m월 %d일").date()
            else:
                current_date = datetime.strptime(date_str, "%Y. %m. %d.").date()
            current_sender = sender.strip()
            current_time = convert_to_24h(time_str, period)
            current_message = message.strip()
        elif current_message:
            current_message += f"\n{line}"

    # 마지막 메시지
    if current_message:
        results.append({
            'date': current_date,
            'sender': current_sender,
            'time': current_time,
            'message': current_message.strip()
        })
    return results


def parse_chat_file(filepath):
    """파일 경로로부터 채팅 메시지 파싱"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    return parse_chat_lines(lines)


def parse_chat_text(text):
    """텍스트 블록으로부터 채팅 메시지 파싱"""
    lines = text.splitlines()
    return parse_chat_lines(lines)


def extract_report_data(messages):
    """
    파싱된 메시지에서 리포트 메시지를 추출하여 DataFrame으로 반환
    """
    records = []
    target_fields = ['종류','호기','공정','발생시간','조치완료','작업자','현상','조치']
    time_val_pattern = re.compile(r"(?:\d{4}.*?\d{1,2}:\d{2})?\s*(오전|오후)?\s*(\d{1,2}:\d{2})")

    for msg in messages:
        if not report_pattern.search(msg['message']):
            continue
        field_data = {f: "" for f in target_fields}
        current_field = None
        just_parsed_operator = False

        for raw in msg['message'].splitlines():
            line = raw.strip()
            if not line:
                continue
            if skip_inner_pattern.match(line):
                continue
            # 필드 매칭
            matched = False
            for field in target_fields:
                m = re.match(fr"^{field}\s*[:：]?\s*(.*)$", line)
                if m:
                    current_field = field
                    val = m.group(1).strip()
                    if field in ['발생시간','조치완료']:
                        tm = time_val_pattern.search(val)
                        if tm:
                            period, ts = tm.groups()
                            val = convert_to_24h(ts, period) if period else ts
                    field_data[field] = val
                    matched = True
                    just_parsed_operator = (field == '작업자')
                    break
                if line == field:
                    current_field = field
                    matched = True
                    just_parsed_operator = (field == '작업자')
                    break
            if matched:
                continue
            # 작업자 다음 라인 -> 현상
            if just_parsed_operator:
                current_field = '현상'
                just_parsed_operator = False
            if current_field:
                field_data[current_field] += f"\n{line}"

        field_data['날짜'] = msg['date']
        records.append(field_data)

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # 호기 정규화
    df['호기'] = (
        df['호기']
        .str.replace(r'[()]','', regex=True)
        .str.strip()
        .str.lstrip('#')
        .apply(lambda x: f"#{x}")
    )
    # 중복 제거
    df = df.drop_duplicates(subset=['현상','조치','발생시간']).reset_index(drop=True)
    # 날짜/시간 포맷
    df['날짜'] = pd.to_datetime(df['날짜']).dt.strftime('%Y-%m-%d')
    df['발생시간'] = df['발생시간'].where(df['발생시간'].str.match(r'^\d{2}:\d{2}$'), '')
    df['조치완료'] = df['조치완료'].where(df['조치완료'].str.match(r'^\d{2}:\d{2}$'), '')
    # 시간 상호 채우기
    df[['발생시간','조치완료']] = df[['발생시간','조치완료']].replace('', pd.NA)
    df['발생시간'] = df['발생시간'].fillna(df['조치완료'])
    df['조치완료'] = df['조치완료'].fillna(df['발생시간'])
    df[['발생시간','조치완료']] = df[['발생시간','조치완료']].astype(str)
    # 작업자 기본값
    df['작업자'] = df['작업자'].str.strip().replace('', '-')
    # 빈 줄 제거 helper
    def strip_blank(s): return '\n'.join([ln for ln in s.splitlines() if ln.strip()])
    for c in target_fields:
        df[c] = df[c].apply(strip_blank)
    # 공정 대문자
    df['공정'] = df['공정'].where(~df['공정'].str.fullmatch(r"[A-Za-z\s]+"), df['공정'].str.upper())
    # 처리시간 계산
    def calc(row):
        try:
            t1 = datetime.strptime(row['발생시간'], '%H:%M')
            t2 = datetime.strptime(row['조치완료'], '%H:%M')
        except:
            return None
        diff = abs((t2 - t1).total_seconds()/60)
        if diff > 720:
            diff = abs(diff - 1440)
        if diff > 600:
            diff = abs(diff - 720)
        return int(diff)
    df['처리시간(분)'] = df.apply(calc, axis=1)
    # 필터링
    eng = lambda s: sum(c.isalpha() and c.isascii() for c in str(s))/len(str(s).replace(' ','')) if str(s).strip() else 0
    mask = (df['조치'].apply(eng) > 0.5) | (df[target_fields].apply(lambda r: sum(not v.strip() for v in r), axis=1) >= 3)
    df = df[~mask].reset_index(drop=True)
    # 컬럼 순서
    cols = ['날짜'] + target_fields[:5] + ['처리시간(분)'] + target_fields[5:]
    return df[cols]
