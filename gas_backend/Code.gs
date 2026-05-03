// ================================================================
// ZODOVIA — Google Apps Script Backend (Data Layer)
// Folder: https://drive.google.com/drive/folders/1ghTe487RyHirRZYx9A9Sd1dVHJWjItAm
//
// DEPLOYMENT:
//   1. Open script.google.com → New project → paste this file
//   2. Extensions → Script Properties → add GAS_API_KEY (any strong secret)
//   3. Deploy → New deployment → Web App
//      Execute as: Me  |  Who can access: Anyone
//   4. Copy the /exec URL → set GAS_URL env var in Railway
//   5. Copy the GAS_API_KEY → set GAS_API_KEY env var in Railway
// ================================================================

const FOLDER_ID = '1ghTe487RyHirRZYx9A9Sd1dVHJWjItAm';
const DB_NAME   = 'Zodovia_Database';

const S = {
  USERS:    'users',
  CHARTS:   'birth_charts',
  COMPAT:   'compatibility_reports',
  FORECASTS:'forecasts',
  DAILY:    'daily_horoscopes',
  REG_IPS:  'registration_ips',
  PW_RESETS:'password_reset_tokens',
};

const COLS = {
  users: [
    'id','email','password_hash','name','birth_date','birth_time','birth_city',
    'birth_lat','birth_lon','birth_timezone','sun_sign','moon_sign','rising_sign',
    'reading_focus','life_context','life_event','gender','marital_status',
    'occupation','job_type','education_level','current_location','wellness_goal',
    'life_phase','primary_intention','sensitive_flags','profile_summary',
    'profile_updated_at','profiling_stage','current_streak','longest_streak',
    'last_active_date','total_active_days','is_superuser','free_uses','trial_uses',
    'is_paid','paypal_subscription_id','subscription_status','subscription_plan',
    'created_at','last_login'
  ],
  birth_charts: ['id','user_id','chart_data','free_reading','full_reading','created_at'],
  compatibility_reports: [
    'id','user_id','person2_name','person2_birth_date','person2_birth_time',
    'person2_birth_city','person2_sun_sign','relationship_type','report','created_at'
  ],
  forecasts: ['id','user_id','period_type','period_key','content','created_at'],
  daily_horoscopes: ['id','user_id','date','content','intention','email_sent','created_at'],
  registration_ips: ['id','ip_address','user_id','created_at'],
  password_reset_tokens: ['id','user_id','token','expires_at','used','created_at'],
};

// ================================================================
// HTTP HANDLERS
// ================================================================

function doGet(e) {
  if (!validateApiKey(e.parameter.api_key)) {
    return respond({error: 'Unauthorized'});
  }
  const action = e.parameter.action || '';
  try {
    const p = e.parameter;
    switch (action) {
      case 'get_user_by_email':      return respond(getUserByEmail(p.email));
      case 'get_user_by_id':         return respond(getUserById(+p.id));
      case 'get_user_by_sub_id':     return respond(getUserBySubId(p.sub_id));
      case 'get_all_users':          return respond(getAllUsers(+(p.limit||500), +(p.offset||0)));
      case 'get_stats':              return respond(getStats());
      case 'get_chart':              return respond(getChartByUserId(+p.user_id));
      case 'count_compat':           return respond({count: countCompatReports(+p.user_id)});
      case 'get_forecast':           return respond(getForecast(+p.user_id, p.period_type, p.period_key));
      case 'get_daily':              return respond(getDailyHoroscope(+p.user_id, p.date));
      case 'get_paid_users_for_daily': return respond(getPaidUsersForDaily());
      case 'get_pw_reset':           return respond(getPwReset(p.token));
      case 'get_reg_ip_count':       return respond({count: getRegIpCount(p.ip, +(p.days||14))});
      default: return respond({error: 'Unknown action: ' + action});
    }
  } catch (err) {
    Logger.log('[doGet] ' + action + ': ' + err + '\n' + err.stack);
    return respond({error: err.message});
  }
}

function doPost(e) {
  let body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return respond({error: 'Invalid JSON'});
  }
  if (!validateApiKey(body.api_key)) {
    return respond({error: 'Unauthorized'});
  }
  const action = body.action || '';
  try {
    switch (action) {
      // Users
      case 'create_user':           return respond(createUser(body));
      case 'update_user':           return respond(updateUser(+body.id, body.fields));
      case 'delete_user':           return respond(deleteUser(+body.id));
      // Password resets
      case 'create_pw_reset':       return respond(createPwReset(body));
      case 'invalidate_pw_resets':  return respond(invalidatePwResets(+body.user_id));
      case 'mark_pw_reset_used':    return respond(markPwResetUsed(body.token));
      // Registration IPs
      case 'log_reg_ip':            return respond(logRegIp(body));
      case 'cleanup_reg_ips':       return respond(cleanupRegIps(body.cutoff));
      // Birth charts
      case 'save_chart':            return respond(saveChart(body));
      case 'update_chart':          return respond(updateChart(+body.user_id, body.fields));
      case 'delete_chart':          return respond(deleteChart(+body.user_id));
      // Compatibility
      case 'save_compat':           return respond(saveCompatReport(body));
      // Forecasts
      case 'save_forecast':         return respond(saveForecast(body));
      case 'delete_forecasts':      return respond(deleteForecasts(+body.user_id, body.period_keys));
      // Daily horoscopes
      case 'save_daily':            return respond(saveDailyHoroscope(body));
      case 'update_daily':          return respond(updateDailyHoroscope(+body.user_id, body.date, body.fields));
      case 'delete_daily':          return respond(deleteDailyHoroscope(+body.user_id, body.date));
      default: return respond({error: 'Unknown action: ' + action});
    }
  } catch (err) {
    Logger.log('[doPost] ' + action + ': ' + err + '\n' + err.stack);
    return respond({error: err.message});
  }
}

// ================================================================
// SPREADSHEET MANAGEMENT
// ================================================================

function getSpreadsheet() {
  const folder = DriveApp.getFolderById(FOLDER_ID);
  const files  = folder.getFilesByName(DB_NAME);
  if (files.hasNext()) {
    return SpreadsheetApp.open(files.next());
  }
  const ss = SpreadsheetApp.create(DB_NAME);
  DriveApp.getFileById(ss.getId()).moveTo(folder);
  initAllSheets(ss);
  return ss;
}

function getSheet(name) {
  const ss    = getSpreadsheet();
  let   sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    const headers = COLS[name];
    if (headers) sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  }
  return sheet;
}

function initAllSheets(ss) {
  Object.entries(COLS).forEach(([name, cols]) => {
    let sheet = ss.getSheetByName(name);
    if (!sheet) sheet = ss.insertSheet(name);
    if (sheet.getLastRow() === 0) {
      sheet.getRange(1, 1, 1, cols.length).setValues([cols]);
    }
  });
}

// Run this manually once to set up the spreadsheet
function setup() {
  const ss = getSpreadsheet();
  initAllSheets(ss);
  Logger.log('Setup complete. Spreadsheet ID: ' + ss.getId());
}

// ================================================================
// GENERIC HELPERS
// ================================================================

function getNextId(sheet) {
  const lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    const last = sheet.getLastRow();
    if (last <= 1) return 1;
    const vals = sheet.getRange(2, 1, last - 1, 1).getValues();
    const max  = vals.reduce((m, r) => Math.max(m, parseInt(r[0]) || 0), 0);
    return max + 1;
  } finally {
    lock.releaseLock();
  }
}

function rowToObj(cols, row) {
  const obj = {};
  cols.forEach((col, i) => {
    let val = row[i];
    if (val === '' || val === undefined) { obj[col] = null; return; }
    // Boolean
    if (val === 'TRUE'  || val === true)  { obj[col] = true;  return; }
    if (val === 'FALSE' || val === false) { obj[col] = false; return; }
    // JSON decode for complex fields
    if (typeof val === 'string' && (val.charAt(0) === '{' || val.charAt(0) === '[')) {
      try { obj[col] = JSON.parse(val); return; } catch(e) {}
    }
    // Numeric coercion for known integer fields
    const intCols = ['id','user_id','profiling_stage','current_streak',
                     'longest_streak','total_active_days','free_uses','trial_uses'];
    if (intCols.includes(col) && val !== null) { obj[col] = parseInt(val) || 0; return; }
    const floatCols = ['birth_lat','birth_lon'];
    if (floatCols.includes(col) && val !== null) { obj[col] = parseFloat(val) || null; return; }
    obj[col] = val;
  });
  return obj;
}

function getAllRows(sheet) {
  const cols = COLS[sheet.getName()];
  const last = sheet.getLastRow();
  if (last <= 1) return [];
  return sheet.getRange(2, 1, last - 1, cols.length).getValues()
    .map(row => rowToObj(cols, row));
}

function findFirst(sheet, predicate) {
  const rows = getAllRows(sheet);
  return rows.find(predicate) || null;
}

function findRowNumber(sheet, predicate) {
  const cols = COLS[sheet.getName()];
  const last = sheet.getLastRow();
  if (last <= 1) return -1;
  const data = sheet.getRange(2, 1, last - 1, cols.length).getValues();
  for (let i = 0; i < data.length; i++) {
    const obj = rowToObj(cols, data[i]);
    if (predicate(obj)) return i + 2; // 1-based sheet row
  }
  return -1;
}

function setField(sheet, rowNum, fieldName, value) {
  const cols   = COLS[sheet.getName()];
  const colIdx = cols.indexOf(fieldName);
  if (colIdx < 0) return;
  const stored = (value !== null && typeof value === 'object')
    ? JSON.stringify(value)
    : (value === null ? '' : value);
  sheet.getRange(rowNum, colIdx + 1).setValue(stored);
}

function validateApiKey(key) {
  const stored = PropertiesService.getScriptProperties().getProperty('GAS_API_KEY');
  if (!stored) return true; // Dev mode: key not configured → allow all
  return key === stored;
}

function respond(data) {
  return ContentService
    .createTextOutput(JSON.stringify({success: true, data: data}))
    .setMimeType(ContentService.MimeType.JSON);
}

// ================================================================
// USERS
// ================================================================

function getUserByEmail(email) {
  if (!email) return null;
  const norm = String(email).toLowerCase().trim();
  return findFirst(getSheet(S.USERS), u => u.email === norm);
}

function getUserById(id) {
  if (!id) return null;
  return findFirst(getSheet(S.USERS), u => u.id === id);
}

function getUserBySubId(subId) {
  if (!subId) return null;
  return findFirst(getSheet(S.USERS), u => u.paypal_subscription_id === subId);
}

function createUser(data) {
  const sheet = getSheet(S.USERS);
  const id    = getNextId(sheet);
  const now   = new Date().toISOString();
  const cols  = COLS[S.USERS];

  const defaults = {
    id, email: (data.email || '').toLowerCase().trim(),
    password_hash: data.password_hash || '',
    name: data.name || '',
    birth_date: '', birth_time: '', birth_city: '',
    birth_lat: '', birth_lon: '', birth_timezone: '',
    sun_sign: '', moon_sign: '', rising_sign: '',
    reading_focus: '', life_context: '', life_event: '',
    gender: '', marital_status: '', occupation: '',
    job_type: '', education_level: '', current_location: '',
    wellness_goal: '', life_phase: '', primary_intention: '',
    sensitive_flags: '', profile_summary: '', profile_updated_at: '',
    profiling_stage: 0, current_streak: 0, longest_streak: 0,
    last_active_date: '', total_active_days: 0,
    is_superuser: data.is_superuser || false,
    free_uses: 0, trial_uses: 0,
    is_paid: data.is_paid || false,
    paypal_subscription_id: '',
    subscription_status: data.subscription_status || 'free',
    subscription_plan: data.subscription_plan || 'free',
    created_at: now, last_login: '',
  };

  sheet.appendRow(cols.map(c => {
    const v = defaults[c];
    return (v === null || v === undefined) ? '' : v;
  }));
  return getUserById(id);
}

function updateUser(id, fields) {
  if (!id || !fields) return null;
  const sheet  = getSheet(S.USERS);
  const rowNum = findRowNumber(sheet, u => u.id === id);
  if (rowNum < 0) return null;
  Object.entries(fields).forEach(([k, v]) => setField(sheet, rowNum, k, v));
  return getUserById(id);
}

function deleteUser(id) {
  // Delete user + all related records
  [S.USERS, S.CHARTS, S.COMPAT, S.FORECASTS, S.DAILY, S.PW_RESETS].forEach(tbl => {
    const sheet  = getSheet(tbl);
    const field  = tbl === S.USERS ? 'id' : 'user_id';
    const last   = sheet.getLastRow();
    if (last <= 1) return;
    const cols   = COLS[tbl];
    const fIdx   = cols.indexOf(field);
    const data   = sheet.getRange(2, 1, last - 1, cols.length).getValues();
    for (let i = data.length - 1; i >= 0; i--) {
      if (parseInt(data[i][fIdx]) === id) sheet.deleteRow(i + 2);
    }
  });
  return {deleted: true};
}

function getAllUsers(limit, offset) {
  const sheet = getSheet(S.USERS);
  const rows  = getAllRows(sheet);
  rows.sort((a, b) => (b.id || 0) - (a.id || 0));
  return rows.slice(offset, offset + limit);
}

function getStats() {
  const users  = getAllRows(getSheet(S.USERS));
  const paid   = users.filter(u => u.is_paid === true).length;
  return {
    total_users: users.length,
    paid_users:  paid,
    free_users:  users.length - paid,
    charts_generated:     Math.max(0, getSheet(S.CHARTS).getLastRow() - 1),
    compatibility_reports: Math.max(0, getSheet(S.COMPAT).getLastRow() - 1),
  };
}

// ================================================================
// PASSWORD RESET TOKENS
// ================================================================

function createPwReset(data) {
  const sheet = getSheet(S.PW_RESETS);
  const id    = getNextId(sheet);
  sheet.appendRow([id, data.user_id, data.token, data.expires_at, false, new Date().toISOString()]);
  return {id};
}

function getPwReset(token) {
  return findFirst(getSheet(S.PW_RESETS), r => r.token === token && r.used === false);
}

function invalidatePwResets(userId) {
  const sheet  = getSheet(S.PW_RESETS);
  const usedIdx = COLS[S.PW_RESETS].indexOf('used');
  const last   = sheet.getLastRow();
  if (last <= 1) return {updated: 0};
  const cols  = COLS[S.PW_RESETS];
  const data  = sheet.getRange(2, 1, last - 1, cols.length).getValues();
  let count   = 0;
  data.forEach((row, i) => {
    const obj = rowToObj(cols, row);
    if (obj.user_id === userId && obj.used === false) {
      sheet.getRange(i + 2, usedIdx + 1).setValue(true);
      count++;
    }
  });
  return {updated: count};
}

function markPwResetUsed(token) {
  const sheet  = getSheet(S.PW_RESETS);
  const rowNum = findRowNumber(sheet, r => r.token === token);
  if (rowNum < 0) return {ok: false};
  setField(sheet, rowNum, 'used', true);
  return {ok: true};
}

// ================================================================
// REGISTRATION IPs
// ================================================================

function logRegIp(data) {
  const sheet = getSheet(S.REG_IPS);
  const id    = getNextId(sheet);
  sheet.appendRow([id, data.ip_address, data.user_id || '', new Date().toISOString()]);
  return {id};
}

function getRegIpCount(ip, days) {
  const cutoff = new Date(Date.now() - days * 86400000).toISOString();
  const rows   = getAllRows(getSheet(S.REG_IPS));
  return rows.filter(r =>
    r.ip_address === ip && r.user_id && r.created_at >= cutoff
  ).length;
}

function cleanupRegIps(cutoff) {
  const sheet  = getSheet(S.REG_IPS);
  const cols   = COLS[S.REG_IPS];
  const tIdx   = cols.indexOf('created_at');
  const last   = sheet.getLastRow();
  if (last <= 1) return {deleted: 0};
  const data   = sheet.getRange(2, tIdx + 1, last - 1, 1).getValues();
  let deleted  = 0;
  for (let i = data.length - 1; i >= 0; i--) {
    if (String(data[i][0]) < cutoff) { sheet.deleteRow(i + 2); deleted++; }
  }
  return {deleted};
}

// ================================================================
// BIRTH CHARTS
// ================================================================

function getChartByUserId(userId) {
  return findFirst(getSheet(S.CHARTS), c => c.user_id === userId);
}

function saveChart(data) {
  const sheet    = getSheet(S.CHARTS);
  const existing = findRowNumber(sheet, c => c.user_id === data.user_id);
  const fields   = {};
  if (data.chart_data   !== undefined) fields.chart_data   = data.chart_data;
  if (data.free_reading !== undefined) fields.free_reading = data.free_reading;
  if (data.full_reading !== undefined) fields.full_reading = data.full_reading;

  if (existing > 0) {
    Object.entries(fields).forEach(([k, v]) => setField(sheet, existing, k, v));
    return getChartByUserId(data.user_id);
  }

  const id  = getNextId(sheet);
  const cdStr = (data.chart_data && typeof data.chart_data === 'object')
    ? JSON.stringify(data.chart_data) : (data.chart_data || '');
  sheet.appendRow([id, data.user_id, cdStr,
    data.free_reading || '', data.full_reading || '', new Date().toISOString()]);
  return getChartByUserId(data.user_id);
}

function updateChart(userId, fields) {
  const sheet  = getSheet(S.CHARTS);
  const rowNum = findRowNumber(sheet, c => c.user_id === userId);
  if (rowNum < 0) return null;
  Object.entries(fields).forEach(([k, v]) => setField(sheet, rowNum, k, v));
  return getChartByUserId(userId);
}

function deleteChart(userId) {
  const sheet  = getSheet(S.CHARTS);
  const rowNum = findRowNumber(sheet, c => c.user_id === userId);
  if (rowNum < 0) return {deleted: false};
  sheet.deleteRow(rowNum);
  return {deleted: true};
}

// ================================================================
// COMPATIBILITY REPORTS
// ================================================================

function saveCompatReport(data) {
  const sheet = getSheet(S.COMPAT);
  const id    = getNextId(sheet);
  sheet.appendRow([
    id, data.user_id, data.person2_name, data.person2_birth_date,
    data.person2_birth_time, data.person2_birth_city || '',
    data.person2_sun_sign || '', data.relationship_type,
    data.report, new Date().toISOString(),
  ]);
  return {id};
}

function countCompatReports(userId) {
  return getAllRows(getSheet(S.COMPAT)).filter(r => r.user_id === userId).length;
}

// ================================================================
// FORECASTS
// ================================================================

function getForecast(userId, periodType, periodKey) {
  return findFirst(getSheet(S.FORECASTS),
    f => f.user_id === userId && f.period_type === periodType && f.period_key === periodKey
  );
}

function saveForecast(data) {
  const sheet = getSheet(S.FORECASTS);
  const id    = getNextId(sheet);
  sheet.appendRow([id, data.user_id, data.period_type, data.period_key,
    data.content, new Date().toISOString()]);
  return {id};
}

function deleteForecasts(userId, periodKeys) {
  const sheet  = getSheet(S.FORECASTS);
  const cols   = COLS[S.FORECASTS];
  const uidIdx = cols.indexOf('user_id');
  const keyIdx = cols.indexOf('period_key');
  const last   = sheet.getLastRow();
  if (last <= 1) return {deleted: 0};
  const data   = sheet.getRange(2, 1, last - 1, cols.length).getValues();
  let deleted  = 0;
  for (let i = data.length - 1; i >= 0; i--) {
    const obj = rowToObj(cols, data[i]);
    if (obj.user_id !== userId) continue;
    if (!periodKeys || periodKeys.includes(data[i][keyIdx])) {
      sheet.deleteRow(i + 2);
      deleted++;
    }
  }
  return {deleted};
}

// ================================================================
// DAILY HOROSCOPES
// ================================================================

function getDailyHoroscope(userId, date) {
  return findFirst(getSheet(S.DAILY),
    h => h.user_id === userId && h.date === date
  );
}

function saveDailyHoroscope(data) {
  const existing = getDailyHoroscope(data.user_id, data.date);
  if (existing) {
    const fields = {};
    if (data.content    !== undefined) fields.content    = data.content;
    if (data.intention  !== undefined) fields.intention  = data.intention;
    if (data.email_sent !== undefined) fields.email_sent = data.email_sent;
    return updateDailyHoroscope(data.user_id, data.date, fields);
  }
  const sheet = getSheet(S.DAILY);
  const id    = getNextId(sheet);
  sheet.appendRow([id, data.user_id, data.date,
    data.content || '', data.intention || '', false, new Date().toISOString()]);
  return getDailyHoroscope(data.user_id, data.date);
}

function updateDailyHoroscope(userId, date, fields) {
  const sheet  = getSheet(S.DAILY);
  const rowNum = findRowNumber(sheet, h => h.user_id === userId && h.date === date);
  if (rowNum < 0) return null;
  Object.entries(fields).forEach(([k, v]) => setField(sheet, rowNum, k, v));
  return getDailyHoroscope(userId, date);
}

function deleteDailyHoroscope(userId, date) {
  const sheet  = getSheet(S.DAILY);
  const rowNum = findRowNumber(sheet, h => h.user_id === userId && h.date === date);
  if (rowNum < 0) return {deleted: false};
  sheet.deleteRow(rowNum);
  return {deleted: true};
}

function getPaidUsersForDaily() {
  return getAllRows(getSheet(S.USERS)).filter(u => u.is_paid === true && u.birth_date);
}
