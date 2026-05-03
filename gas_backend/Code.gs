// ================================================================
// ZODOVIA — Google Apps Script Backend (Data Layer)
// Folder: https://drive.google.com/drive/folders/1ghTe487RyHirRZYx9A9Sd1dVHJWjItAm
//
// DEPLOYMENT:
//   1. Open script.google.com → New project → paste this file
//   2. Project Settings → Script Properties → add GAS_API_KEY (strong secret)
//   3. Select 'setup' in dropdown → Run once to create spreadsheet
//   4. Deploy → New deployment → Web App
//      Execute as: Me  |  Who can access: Anyone
//   5. Copy /exec URL → GAS_URL env var on Render
//   6. Copy GAS_API_KEY value → GAS_API_KEY env var on Render
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
  PAYMENTS: 'payment_records',
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
  payment_records: [
    'id','user_id','user_email','plan','amount_lkr','slip_drive_id','slip_view_url',
    'slip_filename','extracted_name','extracted_bank','extracted_reference',
    'extracted_amount','extracted_date','extracted_currency','raw_extraction',
    'status','admin_notes','reviewed_at','created_at'
  ],
};

// ================================================================
// HTTP HANDLERS
// ================================================================

function doGet(e) {
  if (!e || !e.parameter) {
    return respondError('No request parameters — call via HTTP, not Run button. Use setup() to initialise.');
  }
  if (!validateApiKey(e.parameter.api_key)) {
    return respondError('Unauthorized');
  }
  const action = e.parameter.action || '';
  try {
    const p = e.parameter;
    switch (action) {
      case 'get_user_by_email':        return respond(getUserByEmail(p.email));
      case 'get_user_by_id':           return respond(getUserById(+p.id));
      case 'get_user_by_sub_id':       return respond(getUserBySubId(p.sub_id));
      case 'get_all_users':            return respond(getAllUsers(+(p.limit||500), +(p.offset||0)));
      case 'get_stats':                return respond(getStats());
      case 'get_chart':                return respond(getChartByUserId(+p.user_id));
      case 'count_compat':             return respond({count: countCompatReports(+p.user_id)});
      case 'get_forecast':             return respond(getForecast(+p.user_id, p.period_type, p.period_key));
      case 'get_daily':                return respond(getDailyHoroscope(+p.user_id, p.date));
      case 'get_paid_users_for_daily': return respond(getPaidUsersForDaily());
      case 'get_pw_reset':             return respond(getPwReset(p.token));
      case 'get_reg_ip_count':         return respond({count: getRegIpCount(p.ip, +(p.days||14))});
      case 'get_payment_record':       return respond(getPaymentRecord(+p.id));
      case 'get_all_payment_records':  return respond(getAllPaymentRecords(p.status));
      default: return respondError('Unknown action: ' + action);
    }
  } catch (err) {
    console.log('[doGet] ' + action + ': ' + err + '\n' + err.stack);
    return respondError(err.message);
  }
}

function doPost(e) {
  let body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return respondError('Invalid JSON');
  }
  if (!validateApiKey(body.api_key)) {
    return respondError('Unauthorized');
  }
  const action = body.action || '';
  try {
    switch (action) {
      case 'create_user':           return respond(createUser(body));
      case 'update_user':           return respond(updateUser(+body.id, body.fields));
      case 'delete_user':           return respond(deleteUser(+body.id));
      case 'create_pw_reset':       return respond(createPwReset(body));
      case 'invalidate_pw_resets':  return respond(invalidatePwResets(+body.user_id));
      case 'mark_pw_reset_used':    return respond(markPwResetUsed(body.token));
      case 'log_reg_ip':            return respond(logRegIp(body));
      case 'cleanup_reg_ips':       return respond(cleanupRegIps(body.cutoff));
      case 'save_chart':            return respond(saveChart(body));
      case 'update_chart':          return respond(updateChart(+body.user_id, body.fields));
      case 'delete_chart':          return respond(deleteChart(+body.user_id));
      case 'save_compat':           return respond(saveCompatReport(body));
      case 'save_forecast':         return respond(saveForecast(body));
      case 'delete_forecasts':      return respond(deleteForecasts(+body.user_id, body.period_keys));
      case 'save_daily':            return respond(saveDailyHoroscope(body));
      case 'update_daily':          return respond(updateDailyHoroscope(+body.user_id, body.date, body.fields));
      case 'delete_daily':           return respond(deleteDailyHoroscope(+body.user_id, body.date));
      case 'create_payment_record':  return respond(createPaymentRecord(body));
      case 'update_payment_record':  return respond(updatePaymentRecord(+body.id, body.fields));
      case 'save_payment_slip':      return respond(savePaymentSlip(body.base64, body.mime_type, body.filename));
      default: return respondError('Unknown action: ' + action);
    }
  } catch (err) {
    console.log('[doPost] ' + action + ': ' + err + '\n' + err.stack);
    return respondError(err.message);
  }
}

// ================================================================
// SPREADSHEET MANAGEMENT
// ================================================================

function getSpreadsheet() {
  const props  = PropertiesService.getScriptProperties();
  const cached = props.getProperty('DB_SPREADSHEET_ID');

  // Fast path: open by stored ID
  if (cached) {
    try { return SpreadsheetApp.openById(cached); } catch(e) { /* stale — fall through */ }
  }

  const folder = DriveApp.getFolderById(FOLDER_ID);

  // Check target folder
  const inFolder = folder.getFilesByName(DB_NAME);
  if (inFolder.hasNext()) {
    const ss = SpreadsheetApp.open(inFolder.next());
    props.setProperty('DB_SPREADSHEET_ID', ss.getId());
    return ss;
  }

  // Check My Drive root (in case a previous create landed there)
  const inRoot = DriveApp.getRootFolder().getFilesByName(DB_NAME);
  if (inRoot.hasNext()) {
    const existing = inRoot.next();
    folder.addFile(existing);
    DriveApp.getRootFolder().removeFile(existing);
    const ss = SpreadsheetApp.open(existing);
    props.setProperty('DB_SPREADSHEET_ID', ss.getId());
    console.log('Moved existing spreadsheet into target folder. ID: ' + ss.getId());
    return ss;
  }

  // Create fresh in target folder
  const ss   = SpreadsheetApp.create(DB_NAME);
  const file = DriveApp.getFileById(ss.getId());
  folder.addFile(file);
  DriveApp.getRootFolder().removeFile(file);
  props.setProperty('DB_SPREADSHEET_ID', ss.getId());
  console.log('Created new spreadsheet. ID: ' + ss.getId());
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

// Run this manually once to initialise the spreadsheet
function setup() {
  const ss = getSpreadsheet();
  initAllSheets(ss);
  console.log('Setup complete. Spreadsheet ID: ' + ss.getId());
}

// Run this first if setup() produces no log output — diagnoses each step
function debugSetup() {
  try {
    console.log('Step 1: Accessing folder ' + FOLDER_ID);
    const folder = DriveApp.getFolderById(FOLDER_ID);
    console.log('Step 2: Folder name = ' + folder.getName());

    const inFolder = folder.getFilesByName(DB_NAME);
    console.log('Step 3: File in target folder? ' + inFolder.hasNext());

    const inRoot = DriveApp.getRootFolder().getFilesByName(DB_NAME);
    console.log('Step 4: File in My Drive root? ' + inRoot.hasNext());

    console.log('Step 5: Creating test spreadsheet...');
    const ss   = SpreadsheetApp.create(DB_NAME + '_TEST');
    console.log('Step 6: Created with ID = ' + ss.getId());

    const file = DriveApp.getFileById(ss.getId());
    console.log('Step 7: Got file object: ' + file.getName());

    folder.addFile(file);
    DriveApp.getRootFolder().removeFile(file);
    console.log('Step 8: Moved to target folder successfully!');

    const cleanup = folder.getFilesByName(DB_NAME + '_TEST');
    if (cleanup.hasNext()) cleanup.next().setTrashed(true);
    console.log('Step 9: Test file cleaned up. Ready to run setup().');
  } catch (err) {
    console.log('ERROR: ' + err.message);
    console.log(err.stack);
  }
}

// ================================================================
// GENERIC HELPERS
// ================================================================

// Atomically allocates the next ID and appends the row — prevents duplicate IDs
function appendRowWithId(sheet, buildRow) {
  const lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    const last = sheet.getLastRow();
    const id   = last <= 1 ? 1 :
      sheet.getRange(2, 1, last - 1, 1).getValues()
           .reduce((m, r) => Math.max(m, parseInt(r[0]) || 0), 0) + 1;
    sheet.appendRow(buildRow(id));
    return id;
  } finally {
    lock.releaseLock();
  }
}

function rowToObj(cols, row) {
  const obj = {};
  cols.forEach((col, i) => {
    let val = row[i];
    if (val === '' || val === undefined) { obj[col] = null; return; }
    if (val === 'TRUE'  || val === true)  { obj[col] = true;  return; }
    if (val === 'FALSE' || val === false) { obj[col] = false; return; }
    if (typeof val === 'string' && (val.charAt(0) === '{' || val.charAt(0) === '[')) {
      try { obj[col] = JSON.parse(val); return; } catch(e) {}
    }
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
  return getAllRows(sheet).find(predicate) || null;
}

function findRowNumber(sheet, predicate) {
  const cols = COLS[sheet.getName()];
  const last = sheet.getLastRow();
  if (last <= 1) return -1;
  const data = sheet.getRange(2, 1, last - 1, cols.length).getValues();
  for (let i = 0; i < data.length; i++) {
    if (predicate(rowToObj(cols, data[i]))) return i + 2;
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

// Strip password_hash before returning user lists to callers that don't need it
function _stripSensitive(user) {
  const u = Object.assign({}, user);
  delete u.password_hash;
  return u;
}

function validateApiKey(key) {
  const stored = PropertiesService.getScriptProperties().getProperty('GAS_API_KEY');
  if (!stored) return false; // Deny all when key not configured
  return key === stored;
}

function respond(data) {
  return ContentService
    .createTextOutput(JSON.stringify({success: true, data: data}))
    .setMimeType(ContentService.MimeType.JSON);
}

function respondError(message) {
  return ContentService
    .createTextOutput(JSON.stringify({success: false, error: message}))
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
  const norm = (data.email || '').toLowerCase().trim();
  if (getUserByEmail(norm)) {
    throw new Error('Email already registered: ' + norm);
  }
  const sheet = getSheet(S.USERS);
  const cols  = COLS[S.USERS];
  const now   = new Date().toISOString();

  const id = appendRowWithId(sheet, (id) => {
    const defaults = {
      id, email: norm,
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
    return cols.map(c => (defaults[c] === null || defaults[c] === undefined) ? '' : defaults[c]);
  });

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
  const rows = getAllRows(getSheet(S.USERS));
  rows.sort((a, b) => (b.id || 0) - (a.id || 0));
  return rows.slice(offset, offset + limit).map(_stripSensitive);
}

function getStats() {
  const users = getAllRows(getSheet(S.USERS));
  const paid  = users.filter(u => u.is_paid === true).length;
  return {
    total_users:           users.length,
    paid_users:            paid,
    free_users:            users.length - paid,
    charts_generated:      Math.max(0, getSheet(S.CHARTS).getLastRow() - 1),
    compatibility_reports: Math.max(0, getSheet(S.COMPAT).getLastRow() - 1),
  };
}

// ================================================================
// PASSWORD RESET TOKENS
// ================================================================

function createPwReset(data) {
  const sheet = getSheet(S.PW_RESETS);
  const id    = appendRowWithId(sheet, (id) =>
    [id, data.user_id, data.token, data.expires_at, false, new Date().toISOString()]
  );
  return {id};
}

function getPwReset(token) {
  const now = new Date();
  return findFirst(getSheet(S.PW_RESETS), r =>
    r.token === token &&
    r.used  === false &&
    new Date(r.expires_at) > now
  );
}

function invalidatePwResets(userId) {
  const sheet   = getSheet(S.PW_RESETS);
  const usedIdx = COLS[S.PW_RESETS].indexOf('used');
  const last    = sheet.getLastRow();
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
  const id    = appendRowWithId(sheet, (id) =>
    [id, data.ip_address, data.user_id || '', new Date().toISOString()]
  );
  return {id};
}

function getRegIpCount(ip, days) {
  const cutoff = new Date(Date.now() - days * 86400000).toISOString();
  return getAllRows(getSheet(S.REG_IPS))
    .filter(r => r.ip_address === ip && r.user_id && r.created_at >= cutoff)
    .length;
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

  if (existing > 0) {
    const fields = {};
    if (data.chart_data   !== undefined) fields.chart_data   = data.chart_data;
    if (data.free_reading !== undefined) fields.free_reading = data.free_reading;
    if (data.full_reading !== undefined) fields.full_reading = data.full_reading;
    Object.entries(fields).forEach(([k, v]) => setField(sheet, existing, k, v));
    return getChartByUserId(data.user_id);
  }

  appendRowWithId(sheet, (id) => {
    const cdStr = (data.chart_data && typeof data.chart_data === 'object')
      ? JSON.stringify(data.chart_data) : (data.chart_data || '');
    return [id, data.user_id, cdStr,
      data.free_reading || '', data.full_reading || '', new Date().toISOString()];
  });
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
  const id    = appendRowWithId(sheet, (id) => [
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
  appendRowWithId(sheet, (id) =>
    [id, data.user_id, data.period_type, data.period_key,
     data.content, new Date().toISOString()]
  );
  return getForecast(data.user_id, data.period_type, data.period_key);
}

function deleteForecasts(userId, periodKeys) {
  const sheet  = getSheet(S.FORECASTS);
  const cols   = COLS[S.FORECASTS];
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
  return findFirst(getSheet(S.DAILY), h => h.user_id === userId && h.date === date);
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
  appendRowWithId(sheet, (id) =>
    [id, data.user_id, data.date,
     data.content || '', data.intention || '', false, new Date().toISOString()]
  );
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
  return getAllRows(getSheet(S.USERS))
    .filter(u => u.is_paid === true && u.birth_date)
    .map(_stripSensitive);
}

// ================================================================
// PAYMENT RECORDS
// ================================================================

function getPaymentSlipsFolder() {
  const main = DriveApp.getFolderById(FOLDER_ID);
  const iter = main.getFoldersByName('Payment_Slips');
  if (iter.hasNext()) return iter.next();
  return main.createFolder('Payment_Slips');
}

function savePaymentSlip(base64Data, mimeType, filename) {
  const bytes  = Utilities.base64Decode(base64Data);
  const blob   = Utilities.newBlob(bytes, mimeType || 'image/jpeg', filename || 'slip.jpg');
  const folder = getPaymentSlipsFolder();
  const file   = folder.createFile(blob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  return {
    drive_id: file.getId(),
    view_url: 'https://drive.google.com/file/d/' + file.getId() + '/view',
  };
}

function createPaymentRecord(data) {
  const sheet = getSheet(S.PAYMENTS);
  const now   = new Date().toISOString();
  const id    = appendRowWithId(sheet, (id) => [
    id,
    data.user_id      || '',
    data.user_email   || '',
    data.plan         || '',
    data.amount_lkr   || '',
    data.slip_drive_id  || '',
    data.slip_view_url  || '',
    data.slip_filename  || '',
    data.extracted_name      || '',
    data.extracted_bank      || '',
    data.extracted_reference || '',
    data.extracted_amount    || '',
    data.extracted_date      || '',
    data.extracted_currency  || '',
    data.raw_extraction ? JSON.stringify(data.raw_extraction) : '',
    'pending',
    '',
    '',
    now,
  ]);
  return getPaymentRecord(id);
}

function getPaymentRecord(id) {
  return findFirst(getSheet(S.PAYMENTS), r => r.id === id);
}

function getAllPaymentRecords(status) {
  const rows = getAllRows(getSheet(S.PAYMENTS));
  rows.sort((a, b) => (b.id || 0) - (a.id || 0));
  if (!status || status === 'all') return rows;
  return rows.filter(r => r.status === status);
}

function updatePaymentRecord(id, fields) {
  const sheet  = getSheet(S.PAYMENTS);
  const rowNum = findRowNumber(sheet, r => r.id === id);
  if (rowNum < 0) return null;
  Object.entries(fields).forEach(([k, v]) => setField(sheet, rowNum, k, v));
  return getPaymentRecord(id);
}
