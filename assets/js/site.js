// 금속노조 오스템임플란트지회 — 작은 편의 기능만 담습니다.
(function () {
  // 1) 최근 글에 NEW 표시 (기본 14일)
  var NEW_DAYS = 14;
  var now = Date.now();
  document.querySelectorAll('.news-row').forEach(function (row) {
    var d = Date.parse(row.getAttribute('data-date'));
    if (!isNaN(d) && (now - d) / 86400000 <= NEW_DAYS) {
      var badge = row.querySelector('.new');
      if (badge) badge.hidden = false;
    }
  });

  // 2) 노조소식 분류 필터
  var chips = document.querySelectorAll('.filters .chip');
  if (chips.length) {
    var rows = document.querySelectorAll('.news-list-full .news-row');
    var empty = document.querySelector('.news-list-full + .empty');
    var apply = function (filter) {
      var shown = 0;
      chips.forEach(function (c) { c.setAttribute('aria-pressed', String(c.dataset.filter === filter)); });
      rows.forEach(function (r) {
        var ok = filter === 'all' || r.dataset.category === filter;
        r.hidden = !ok;
        if (ok) shown++;
      });
      if (empty) empty.hidden = shown > 0;
    };
    chips.forEach(function (c) {
      c.addEventListener('click', function () { apply(c.dataset.filter); });
    });
  }

  // 3) 자주 묻는 질문 검색
  var input = document.getElementById('faq-search');
  if (input) {
    var items = document.querySelectorAll('.faq-page .faq');
    var groups = document.querySelectorAll('.faq-group');
    var none = document.getElementById('faq-empty');
    input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase();
      var total = 0;
      items.forEach(function (it) {
        var hit = !q || it.textContent.toLowerCase().indexOf(q) !== -1;
        it.hidden = !hit;
        it.open = !!q && hit;
        if (hit) total++;
      });
      groups.forEach(function (g) {
        g.hidden = !g.querySelector('.faq:not([hidden])');
      });
      none.hidden = total > 0;
    });
  }

  // 4) 조합비 계산기 (FAQ '조합비는 얼마인가요?')
  var dues = document.getElementById('dues-calculator');
  if (dues) {
    var form = dues.querySelector('.dues-form');
    var won = function (n) { return n.toLocaleString('ko-KR') + '원'; };
    var num = function (input) { return parseInt(input.value.replace(/[^0-9]/g, ''), 10) || 0; };
    var calc = function () {
      var f = form.elements;
      var wage = num(f.base) + num(f.allow) + Math.floor(num(f.bonus) / 12);
      var fee = Math.floor(wage / 100 / 10) * 10; // 1%, 1원 단위 버림
      document.getElementById('dues-wage').textContent = won(wage);
      document.getElementById('dues-fee').textContent = won(fee);
    };
    form.addEventListener('input', function (e) {
      var v = num(e.target);
      e.target.value = v ? v.toLocaleString('ko-KR') : '';
      calc();
    });
    form.addEventListener('submit', function (e) { e.preventDefault(); });
    dues.querySelector('.dues-fill').addEventListener('click', function () {
      var f = form.elements;
      f.base.value = '2,800,000'; f.allow.value = '200,000'; f.bonus.value = '4,800,000';
      calc();
      f.base.focus();
    });
    var openCalc = function () {
      if (location.hash === '#dues-calculator' || location.hash === '#dues') {
        var d = document.getElementById('dues');
        if (d) { d.open = true; dues.scrollIntoView({ block: 'start' }); }
      }
    };
    openCalc();
    window.addEventListener('hashchange', openCalc);
  }
})();
