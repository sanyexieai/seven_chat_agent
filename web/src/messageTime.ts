/** 与微信类似：相邻消息间隔超过该时长则插入居中时间条（毫秒） */
export const MESSAGE_TIME_GAP_MS = 5 * 60 * 1000;

const WEEKDAY = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"];

function startOfLocalDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function pad2(n: number): string {
  return n.toString().padStart(2, "0");
}

/** 是否在本条消息上方显示时间分隔（参考微信） */
export function shouldShowMessageTime(
  currentCreatedAt: string,
  previousCreatedAt?: string,
): boolean {
  if (!previousCreatedAt) return true;
  const cur = new Date(currentCreatedAt).getTime();
  const prev = new Date(previousCreatedAt).getTime();
  if (Number.isNaN(cur) || Number.isNaN(prev)) return true;
  return cur - prev >= MESSAGE_TIME_GAP_MS;
}

/**
 * 格式化聊天时间条文案（今天只显示 HH:mm，昨天/星期/日期等同微信习惯）
 */
export function formatWeChatMessageTime(
  iso: string,
  now: Date = new Date(),
): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";

  const hm = `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  const dayDiff = Math.floor(
    (startOfLocalDay(now).getTime() - startOfLocalDay(d).getTime()) / 86_400_000,
  );

  if (dayDiff === 0) {
    const ago = now.getTime() - d.getTime();
    if (ago >= 0 && ago < 60_000) return "刚刚";
    return hm;
  }
  if (dayDiff === 1) return `昨天 ${hm}`;
  if (dayDiff > 1 && dayDiff < 7) return `${WEEKDAY[d.getDay()]} ${hm}`;
  if (d.getFullYear() === now.getFullYear()) {
    return `${d.getMonth() + 1}月${d.getDate()}日 ${hm}`;
  }
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${hm}`;
}
