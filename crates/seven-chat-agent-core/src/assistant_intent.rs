/// 助理意图层：只负责把输入转为结构化意图，不关心执行。
#[derive(Debug, Clone)]
pub enum AssistantIntent {
    TodoCreate {
        title: String,
        detail: Option<String>,
        priority: i64,
        remind_after_seconds: Option<i64>,
    },
    ReminderAfter {
        title: String,
        detail: Option<String>,
        after_seconds: i64,
    },
    ReminderDailyAt {
        title: String,
        detail: Option<String>,
        hour: u32,
        minute: u32,
        timezone: String,
    },
}

/// 轻量规则识别：用于“X 分钟后叫我/提醒我”这类定时提醒。
/// 后续可替换为 LLM/NLU，不影响 planner 与执行层。
pub fn parse_quick_intent(raw: &str) -> Option<AssistantIntent> {
    let text = raw.trim();
    if text.is_empty() {
        return None;
    }
    if let Some((hour, minute, content)) = parse_daily_reminder(text) {
        return Some(AssistantIntent::ReminderDailyAt {
            title: if content.is_empty() {
                format!("每天 {:02}:{:02} 提醒", hour, minute)
            } else {
                content
            },
            detail: Some(text.to_string()),
            hour,
            minute,
            timezone: "Asia/Shanghai".to_string(),
        });
    }
    let (after_seconds, content) = parse_after_reminder(text)?;
    Some(AssistantIntent::ReminderAfter {
        title: if content.is_empty() {
            "到点提醒".to_string()
        } else {
            content.to_string()
        },
        detail: Some(text.to_string()),
        after_seconds,
    })
}

fn parse_daily_reminder(text: &str) -> Option<(u32, u32, String)> {
    if !text.contains("每天") {
        return None;
    }
    if !(text.contains("提醒我") || text.contains("叫我")) {
        return None;
    }
    let day_pos = text.find("每天")?;
    let after_day = &text[day_pos + "每天".len()..];
    let point_pos = after_day.find('点')?;
    let hour_raw = after_day[..point_pos].trim();
    if hour_raw.is_empty() {
        return None;
    }
    let hour = parse_hour(hour_raw)?;
    let after_point = after_day[point_pos + '点'.len_utf8()..].trim();
    let minute = if let Some(min_pos) = after_point.find('分') {
        let m_raw = after_point[..min_pos].trim();
        if m_raw.is_empty() {
            0
        } else {
            parse_minute(m_raw)?
        }
    } else if let Some(colon_pos) = hour_raw.find(':') {
        let m_raw = hour_raw[colon_pos + 1..].trim();
        parse_minute(m_raw)?
    } else {
        0
    };
    let content = after_point
        .replace("提醒我", "")
        .replace("叫我", "")
        .replace("闹钟", "")
        .trim()
        .to_string();
    Some((hour, minute, content))
}

fn parse_hour(s: &str) -> Option<u32> {
    if let Ok(v) = s.parse::<u32>() {
        return (v <= 23).then_some(v);
    }
    parse_chinese_number(s).filter(|v| *v <= 23)
}

fn parse_minute(s: &str) -> Option<u32> {
    if let Ok(v) = s.parse::<u32>() {
        return (v <= 59).then_some(v);
    }
    parse_chinese_number(s).filter(|v| *v <= 59)
}

fn parse_chinese_number(s: &str) -> Option<u32> {
    let t = s.trim();
    if t.is_empty() {
        return None;
    }
    let digit = |c: char| match c {
        '零' => Some(0),
        '一' => Some(1),
        '二' | '两' => Some(2),
        '三' => Some(3),
        '四' => Some(4),
        '五' => Some(5),
        '六' => Some(6),
        '七' => Some(7),
        '八' => Some(8),
        '九' => Some(9),
        _ => None,
    };
    if t == "十" {
        return Some(10);
    }
    if let Some(pos) = t.find('十') {
        let left = t[..pos].chars().next().and_then(digit).unwrap_or(1);
        let right = t[pos + '十'.len_utf8()..]
            .chars()
            .next()
            .and_then(digit)
            .unwrap_or(0);
        return Some(left * 10 + right);
    }
    t.chars().next().and_then(digit)
}

fn parse_after_reminder(text: &str) -> Option<(i64, String)> {
    let after_pos = text.find('后')?;
    let prefix = &text[..after_pos];
    let suffix = text[after_pos + '后'.len_utf8()..].trim();
    if !(suffix.contains("叫我") || suffix.contains("提醒我")) {
        return None;
    }

    let digits: String = prefix
        .chars()
        .filter(|c| c.is_ascii_digit())
        .collect::<String>();
    let n = digits.parse::<i64>().ok()?;
    if n <= 0 {
        return None;
    }
    let seconds = if prefix.contains("小时") {
        n.saturating_mul(3600)
    } else if prefix.contains("分钟") {
        n.saturating_mul(60)
    } else {
        n
    };

    let content = suffix
        .replace("叫我", "")
        .replace("提醒我", "")
        .trim()
        .to_string();
    Some((seconds, content))
}
