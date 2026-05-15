ADMIN_PAGE_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FMS Admin Panel</title>
<style>
:root{--bg:#07111f;--panel:#0c1729;--panel2:#101e33;--line:#21324c;--text:#e6eefc;--muted:#8ea3c7;--accent:#29b6f6;--accent2:#6d5efc;--danger:#ff5d6c;--ok:#4ee59b}
*{box-sizing:border-box}
body{margin:0;font-family:Segoe UI,Arial,sans-serif;background:radial-gradient(circle at top,#0f203c 0,#07111f 40%,#050b14 100%);color:var(--text);min-height:100vh}
a{color:var(--accent)}
.hidden{display:none!important}
.wrap{min-height:100vh;padding:24px}
.grid{display:grid;grid-template-columns:260px 1fr;gap:18px}
.panel{background:rgba(12,23,41,.92);border:1px solid var(--line);border-radius:16px;backdrop-filter:blur(14px);box-shadow:0 20px 50px rgba(0,0,0,.25)}
.side{padding:18px}
.title{font-size:22px;font-weight:700;letter-spacing:.4px}
.sub{color:var(--muted);font-size:13px;margin-top:6px;line-height:1.6}
.nav{display:grid;gap:8px;margin-top:18px}
.nav button,.btn{border:1px solid var(--line);background:linear-gradient(180deg,#12213a,#0d192b);color:var(--text);border-radius:12px;padding:10px 14px;text-align:left;cursor:pointer;font-size:14px;font-family:inherit}
.nav button.active{border-color:rgba(41,182,246,.7);box-shadow:0 0 0 1px rgba(41,182,246,.15) inset;color:#fff}
.btn{display:inline-block}
.btn.primary{background:linear-gradient(180deg,#29b6f6,#1958c4);border-color:rgba(41,182,246,.7);color:#fff;font-weight:600}
.btn.danger{background:linear-gradient(180deg,#ff5d6c,#c4313f);border-color:rgba(255,93,108,.6);color:#fff}
.btn.ghost{background:transparent}
.btn:hover{filter:brightness(1.08)}
.main{padding:20px}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.card{background:linear-gradient(180deg,#0f1d33,#0b1526);border:1px solid var(--line);border-radius:14px;padding:16px}
.k{font-size:12px;color:var(--muted)}
.v{font-size:28px;font-weight:700;margin-top:6px}
.section{margin-top:16px;background:rgba(10,18,31,.7);border:1px solid var(--line);border-radius:16px;padding:18px}
.section h3{margin:0 0 12px;font-size:16px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:10px 8px;border-bottom:1px solid rgba(33,50,76,.7);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
input,select,textarea{width:100%;background:#09111d;border:1px solid #20314a;color:var(--text);border-radius:10px;padding:10px 12px;font-family:inherit;font-size:14px}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--accent)}
label{font-size:12px;color:var(--muted);display:block;margin-bottom:4px}
.row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:12px}
.row.three{grid-template-columns:repeat(3,minmax(0,1fr))}
.row.four{grid-template-columns:repeat(4,minmax(0,1fr))}
.hint{color:var(--muted);font-size:12px;margin-top:8px}
.status{padding:5px 10px;border-radius:999px;font-size:12px;display:inline-flex;align-items:center;gap:6px;background:rgba(41,182,246,.12);color:var(--accent)}
.status.ok{background:rgba(78,229,155,.12);color:var(--ok)}
.status.bad{background:rgba(255,93,108,.12);color:var(--danger)}
.msg{white-space:pre-wrap;background:#09111d;border:1px solid var(--line);border-radius:10px;padding:10px;color:#cdd9ef;font-size:12px;margin-top:10px;max-height:160px;overflow:auto}
.actions{display:flex;gap:6px;flex-wrap:wrap}
.flex{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.flex .grow{flex:1 1 200px}
.login-wrap{max-width:420px;margin:8vh auto 0}
.userinfo{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:13px}
.pill{padding:3px 8px;border-radius:999px;background:rgba(41,182,246,.12);color:var(--accent);font-size:11px}
@media (max-width: 980px){.grid{grid-template-columns:1fr}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.row,.row.three,.row.four{grid-template-columns:1fr}}
</style>
</head>
<body>

<!-- LOGIN VIEW -->
<div id="loginView" class="wrap">
  <div class="login-wrap panel" style="padding:24px">
    <div class="title">FMS Admin Panel</div>
    <div class="sub">请使用管理员账号登录后台。</div>
    <div style="margin-top:18px">
      <label>用户名</label>
      <input id="login_username" placeholder="管理员用户名" autocomplete="username">
    </div>
    <div style="margin-top:10px">
      <label>密码</label>
      <input id="login_password" placeholder="管理员密码" type="password" autocomplete="current-password">
    </div>
    <div style="margin-top:14px">
      <button class="btn primary" style="width:100%" onclick="doLogin()">登录</button>
    </div>
    <div id="login_msg" class="msg hidden"></div>
  </div>
</div>

<!-- MAIN VIEW -->
<div id="appView" class="wrap hidden">
  <div class="grid">
    <aside class="panel side">
      <div class="title">FMS Admin</div>
      <div class="sub">1145 管理端 · 用户/SMTP/Turnstile/日志</div>
      <div class="nav">
        <button data-page="dashboard" class="active" onclick="switchPage('dashboard')">仪表盘</button>
        <button data-page="users" onclick="switchPage('users')">用户管理</button>
        <button data-page="smtp" onclick="switchPage('smtp')">SMTP 设置</button>
        <button data-page="turnstile" onclick="switchPage('turnstile')">Turnstile 设置</button>
        <button data-page="email_logs" onclick="switchPage('email_logs')">邮件日志</button>
        <button data-page="audit_logs" onclick="switchPage('audit_logs')">审计日志</button>
      </div>
    </aside>
    <main class="panel main">
      <div class="top">
        <div>
          <div id="page_title" class="title">仪表盘</div>
          <div class="sub" id="page_sub">运行状态总览</div>
        </div>
        <div class="userinfo">
          <span class="pill" id="who">--</span>
          <button class="btn ghost" onclick="doLogout()">退出</button>
        </div>
      </div>

      <!-- Dashboard -->
      <section id="page-dashboard">
        <div class="cards">
          <div class="card"><div class="k">用户总数</div><div class="v" id="stat_users">--</div></div>
          <div class="card"><div class="k">今日注册</div><div class="v" id="stat_new">--</div></div>
          <div class="card"><div class="k">今日登录失败</div><div class="v" id="stat_fail">--</div></div>
          <div class="card"><div class="k">邮件状态</div><div class="v" id="stat_mail">--</div></div>
        </div>
        <div class="section">
          <h3>系统信息</h3>
          <div id="dash_extra" class="hint">加载中…</div>
        </div>
      </section>

      <!-- Users -->
      <section id="page-users" class="hidden">
        <div class="section">
          <h3>新增用户</h3>
          <div class="row four">
            <div><label>用户名</label><input id="nu_username"></div>
            <div><label>邮箱（可选）</label><input id="nu_email"></div>
            <div><label>密码</label><input id="nu_password" type="password"></div>
            <div><label>角色</label>
              <select id="nu_role"><option value="user">user</option><option value="admin">admin</option></select>
            </div>
          </div>
          <div style="margin-top:12px"><button class="btn primary" onclick="createUserSubmit()">创建用户</button></div>
          <div id="users_create_msg" class="msg hidden"></div>
        </div>
        <div class="section">
          <h3>用户列表</h3>
          <div class="flex" style="margin-bottom:10px">
            <div class="grow"><input id="users_q" placeholder="搜索用户名/邮箱"></div>
            <button class="btn" onclick="loadUsers()">刷新</button>
          </div>
          <table id="users_table">
            <thead><tr><th>ID</th><th>用户名</th><th>邮箱</th><th>角色</th><th>启用</th><th>创建时间</th><th>操作</th></tr></thead>
            <tbody></tbody>
          </table>
          <div id="users_msg" class="msg hidden"></div>
        </div>
      </section>

      <!-- SMTP -->
      <section id="page-smtp" class="hidden">
        <div class="section">
          <h3>SMTP 设置</h3>
          <div class="row">
            <div><label>主机</label><input id="smtp_host"></div>
            <div><label>端口</label><input id="smtp_port" type="number"></div>
          </div>
          <div class="row">
            <div><label>用户名</label><input id="smtp_user"></div>
            <div><label>密码（留空保留原值）</label><input id="smtp_pass" type="password"></div>
          </div>
          <div class="row">
            <div><label>发件人邮箱</label><input id="smtp_sender"></div>
            <div><label>发件人名称</label><input id="smtp_sender_name"></div>
          </div>
          <div class="row four">
            <div><label>SSL</label>
              <select id="smtp_use_ssl"><option value="true">是</option><option value="false">否</option></select>
            </div>
            <div><label>STARTTLS</label>
              <select id="smtp_use_tls"><option value="false">否</option><option value="true">是</option></select>
            </div>
            <div><label>验证码 TTL（秒）</label><input id="smtp_ttl" type="number"></div>
            <div><label>验证码长度</label><input id="smtp_code_len" type="number"></div>
          </div>
          <div style="margin-top:14px" class="flex">
            <button class="btn primary" onclick="saveSmtp()">保存 SMTP</button>
            <button class="btn" onclick="loadSmtp()">重新加载</button>
            <div class="grow"><input id="smtp_test_to" placeholder="测试收件人邮箱"></div>
            <button class="btn" onclick="testSmtp()">发送测试邮件</button>
          </div>
          <div id="smtp_msg" class="msg hidden"></div>
        </div>
      </section>

      <!-- Turnstile -->
      <section id="page-turnstile" class="hidden">
        <div class="section">
          <h3>Turnstile 设置</h3>
          <div class="row">
            <div><label>Site Key</label><input id="ts_site"></div>
            <div><label>Secret Key（留空保留原值）</label><input id="ts_secret" type="password"></div>
          </div>
          <div style="margin-top:14px" class="flex">
            <button class="btn primary" onclick="saveTurnstile()">保存 Turnstile</button>
            <button class="btn" onclick="loadTurnstile()">重新加载</button>
          </div>
          <div class="hint">未配置 secret_key 时注册流程会跳过人机校验；site_key 公开通过 auth_api 提供给注册页。</div>
          <div id="ts_msg" class="msg hidden"></div>
        </div>
      </section>

      <!-- Email logs -->
      <section id="page-email_logs" class="hidden">
        <div class="section">
          <h3>邮件日志</h3>
          <div class="flex" style="margin-bottom:10px">
            <div class="grow"><input id="email_logs_q" placeholder="收件人/主题/用途"></div>
            <select id="email_logs_success" style="max-width:140px">
              <option value="">全部</option><option value="true">成功</option><option value="false">失败</option>
            </select>
            <button class="btn" onclick="loadEmailLogs()">刷新</button>
          </div>
          <table id="email_logs_table">
            <thead><tr><th>ID</th><th>收件人</th><th>主题</th><th>用途</th><th>结果</th><th>错误</th><th>发送者</th><th>时间</th></tr></thead>
            <tbody></tbody>
          </table>
          <div id="email_logs_msg" class="msg hidden"></div>
        </div>
      </section>

      <!-- Audit logs -->
      <section id="page-audit_logs" class="hidden">
        <div class="section">
          <h3>审计日志</h3>
          <div class="flex" style="margin-bottom:10px">
            <div class="grow"><input id="audit_q" placeholder="管理员/动作/目标"></div>
            <button class="btn" onclick="loadAuditLogs()">刷新</button>
          </div>
          <h4 style="margin:18px 0 8px;color:#8ea3c7;font-size:12px;text-transform:uppercase">管理员操作</h4>
          <table id="audit_table">
            <thead><tr><th>ID</th><th>管理员</th><th>动作</th><th>目标</th><th>详情</th><th>IP</th><th>时间</th></tr></thead>
            <tbody></tbody>
          </table>
          <h4 style="margin:24px 0 8px;color:#8ea3c7;font-size:12px;text-transform:uppercase">登录日志</h4>
          <table id="login_audit_table">
            <thead><tr><th>ID</th><th>用户</th><th>IP</th><th>结果</th><th>详情</th><th>时间</th></tr></thead>
            <tbody></tbody>
          </table>
          <div id="audit_msg" class="msg hidden"></div>
        </div>
      </section>
    </main>
  </div>
</div>

<script>
const STORAGE_KEY = 'fms_admin_token';
let token = localStorage.getItem(STORAGE_KEY) || '';
let currentPage = 'dashboard';

const PAGE_META = {
  dashboard: {title:'仪表盘', sub:'运行状态总览'},
  users: {title:'用户管理', sub:'添加、修改、删除用户'},
  smtp: {title:'SMTP 设置', sub:'配置发件 SMTP 服务'},
  turnstile: {title:'Turnstile 设置', sub:'Cloudflare 人机校验'},
  email_logs: {title:'邮件日志', sub:'邮件发送历史记录'},
  audit_logs: {title:'审计日志', sub:'管理员操作与登录记录'}
};

function showMsg(id, text, ok){
  const el = document.getElementById(id);
  if(!el) return;
  el.textContent = text || '';
  el.classList.toggle('hidden', !text);
}

function authHeaders(extra){
  return Object.assign({'Content-Type':'application/json','Authorization':'Bearer ' + token}, extra || {});
}

async function apiFetch(url, opts){
  opts = opts || {};
  opts.headers = authHeaders(opts.headers);
  const r = await fetch(url, opts);
  if(r.status === 401){
    setLoggedOut('登录已失效，请重新登录。');
    throw new Error('unauthorized');
  }
  return r;
}

async function doLogin(){
  const username = document.getElementById('login_username').value.trim();
  const password = document.getElementById('login_password').value;
  if(!username || !password){ showMsg('login_msg','请输入用户名和密码。'); return; }
  try{
    const r = await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
    const text = await r.text();
    if(!r.ok){ showMsg('login_msg','登录失败：' + text); return; }
    const data = JSON.parse(text);
    token = data.token || '';
    localStorage.setItem(STORAGE_KEY, token);
    enterApp(data.user);
  }catch(e){ showMsg('login_msg','请求异常：' + e); }
}

function doLogout(){
  setLoggedOut('已退出登录。');
}

function setLoggedOut(message){
  token = '';
  localStorage.removeItem(STORAGE_KEY);
  document.getElementById('appView').classList.add('hidden');
  document.getElementById('loginView').classList.remove('hidden');
  if(message) showMsg('login_msg', message);
}

function enterApp(user){
  document.getElementById('loginView').classList.add('hidden');
  document.getElementById('appView').classList.remove('hidden');
  document.getElementById('who').textContent = user ? (user.username + ' · ' + user.role) : '';
  switchPage('dashboard');
}

function switchPage(name){
  currentPage = name;
  for(const btn of document.querySelectorAll('.nav button')){
    btn.classList.toggle('active', btn.dataset.page === name);
  }
  for(const sec of document.querySelectorAll('main section')){
    sec.classList.add('hidden');
  }
  const sec = document.getElementById('page-' + name);
  if(sec) sec.classList.remove('hidden');
  const meta = PAGE_META[name] || {};
  document.getElementById('page_title').textContent = meta.title || name;
  document.getElementById('page_sub').textContent = meta.sub || '';
  if(name === 'dashboard') loadDashboard();
  else if(name === 'users') loadUsers();
  else if(name === 'smtp') loadSmtp();
  else if(name === 'turnstile') loadTurnstile();
  else if(name === 'email_logs') loadEmailLogs();
  else if(name === 'audit_logs'){ loadAuditLogs(); loadLoginLogs(); }
}

async function loadDashboard(){
  try{
    const r = await apiFetch('/api/dashboard');
    if(!r.ok) return;
    const d = await r.json();
    const s = d.stats || {};
    document.getElementById('stat_users').textContent = s.total_users ?? '--';
    document.getElementById('stat_new').textContent = s.new_users_today ?? '--';
    document.getElementById('stat_fail').textContent = s.today_login_fail ?? '--';
    const ms = d.smtp || {};
    document.getElementById('stat_mail').textContent = ms.configured ? '已配置' : '未配置';
    document.getElementById('dash_extra').innerHTML =
      '启用用户：' + (s.enabled_users ?? '--') +
      ' · 管理员：' + (s.admins ?? '--') +
      '<br>今日登录：' + (s.today_logins ?? '--') +
      ' · 今日发邮件：' + (s.today_emails ?? '--') +
      ' · 今日发邮件失败：' + (s.today_email_fail ?? '--') +
      '<br>昨日注册：' + (s.new_users_yesterday ?? '--');
  }catch(e){}
}

function escapeHtml(s){
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function loadUsers(){
  const q = document.getElementById('users_q').value.trim();
  const url = '/api/users?limit=500' + (q ? '&q=' + encodeURIComponent(q) : '');
  try{
    const r = await apiFetch(url);
    const text = await r.text();
    if(!r.ok){ showMsg('users_msg','加载失败：' + text); return; }
    const d = JSON.parse(text);
    const tb = document.querySelector('#users_table tbody');
    tb.innerHTML = '';
    for(const u of d.users || []){
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + u.id + '</td>' +
        '<td>' + escapeHtml(u.username) + '</td>' +
        '<td>' + escapeHtml(u.email || '') + '</td>' +
        '<td>' + escapeHtml(u.role) + '</td>' +
        '<td>' + (u.enabled ? '是' : '否') + '</td>' +
        '<td>' + escapeHtml(u.created_at || '') + '</td>' +
        '<td><div class="actions">' +
          '<button class="btn" onclick="chgPwd(' + u.id + ')">改密</button> ' +
          '<button class="btn" onclick="toggleEnabled(' + u.id + ',' + (!u.enabled) + ')">' + (u.enabled ? '禁用' : '启用') + '</button> ' +
          '<button class="btn danger" onclick="delUser(' + u.id + ',' + JSON.stringify(u.username) + ')">删除</button>' +
        '</div></td>';
      tb.appendChild(tr);
    }
    showMsg('users_msg', '');
  }catch(e){}
}

async function createUserSubmit(){
  const payload = {
    username: document.getElementById('nu_username').value.trim(),
    email: document.getElementById('nu_email').value.trim() || null,
    password: document.getElementById('nu_password').value,
    role: document.getElementById('nu_role').value,
    enabled: true
  };
  const r = await apiFetch('/api/users',{method:'POST',body:JSON.stringify(payload)});
  const text = await r.text();
  if(!r.ok){ showMsg('users_create_msg','创建失败：' + text); return; }
  showMsg('users_create_msg','创建成功。');
  document.getElementById('nu_username').value='';
  document.getElementById('nu_email').value='';
  document.getElementById('nu_password').value='';
  loadUsers();
}

async function chgPwd(id){
  const pw = prompt('请输入新密码（至少 6 位）');
  if(!pw) return;
  const r = await apiFetch('/api/users/' + id + '/password',{method:'PATCH',body:JSON.stringify({password:pw})});
  const text = await r.text();
  showMsg('users_msg', r.ok ? '密码已修改。' : ('修改失败：' + text));
}

async function toggleEnabled(id, enabled){
  const r = await apiFetch('/api/users/' + id,{method:'PATCH',body:JSON.stringify({enabled})});
  const text = await r.text();
  if(!r.ok){ showMsg('users_msg', '操作失败：' + text); return; }
  loadUsers();
}

async function delUser(id, name){
  if(!confirm('确认删除用户 ' + name + ' ？')) return;
  const r = await apiFetch('/api/users/' + id,{method:'DELETE'});
  const text = await r.text();
  if(!r.ok){ showMsg('users_msg','删除失败：' + text); return; }
  loadUsers();
}

async function loadSmtp(){
  const r = await apiFetch('/api/settings/smtp');
  const text = await r.text();
  if(!r.ok){ showMsg('smtp_msg','加载失败：' + text); return; }
  const d = (JSON.parse(text).smtp) || {};
  document.getElementById('smtp_host').value = d.host || '';
  document.getElementById('smtp_port').value = d.port || 465;
  document.getElementById('smtp_user').value = d.username || '';
  document.getElementById('smtp_pass').value = '';
  document.getElementById('smtp_sender').value = d.sender || '';
  document.getElementById('smtp_sender_name').value = d.sender_name || '';
  document.getElementById('smtp_use_ssl').value = d.use_ssl ? 'true' : 'false';
  document.getElementById('smtp_use_tls').value = d.use_tls ? 'true' : 'false';
  document.getElementById('smtp_ttl').value = d.code_ttl_seconds || 600;
  document.getElementById('smtp_code_len').value = d.code_length || 6;
  showMsg('smtp_msg','');
}

async function saveSmtp(){
  const body = {
    host: document.getElementById('smtp_host').value.trim(),
    port: parseInt(document.getElementById('smtp_port').value || '465', 10),
    username: document.getElementById('smtp_user').value.trim(),
    password: document.getElementById('smtp_pass').value,
    sender: document.getElementById('smtp_sender').value.trim(),
    sender_name: document.getElementById('smtp_sender_name').value.trim(),
    use_ssl: document.getElementById('smtp_use_ssl').value === 'true',
    use_tls: document.getElementById('smtp_use_tls').value === 'true',
    code_ttl_seconds: parseInt(document.getElementById('smtp_ttl').value || '600', 10),
    code_length: parseInt(document.getElementById('smtp_code_len').value || '6', 10)
  };
  const r = await apiFetch('/api/settings/smtp',{method:'PUT',body:JSON.stringify(body)});
  const text = await r.text();
  showMsg('smtp_msg', r.ok ? '已保存。' : ('保存失败：' + text));
}

async function testSmtp(){
  const to = document.getElementById('smtp_test_to').value.trim();
  if(!to){ showMsg('smtp_msg','请填写测试收件人。'); return; }
  const r = await apiFetch('/api/settings/smtp/test',{method:'POST',body:JSON.stringify({recipient:to})});
  const text = await r.text();
  showMsg('smtp_msg', r.ok ? '测试邮件已发送。' : ('发送失败：' + text));
}

async function loadTurnstile(){
  const r = await apiFetch('/api/settings/turnstile');
  const text = await r.text();
  if(!r.ok){ showMsg('ts_msg','加载失败：' + text); return; }
  const d = (JSON.parse(text).turnstile) || {};
  document.getElementById('ts_site').value = d.site_key || '';
  document.getElementById('ts_secret').value = '';
  showMsg('ts_msg','');
}

async function saveTurnstile(){
  const body = {
    site_key: document.getElementById('ts_site').value.trim(),
    secret_key: document.getElementById('ts_secret').value
  };
  const r = await apiFetch('/api/settings/turnstile',{method:'PUT',body:JSON.stringify(body)});
  const text = await r.text();
  showMsg('ts_msg', r.ok ? '已保存。' : ('保存失败：' + text));
}

async function loadEmailLogs(){
  const q = document.getElementById('email_logs_q').value.trim();
  const s = document.getElementById('email_logs_success').value;
  let url = '/api/logs/email?limit=200';
  if(q) url += '&q=' + encodeURIComponent(q);
  if(s) url += '&success=' + s;
  const r = await apiFetch(url);
  const text = await r.text();
  if(!r.ok){ showMsg('email_logs_msg','加载失败：' + text); return; }
  const d = JSON.parse(text);
  const tb = document.querySelector('#email_logs_table tbody');
  tb.innerHTML = '';
  for(const it of d.items || []){
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + it.id + '</td>' +
      '<td>' + escapeHtml(it.recipient) + '</td>' +
      '<td>' + escapeHtml(it.subject) + '</td>' +
      '<td>' + escapeHtml(it.purpose) + '</td>' +
      '<td>' + (it.success ? '<span class="status ok">成功</span>' : '<span class="status bad">失败</span>') + '</td>' +
      '<td>' + escapeHtml(it.error || '') + '</td>' +
      '<td>' + escapeHtml(it.sent_by || '') + '</td>' +
      '<td>' + escapeHtml(it.created_at || '') + '</td>';
    tb.appendChild(tr);
  }
  showMsg('email_logs_msg','');
}

async function loadAuditLogs(){
  const q = document.getElementById('audit_q').value.trim();
  let url = '/api/logs/admin?limit=200';
  if(q) url += '&q=' + encodeURIComponent(q);
  const r = await apiFetch(url);
  const text = await r.text();
  if(!r.ok){ showMsg('audit_msg','加载失败：' + text); return; }
  const d = JSON.parse(text);
  const tb = document.querySelector('#audit_table tbody');
  tb.innerHTML = '';
  for(const it of d.items || []){
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + it.id + '</td>' +
      '<td>' + escapeHtml(it.admin_username) + '</td>' +
      '<td>' + escapeHtml(it.action) + '</td>' +
      '<td>' + escapeHtml(it.target) + '</td>' +
      '<td>' + escapeHtml(it.detail) + '</td>' +
      '<td>' + escapeHtml(it.ip) + '</td>' +
      '<td>' + escapeHtml(it.created_at || '') + '</td>';
    tb.appendChild(tr);
  }
  showMsg('audit_msg','');
}

async function loadLoginLogs(){
  const q = document.getElementById('audit_q').value.trim();
  let url = '/api/logs/login?limit=200';
  if(q) url += '&q=' + encodeURIComponent(q);
  const r = await apiFetch(url);
  if(!r.ok) return;
  const d = await r.json();
  const tb = document.querySelector('#login_audit_table tbody');
  tb.innerHTML = '';
  for(const it of d.items || []){
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + it.id + '</td>' +
      '<td>' + escapeHtml(it.username) + '</td>' +
      '<td>' + escapeHtml(it.ip) + '</td>' +
      '<td>' + (it.success ? '<span class="status ok">成功</span>' : '<span class="status bad">失败</span>') + '</td>' +
      '<td>' + escapeHtml(it.detail || '') + '</td>' +
      '<td>' + escapeHtml(it.created_at || '') + '</td>';
    tb.appendChild(tr);
  }
}

async function bootstrap(){
  if(!token){ setLoggedOut(''); return; }
  try{
    const r = await fetch('/api/me',{headers:authHeaders()});
    if(!r.ok){ setLoggedOut(''); return; }
    const d = await r.json();
    enterApp(d.user);
  }catch(e){ setLoggedOut(''); }
}

bootstrap();
</script>
</body>
</html>
"""
