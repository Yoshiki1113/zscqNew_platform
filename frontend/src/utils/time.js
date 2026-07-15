/**
 * 统一时间格式化工具
 * 所有时间均以 UTC+8 北京时间展示，格式 yyyy-MM-dd HH:mm:ss
 */

/**
 * 格式化时间为 yyyy-MM-dd HH:mm:ss
 * @param {string|Date} val - ISO 字符串、Date 对象、时间戳
 * @returns {string} 格式化后的时间字符串，无效时返回空串
 */
export function formatDateTime(val) {
  if (!val) return ''
  const d = new Date(val)
  if (isNaN(d.getTime())) return String(val)  // 非时间字符串原样返回
  return [
    d.getFullYear(),
    '-',
    String(d.getMonth() + 1).padStart(2, '0'),
    '-',
    String(d.getDate()).padStart(2, '0'),
    ' ',
    String(d.getHours()).padStart(2, '0'),
    ':',
    String(d.getMinutes()).padStart(2, '0'),
    ':',
    String(d.getSeconds()).padStart(2, '0'),
  ].join('')
}

/**
 * 格式化为 yyyy-MM-dd HH:mm（不含秒）
 */
export function formatDateTimeShort(val) {
  if (!val) return ''
  const d = new Date(val)
  if (isNaN(d.getTime())) return String(val)
  return [
    d.getFullYear(),
    '-',
    String(d.getMonth() + 1).padStart(2, '0'),
    '-',
    String(d.getDate()).padStart(2, '0'),
    ' ',
    String(d.getHours()).padStart(2, '0'),
    ':',
    String(d.getMinutes()).padStart(2, '0'),
  ].join('')
}

/**
 * 格式化为 yyyy-MM-dd（仅日期）
 */
export function formatDateOnly(val) {
  if (!val) return ''
  const d = new Date(val)
  if (isNaN(d.getTime())) return String(val)
  return [
    d.getFullYear(),
    '-',
    String(d.getMonth() + 1).padStart(2, '0'),
    '-',
    String(d.getDate()).padStart(2, '0'),
  ].join('')
}
