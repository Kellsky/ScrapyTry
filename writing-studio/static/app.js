const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const text = value => Array.isArray(value) ? value.join('；') : typeof value === 'object' && value ? JSON.stringify(value) : String(value ?? '');
const paths = {
  home:'M3 10 12 3l9 7M5 9v11h5v-6h4v6h5V9',
  inbox:'M4 4h16v16H4zM4 14h5l1 3h4l1-3h5',
  review:'m8 12 3 3 5-6M8 3H5v18h14V3h-3M9 2h6v4H9z',
  book:'M12 5c-3-2-7-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Zm0 0v15',
  settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM10 3h4l1 3 3 1 3 2v5l-3 1-1 3-2 3h-5l-1-3-3-1-3-2v-5l3-1 1-3Z',
  plus:'M12 5v14M5 12h14', arrow:'M5 12h14m-6-6 6 6-6 6', back:'M19 12H5m6-6-6 6 6 6',
  file:'M6 3h8l4 4v14H6zM14 3v5h5M9 12h6M9 16h6', spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4M18 4h4',
  check:'m5 12 4 4L19 6', clock:'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  leaf:'M20 3c-8-1-15 2-15 9a6 6 0 0 0 6 6c7 0 10-7 9-15ZM3 21 15 9',
  search:'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',link:'M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2',
  image:'M3 3h18v18H3zM3 17l5-5 4 4 4-6 5 7M9 7h.01', close:'m6 6 12 12M6 18 18 6',
  upload:'M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5',edit:'m14 5 5 5M4 20l5-1L20 8a3 3 0 0 0-4-4L5 15Z',
  download:'M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5',mail:'M3 5h18v14H3zM3 5l9 8 9-8',
  info:'M12 11v6M12 7h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',trash:'M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7',
  up:'m7 14 5-5 5 5',down:'m7 10 5 5 5-5',refresh:'M20 7v5h-5M4 17v-5h5M19 12a7 7 0 0 0-12-5L4 10m16 4-3 3A7 7 0 0 1 5 12',shield:'m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Zm-4 9 3 3 5-6',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.file}"/></svg>`;
const navItems = [['home','home','工作台'],['tasks','inbox','征稿箱'],['review','review','待我审阅'],['profile','book','我的素材'],['settings','settings','模型设置']];
const activeStatuses = ['queued','extracting','writing','reviewing','revising'];
const statusNames = {queued:'等待开始',extracting:'提取要求中',writing:'正在写作',reviewing:'交叉点评中',revising:'正在修改',needs_input:'待补充信息',needs_review:'待你审阅',approved:'已审阅',failed:'处理失败'};
const state = {tasks:[],profile:{},settings:{},providers:[],page:'home',task:null,filter:'all',query:'',tab:'requirements',editing:false,editText:'',loading:true,modal:null,create:null,busy:false};
let toastTimer, pollBusy = false, lastFocus;
const countWords = value => ((value || '').match(/[\u3400-\u9fff]|[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*/g) || []).length;
const prettyTime = value => {
  if (!value) return '刚刚'; const date = new Date(value.endsWith?.('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z');
  if (Number.isNaN(+date)) return String(value).slice(0,16);
  const delta = Date.now() - date; if (delta < 60000) return '刚刚'; if (delta < 3600000) return `${Math.floor(delta/60000)} 分钟前`; if (delta < 86400000) return `${Math.floor(delta/3600000)} 小时前`;
  return date.toLocaleDateString('zh-CN',{month:'short',day:'numeric'});
};
const statusClass = task => task.status === 'needs_review' ? 'review' : task.status === 'approved' ? 'approved' : task.status === 'needs_input' ? 'input' : task.status === 'failed' ? 'failed' : 'active';
const badge = task => `<span class="status-badge ${statusClass(task)}">${esc(statusNames[task.status] || task.status)}</span>`;
const field = (label,name,value='',hint='',type='text') => `<label class="form-field"><span>${esc(label)}</span><input name="${esc(name)}" type="${type}" value="${esc(value)}" ${type==='password'?'autocomplete="new-password"':''}>${hint?`<small>${esc(hint)}</small>`:''}</label>`;
async function api(path, options = {}) {
  const opts = {...options, credentials:'same-origin'};
  if (opts.body && !(opts.body instanceof FormData)) { opts.headers = {...opts.headers,'Content-Type':'application/json'}; opts.body = JSON.stringify(opts.body); }
  let response;
  try { response = await fetch(path, opts); } catch { throw new Error('暂时无法连接服务，请检查服务是否正在运行。'); }
  if (!response.ok) {
    let message = `请求未成功（${response.status}）`;
    try { const data = await response.json(); message = Array.isArray(data.detail) ? data.detail.map(i=>i.msg).join('；') : text(data.detail || data.error || message); } catch {}
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}
function toast(message,error=false) {
  clearTimeout(toastTimer); $('#toast-root').innerHTML = `<div class="toast ${error?'error':''}" role="status">${icon(error?'info':'check')}<span>${esc(message)}</span></div>`;
  toastTimer = setTimeout(()=>$('#toast-root').innerHTML='',5000);
}
function stats() { return {total:state.tasks.length,active:state.tasks.filter(t=>activeStatuses.includes(t.status)).length,review:state.tasks.filter(t=>t.status==='needs_review').length,approved:state.tasks.filter(t=>t.status==='approved').length}; }
function demoNotice(task) { return (!task || task.mode === 'demo') ? `<div class="demo-notice">${icon('info')}<span>演示模式：使用预设内容演示工作流，未调用真实 AI。示例稿件仅供体验。<button data-action="settings">配置模型</button>后可创建真实任务。</span></div>` : `<div class="demo-notice">${icon('shield')}<span>真实模型任务 · 请在最终审阅时核对事实、征稿要求及 AI 使用约定。系统不会自动投稿。</span></div>`; }
function renderShell(content) {
  const page = state.page==='task' ? 'tasks' : state.page; const counts = stats();
  const navigation = navItems.map(([key,i,label])=>`<a href="#${key}" class="nav-item ${page===key?'active':''}" aria-label="${label}" ${page===key?'aria-current="page"':''}>${icon(i)}<span>${label}</span>${key==='review'&&counts.review?`<span class="nav-count">${counts.review}</span>`:''}</a>`).join('');
  const label = state.page==='task'?'稿件详情':navItems.find(item=>item[0]===page)?.[2] || '工作台';
  $('#app').innerHTML = `<div class="app-shell"><aside class="sidebar"><a class="brand" href="#home" aria-label="稿间首页"><span class="brand-mark">稿</span><div class="brand-text"><div class="brand-name">稿间</div><div class="brand-sub">A SPACE TO WRITE</div></div></a><div class="nav-label">我的工作空间</div><nav class="nav-list" aria-label="主导航">${navigation}</nav><div class="sidebar-note"><div class="leaf">${icon('leaf')}</div><p>让灵感停留，<br>让写作从容。</p><small>WORDS FIND THEIR WAY.</small></div><div class="sidebar-foot"><i class="online-dot"></i>你的个人写作工作台</div></aside><div class="app-body"><header class="topbar"><div class="breadcrumbs"><span>我的工作空间</span><span class="crumb-divider">/</span><span>${label}</span></div><div class="topbar-right"><span class="topbar-date">${new Intl.DateTimeFormat('zh-CN',{month:'long',day:'numeric',weekday:'long',timeZone:'Asia/Shanghai'}).format(new Date())}</span><span class="mode-pill ${state.settings.configured?'live':''}"><i></i>${state.settings.configured?'模型已配置':'演示体验'}</span><a class="avatar" href="#profile" title="我的素材">${esc((state.profile.pen_name || '写').slice(0,1))}</a></div></header><main id="main" class="main" tabindex="-1">${content}</main></div><nav class="mobile-nav" aria-label="手机导航">${navItems.map(([key,i,label])=>`<a href="#${key}" class="${page===key?'active':''}" ${page===key?'aria-current="page"':''}>${icon(i)}<span>${label}</span></a>`).join('')}</nav></div>`;
  bindCommon();
}
function intro(eyebrow,title,subtitle,button=true) { return `<div class="page-intro"><div><span class="eyebrow">${eyebrow}</span><h1>${title}</h1><p>${subtitle}</p></div>${button?`<button class="primary-btn" data-action="create">${icon('plus')}新建写作任务</button>`:''}</div>`; }
function taskRow(task) { const req = task.requirements || {}; return `<a href="#task/${encodeURIComponent(task.id)}" class="task-row"><div class="task-thumbnail ${statusClass(task)}">${icon(task.status==='approved'?'check':'file')}</div><div class="task-main"><div class="task-title">${esc(task.title || req.title || '未命名写作任务')}${task.is_sample?'<span class="sample-tag">示例</span>':''}</div><div class="task-meta"><span>${esc(req.publication || (task.source_type==='images'?'截图导入':task.source_type==='url'?'链接导入':'正文导入'))}</span><span>${task.mode==='demo'?'演示任务':'真实模型'}</span>${task.word_count?`<span>${esc(task.word_count)} 字</span>`:''}${req.genre?`<span>${esc(req.genre)}</span>`:''}</div></div><div class="task-right">${badge(task)}<span class="task-time">${esc(prettyTime(task.updated_at || task.created_at))}</span></div></a>`; }
function empty(title='还没有写作任务',description='把第一条征稿放进来，让写作从这里开始。',button=true) { return `<div class="empty-state"><div class="empty-icon">${icon('file')}</div><h3>${title}</h3><p>${description}</p>${button?'<button class="secondary-btn" data-action="create">导入一条征稿</button>':''}</div>`; }
function filteredTasks() { return state.tasks.filter(t=>(state.filter==='all'||state.filter==='active'&&activeStatuses.includes(t.status)||state.filter==='review'&&['needs_review','needs_input','failed'].includes(t.status)||state.filter==='approved'&&t.status==='approved')&&(!state.query||`${t.title} ${t.requirements?.publication||''} ${t.requirements?.topic||''}`.toLowerCase().includes(state.query.toLowerCase()))); }
function taskPanel(limit=0) { const counts = stats(); const tasks = filteredTasks(); return `<div class="task-panel"><div class="task-filter" role="tablist" aria-label="任务状态">${[['all','全部任务',counts.total],['active','进行中',counts.active],['review','待处理',state.tasks.filter(t=>['needs_review','needs_input','failed'].includes(t.status)).length],['approved','已审阅',counts.approved]].map(([key,label,num])=>`<button role="tab" aria-selected="${state.filter===key}" class="filter-btn ${state.filter===key?'active':''}" data-filter="${key}">${label}<span>${num}</span></button>`).join('')}</div><div class="task-list" id="task-list">${tasks.length?(limit?tasks.slice(0,limit):tasks).map(taskRow).join(''):empty(state.query?'没有找到相关任务':'这里还很安静',state.query?'换个关键词，或查看其他任务状态。':'导入征稿信息，自动完成写作、点评与修改。',!state.query)}</div><div class="panel-foot">${icon('shield')}内容保存在当前服务中 · 由你完成最终审阅与投稿</div></div>`; }
function workflow() { return `<div class="workflow-card"><div class="workflow-heading">${icon('spark')}把流程交给稿间</div><div class="workflow-steps">${[['导入征稿','链接、正文或多张截图'],['自动写作','结合要求与个人素材'],['交叉点评','两路评审，有限轮修改'],['最终审阅','你保留最后的决定权']].map(([title,sub],i)=>`<div class="workflow-step"><span class="step-number">0${i+1}</span><div><h3>${title}</h3><p>${sub}</p></div></div>`).join('')}</div></div>`; }
function home() { const s=stats(); renderShell(`${intro('YOUR WRITING SPACE','写作工作台','把繁琐交给流程，把心思留给文字。')}<section class="hero"><div class="hero-copy"><span class="hero-label">FROM AN IDEA TO A FINISHED STORY</span><h2>好文章，从容写。</h2><p>一条征稿，一次开始。<br>从初稿到打磨，让每一步都有条不紊。</p><button class="hero-link" data-action="example">用一条示例，体验完整流程 ${icon('arrow')}</button></div><div class="paper-art" aria-hidden="true"><div class="art-sheet back"></div><div class="art-sheet front"><div class="art-caption">A NOTE FOR EVERYDAY LIFE</div><h3>在寻常里，<br>遇见微光。</h3><div class="art-lines"><span></span><span></span><span></span><span></span></div><div class="art-seal">稿</div></div><div class="art-pen"></div><div class="art-tag">${icon('check')}灵感，正在成稿</div></div></section><div class="stats-grid">${[['all','inbox',s.total,'全部写作任务',''],['active','spark',s.active,'自动处理中','green'],['review','review',s.review,'等待你的审阅','rust'],['approved','check',s.approved,'已完成审阅','gold']].map(([filter,i,n,label,color])=>`<button class="stat-card" data-stat="${filter}"><span class="stat-icon ${color}">${icon(i)}</span><div><div class="stat-value">${String(n).padStart(2,'0')}</div><div class="stat-label">${label}</div></div><span class="stat-arrow">${icon('arrow')}</span></button>`).join('')}</div><div class="dashboard-grid"><section><div class="section-head"><h2>最近的写作 <small>RECENT WORK</small></h2><a href="#tasks" class="text-link">查看全部 ${icon('arrow')}</a></div>${taskPanel(5)}</section><aside class="dashboard-aside">${workflow()}<div class="tip-card"><span class="eyebrow">MAKE IT YOURS</span><h3>文字，也可以更像你。</h3><p>保存你的文风、经历和写作素材，<br>让每一次创作都有自己的底色。</p><a class="text-link" href="#profile">完善我的素材 ${icon('arrow')}</a></div></aside></div><div class="bottom-note">${icon('leaf')}稿间，让表达慢慢发生。<span>·</span>原型演示 · 不会自动投稿</div>`); bindFilters(); }
function listPage() { const review=state.page==='review'; renderShell(`${intro(review?'READY FOR YOUR EYES':'YOUR SUBMISSIONS',review?'待我审阅':'征稿箱',review?'最后一道目光，留给你自己。':'收藏值得写的题目，照看正在生长的文章。')}<div class="list-toolbar"><label class="search-wrap">${icon('search')}<input id="task-search" placeholder="搜索题目、刊物或主题" value="${esc(state.query)}" aria-label="搜索写作任务"></label><button class="secondary-btn" data-action="refresh">${icon('refresh')}刷新</button></div>${taskPanel()}`); bindFilters(); $('#task-search')?.addEventListener('input',e=>{state.query=e.target.value; $('#task-list').innerHTML=filteredTasks().map(taskRow).join('') || empty('没有找到相关任务','换个关键词试试。',false);}); }
function profilePage() { renderShell(`${intro('A LITTLE MORE LIKE YOU','我的素材','让 AI 理解你的表达，也尊重你的真实经历。',false)}<div class="settings-layout"><form id="profile-form" class="form-panel"><section class="form-section"><h2>你的写作名片</h2><p>这些信息只会在你创建真实写作任务时作为创作上下文使用。</p><div class="form-grid">${field('笔名','pen_name',state.profile.pen_name||'','用于工作台显示与稿件署名，可随时修改。')}<label class="form-field full"><span>喜欢怎样的文字</span><textarea name="style" rows="4" placeholder="例如：克制、细腻、有生活感；少用抒情口号，用细节推动故事。">${esc(state.profile.style)}</textarea></label><label class="form-field full"><span>可使用的真实素材与样稿</span><textarea name="materials" rows="9" placeholder="写下可使用的经历、场景，或粘贴你喜欢的写作样稿。请注明哪些属于虚构。">${esc(state.profile.materials)}</textarea><small>真实经历不足时，系统应请求补充；不会把虚构内容自动当作你的亲身经历。</small></label></div></section><div id="profile-error"></div><div class="form-actions"><button class="primary-btn" type="submit">${icon('check')}保存我的素材</button></div></form><aside class="form-aside"><span class="eyebrow">YOUR VOICE MATTERS</span><h3>比“写得好”更重要的，<br>是“像你写的”。</h3><p>可以从一段你熟悉的生活开始：一条街、一场相遇、一种气味。<br><br>保存前，建议去除不想发给模型的敏感信息。真实任务会把相关素材发送到你配置的服务。</p></aside></div>`); $('#profile-form').addEventListener('submit',saveProfile); }
function safeExternal(value) {
  try { const url=new URL(value); return url.protocol==='https:'?url.href:''; } catch { return ''; }
}
function providerDetails(provider) {
  if(!provider)return '<p class="provider-note">使用你自己的兼容 API 地址与模型名称。密钥请在下方填写，保存前不会发起请求。</p>';
  const signup=safeExternal(provider.signup_url),docs=safeExternal(provider.docs_url);
  return `<div class="provider-details"><p>${esc(provider.free_note||'免费额度和可用模型以服务商当前账号控制台为准。')}</p><div class="provider-links">${signup?`<a href="${esc(signup)}" target="_blank" rel="noopener noreferrer">${icon('link')}官方领取免费 Token ${icon('arrow')}</a>`:''}${docs?`<a href="${esc(docs)}" target="_blank" rel="noopener noreferrer">查看官方说明 ${icon('arrow')}</a>`:''}</div><small>使用你自己的账号与 Token；无需将密钥发给聊天助手。免费额度可能调整，不代表永久免费或无限使用。</small></div>`;
}
function settingsPage() {
  const s=state.settings,providers=state.providers||[];
  const selected=providers.find(p=>p.base_url===s.base_url)?.id||(!s.configured?providers[0]?.id:'custom')||'custom';
  renderShell(`${intro('THE MINDS BEHIND YOUR WORDS','模型设置','选择你的写作搭档与评审搭档。',false)}
    <div class="settings-layout"><form id="settings-form" class="form-panel">
      <section class="provider-onboarding" aria-labelledby="provider-heading">
        <span class="eyebrow">START WITH AN OFFICIAL FREE TIER</span>
        <h2 id="provider-heading">先用官方免费额度，把流程跑起来。</h2>
        <p>领取自己的 Token，填入模型设置，再测试实际连接。</p>
        <div class="provider-picker"><label class="form-field"><span>接入方案</span><select id="provider-select" aria-label="选择 API 接入方案">${providers.map(p=>`<option value="${esc(p.id)}" ${selected===p.id?'selected':''}>${esc(p.name)}</option>`).join('')}<option value="custom" ${selected==='custom'?'selected':''}>自定义兼容服务</option></select></label><button class="secondary-btn" id="apply-provider" type="button" ${selected==='custom'?'disabled':''}>${icon('edit')}填入表单</button></div>
        <div id="provider-info">${providerDetails(providers.find(p=>p.id===selected))}</div>
        <p class="provider-apply-note" id="provider-apply-note">预设只填入地址和模型，不会保存或调用 API；已有独立评审服务会保留。</p>
      </section>
      <div class="settings-summary">${icon(s.configured?'check':'info')}<div><strong>${s.configured?'模型设置已保存，连接状态请实际测试':'当前可以完整体验演示模式'}</strong><small>${s.configured?'填写密钥不等于连接成功；下方可测试写作与评审服务。':'演示使用预设内容。保存可用 API 后，才能生成真实稿件。'}</small></div></div>
      <section class="form-section"><h2>写作服务</h2><p>接入支持 OpenAI Chat Completions 格式的模型 API。</p><div class="form-grid">
        ${field('API 基础地址','base_url',s.base_url||'https://api.openai.com/v1','填写 API 根路径，不包含 /chat/completions。','url')}
        ${field('API Key / Token','api_key','',s.has_key?'已保存密钥；同一服务留空会保留。更换服务需填写新 Token。':'填写自己的服务商 Token，服务端保存，不返回浏览器。','password')}
        ${field('写作模型','writer_model',s.writer_model||'','先应用官方预设，或读取账号当前可用模型。')}
        ${field('视觉 / OCR 模型（可选）','vision_model',s.vision_model||'','只有支持图片输入的模型才能识别截图；可先留空。')}
      </div><div id="key-change-warning" aria-live="polite"></div></section>
      <section class="form-section"><h2>独立评审服务</h2><p>可让另一家模型点评稿件；地址留空时沿用写作服务。</p><div class="form-grid">
        ${field('评审 API 地址（可选）','reviewer_base_url',s.reviewer_base_url||'','使用独立服务时需填写对应的 API Token。','url')}
        ${field('评审 API Key（可选）','reviewer_api_key','',s.has_reviewer_key?'已保存独立密钥；同一服务留空保留。换服务需填新密钥。':'独立评审服务的 Token；沿用写作服务时可留空。','password')}
        ${field('评审模型','reviewer_model',s.reviewer_model||'','两个评审会话分别核对征稿要求与表达。')}
      </div></section>
      <section class="form-section"><h2>用量上限</h2><div class="form-grid">
        ${field('每日 token 上限','daily_limit',s.daily_limit||100000,'这是应用自己的调用上限，不能替代服务商的免费额度。','number')}
        <div class="settings-summary" style="margin:0"><div><strong>${Number(s.used_tokens||0).toLocaleString()} tokens</strong><small>今日记录的模型用量 · 非人民币费用</small></div></div>
      </div><p class="inline-note">免费余额、限流和可用模型以官方账号控制台为准。聊天应用会员通常不包含 API 额度。</p></section>
      <div id="settings-error"></div><div class="form-actions"><button class="primary-btn" type="submit">${icon('check')}保存模型设置</button></div>
      <section class="form-section model-connect-section" aria-labelledby="connect-heading"><h2 id="connect-heading">保存后，验证实际连接。</h2><p>测试使用已保存的设置，会发起简短的真实请求，并可能消耗免费额度。修改表单后请先保存。</p>
        <div class="model-test-buttons"><button class="secondary-btn" type="button" data-model-action="test" data-role="writer">${icon('spark')}测试写作</button><button class="secondary-btn" type="button" data-model-action="test" data-role="reviewer">${icon('review')}测试评审</button><button class="secondary-btn" type="button" data-model-action="test" data-role="vision">${icon('image')}测试截图模型</button></div>
        <div class="model-catalog-controls"><label class="form-field"><span>读取账号可用模型</span><select id="model-catalog-role" aria-label="选择读取哪一个服务的模型"><option value="writer">写作服务</option><option value="reviewer">评审服务</option><option value="vision">截图服务</option></select></label><button class="secondary-btn" type="button" id="load-models">${icon('refresh')}读取可用模型</button></div>
        <p class="inline-note">读取列表后可在模型输入框选择建议，也可手动填写模型 ID。出现在列表中不代表支持图片输入。</p>
        <div id="settings-connection-result" aria-live="polite"></div><datalist id="model-options-writer"></datalist><datalist id="model-options-reviewer"></datalist><datalist id="model-options-vision"></datalist>
      </section>
    </form><aside class="form-aside"><span class="eyebrow">THREE SIMPLE STEPS</span><h3>接好模型，<br>开始真实写作。</h3><ol class="provider-steps"><li><strong>官方领取 Token</strong><span>注册自己的服务商账号，查看当前免费额度和使用规则。</span></li><li><strong>填入并保存</strong><span>选择预设、填写 Token；独立评审服务使用各自的密钥。</span></li><li><strong>测试，再开始任务</strong><span>写作、评审连接成功后，创建任务并选择“真实模型”。</span></li></ol><p>多模型互评帮助打磨文章；事实仍需要来源或你的核对。</p></aside></div>`);
  const form=$('#settings-form');form.addEventListener('submit',saveSettings);
  $('#provider-select').addEventListener('change',event=>{const provider=providers.find(p=>p.id===event.target.value);$('#provider-info').innerHTML=providerDetails(provider);$('#apply-provider').disabled=!provider;});
  $('#apply-provider').addEventListener('click',()=>{
    const provider=providers.find(p=>p.id===$('#provider-select').value);if(!provider)return;
    form.elements.base_url.value=provider.base_url||'';form.elements.writer_model.value=provider.writer_model||'';
    form.elements.vision_model.value=provider.vision_model||'';
    if(!form.elements.reviewer_base_url.value.trim())form.elements.reviewer_model.value=provider.reviewer_model||provider.writer_model||'';
    $('#provider-apply-note').textContent='预设已填入，尚未保存。请填入该服务的 Token，保存设置后再测试；独立评审服务已保留。';
    updateKeyWarning();form.elements.api_key.focus({preventScroll:true});toast('已填入预设，尚未保存或调用 API');
  });
  ['base_url','reviewer_base_url','api_key','reviewer_api_key'].forEach(name=>form.elements[name].addEventListener('input',updateKeyWarning));
  $$('[data-model-action]').forEach(button=>button.addEventListener('click',()=>modelOperation('test',button.dataset.role)));
  $('#load-models').addEventListener('click',()=>modelOperation('models',$('#model-catalog-role').value));
  for(const role of ['writer','reviewer','vision'])form.elements[`${role}_model`].setAttribute('list',`model-options-${role}`);
  updateKeyWarning();
}
function settingsOrigin(value) {try{return new URL(value).origin;}catch{return '';}}
function updateKeyWarning() {
  const form=$('#settings-form'),box=$('#key-change-warning');if(!form||!box)return;
  const messages=[];
  const current=settingsOrigin(form.elements.base_url.value),saved=settingsOrigin(state.settings.base_url);
  if(state.settings.has_key&&current&&saved&&current!==saved)messages.push(form.elements.api_key.value?'你已更换写作服务，请确认当前 Token 属于新的服务商。':'你已更换写作服务，原密钥不会转发给新服务；请填写新的 Token 后保存。');
  const reviewCurrent=settingsOrigin(form.elements.reviewer_base_url.value),reviewSaved=settingsOrigin(state.settings.reviewer_base_url);
  if(state.settings.has_reviewer_key&&reviewCurrent&&reviewSaved&&reviewCurrent!==reviewSaved)messages.push('你已更换独立评审服务，请填写新服务的 Token，避免跨服务使用旧密钥。');
  box.innerHTML=messages.length?`<div class="provider-key-warning">${icon('shield')}<span>${messages.map(esc).join('<br>')}</span></div>`:'';
}
function settingsHaveUnsavedChanges() {
  const form=$('#settings-form');if(!form)return false;
  if(form.elements.api_key.value||form.elements.reviewer_api_key.value)return true;
  return ['base_url','writer_model','reviewer_model','vision_model','reviewer_base_url','daily_limit'].some(name=>String(form.elements[name].value).trim()!==String(state.settings[name]??(name==='daily_limit'?100000:'')).trim());
}
function connectionResult(kind,message) {
  const box=$('#settings-connection-result');if(box)box.innerHTML=`<div class="connection-result ${kind}">${kind==='pending'?'<span class="spinner"></span>':icon(kind==='success'?'check':'info')}<span>${esc(message)}</span></div>`;
}
async function modelOperation(action,role) {
  if(state.settingsActionBusy)return;
  if(settingsHaveUnsavedChanges()){connectionResult('warning','表单有未保存的修改。请先点击“保存模型设置”，再测试连接或读取模型；当前输入已保留。');return;}
  if(action==='test'&&!state.settings.configured){connectionResult('warning','请先填写并保存自己的 API Token、写作模型与评审模型，再进行测试。');return;}
  if(action==='models'&&!(role==='reviewer'?(state.settings.has_reviewer_key||state.settings.has_key):state.settings.has_key)){connectionResult('warning','请先填写并保存该服务的 Token，再读取当前账号的模型列表。');return;}
  if(action==='test'&&role==='vision'&&!state.settings.vision_model){connectionResult('warning','截图模型尚未配置。可先填写支持图片输入的模型并保存，也可通过粘贴正文开始写作。');return;}
  const roleName={writer:'写作',reviewer:'评审',vision:'截图'}[role]||'模型';
  connectionResult('pending',action==='test'?`正在向已保存的${roleName}服务发起简短测试…`:`正在读取${roleName}服务当前账号的模型列表…`);
  state.settingsActionBusy=true;const buttons=$$('[data-model-action],#load-models');buttons.forEach(button=>button.disabled=true);
  try{
    const data=await api(`/api/settings/${action}`,{method:'POST',body:{role}});
    if(action==='test'){
      if(!data.ok)throw new Error(data.message||'服务没有返回成功的测试结果。');
      connectionResult('success',`${roleName}连接测试成功${data.model?` · ${data.model}`:''}。${data.message||''}`);
    }else{
      const models=(data.models||[]).map(model=>typeof model==='string'?model:model.id).filter(id=>typeof id==='string'&&id);
      const targets=role==='writer'&&!state.settings.reviewer_base_url?['writer','reviewer','vision']:[role];
      for(const target of targets){const datalist=$(`#model-options-${target}`);if(datalist)datalist.innerHTML=models.map(id=>`<option value="${esc(id)}"></option>`).join('');}
      connectionResult(models.length?'success':'warning',models.length?`已读取 ${models.length} 个模型 ID，可在${roleName}模型输入框选择。实际权限、免费额度和图片支持仍以服务商为准。`:(data.message||'服务没有返回可用模型，请按官方说明手动填写模型 ID。'));
    }
  }catch(error){connectionResult('error',error.message);}finally{state.settingsActionBusy=false;buttons.forEach(button=>button.disabled=false);}
}
function stageIndex(t) { return {queued:0,extracting:0,writing:1,reviewing:2,revising:3,needs_input:0,needs_review:4,approved:5,failed:0}[t.status]??0; }
function detailPage() {
  const t=state.task;if(!t){renderShell('<div class="empty-state"><span class="spinner"></span><p>正在打开稿件…</p></div>');return;}
  const steps=['提取要求','生成初稿','交叉点评','修改打磨','最终审阅']; const idx=stageIndex(t); const active=activeStatuses.includes(t.status); const approved=t.status==='approved'; const blockers=t.blockers||[]; const canApprove=t.status==='needs_review'&&!blockers.length&&!(t.checks||[]).some(c=>c.status==='fail');
  renderShell(`<button class="back-btn" data-action="back">${icon('back')}返回征稿箱</button><div class="page-intro detail-intro"><div><span class="eyebrow">A WORK IN PROGRESS</span><h1>${esc(t.title||'写作任务')}</h1><div class="detail-meta">${badge(t)}<span>${esc(t.requirements?.publication||'征稿信息')}</span><span>第 ${esc(t.round||0)} / ${esc(t.max_rounds||3)} 轮修改</span><span>${esc(prettyTime(t.created_at))}创建</span></div></div><button class="ghost-btn" data-action="delete">${icon('trash')}删除任务</button></div>${demoNotice(t)}<div class="detail-stage">${steps.map((label,i)=>`<div class="stage-item ${i<idx?'done':i===idx?'current':''}"><span class="stage-dot">${i<idx?icon('check'):i+1}</span><span>${label}</span></div>`).join('')}</div>${blockers.length?`<div class="blocker-box"><strong>需要你补充或核对</strong><br>${blockers.map(esc).join('<br>')}</div>`:''}<div class="detail-grid"><section><div class="draft-card"><div class="draft-toolbar"><div class="draft-toolbar-title">${icon('file')}当前稿件 <small>${esc(t.word_count||countWords(t.draft))} 字</small></div><div class="draft-actions">${t.draft&&!state.editing?`<button class="ghost-btn" data-action="edit" ${active?'disabled':''}>${icon('edit')}编辑</button><button class="ghost-btn" data-action="refine" ${active?'disabled':''}>${icon('spark')}再打磨</button>`:''}</div></div>${state.editing?`<textarea class="draft-editor" id="draft-editor" aria-label="编辑文章">${esc(state.editText)}</textarea><div class="edit-foot"><span id="edit-count">${countWords(state.editText)} 字 · 修改会生成新版本</span><div class="modal-actions"><button class="secondary-btn" data-action="cancel-edit">取消</button><button class="primary-btn" data-action="save-edit">保存修改</button></div></div>`:t.draft?`<article class="draft-content">${esc(t.draft)}</article>`:`<div class="draft-empty">${active?'<span class="spinner"></span>':icon('file')}<h3 style="margin-top:17px">${active?'文字正在酝酿':t.status==='needs_input'?'等一份更完整的材料':'稿件暂未生成'}</h3><p>${esc(t.message||'导入完整的征稿信息后，写作流程就会开始。')}</p>${['failed','needs_input'].includes(t.status)?'<button class="secondary-btn" style="margin-top:20px" data-action="retry">补充材料 / 重试</button>':''}</div>`}<div class="review-bar"><div class="review-bar-copy">${approved?'这篇稿件已由你完成审阅':active?'后台处理中，可以稍后回来查看':canApprove?'让最后一道目光，落在文字上':'请先处理核对表中的问题'}<small>${approved?'可导出使用；系统没有发送或发布文章。':'确认审阅只改变任务状态，不会自动投稿。'}</small></div><button class="primary-btn" data-action="approve" ${!canApprove||state.editing?'disabled':''}>${icon('check')}${approved?'已完成审阅':'完成审阅'}</button></div></div>${t.draft?`<div class="form-actions" style="justify-content:flex-start;margin-top:14px;flex-wrap:wrap"><button class="secondary-btn" data-export="docx">${icon('download')}导出 Word</button><button class="secondary-btn" data-export="txt">纯文本</button><button class="secondary-btn" data-export="email">${icon('mail')}邮件草稿</button></div>`:''}<details class="events-list"><summary>处理记录 · ${(t.events||[]).length} 条</summary>${(t.events||[]).map(e=>`<div class="event"><time>${esc(prettyTime(e.created_at))}</time><span>${esc(e.message||e.stage)}</span></div>`).join('')||'<div class="event">还没有执行记录。</div>'}</details></section><aside class="inspector"><div class="inspector-tabs" role="tablist" aria-label="稿件信息">${[['requirements','要求'],['reviews','点评'],['versions','版本'],['source','原文']].map(([key,label])=>`<button role="tab" aria-selected="${state.tab===key}" class="${state.tab===key?'active':''}" data-inspector="${key}">${label}</button>`).join('')}</div><div class="inspector-body">${inspector(t)}</div></aside></div>`);
  $$('[data-inspector]').forEach(el=>el.addEventListener('click',()=>{state.tab=el.dataset.inspector;detailPage();}));
  $$('[data-version]').forEach(el=>el.addEventListener('click',()=>showVersion(Number(el.dataset.version))));
  $$('[data-export]').forEach(el=>el.addEventListener('click',()=>download(el.dataset.export)));
  if(state.editing) $('#draft-editor').addEventListener('input',e=>{state.editText=e.target.value;$('#edit-count').textContent=`${countWords(state.editText)} 字 · 修改会生成新版本`;});
}
function inspector(t) {
  const r=t.requirements||{};
  if(state.tab==='source') return `<h3>征稿原文</h3>${t.source_url?`<p class="inline-note" style="overflow-wrap:anywhere;margin-bottom:16px">来源：${esc(t.source_url)}</p>`:''}<div class="source-text">${esc(t.source_text||'尚未提取到正文。链接无法读取时，请补充正文；截图识别需要可用的视觉模型。')}</div>${t.status==='needs_input'?'<button class="secondary-btn" style="margin-top:18px" data-action="retry">补充正文</button>':''}`;
  if(state.tab==='reviews') return (t.reviews||[]).length?t.reviews.map((review,i)=>`<div class="reviewer-label"><span class="reviewer-avatar">${i%2?'B':'A'}</span><h3>${esc(review.role||'独立评审')}</h3></div><p class="reviewer-summary">${esc(review.summary)}</p>${(review.issues||[]).map(issue=>`<div class="issue-card"><strong>${esc(issue.location||'整体')}<span class="severity">${esc(issue.severity||'建议')}</span></strong><p>${esc(issue.problem)}</p><p class="suggestion">${esc(issue.suggestion)}</p></div>`).join('')||'<p class="reviewer-summary">本轮未列出具体问题，请仍核对征稿要求与事实。</p>'}<hr class="inspector-divider">`).join(''):'<h3>交叉点评</h3><p class="reviewer-summary">写作完成后，两路评审会从要求符合度和文字表达两个角度提出意见。</p>';
  if(state.tab==='versions') return `<h3>每一次打磨，都有迹可循</h3>${(t.versions||[]).map((v,i)=>`<button class="version-card" data-version="${i}"><strong>${esc(v.title||`第 ${v.round??i} 版`)}</strong><small>${esc(prettyTime(v.created_at))} · ${countWords(v.content||v.draft)} 字 · 点击阅读</small></button>`).join('')||'<p class="reviewer-summary">生成或编辑后的稿件版本将保存在这里。</p>'}`;
  const aiMap={allowed:'允许 AI 辅助',forbidden:'不接受 AI 创作',unspecified:'原文未明确说明',unknown:'待核对'};
  return `<h3>征稿要求</h3>${[['刊物',r.publication],['主题',r.topic||r.title],['体裁',r.genre],['字数',r.min_words||r.max_words?`${r.min_words||'不限'} — ${r.max_words||'不限'} 字`:'原文未说明'],['截止',r.deadline],['投稿',r.submission],['AI 约定',aiMap[r.ai_policy]||r.ai_policy],['其他',text(r.notes)]].map(([label,value])=>`<div class="requirement-row"><span class="requirement-label">${label}</span><span class="requirement-value">${esc(value||'原文未说明')}</span></div>`).join('')}<hr class="inspector-divider"><h3>提交前核对</h3>${(t.checks||[]).map(check=>`<div class="check-item ${esc(['pass','warn','fail'].includes(check.status)?check.status:'warn')}">${icon(check.status==='pass'?'check':'info')}<div>${esc(check.label)}<small>${esc(check.detail)}</small></div></div>`).join('')||'<p class="reviewer-summary">提取要求并生成稿件后，系统会展示核对结果。</p>'}${r.source_excerpt?`<hr class="inspector-divider"><h3>要求的原文依据</h3><div class="source-text">${esc(text(r.source_excerpt))}</div>`:''}`;
}
function render() { if(state.page==='home')home(); else if(['tasks','review'].includes(state.page))listPage(); else if(state.page==='profile')profilePage(); else if(state.page==='settings')settingsPage(); else if(state.page==='task')detailPage(); }
function bindFilters() { $$('[data-filter]').forEach(el=>el.addEventListener('click',()=>{state.filter=el.dataset.filter;render();})); }
function bindCommon() {
  $$('[data-action]').forEach(el=>el.addEventListener('click',()=>handleAction(el.dataset.action)));
  $$('[data-stat]').forEach(el=>el.addEventListener('click',()=>{state.filter=el.dataset.stat;state.query='';if(state.page==='tasks')render();else location.hash='tasks';}));
}
async function route() {
  const hash=location.hash.slice(1)||'home'; if(state.editing&&!confirm('尚未保存的编辑会丢失，确定离开？')){history.replaceState(null,'',`#task/${encodeURIComponent(state.task.id)}`);return;}
  state.editing=false; state.query='';
  if(hash.startsWith('task/')) { const id=decodeURIComponent(hash.slice(5)); state.page='task';state.tab='requirements';state.task=state.tasks.find(t=>t.id===id)||null;render();try{state.task=await api(`/api/tasks/${encodeURIComponent(id)}`);render();}catch(e){toast(e.message,true);location.hash='tasks';} }
  else { state.page=navItems.some(i=>i[0]===hash)?hash:'home';if(state.page==='review')state.filter='review';else if(state.page!=='tasks')state.filter='all';render(); }
  window.scrollTo({top:0,behavior:'instant'});
}
async function refresh(showToast=false) { const data=await api('/api/bootstrap'); state.tasks=data.tasks||[];state.profile=data.profile||{};state.settings=data.settings||{};state.providers=data.providers||state.providers||[];if(state.page==='task'&&state.task)state.task=await api(`/api/tasks/${encodeURIComponent(state.task.id)}`); if(!state.editing)render();if(showToast)toast('工作台已更新'); }
async function handleAction(action) {
  if(action==='create')openCreate(); if(action==='example')openCreate(true);if(action==='settings')location.hash='settings';if(action==='back')location.hash='tasks';
  if(action==='refresh')try{await refresh(true);}catch(e){toast(e.message,true);}
  if(action==='edit'){state.editing=true;state.editText=state.task.draft||'';detailPage();$('#draft-editor').focus();}
  if(action==='cancel-edit'){state.editing=false;detailPage();}
  if(action==='save-edit')saveEdit();if(action==='refine')openRefine();if(action==='approve')openApproval();if(action==='retry')openRetry();if(action==='delete')openDelete();
}
const sampleContent='【虚构演示征稿】\n刊物：《慢生活》示例栏目\n主题：寻常日子里的微光\n体裁：生活散文，可以虚构，不要求作者真实经历。\n字数：600—1200字。\n要求：从一个具体生活场景展开，有细节、有变化，避免空泛说教；标题自拟。\nAI约定：本虚构示例允许AI辅助创作，作者须最终核对。\n截止日期：2099年12月31日。\n投稿方式：示例邮箱 editor@example.com，仅用于演示，不会实际发送。';
function openCreate(example=false) {
  state.create={title:'',source_type:'text',content:'',url:'',mode:'demo',max_rounds:'3',author_notes:'',fiction:true,files:[]}; if(example)Object.assign(state.create,{title:'寻常日子里的微光',content:sampleContent,author_notes:'用一个具体场景展开，语言克制、细节自然。此任务为虚构演示。'});
  state.modal='create';renderCreate();
}
function modalShell(title,subtitle,body,footer,small=false) {
  const root=$('#overlay-root'); if(!root.innerHTML)lastFocus=document.activeElement;
  root.innerHTML=`<div class="modal-backdrop"><section class="modal ${small?'small':''}" role="dialog" aria-modal="true" aria-labelledby="modal-title" tabindex="-1"><header class="modal-header"><div><span class="eyebrow">A NEW CHAPTER</span><h2 id="modal-title">${title}</h2><p>${subtitle}</p></div><button class="icon-btn" data-close aria-label="关闭弹窗">${icon('close')}</button></header>${body}${footer}</section></div>`;
  document.body.style.overflow='hidden';root.querySelectorAll('[data-close]').forEach(el=>el.addEventListener('click',closeModal));$('.modal-backdrop').addEventListener('click',e=>{if(e.target.classList.contains('modal-backdrop'))closeModal();});
  $('.modal').focus({preventScroll:true});
}
function closeModal() { if(state.busy)return; if(state.create)state.create.files.forEach(item=>URL.revokeObjectURL(item.preview));state.modal=null;state.create=null;$('#overlay-root').innerHTML='';document.body.style.overflow='';lastFocus?.focus?.({preventScroll:true}); }
function syncCreate() { const form=$('#create-form');if(!form||!state.create)return;for(const name of ['title','content','url','mode','max_rounds','author_notes']){const el=form.elements.namedItem(name);if(el)state.create[name]=el.value;}state.create.fiction=form.elements.namedItem('fiction')?.value==='true'; }
function renderCreate() {
  const c=state.create; const tabs=[['url','link','公众号链接'],['text','file','粘贴正文'],['images','image','上传截图']];
  const source=c.source_type==='text'?`<div class="modal-example"><span>每次导入一条征稿；合集请截取目标段落</span><button type="button" id="fill-example">填入演示示例</button></div><label class="form-field"><span class="hide">征稿正文</span><textarea name="content" rows="6" placeholder="在这里粘贴征稿正文…" required>${esc(c.content)}</textarea></label>`:c.source_type==='url'?`<label class="form-field"><span>公众号文章链接</span><input name="url" type="url" value="${esc(c.url)}" placeholder="https://mp.weixin.qq.com/s/…" required><small>读取受限时，可以在同一任务补充正文或截图。</small></label>`:`<label class="dropzone">${icon('upload')}<strong>选择征稿截图，或拖到这里</strong><small>支持 PNG、JPG、WebP · 每张不超过 5MB，最多 8 张</small><input id="upload-input" type="file" accept="image/png,image/jpeg,image/webp" multiple aria-label="上传征稿截图"></label><div class="upload-list">${c.files.map((item,i)=>`<div class="upload-item"><img src="${esc(item.preview)}" alt="第 ${i+1} 张截图预览"><span>${i+1}. ${esc(item.file.name)}</span><button type="button" class="icon-btn" data-move-up="${i}" ${i===0?'disabled':''} aria-label="截图上移">${icon('up')}</button><button type="button" class="icon-btn" data-move-down="${i}" ${i===c.files.length-1?'disabled':''} aria-label="截图下移">${icon('down')}</button><button type="button" class="icon-btn" data-remove="${i}" aria-label="删除截图">${icon('close')}</button></div>`).join('')}</div><p class="inline-note">按正文顺序排列。演示模式不会识别图片；真实 OCR 需要配置支持图片的视觉模型。</p>`;
  modalShell('把一条征稿，变成一篇文章。','导入一次，后面的写作与打磨交给工作流。',`<form id="create-form"><div class="modal-content"><div class="input-tabs" role="tablist" aria-label="导入方式">${tabs.map(([key,i,label])=>`<button type="button" role="tab" aria-selected="${c.source_type===key}" class="${c.source_type===key?'active':''}" data-source="${key}">${icon(i)}${label}</button>`).join('')}</div><div class="source-fields">${source}</div><div class="form-grid two-col"><label class="form-field full"><span>任务名称（可选）</span><input name="title" value="${esc(c.title)}" maxlength="100" placeholder="给这次写作起个名字"></label><label class="form-field"><span>运行方式</span><select name="mode"><option value="demo" ${c.mode==='demo'?'selected':''}>演示模式 · 无需密钥</option><option value="live" ${c.mode==='live'?'selected':''}>真实模型 · 消耗 API 额度</option></select></label><label class="form-field"><span>最多修改轮数</span><select name="max_rounds">${[1,2,3].map(n=>`<option value="${n}" ${String(c.max_rounds)===String(n)?'selected':''}>${n} 轮</option>`).join('')}</select></label><label class="form-field full"><span>给写作搭档的话（可选）</span><textarea name="author_notes" rows="2" placeholder="想要的角度、必须保留的素材，或不希望出现的表达…">${esc(c.author_notes)}</textarea></label><div class="form-field full"><span>内容设定</span><div class="radio-grid"><label class="choice-card"><input type="radio" name="fiction" value="true" ${c.fiction?'checked':''}><span>可创作虚构场景<small>仍以征稿要求为准</small></span></label><label class="choice-card"><input type="radio" name="fiction" value="false" ${!c.fiction?'checked':''}><span>须依据真实素材<small>素材不足时暂停补充</small></span></label></div></div></div><div id="create-error"></div></div><footer class="modal-footer"><small>演示使用预设内容。所有稿件都需要你最终审阅。</small><div class="modal-actions"><button class="secondary-btn" type="button" data-close>取消</button><button class="primary-btn" type="submit">${icon('spark')}开始写作</button></div></footer></form>`,'');
  $('#create-form').addEventListener('submit',submitCreate);
  $$('[data-source]').forEach(el=>el.addEventListener('click',()=>{syncCreate();c.source_type=el.dataset.source;renderCreate();}));
  $('#fill-example')?.addEventListener('click',()=>{syncCreate();c.content=sampleContent;c.title=c.title||'寻常日子里的微光';c.fiction=true;renderCreate();});
  $('#upload-input')?.addEventListener('change',e=>addFiles([...e.target.files]));
  $('.dropzone')?.addEventListener('dragover',e=>e.preventDefault());$('.dropzone')?.addEventListener('drop',e=>{e.preventDefault();addFiles([...e.dataTransfer.files]);});
  $$('[data-remove]').forEach(el=>el.addEventListener('click',()=>{syncCreate();const [item]=c.files.splice(Number(el.dataset.remove),1);URL.revokeObjectURL(item.preview);renderCreate();}));
  $$('[data-move-up],[data-move-down]').forEach(el=>el.addEventListener('click',()=>{syncCreate();const up=el.dataset.moveUp!==undefined;const i=Number(up?el.dataset.moveUp:el.dataset.moveDown),next=i+(up?-1:1);[c.files[i],c.files[next]]=[c.files[next],c.files[i]];renderCreate();}));
}
function addFiles(files) { syncCreate();const c=state.create;for(const file of files){if(c.files.length>=8){toast('一次最多上传 8 张截图',true);break;}if(!['image/png','image/jpeg','image/webp'].includes(file.type)){toast('请选择 PNG、JPG 或 WebP 图片',true);continue;}if(file.size>5*1024*1024){toast(`${file.name} 超过 5MB`,true);continue;}c.files.push({file,preview:URL.createObjectURL(file)});}renderCreate(); }
async function submitCreate(e) { e.preventDefault();if(state.busy)return;syncCreate();const c=state.create;if(c.source_type==='images'&&!c.files.length){$('#create-error').innerHTML='<div class="error-inline">请至少选择一张截图。</div>';return;}if(c.mode==='live'&&!state.settings.configured){$('#create-error').innerHTML='<div class="error-inline">请先在“模型设置”配置可用的 API，再创建真实任务。</div>';return;}
  const data=new FormData();for(const name of ['title','source_type','mode','max_rounds','author_notes'])data.append(name,c[name]);data.append('fiction',String(c.fiction));if(c.source_type==='text')data.append('content',c.content);if(c.source_type==='url')data.append('url',c.url);for(const item of c.files)data.append('images',item.file);
  const button=$('button[type="submit"]',$('#create-form'));button.disabled=true;button.innerHTML='<span class="spinner" style="width:14px;height:14px"></span>正在创建';state.busy=true;
  try{const task=await api('/api/tasks',{method:'POST',body:data});state.tasks.unshift(task);state.busy=false;closeModal();location.hash=`task/${encodeURIComponent(task.id)}`;toast('写作任务已创建，后台会自动推进');}catch(error){$('#create-error').innerHTML=`<div class="error-inline">${esc(error.message)}</div>`;button.disabled=false;button.innerHTML=`${icon('spark')}开始写作`;state.busy=false;}
}
function simpleModal(title,subtitle,content,buttonLabel,onSubmit,small=true) { modalShell(title,subtitle,`<form id="simple-form"><div class="modal-content">${content}<div id="modal-error"></div></div><footer class="modal-footer"><small>所有变更都会保留在当前任务中。</small><div class="modal-actions"><button class="secondary-btn" type="button" data-close>取消</button><button class="primary-btn" type="submit">${buttonLabel}</button></div></footer></form>`,'',small);$('#simple-form').addEventListener('submit',async e=>{e.preventDefault();if(state.busy)return;state.busy=true;const button=$('button[type="submit"]',e.currentTarget);button.disabled=true;try{await onSubmit(new FormData(e.currentTarget));state.busy=false;closeModal();}catch(error){$('#modal-error').innerHTML=`<div class="error-inline">${esc(error.message)}</div>`;state.busy=false;button.disabled=false;}}); }
function openRefine(){state.modal='refine';simpleModal('再打磨一下','把你的判断，变成下一轮明确的修改方向。','<label class="form-field"><span>这次想怎样修改？</span><textarea name="instruction" rows="5" required maxlength="3000" placeholder="例如：保留第二段的场景，删掉结尾的说教，让人物的变化通过动作体现。"></textarea><small>将基于当前稿件修改，并保留历史版本；真实模式会产生 API 用量。</small></label>','开始修改',async data=>{state.task=await api(`/api/tasks/${encodeURIComponent(state.task.id)}/refine`,{method:'POST',body:{instruction:data.get('instruction')}});await refresh();toast('修改任务已开始');});}
function openRetry(){state.modal='retry';simpleModal('补充材料，继续写作','保留任务，补齐缺失的原文或创作素材。',`<label class="form-field"><span>完整征稿正文（可选）</span><textarea name="content" rows="6" placeholder="链接读取受限或截图无法识别时，请粘贴征稿正文。">${esc(state.task.status==='needs_input'?'':state.task.source_text||'')}</textarea></label><label class="form-field" style="margin-top:16px"><span>内容设定</span><select name="fiction"><option value="true" ${state.task.fiction?'selected':''}>可创作虚构场景（仍以征稿要求为准）</option><option value="false" ${!state.task.fiction?'selected':''}>必须依据真实素材</option></select></label><label class="form-field" style="margin-top:16px"><span>补充真实素材或写作要求</span><textarea name="author_notes" rows="3">${esc(state.task.author_notes||'')}</textarea><small>正文发生变化时，会重新提取要求并生成稿件。留空则从现有材料重试。</small></label>`,'保存并继续',async data=>{const body={author_notes:data.get('author_notes'),fiction:data.get('fiction')==='true'};if(data.get('content').trim())body.content=data.get('content').trim();state.task=await api(`/api/tasks/${encodeURIComponent(state.task.id)}/retry`,{method:'POST',body});await refresh();toast('任务已重新加入处理队列');},false);}
function openApproval(){state.modal='approve';const demo=state.task.mode==='demo';simpleModal('最后的决定，交给你。',demo?'当前为演示内容；完成审阅不会产生真实投稿。':'请核对要求、事实及 AI 使用约定后确认。',`<div class="inline-note" style="margin-bottom:18px">确认后会将本任务标记为“已审阅”，你仍可下载文章或继续修改。系统不会发送邮件或发布稿件。</div><label class="choice-card"><input name="acknowledged" type="checkbox" required><span>${demo?'我已了解这是演示内容，并核对示例稿件。':'我已核对征稿要求、事实及 AI 使用约定。'}</span></label>`,'确认完成审阅',async()=>{state.task=await api(`/api/tasks/${encodeURIComponent(state.task.id)}/approve`,{method:'POST',body:{acknowledged:true}});await refresh();toast('已完成审阅，可导出稿件');});}
function openDelete(){state.modal='delete';simpleModal('删除这条写作任务？','关联的稿件版本和点评记录也会一并删除。','<p class="inline-note">删除后无法恢复。需要保留稿件时，请先导出。</p>','确认删除',async()=>{await api(`/api/tasks/${encodeURIComponent(state.task.id)}`,{method:'DELETE'});state.task=null;state.tasks=state.tasks.filter(t=>t.id!==location.hash.slice(6));location.hash='tasks';await refresh();toast('任务已删除');});}
function showVersion(index){const version=state.task.versions[index];state.modal='version';modalShell(esc(version.title||`第 ${version.round??index} 版`),'历史稿件只读，当前终稿不会被覆盖。',`<div class="modal-content"><article class="version-preview">${esc(version.content||version.draft||'暂无文本')}</article></div>`,`<footer class="modal-footer"><small>${countWords(version.content||version.draft)} 字</small><button class="secondary-btn" data-close>关闭</button></footer>`,false);}
async function saveEdit(){if(state.busy)return;state.busy=true;try{state.task=await api(`/api/tasks/${encodeURIComponent(state.task.id)}/edit`,{method:'POST',body:{draft:state.editText}});state.editing=false;await refresh();toast('修改已保存，历史版本仍然保留');}catch(e){toast(e.message,true);}finally{state.busy=false;}}
async function saveProfile(e){e.preventDefault();const button=$('button[type="submit"]',e.currentTarget);button.disabled=true;try{const data=Object.fromEntries(new FormData(e.currentTarget));state.profile=await api('/api/profile',{method:'PUT',body:data});await refresh();toast('你的写作素材已保存');}catch(error){$('#profile-error').innerHTML=`<div class="error-inline">${esc(error.message)}</div>`;button.disabled=false;}}
async function saveSettings(e){e.preventDefault();const button=$('button[type="submit"]',e.currentTarget);button.disabled=true;try{const data=Object.fromEntries(new FormData(e.currentTarget));data.daily_limit=Number(data.daily_limit);if(!Number.isInteger(data.daily_limit)||data.daily_limit<1000)throw new Error('每日 token 上限请填写至少 1000 的整数。');state.settings=await api('/api/settings',{method:'PUT',body:data});await refresh();toast('模型设置已保存；可在下方测试实际连接');}catch(error){$('#settings-error').innerHTML=`<div class="error-inline">${esc(error.message)}</div>`;button.disabled=false;}}
async function download(format){try{const response=await fetch(`/api/tasks/${encodeURIComponent(state.task.id)}/export?format=${encodeURIComponent(format)}`,{credentials:'same-origin'});if(!response.ok){let message='导出失败';try{message=text((await response.json()).detail)||message;}catch{}throw new Error(message);}const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`${state.task.title||'稿间文章'}${format==='email'?'-邮件草稿':''}.${format==='docx'?'docx':'txt'}`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);toast(format==='email'?'已导出邮件草稿，尚未发送':'稿件已导出');}catch(e){toast(e.message,true);}}
document.addEventListener('keydown',e=>{if(!state.modal)return;if(e.key==='Escape')closeModal();if(e.key==='Tab'){const items=$$('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href]',$('#overlay-root'));const first=items[0],last=items.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}});
window.addEventListener('hashchange',route);
window.addEventListener('beforeunload',e=>{if(state.editing){e.preventDefault();e.returnValue='';}});
async function poll(){if(pollBusy||document.hidden||state.modal)return;const running=state.tasks.some(t=>activeStatuses.includes(t.status));if(!running)return;pollBusy=true;try{const tasks=await api('/api/tasks');state.tasks=tasks;if(state.page==='task'&&state.task){const updated=tasks.find(t=>t.id===state.task.id);if(updated&&!state.editing){state.task=updated;detailPage();}}else if(['home','tasks','review'].includes(state.page)&&!$('#task-search')?.matches(':focus'))render();}catch{}finally{pollBusy=false;}}
async function start(){try{const data=await api('/api/bootstrap');state.tasks=data.tasks||[];state.profile=data.profile||{};state.settings=data.settings||{};state.providers=data.providers||state.providers||[];state.loading=false;await route();setInterval(poll,1700);}catch(e){$('#app').innerHTML=`<main class="initial-loading"><span class="brand-mark">稿</span><h1 style="font:25px var(--serif)">工作台暂时没有连接上</h1><p>${esc(e.message)}</p><button class="primary-btn" id="reload">重新连接</button></main>`;$('#reload').addEventListener('click',start);}}
start();
