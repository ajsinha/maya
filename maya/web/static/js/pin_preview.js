/*
 * pin_preview.js — §16.4, nothing destructive without a preview.
 *
 * The pin form's submit button starts disabled. Preview asks the server what the pin
 * would produce — rows, the fill report, the quality verdict, the storage it would take
 * — and only a preview that comes back with no blockers turns the button on. Changing
 * any field turns it off again, so the button can never be armed for one pin and
 * pressed for another.
 *
 * The CSP is `script-src 'self'`: the form declares itself with data-pin-preview.
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';

  function bytes(n) {
    if (!n) return '0 B';
    var units = ['B', 'KB', 'MB', 'GB', 'TB'];
    var i = Math.floor(Math.log(n) / Math.log(1024));
    i = Math.min(i, units.length - 1);
    return (n / Math.pow(1024, i)).toFixed(i ? 1 : 0) + ' ' + units[i];
  }

  function fills(report) {
    var parts = [];
    Object.keys(report || {}).forEach(function (attr) {
      var r = report[attr];
      if (r && typeof r === 'object') {
        parts.push(attr + ': ' + (r.rule || '—') + (r.filled !== undefined ? ' filled ' + r.filled : ''));
      } else {
        parts.push(attr + ': ' + r);
      }
    });
    return parts;
  }

  function render(panel, data) {
    var el = document.createElement('div');
    el.className = 'card card-body';
    var head = document.createElement('div');
    head.innerHTML = '<strong>' + data.rows + '</strong> row(s) over ' +
      data.columns.length + ' column(s) · about <strong>' + bytes(data.storage.estimated_bytes) +
      '</strong> stored (' + data.storage.bytes_per_row + ' B/row, measured on ' +
      data.storage.sampled_rows + ' sampled rows)';
    el.appendChild(head);
    var q = document.createElement('div');
    q.className = 'small-muted';
    q.textContent = data.storage.namespace + ' already holds ' + bytes(data.storage.held_bytes) +
      (data.storage.quota_bytes
        ? ' of a ' + bytes(data.storage.quota_bytes) + ' quota'
        : ' and has no quota set');
    el.appendChild(q);
    var lines = fills(data.fill_report);
    if (lines.length) {
      var f = document.createElement('div');
      f.className = 'small';
      f.textContent = 'Fill report — ' + lines.join('; ');
      el.appendChild(f);
    }
    (data.checks || []).forEach(function (c) {
      var line = document.createElement('div');
      line.className = 'small' + (c.passed ? '' : ' fw-semibold');
      line.textContent = (c.passed ? '✓ ' : '✗ ') + c.check + ': ' + c.detail;
      el.appendChild(line);
    });
    if (data.blockers.length) {
      var ul = document.createElement('ul');
      ul.className = 'mb-0 small';
      data.blockers.forEach(function (b) {
        var li = document.createElement('li');
        li.textContent = b;
        ul.appendChild(li);
      });
      var why = document.createElement('div');
      why.className = 'mt-1';
      why.textContent = 'This pin would be refused:';
      el.appendChild(why);
      el.appendChild(ul);
    }
    panel.replaceChildren(el);
  }

  document.querySelectorAll('form[data-pin-preview]').forEach(function (form) {
    var url = form.getAttribute('data-pin-preview');
    var check = form.querySelector('[data-pin-check]');
    var submit = form.querySelector('[data-pin-submit]');
    var panel = form.querySelector('[data-pin-report]');
    if (!check || !submit || !panel) return;

    function disarm() {
      submit.disabled = true;
      submit.title = 'Preview the pin first: §16.4 asks for the row count, the fill report and the ' +
        'storage estimate before the button becomes active.';
    }
    disarm();
    form.querySelectorAll('input, select').forEach(function (field) {
      field.addEventListener('change', disarm);
      field.addEventListener('input', disarm);
    });

    check.addEventListener('click', function () {
      var version = form.querySelector('[name=version_no]');
      var asOf = form.querySelector('[name=as_of]');
      if (!asOf || !asOf.value) {
        panel.textContent = 'Choose an as-of date first.';
        return;
      }
      check.disabled = true;
      panel.textContent = 'Resolving…';
      fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.MayaCsrf || '' },
        body: JSON.stringify({
          version_no: version ? version.value : 1,
          as_of: asOf.value,
          as_of_known: (form.querySelector('[name=as_of_known]') || {}).value || null,
          pin_name: (form.querySelector('[name=pin_name]') || {}).value || ''
        })
      }).then(function (r) { return r.json(); }).then(function (data) {
        check.disabled = false;
        if (data.error) {
          panel.textContent = data.error;
          disarm();
          return;
        }
        render(panel, data);
        submit.disabled = !data.may_pin;
        submit.title = data.may_pin ? 'Pin ' + data.rows + ' row(s)' : data.blockers.join('; ');
      }).catch(function (err) {
        check.disabled = false;
        panel.textContent = 'Could not preview the pin: ' + err;
        disarm();
      });
    });
  });
}());
