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

  // ── Profile modal styles ──────────────────────────────────────────────────────
  const MODAL_CSS = `
    #profile-overlay {
      display:none; position:fixed; inset:0; background:rgba(0,0,0,.6);
      z-index:9999; align-items:center; justify-content:center;
    }
    #profile-overlay.open { display:flex; }
    #profile-modal {
      background:var(--surface); border:1px solid var(--border); border-radius:4px;
      padding:28px 28px 24px; width:100%; max-width:400px; position:relative;
    }
    #profile-modal h3 {
      font-family:var(--mono); font-size:12px; letter-spacing:.07em; text-transform:uppercase;
      color:var(--text-dim); margin-bottom:20px;
    }
    .pm-row { margin-bottom:14px; }
    .pm-row label {
      display:block; font-family:var(--mono); font-size:10px; letter-spacing:.06em;
      text-transform:uppercase; color:var(--text-dim); margin-bottom:5px;
    }
    .pm-row input {
      width:100%; padding:8px 10px; background:var(--surface2); border:1px solid var(--border2);
      border-radius:3px; color:var(--text); font-family:var(--mono); font-size:12px; outline:none;
      transition:border-color .15s; box-sizing:border-box;
    }
    .pm-row input:focus { border-color:var(--accent); }
    .pm-pw-wrap { position:relative; }
    .pm-pw-wrap input { padding-right:36px; }
    .pm-pw-toggle {
      position:absolute; right:9px; top:50%; transform:translateY(-50%);
      background:none; border:none; cursor:pointer; padding:0;
      color:var(--text-muted); line-height:1;
    }
    .pm-pw-toggle:hover { color:var(--text-dim); }
    .pm-divider {
      font-family:var(--mono); font-size:9px; text-transform:uppercase; letter-spacing:.07em;
      color:var(--text-muted); margin:18px 0 14px; display:flex; align-items:center; gap:8px;
    }
    .pm-divider::before,.pm-divider::after { content:''; flex:1; height:1px; background:var(--border); }
    .pm-footer { display:flex; gap:10px; align-items:center; margin-top:20px; }
    .pm-btn-save {
      padding:9px 20px; background:var(--accent); color:#fff; border:none; border-radius:3px;
      font-family:var(--mono); font-size:11px; letter-spacing:.05em; text-transform:uppercase;
      cursor:pointer; transition:opacity .15s;
    }
    .pm-btn-save:hover { opacity:.88; }
    .pm-btn-save:disabled { opacity:.5; cursor:default; }
    .pm-btn-cancel {
      padding:9px 14px; background:transparent; border:1px solid var(--border2);
      color:var(--text-dim); border-radius:3px; font-family:var(--mono); font-size:11px;
      cursor:pointer;
    }
    .pm-msg {
      font-family:var(--mono); font-size:11px; padding:7px 10px; border-radius:3px;
      display:none; margin-left:auto;
    }
    .pm-msg.ok  { background:color-mix(in srgb,var(--green) 12%,transparent); color:var(--green); }
    .pm-msg.err { background:color-mix(in srgb,var(--red)   12%,transparent); color:var(--red); }
    #user-nav-btn {
      background:transparent; border:none; cursor:pointer; padding:0;
      font-family:var(--mono); font-size:11px; color:var(--text-dim);
      text-decoration:underline; text-decoration-style:dotted;
      text-underline-offset:3px; transition:color .15s;
    }
    #user-nav-btn:hover { color:var(--accent); }
  `;

  function injectStyles() {
    const el = document.createElement('style');
    el.textContent = MODAL_CSS;
    document.head.appendChild(el);
  }

  function injectModal() {
    const div = document.createElement('div');
    div.id = 'profile-overlay';
    div.innerHTML = `
      <div id="profile-modal">
        <h3>My Profile</h3>
        <div class="pm-row">
          <label>Display Name</label>
          <input type="text" id="pm-display" autocomplete="name">
        </div>
        <div class="pm-row">
          <label>Username</label>
          <input type="text" id="pm-username" autocomplete="username">
        </div>
        <div class="pm-row">
          <label>Email</label>
          <input type="email" id="pm-email" autocomplete="email">
        </div>
        <div class="pm-divider">Change password</div>
        <div class="pm-row">
          <label>New Password <span style="color:var(--text-muted)">(leave blank to keep)</span></label>
          <div class="pm-pw-wrap">
            <input type="password" id="pm-pw1" autocomplete="new-password" placeholder="min 8 characters">
            <button type="button" class="pm-pw-toggle" onclick="window.__pmTogglePw('pm-pw1',this)" tabindex="-1">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            </button>
          </div>
        </div>
        <div class="pm-row">
          <label>Confirm Password</label>
          <div class="pm-pw-wrap">
            <input type="password" id="pm-pw2" autocomplete="new-password" placeholder="repeat new password">
            <button type="button" class="pm-pw-toggle" onclick="window.__pmTogglePw('pm-pw2',this)" tabindex="-1">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            </button>
          </div>
        </div>
        <div class="pm-footer">
          <button class="pm-btn-save" id="pm-save" onclick="window.__pmSave()">Save Changes</button>
          <button class="pm-btn-cancel" onclick="window.__pmClose()">Cancel</button>
          <span class="pm-msg" id="pm-msg"></span>
        </div>
      </div>`;
    document.body.appendChild(div);
    div.addEventListener('click', e => { if (e.target === div) window.__pmClose(); });
  }

  window.__pmTogglePw = function(id, btn) {
    const inp = document.getElementById(id);
    const showing = inp.type === 'text';
    inp.type = showing ? 'password' : 'text';
    btn.style.color = showing ? '' : 'var(--accent)';
  };

  window.__pmOpen = function(user) {
    document.getElementById('pm-display').value  = user.display_name || '';
    document.getElementById('pm-username').value = user.username || '';
    document.getElementById('pm-email').value    = user.email || '';
    document.getElementById('pm-pw1').value      = '';
    document.getElementById('pm-pw2').value      = '';
    const msg = document.getElementById('pm-msg');
    msg.style.display = 'none';
    document.getElementById('pm-save').disabled = false;
    document.getElementById('profile-overlay').classList.add('open');
    document.getElementById('pm-display').focus();
  };

  window.__pmClose = function() {
    document.getElementById('profile-overlay').classList.remove('open');
  };

  window.__pmSave = async function() {
    const pw1 = document.getElementById('pm-pw1').value;
    const pw2 = document.getElementById('pm-pw2').value;
    const msg = document.getElementById('pm-msg');
    const btn = document.getElementById('pm-save');
    msg.style.display = 'none';

    if (pw1 && pw1 !== pw2) {
      msg.className = 'pm-msg err'; msg.textContent = 'Passwords do not match.'; msg.style.display = ''; return;
    }

    const body = {
      display_name: document.getElementById('pm-display').value.trim(),
      username:     document.getElementById('pm-username').value.trim(),
      email:        document.getElementById('pm-email').value.trim(),
    };
    if (pw1) body.password = pw1;

    btn.disabled = true;
    try {
      const res  = await _fetch('/auth/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        msg.className = 'pm-msg ok'; msg.textContent = 'Saved!'; msg.style.display = '';
        // Update the displayed name
        const nameEl = document.getElementById('user-nav-btn');
        if (nameEl) nameEl.textContent = data.display_name || data.username;
        // Store updated user for re-open
        window.__authUser = data;
        setTimeout(() => window.__pmClose(), 1200);
      } else {
        msg.className = 'pm-msg err'; msg.textContent = data.detail || 'Save failed.'; msg.style.display = '';
        btn.disabled = false;
      }
    } catch(e) {
      msg.className = 'pm-msg err'; msg.textContent = 'Network error.'; msg.style.display = '';
      btn.disabled = false;
    }
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

    window.__authUser = user;

    const nav = document.getElementById('user-nav');
    if (nav) {
      nav.style.marginLeft = 'auto';   // push user-nav + theme-toggle (its next sibling) to far right
      nav.style.display    = 'flex';
      nav.style.alignItems = 'center';
      nav.style.gap        = '8px';
      nav.style.flexShrink = '0';

      nav.innerHTML =
        '<button id="user-nav-btn" onclick="window.__pmOpen(window.__authUser)" title="Edit profile">' +
        escHtml(user.display_name || user.username) + '</button>' +
        '<button onclick="window.__authLogout()" style="padding:4px 10px;font-family:var(--mono);' +
        'font-size:10px;letter-spacing:.05em;background:transparent;border:1px solid var(--border2);' +
        'color:var(--text-dim);cursor:pointer;border-radius:2px;white-space:nowrap;transition:border-color .15s,color .15s;" ' +
        'onmouseenter="this.style.borderColor=\'var(--red)\';this.style.color=\'var(--red)\'" ' +
        'onmouseleave="this.style.borderColor=\'\';this.style.color=\'\'">LOGOUT</button>';
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

  document.addEventListener('DOMContentLoaded', function() {
    injectStyles();
    injectModal();
    initAuth();
  });
})();
