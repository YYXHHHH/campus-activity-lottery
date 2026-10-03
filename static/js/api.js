/* api.js — 统一 fetch 封装：注入 token、解析 {code,message,data}、401 清 token 跳登录、抛出中文错误 */
(function (global) {
  'use strict';

  var TOKEN_KEY = 'token';
  var USER_KEY = 'user';

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || '';
  }

  function getUser() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || 'null');
    } catch (e) {
      return null;
    }
  }

  function setSession(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function setUser(user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function isAuthPage() {
    return /\/(login|register)\.html$/i.test(global.location.pathname);
  }

  function redirectToLogin() {
    if (!isAuthPage()) {
      global.location.replace('login.html');
    }
  }

  function ApiError(message, code, data) {
    var err = new Error(message || '请求失败');
    err.code = code;
    err.data = data;
    return err;
  }

  function handleEnvelope(json) {
    if (json && json.code === 0) {
      return json.data;
    }
    if (json && json.code === 40101) {
      clearSession();
      redirectToLogin();
    }
    throw ApiError(json ? json.message : '服务器响应异常', json ? json.code : -1, json ? json.data : null);
  }

  /**
   * request(path, options) -> Promise<data>
   * options: { method, body(对象自动 JSON.stringify), blob:true 返回 Blob, raw:true 返回整个信封 }
   */
  function request(path, options) {
    options = options || {};
    var headers = {};
    var token = getToken();
    if (token) {
      headers['Authorization'] = 'Bearer ' + token;
    }
    var body;
    if (options.body !== undefined && options.body !== null) {
      if (typeof options.body === 'string') {
        body = options.body;
      } else {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify(options.body);
      }
    }

    return fetch('/api' + path, {
      method: options.method || 'GET',
      headers: headers,
      body: body
    }).then(function (resp) {
      var ct = (resp.headers.get('Content-Type') || '').toLowerCase();

      if (options.blob) {
        // 二进制接口（二维码 / 导出）：出错时后端仍返回 JSON 信封
        if (ct.indexOf('application/json') !== -1) {
          return resp.json().then(function (json) {
            handleEnvelope(json); // 必抛（code!=0）
          });
        }
        if (!resp.ok) {
          return resp.text().then(function (t) {
            throw ApiError(t || ('请求失败（HTTP ' + resp.status + '）'), -1, null);
          });
        }
        return resp.blob().then(function (blob) {
          // 服务端用 filename*=UTF-8'' 给出中文文件名（§5.8 / R6）
          blob.name = filenameFromDisposition(resp.headers.get('Content-Disposition'));
          return blob;
        });
      }

      return resp.json().catch(function () {
        throw ApiError('服务器返回了非法响应（HTTP ' + resp.status + '）', -1, null);
      }).then(function (json) {
        if (options.raw) {
          if (json && json.code === 40101) {
            clearSession();
            redirectToLogin();
          }
          return json;
        }
        return handleEnvelope(json);
      });
    });
  }

  function get(path) { return request(path, {}); }

  function post(path, body) { return request(path, { method: 'POST', body: body || {} }); }

  function patch(path, body) { return request(path, { method: 'PATCH', body: body || {} }); }

  function del(path) { return request(path, { method: 'DELETE' }); }

  function getBlob(path) { return request(path, { blob: true }); }

  /** 取导出文件名：优先 RFC 5987 形式，中文活动名才不乱码（§5.8、R6） */
  function filenameFromDisposition(header) {
    if (!header) return '';
    var utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header);
    if (utf8) {
      try {
        return decodeURIComponent(utf8[1]);
      } catch (e) {
        /* 百分号编码异常时退回普通 filename */
      }
    }
    var plain = /filename="?([^";]+)"?/i.exec(header);
    return plain ? plain[1] : '';
  }

  /** 下载二进制内容（带 token），filename 为默认文件名 */
  function download(path, filename) {
    return getBlob(path).then(function (blob) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = blob.name || filename || 'download';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
    });
  }

  /** 登录：成功后写入 session */
  function login(username, password) {
    return request('/auth/login', { method: 'POST', body: { username: username, password: password } })
      .then(function (data) {
        setSession(data.access_token, data.user);
        return data;
      });
  }

  /** 登录态检查：有 token 时向后端验证并刷新本地 user，返回 Promise<user|null> */
  function ensureLoggedIn() {
    if (!getToken()) {
      redirectToLogin();
      return Promise.resolve(null);
    }
    return get('/auth/me').then(function (user) {
      setUser(user);
      return user;
    }).catch(function () {
      clearSession();
      redirectToLogin();
      return null;
    });
  }

  function logout() {
    clearSession();
    global.location.href = 'login.html';
  }

  global.Api = {
    getToken: getToken,
    getUser: getUser,
    setSession: setSession,
    setUser: setUser,
    clearSession: clearSession,
    redirectToLogin: redirectToLogin,
    request: request,
    get: get,
    post: post,
    patch: patch,
    del: del,
    getBlob: getBlob,
    download: download,
    login: login,
    logout: logout,
    ensureLoggedIn: ensureLoggedIn
  };
})(window);