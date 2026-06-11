// Thông Tin Là Sức Mạnh! — interactive digest
(function() {
  'use strict';

  var CARDS_PER_PAGE = 48;
  var visibleCount = CARDS_PER_PAGE;
  var activeSource = 'all';
  var activeTopic = 'all';
  var activeSort = 'score'; // 'score' | 'time' | 'unread'

  // ---------- Article metadata ----------
  var meta = {};
  var dataEl = document.getElementById('articles-data');
  if (dataEl) {
    try { meta = JSON.parse(dataEl.textContent); } catch (e) {}
  }

  // ---------- Read tracking (localStorage) ----------
  var readSet = new Set();
  try {
    var stored = JSON.parse(localStorage.getItem('ttsm-read') || '[]');
    if (Array.isArray(stored)) stored.forEach(function(id) { readSet.add(id); });
  } catch (e) {}

  function persistRead() {
    try {
      var arr = Array.from(readSet);
      if (arr.length > 3000) arr = arr.slice(arr.length - 3000);
      localStorage.setItem('ttsm-read', JSON.stringify(arr));
    } catch (e) {}
  }

  // ---------- Collect cards + search index ----------
  var cardGrid = document.getElementById('card-grid');
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var searchIndex = {}; // id -> lowercase searchable text

  cards.forEach(function(card) {
    var id = card.getAttribute('data-id');
    var m = meta[id] || {};
    var previewEl = card.querySelector('.card-preview');
    searchIndex[id] = ((m.title || '') + ' ' + (m.source || '') + ' ' +
      (m.category || '') + ' ' + (m.topics || []).join(' ') + ' ' +
      (previewEl ? previewEl.textContent : '')).toLowerCase();
    if (readSet.has(id)) card.classList.add('read');
  });

  // ---------- Theme toggle ----------
  var themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) {
    themeBtn.addEventListener('click', function() {
      var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      var next = isDark ? 'light' : 'dark';
      if (next === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
      } else {
        document.documentElement.removeAttribute('data-theme');
      }
      try { localStorage.setItem('ttsm-theme', next); } catch (e) {}
    });
  }

  // ---------- Toast ----------
  var toastEl = document.getElementById('toast');
  var toastTimer;
  function toast(msg) {
    if (!toastEl) return;
    toastEl.textContent = msg;
    toastEl.classList.add('visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function() { toastEl.classList.remove('visible'); }, 2200);
  }

  // ---------- Search ----------
  var searchBox = document.getElementById('search-box');
  if (searchBox) {
    var debounceTimer;
    searchBox.addEventListener('input', function() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function() {
        visibleCount = CARDS_PER_PAGE;
        applyFilters();
      }, 250);
    });
  }

  // ---------- Filter chips ----------
  function bindChips(selector, attr, onPick) {
    document.querySelectorAll(selector).forEach(function(btn) {
      btn.addEventListener('click', function() {
        document.querySelectorAll(selector).forEach(function(b) { b.classList.remove('active'); });
        this.classList.add('active');
        onPick(this.getAttribute(attr));
        visibleCount = CARDS_PER_PAGE;
        applyFilters();
      });
    });
  }

  bindChips('.filter-source', 'data-source', function(v) { activeSource = v; });
  bindChips('.filter-topic', 'data-topic', function(v) { activeTopic = v; });

  // Topic tags inside cards also set the topic filter
  document.addEventListener('click', function(e) {
    var tag = e.target.closest('.tag[data-topic]');
    if (!tag || tag.closest('.modal-backdrop')) return;
    var topic = tag.getAttribute('data-topic');
    document.querySelectorAll('.filter-topic').forEach(function(b) {
      b.classList.toggle('active', b.getAttribute('data-topic') === topic);
    });
    activeTopic = topic;
    visibleCount = CARDS_PER_PAGE;
    applyFilters();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  // ---------- Sort ----------
  document.querySelectorAll('.sort-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      activeSort = this.getAttribute('data-sort');
      document.querySelectorAll('.sort-btn').forEach(function(b) { b.classList.remove('active'); });
      this.classList.add('active');
      sortCards();
      visibleCount = CARDS_PER_PAGE;
      applyFilters();
    });
  });

  function sortCards() {
    var byTime = function(a, b) {
      return (b.getAttribute('data-time') || '').localeCompare(a.getAttribute('data-time') || '');
    };
    var sorted = cards.slice().sort(function(a, b) {
      if (activeSort === 'score') {
        var sa = parseFloat(a.getAttribute('data-score') || '0');
        var sb = parseFloat(b.getAttribute('data-score') || '0');
        if (sb !== sa) return sb - sa;
      }
      return byTime(a, b);
    });
    var frag = document.createDocumentFragment();
    sorted.forEach(function(card) { frag.appendChild(card); });
    cardGrid.appendChild(frag);
    cards = sorted;
  }

  // ---------- Filtering ----------
  var loadMoreBtn = document.getElementById('load-more');
  var resultCount = document.getElementById('result-count');
  var currentOrder = []; // ids of cards passing the filter, in display order

  function applyFilters() {
    var query = (searchBox ? searchBox.value : '').toLowerCase().trim();
    var shown = 0;
    var totalMatched = 0;
    currentOrder = [];

    cards.forEach(function(card) {
      var id = card.getAttribute('data-id');
      var match = true;

      if (activeSource !== 'all' && card.getAttribute('data-source') !== activeSource) match = false;
      if (match && activeTopic !== 'all') {
        var topics = card.getAttribute('data-topics') || '';
        if (topics.split(',').indexOf(activeTopic) === -1) match = false;
      }
      if (match && activeSort === 'unread' && readSet.has(id)) match = false;
      if (match && query && (searchIndex[id] || '').indexOf(query) === -1) match = false;

      if (match) {
        totalMatched++;
        currentOrder.push(id);
        if (shown < visibleCount) {
          card.classList.remove('hidden');
          shown++;
        } else {
          card.classList.add('hidden');
        }
      } else {
        card.classList.add('hidden');
      }
    });

    if (loadMoreBtn) {
      var remaining = totalMatched - shown;
      loadMoreBtn.style.display = remaining > 0 ? '' : 'none';
      loadMoreBtn.textContent = 'Hiển thị thêm (' + remaining + ' bài)';
    }
    if (resultCount) {
      resultCount.textContent = totalMatched === cards.length
        ? ''
        : totalMatched + ' / ' + cards.length + ' bài';
    }
  }

  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', function() {
      visibleCount += CARDS_PER_PAGE;
      applyFilters();
    });
  }

  // Infinite scroll: auto-expand when the sentinel becomes visible
  var sentinel = document.getElementById('scroll-sentinel');
  if (sentinel && 'IntersectionObserver' in window) {
    new IntersectionObserver(function(entries) {
      if (entries[0].isIntersecting && loadMoreBtn && loadMoreBtn.style.display !== 'none') {
        visibleCount += CARDS_PER_PAGE;
        applyFilters();
      }
    }, { rootMargin: '600px' }).observe(sentinel);
  }

  // ---------- Reading modal ----------
  var modal = document.getElementById('article-modal');
  var modalHero = document.getElementById('modal-hero');
  var modalMeta = document.getElementById('modal-meta');
  var modalTitleText = document.getElementById('modal-title-text');
  var modalExternalLink = document.getElementById('modal-external-link');
  var modalTags = document.getElementById('modal-tags');
  var modalBody = document.getElementById('modal-body');
  var modalFooter = document.getElementById('modal-footer');
  var modalPrev = document.getElementById('modal-prev');
  var modalNext = document.getElementById('modal-next');
  var progressFill = document.getElementById('modal-progress-fill');
  var currentId = null;
  var contentCache = {}; // id -> content_html
  var fetchSeq = 0;

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function renderContent(id, html) {
    modalBody.innerHTML = html;
  }

  function renderFallback(id) {
    var m = meta[id] || {};
    var card = document.querySelector('.card[data-id="' + id + '"]');
    var preview = card ? card.querySelector('.card-preview') : null;
    modalBody.innerHTML =
      '<div class="modal-fallback">' +
      (preview ? '<p>' + escapeHtml(preview.textContent) + '…</p>' : '') +
      '<p>Không tải được nội dung đầy đủ tại đây.</p>' +
      '<a href="' + (m.url || '#') + '" target="_blank" rel="noopener">Đọc bài trên ' + escapeHtml(m.source || 'trang gốc') + ' ↗</a>' +
      '</div>';
  }

  function loadContent(id) {
    var seq = ++fetchSeq;
    if (contentCache[id] !== undefined) {
      renderContent(id, contentCache[id]);
      return;
    }
    modalBody.innerHTML = '<div class="modal-loading"><div class="spinner"></div> Đang tải bài viết…</div>';
    fetch('articles/' + id + '.json')
      .then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function(data) {
        contentCache[id] = data.content_html || '';
        if (seq === fetchSeq && currentId === id) {
          if (contentCache[id]) renderContent(id, contentCache[id]);
          else renderFallback(id);
        }
      })
      .catch(function() {
        if (seq === fetchSeq && currentId === id) renderFallback(id);
      });
  }

  function openModal(id) {
    var m = meta[id];
    if (!m || !modal) return;
    currentId = id;

    modalHero.innerHTML = m.img
      ? '<img src="' + m.img + '" alt="" decoding="async">'
      : '';

    modalMeta.innerHTML =
      '<span class="src">' + escapeHtml(m.source) + '</span>' +
      '<span class="meta-dot"></span><span>' + escapeHtml(m.category) + '</span>' +
      '<span class="meta-dot"></span><span>' + m.date + '</span>' +
      '<span class="meta-dot"></span><span>' + m.rt + ' phút đọc</span>';

    modalTitleText.textContent = m.title;
    modalExternalLink.href = m.url;

    modalTags.innerHTML = (m.topics || []).map(function(t) {
      return '<span class="tag">' + escapeHtml(t) + '</span>';
    }).join('');

    modalFooter.innerHTML = m.author ? 'Tác giả: ' + escapeHtml(m.author) : '';

    loadContent(id);
    updateNavButtons();

    modal.hidden = false;
    void modal.offsetHeight;
    modal.classList.add('visible');
    document.body.classList.add('modal-open');
    modal.scrollTop = 0;
    if (progressFill) progressFill.style.width = '0';

    // Mark as read
    if (!readSet.has(id)) {
      readSet.add(id);
      persistRead();
      var card = document.querySelector('.card[data-id="' + id + '"]');
      if (card) card.classList.add('read');
    }
  }

  function closeModal() {
    if (!modal) return;
    currentId = null;
    modal.classList.remove('visible');
    document.body.classList.remove('modal-open');
    setTimeout(function() {
      if (!modal.classList.contains('visible')) modal.hidden = true;
    }, 230);
  }

  // Prev/next within the current filtered order
  function navOffset(delta) {
    if (!currentId) return;
    var idx = currentOrder.indexOf(currentId);
    if (idx === -1) return;
    var nextIdx = idx + delta;
    if (nextIdx < 0 || nextIdx >= currentOrder.length) return;
    openModal(currentOrder[nextIdx]);
  }

  function updateNavButtons() {
    var idx = currentOrder.indexOf(currentId);
    if (modalPrev) modalPrev.disabled = idx <= 0;
    if (modalNext) modalNext.disabled = idx === -1 || idx >= currentOrder.length - 1;
  }

  if (modalPrev) modalPrev.addEventListener('click', function() { navOffset(-1); });
  if (modalNext) modalNext.addEventListener('click', function() { navOffset(1); });

  // Open on card areas
  document.addEventListener('click', function(e) {
    var openEl = e.target.closest('[data-open]');
    if (openEl) {
      e.preventDefault();
      openModal(openEl.getAttribute('data-open'));
    }
  });

  // Close interactions
  ['modal-close', 'modal-close-fixed', 'modal-swipe-handle'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('click', closeModal);
  });

  if (modal) {
    modal.addEventListener('click', function(e) {
      if (e.target === modal) closeModal();
    });

    // Reading progress
    modal.addEventListener('scroll', function() {
      if (!progressFill) return;
      var max = modal.scrollHeight - modal.clientHeight;
      progressFill.style.width = max > 0 ? (modal.scrollTop / max * 100) + '%' : '0';
    }, { passive: true });

    // Swipe down to close (mobile): only when already scrolled to top
    var touchStartY = null;
    modal.addEventListener('touchstart', function(e) {
      touchStartY = modal.scrollTop <= 0 ? e.touches[0].clientY : null;
    }, { passive: true });
    modal.addEventListener('touchmove', function(e) {
      if (touchStartY === null) return;
      if (e.touches[0].clientY - touchStartY > 90 && modal.scrollTop <= 0) {
        touchStartY = null;
        closeModal();
      }
    }, { passive: true });
  }

  // Keyboard
  document.addEventListener('keydown', function(e) {
    if (!modal || modal.hidden) return;
    if (e.key === 'Escape') closeModal();
    else if (e.key === 'ArrowLeft') navOffset(-1);
    else if (e.key === 'ArrowRight') navOffset(1);
  });

  // ---------- Reader font size ----------
  var READER_MIN = 14, READER_MAX = 24;
  var readerSize = 17;
  try { readerSize = parseInt(localStorage.getItem('ttsm-fontsize'), 10) || 17; } catch (e) {}
  applyReaderSize();

  function applyReaderSize() {
    readerSize = Math.min(READER_MAX, Math.max(READER_MIN, readerSize));
    document.documentElement.style.setProperty('--reader-size', readerSize + 'px');
    try { localStorage.setItem('ttsm-fontsize', String(readerSize)); } catch (e) {}
  }

  var fontMinus = document.getElementById('font-minus');
  var fontPlus = document.getElementById('font-plus');
  if (fontMinus) fontMinus.addEventListener('click', function() { readerSize -= 1; applyReaderSize(); });
  if (fontPlus) fontPlus.addEventListener('click', function() { readerSize += 1; applyReaderSize(); });

  // ---------- Share ----------
  var shareBtn = document.getElementById('modal-share');
  if (shareBtn) {
    shareBtn.addEventListener('click', function() {
      var m = currentId ? meta[currentId] : null;
      if (!m) return;
      if (navigator.share) {
        navigator.share({ title: m.title, url: m.url }).catch(function() {});
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(m.url).then(function() {
          toast('Đã sao chép liên kết');
        }).catch(function() {});
      }
    });
  }

  // ---------- Back to top ----------
  var backToTop = document.getElementById('back-to-top');
  if (backToTop) {
    var ticking = false;
    window.addEventListener('scroll', function() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function() {
        backToTop.classList.toggle('visible', window.scrollY > 600);
        ticking = false;
      });
    }, { passive: true });

    backToTop.addEventListener('click', function() {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  // Initial pass
  applyFilters();

})();
