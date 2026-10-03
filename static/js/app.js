/* app.js — 公共工具：品牌初始化、导航栏渲染、登录态检查、状态徽章、时间格式化、Toast、分页等 */
(function (global) {
  'use strict';

  /* 品牌与术语：由 api/brand.js（服务端按 .env 生成）注入，未注入时退化为中文默认值 */
  var BRAND = global.__BRAND__ || {};
  var LABELS = BRAND.labels || {};
  var ROLE_CN = BRAND.role_labels || { STUDENT: '学生', ORGANIZER: '组织者', ADMIN: '管理员' };
  var ACTIVITY_STATUS = {
    DRAFT: { cn: '草稿', cls: 'badge-gray' },
    PUBLISHED: { cn: '报名中', cls: 'badge-blue' },
    LOTTERY_DONE: { cn: '已抽签', cls: 'badge-green' },
    CANCELLED: { cn: '已取消', cls: 'badge-red' }
  };
  var REG_STATUS = {
    PENDING: { cn: '待抽签', cls: 'badge-blue' },
    WON: { cn: '已中签', cls: 'badge-green' },
    WAITING: { cn: '候补中', cls: 'badge-orange' },
    LOST: { cn: '未中签', cls: 'badge-gray' },
    CANCELLED: { cn: '已取消', cls: 'badge-red' },
    WITHDRAWN: { cn: '已退出', cls: 'badge-red' }
  };

  /* 用服务端下发的文案覆盖状态徽章文本（键与枚举值一致） */
  Object.keys(ACTIVITY_STATUS).forEach(function (key) {
    if (BRAND.status_labels && BRAND.status_labels[key]) ACTIVITY_STATUS[key].cn = BRAND.status_labels[key];
  });
  Object.keys(REG_STATUS).forEach(function (key) {
    if (BRAND.registration_status_labels && BRAND.registration_status_labels[key]) {
      REG_STATUS[key].cn = BRAND.registration_status_labels[key];
    }
  });

  /** 取界面文案：LABELS['activity.unit']，缺省回退到 fallback */
  function label(key, fallback) {
    return LABELS[key] || fallback || key;
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /** ISO 时间 -> 本地时间字符串；空值返回占位符 */
  function fmtTime(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    return d.toLocaleString(BRAND.locale || 'zh-CN');
  }

  /**
   * datetime-local 输入值（本地时间）-> UTC ISO 字符串（Z 结尾），供提交后端。
   * 空值返回 null。
   */
  function toUtcIso(localValue) {
    if (!localValue) return null;
    var d = new Date(localValue);
    if (isNaN(d.getTime())) return null;
    return d.toISOString();
  }

  function statusBadge(status) {
    var info = REG_STATUS[status] || ACTIVITY_STATUS[status];
    if (!info) {
      return '<span class="badge badge-gray">' + escapeHtml(status || '未知') + '</span>';
    }
    return '<span class="badge ' + info.cls + '">' + info.cn + '</span>';
  }

  function qs(name) {
    return new URLSearchParams(global.location.search).get(name);
  }

  /* ---------- Toast ---------- */
  function toast(message, type, durationMs) {
    var root = document.getElementById('toast-root');
    if (!root) {
      root = document.createElement('div');
      root.id = 'toast-root';
      document.body.appendChild(root);
    }
    var el = document.createElement('div');
    el.className = 'toast ' + (type || 'info');
    el.textContent = message;
    root.appendChild(el);
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, durationMs || 3200);
  }

  /* ---------- 导航栏 ---------- */
  var NAV_ITEMS = [
    { href: 'index.html', text: '活动列表', labelKey: 'activity.list', roles: ['STUDENT', 'ORGANIZER', 'ADMIN'] },
    { href: 'my_registrations.html', text: '我的报名', labelKey: 'activity.mine_registrations', roles: ['STUDENT'] },
    { href: 'organizer.html', text: '我的活动', labelKey: 'activity.mine_managed', roles: ['ORGANIZER', 'ADMIN'] },
    { href: 'activity_manage.html', text: '活动管理', labelKey: 'activity.manage', roles: ['ORGANIZER', 'ADMIN'] },
    { href: 'admin.html', text: '用户管理', labelKey: 'user.list', roles: ['ADMIN'] }
  ];

  function renderNav(activeHref, user) {
    var navbar = document.getElementById('navbar');
    if (!navbar) return;
    var links = NAV_ITEMS.filter(function (item) {
      return user && item.roles.indexOf(user.role) !== -1;
    }).map(function (item) {
      var cls = item.href === activeHref ? ' class="active"' : '';
      return '<a href="' + item.href + '"' + cls + '>' + escapeHtml(label(item.labelKey, item.text)) + '</a>';
    }).join('');
    var who = user
      ? escapeHtml(user.real_name || user.username) + '（' + (ROLE_CN[user.role] || user.role) + '）'
      : '';
    var brandName = BRAND.short_name || BRAND.name || '活动系统';
    navbar.className = 'navbar';
    navbar.innerHTML =
      '<a class="brand" href="index.html">' + escapeHtml(brandName) + '</a>' +
      '<div class="nav-links">' + links + '</div>' +
      '<div class="nav-user"><span class="who">' + who + '</span>' +
      '<button class="btn" id="nav-logout" type="button">退出</button></div>';
    var logoutBtn = document.getElementById('nav-logout');
    if (logoutBtn) logoutBtn.addEventListener('click', Api.logout);
  }

  /* ---------- 角色下拉框 ---------- */
  /** 给带 data-role-options="STUDENT,ORGANIZER" 的 <select> 填充角色选项（文案由后端下发） */
  function fillRoleOptions(root) {
    var scope = root || document;
    var selects = scope.querySelectorAll('select[data-role-options]');
    Array.prototype.forEach.call(selects, function (select) {
      var values = (select.getAttribute('data-role-options') || '').split(',');
      values.forEach(function (raw) {
        var value = raw.trim();
        if (!value) return;
        var option = document.createElement('option');
        option.value = value;
        option.textContent = ROLE_CN[value] || value;
        select.appendChild(option);
      });
    });
  }

  /**
   * 页面初始化守卫：渲染导航、校验登录（401 自动跳登录页）、校验角色。
   * opts: { page: 'index.html', roles: ['STUDENT','ORGANIZER'] }
   * 返回 Promise<user|null>；角色不符时提示并跳回首页。
   */
  function initPage(opts) {
    opts = opts || {};
    fillRoleOptions();
    if (!Api.getToken()) {
      Api.redirectToLogin();
      return Promise.resolve(null);
    }
    return Api.ensureLoggedIn().then(function (user) {
      if (!user) return null;
      if (opts.roles && opts.roles.indexOf(user.role) === -1) {
        toast('无权限访问该页面', 'error');
        global.location.replace('index.html');
        return null;
      }
      renderNav(opts.page, user);
      return user;
    });
  }

  /* ---------- 分页渲染 ---------- */
  function renderPagination(container, pageData, onPage) {
    if (!container) return;
    if (!pageData || !pageData.items) { container.innerHTML = ''; return; }
    var d = pageData;
    var html =
      '<div class="pager">' +
      '<button class="btn" type="button" data-pager="prev"' + (d.page <= 1 ? ' disabled' : '') + '>上一页</button>' +
      '<button class="btn" type="button" data-pager="next"' + (d.page >= d.pages ? ' disabled' : '') + '>下一页</button>' +
      '<span class="info">第 ' + d.page + ' / ' + (d.pages || 1) + ' 页，共 ' + d.total + ' 条</span>' +
      '</div>';
    container.innerHTML = html;
    var prev = container.querySelector('[data-pager="prev"]');
    var next = container.querySelector('[data-pager="next"]');
    if (prev) prev.addEventListener('click', function () { onPage(d.page - 1); });
    if (next) next.addEventListener('click', function () { onPage(d.page + 1); });
  }

  /** 比率 0~1 -> 百分比文本 */
  function pct(ratio) {
    if (ratio === null || ratio === undefined) return '—';
    return (ratio * 100).toFixed(1) + '%';
  }

  /** URL 追加查询参数（仅用于 GET 列表接口） */
  function buildQuery(params) {
    var parts = [];
    Object.keys(params).forEach(function (key) {
      var value = params[key];
      if (value === null || value === undefined || value === '') return;
      parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(value));
    });
    return parts.length ? '?' + parts.join('&') : '';
  }

  global.App = {
    BRAND: BRAND,
    LABELS: LABELS,
    label: label,
    ROLE_CN: ROLE_CN,
    escapeHtml: escapeHtml,
    fmtTime: fmtTime,
    toUtcIso: toUtcIso,
    statusBadge: statusBadge,
    qs: qs,
    toast: toast,
    renderNav: renderNav,
    fillRoleOptions: fillRoleOptions,
    initPage: initPage,
    renderPagination: renderPagination,
    pct: pct,
    buildQuery: buildQuery
  };

  /* 角色下拉框在脚本加载后立即填充（auth 页面不走 initPage） */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { fillRoleOptions(); });
  } else {
    fillRoleOptions();
  }
})(window);
