/*
 * Security keys (WebAuthn) for MAYA's second factor. No library: the browser's own
 * navigator.credentials API, with base64url <-> ArrayBuffer conversion for the JSON
 * the server speaks. Buttons: [data-webauthn="register"] (with an optional
 * #key-name input) and [data-webauthn="authenticate"].
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';

  function toBuf(b64u) {
    var s = b64u.replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) { s += '='; }
    var bin = atob(s), out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) { out[i] = bin.charCodeAt(i); }
    return out.buffer;
  }

  function toB64u(buf) {
    var bytes = new Uint8Array(buf), bin = '';
    for (var i = 0; i < bytes.length; i++) { bin += String.fromCharCode(bytes[i]); }
    return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function post(url, body) {
    return fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.MayaCsrf || '' },
      body: JSON.stringify(body || {})
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) { throw new Error(data.error || ('HTTP ' + r.status)); }
        return data;
      });
    });
  }

  function say(el, text, bad) {
    var box = document.getElementById('webauthn-status');
    if (box) { box.textContent = text; box.className = 'small mt-2 ' + (bad ? 'text-danger' : 'small-muted'); }
    if (el) { el.disabled = false; }
  }

  function register(btn) {
    var nameInput = document.getElementById('key-name');
    post('/account/security-keys/options').then(function (res) {
      var o = res.options;
      o.challenge = toBuf(o.challenge);
      o.user.id = toBuf(o.user.id);
      (o.excludeCredentials || []).forEach(function (c) { c.id = toBuf(c.id); });
      say(btn, 'Touch your security key…');
      return navigator.credentials.create({ publicKey: o });
    }).then(function (cred) {
      var r = cred.response;
      return post('/account/security-keys', {
        name: (nameInput && nameInput.value) || 'security key',
        credential: {
          id: cred.id, rawId: toB64u(cred.rawId), type: cred.type,
          clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
          response: {
            clientDataJSON: toB64u(r.clientDataJSON), attestationObject: toB64u(r.attestationObject),
            transports: r.getTransports ? r.getTransports() : []
          }
        }
      });
    }).then(function (res) { window.location = res.next || '/account/mfa'; })
      .catch(function (err) { say(btn, 'Not registered: ' + err.message, true); });
  }

  function authenticate(btn) {
    post('/mfa/key/options').then(function (res) {
      var o = res.options;
      o.challenge = toBuf(o.challenge);
      (o.allowCredentials || []).forEach(function (c) { c.id = toBuf(c.id); });
      say(btn, 'Touch your security key…');
      return navigator.credentials.get({ publicKey: o });
    }).then(function (cred) {
      var r = cred.response;
      return post('/mfa/key', {
        credential: {
          id: cred.id, rawId: toB64u(cred.rawId), type: cred.type,
          clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
          response: {
            clientDataJSON: toB64u(r.clientDataJSON), authenticatorData: toB64u(r.authenticatorData),
            signature: toB64u(r.signature), userHandle: r.userHandle ? toB64u(r.userHandle) : null
          }
        }
      });
    }).then(function (res) { window.location = res.next || '/'; })
      .catch(function (err) {
        say(btn, err.message, true);
        if (/log in again/i.test(err.message)) { setTimeout(function () { window.location = '/login'; }, 2500); }
      });
  }

  document.querySelectorAll('[data-webauthn]').forEach(function (btn) {
    if (!window.PublicKeyCredential) {
      btn.disabled = true;
      say(null, 'This browser does not support security keys.', true);
      return;
    }
    btn.addEventListener('click', function () {
      btn.disabled = true;
      (btn.getAttribute('data-webauthn') === 'register' ? register : authenticate)(btn);
    });
  });
})();
