(function () {
  'use strict';

  const LOGIN = '/login';

  // Wrap fetch to redirect on 401
  const _fetch = window.fetch.bind(window);
  window.fetch = async function (...args) {
    const res = await _fetch(...args);
    if (res.status === 401 && !window.location.pathname.startsWith(LOGIN)) {
      window.location.href = LOGIN + '?next=' + encodeURIComponent(window.location.pathname);
    }
    return res;
  };

  async function initAuth() {
    if (window.location.pathname.startsWith(LOGIN)) return;

    let user;
    try {
      const res = await _fetch('/auth/me');
      if (res.status === 401) {
        window.location.href = LOGIN + '?next=' + encodeURIComponent(window.location.pathname);
        return;
      }
      user = await res.json();
    } catch (e) {
      console.error('Auth init failed:', e);
      return;
    }

    const nav = document.getElementById('user-nav');
    if (nav) {
      nav.innerHTML =
        '<span style="color:var(--text-dim);font-size:11px;font-family:var(--mono);">' +
        escHtml(user.display_name || user.username) + '</span>' +
        '<button onclick="window.__authLogout()" style="padding:4px 10px;font-family:var(--mono);' +
        'font-size:10px;letter-spacing:.05em;background:transparent;border:1px solid var(--border2);' +
        'color:var(--text-dim);cursor:pointer;border-radius:2px;margin-left:8px;">LOGOUT</button>';
    }

    if (user.is_admin) {
      const navEl = document.querySelector('nav');
      if (navEl && !document.getElementById('nav-admin-link')) {
        const a = document.createElement('a');
        a.id = 'nav-admin-link';
        a.href = '/admin';
        a.textContent = 'Admin';
        a.style.cssText =
          'padding:6px 14px;font-family:var(--mono);font-size:11px;letter-spacing:.06em;' +
          'text-transform:uppercase;text-decoration:none;color:var(--purple);border-radius:2px;';
        navEl.appendChild(a);
      }
    }
  }

  function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  window.__authLogout = async function () {
    await _fetch('/auth/logout', { method: 'POST' });
    window.location.href = LOGIN;
  };

  document.addEventListener('DOMContentLoaded', initAuth);
})();
