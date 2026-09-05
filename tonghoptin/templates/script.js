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
  var returnFocus = null;
  var contentCache = {}; // id -> content_html
  var fetchSeq = 0;

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function renderContent(id, html) {
    modalBody.innerHTML = html;
  }

  function finishContentLoad(id, html, seq) {
    contentCache[id] = html || '';
    if (seq === fetchSeq && currentId === id) {
      if (contentCache[id]) renderContent(id, contentCache[id]);
      else renderFallback(id);
    }
  }

  function renderFallback(id) {
    var m = meta[id] || {};
    var card = document.querySelector('.card[data-id="' + id + '"]');
    var preview = card ? card.querySelector('.card-preview') : null;
    modalBody.innerHTML =
      '<div class="modal-fallback">' +
      (preview ? '<p>' + escapeHtml(preview.textContent) + '…</p>' : '') +
      '<p>Không tải được nội dung đầy đủ tại đây.</p>' +
      '<a href="' + escapeHtml(m.url || '#') + '" target="_blank" rel="noopener">Đọc bài trên ' + escapeHtml(m.source || 'trang gốc') + ' ↗</a>' +
      '</div>';
  }

  function loadScriptContent(id, seq) {
    var registry = window.__ttsmArticleContent || {};
    if (registry[id] !== undefined) {
      finishContentLoad(id, registry[id], seq);
      return;
    }

    var script = document.createElement('script');
    var contentPath = (meta[id] || {}).content || ('articles/' + id);
    script.src = contentPath + '.js';
    script.onload = function() {
      var loaded = (window.__ttsmArticleContent || {})[id];
      script.remove();
      if (loaded === undefined) {
        if (seq === fetchSeq && currentId === id) renderFallback(id);
        return;
      }
      finishContentLoad(id, loaded, seq);
    };
    script.onerror = function() {
      script.remove();
      if (seq === fetchSeq && currentId === id) renderFallback(id);
    };
    document.head.appendChild(script);
  }

  function loadContent(id) {
    var seq = ++fetchSeq;
    if (contentCache[id] !== undefined) {
      renderContent(id, contentCache[id]);
      return;
    }
    modalBody.innerHTML = '<div class="modal-loading"><div class="spinner"></div> Đang tải bài viết…</div>';

    // fetch() cannot read adjacent files from a file:// page. A JavaScript
    // sidecar keeps archived HTML files readable when opened directly.
    if (window.location.protocol === 'file:') {
      loadScriptContent(id, seq);
      return;
    }

    var contentPath = (meta[id] || {}).content || ('articles/' + id);
    fetch(contentPath + '.json')
      .then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function(data) {
        finishContentLoad(id, data.content_html || '', seq);
      })
      .catch(function() {
        loadScriptContent(id, seq);
      });
  }

  // Archives created before permanent retention may have lost hero images.
  // Replace broken images with the source placeholder instead of an empty box.
  cards.forEach(function(card) {
    var img = card.querySelector('.card-media > img');
    if (!img) return;
    var replaceImage = function() {
      if (!img.parentNode) return;
      var id = card.getAttribute('data-id');
      var source = (meta[id] || {}).source || '?';
      var placeholder = document.createElement('div');
      placeholder.className = 'card-media-placeholder';
      var initial = document.createElement('span');
      initial.textContent = source.charAt(0);
      placeholder.appendChild(initial);
      img.parentNode.replaceChild(placeholder, img);
    };
    img.addEventListener('error', replaceImage, { once: true });
    if (img.complete && !img.naturalWidth) replaceImage();
  });

  function openModal(id) {
    var m = meta[id];
    if (!m || !modal) return;
    if (!currentId) returnFocus = document.activeElement;
    currentId = id;

    modalHero.innerHTML = m.img
      ? '<img src="' + escapeHtml(m.img) + '" alt="" decoding="async">'
      : '';
    var heroImg = modalHero.querySelector('img');
    if (heroImg) heroImg.addEventListener('error', function() {
      modalHero.innerHTML = '';
    }, { once: true });

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
    document.getElementById('modal-close').focus();
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
    if (returnFocus) returnFocus.focus();
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

  cards.forEach(function(card) { var title = card.querySelector('.card-title'); if (title) { title.tabIndex = 0; title.setAttribute('role', 'button'); title.addEventListener('keydown', function(e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openModal(title.dataset.open); } }); } });

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
    if (e.key === 'Tab') {
      var focusable = Array.from(modal.querySelectorAll('button:not([disabled]),a[href],input,select,[tabindex="0"]')).filter(function(el) { return el.getClientRects().length; });
      var first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
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

  // Daily overview: build only the selected category's visible story list.
  var overviewEl = document.getElementById('overview-data');
  if (overviewEl) {
    var overview = JSON.parse(overviewEl.textContent);
    var datePicker = document.getElementById('overview-date');
    var map = document.getElementById('topic-map');
    var storyList = document.getElementById('overview-stories');
    var storySearch = document.getElementById('overview-search');
    var moreStories = document.getElementById('overview-more');
    var selectedCategory = 'economy', storyLimit = 16;
    Object.keys(overview.days).forEach(function(day) {
      var option = document.createElement('option'); option.value = day; option.textContent = day; datePicker.appendChild(option);
    });
    function showView(isOverview) {
      document.getElementById('news-view').hidden = isOverview;
      document.getElementById('overview-view').hidden = !isOverview;
      ['news', 'overview'].forEach(function(name) {
        var active = (name === 'overview') === isOverview;
        var button = document.getElementById('tab-' + name);
        button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
      });
      if (isOverview) renderOverview();
      else applyFilters();
      try { history.replaceState(null, "", isOverview ? "#overview" : "#news"); } catch (e) {}
    }
    document.getElementById('tab-news').addEventListener('click', function() { showView(false); });
    document.getElementById('tab-overview').addEventListener('click', function() { showView(true); });
    overview.categories.forEach(function(category, index) {
      var angle = index * 2 * Math.PI / overview.categories.length - Math.PI / 2;
      var button = document.createElement('button'); button.className = 'map-node';
      button.style.setProperty('--x', (50 + Math.cos(angle) * 36) + '%');
      button.style.setProperty('--y', (50 + Math.sin(angle) * 39) + '%');
      button.dataset.category = category.id;
      button.addEventListener('click', function() { selectedCategory = category.id; storyLimit = 16; storySearch.value = ''; renderOverview(); });
      map.appendChild(button);
    });
    function renderOverview() {
      var groups = overview.days[datePicker.value] || {}, total = 0;
      overview.categories.forEach(function(category) {
        var stories = groups[category.id] || [];
        var count = stories.reduce(function(n, story) { return n + story.articles.length; }, 0); total += count;
        var button = map.querySelector('[data-category="' + category.id + '"]');
        button.innerHTML = '<span>' + escapeHtml(category.name) + '</span><small>' + count + ' bài · ' + stories.length + ' tin</small>';
        button.setAttribute('aria-pressed', String(category.id === selectedCategory)); button.classList.toggle('empty', count === 0);
      });
      document.getElementById('overview-total').textContent = total + ' bài';
      document.getElementById('overview-day').textContent = datePicker.value || 'Chưa có dữ liệu';
      var category = overview.categories.find(function(c) { return c.id === selectedCategory; });
      document.getElementById('topic-heading').textContent = category.name;
      document.getElementById('topic-description').textContent = category.description;
      var query = storySearch.value.trim().toLocaleLowerCase('vi');
      var stories = (groups[selectedCategory] || []).filter(function(story) { return (story.title + ' ' + story.brief).toLocaleLowerCase('vi').includes(query); });
      currentOrder = stories.reduce(function(ids, story) { return ids.concat(story.articles); }, []);
      storyList.replaceChildren();
      stories.slice(0, storyLimit).forEach(function(story) {
        var item = document.createElement('article'); item.className = 'story';
        var heading = document.createElement('button'); heading.className = 'story-heading'; heading.textContent = story.title; heading.dataset.open = story.articles[0];
        var brief = document.createElement('p'); brief.textContent = story.brief;
        var sources = document.createElement('div'); sources.className = 'story-sources';
        var time = document.createElement('time'); time.textContent = story.time; sources.appendChild(time);
        story.articles.forEach(function(id) { var button = document.createElement('button'); button.dataset.open = id; button.textContent = (meta[id] || {}).source || 'Đọc bài'; sources.appendChild(button); });
        item.append(heading, brief, sources); storyList.appendChild(item);
      });
      if (!stories.length) { var empty = document.createElement('p'); empty.textContent = 'Chưa có tin phù hợp trong lĩnh vực này.'; storyList.appendChild(empty); }
      moreStories.hidden = stories.length <= storyLimit;
    }
    datePicker.addEventListener('change', function() { storyLimit = 16; renderOverview(); });
    storySearch.addEventListener('input', function() { storyLimit = 16; renderOverview(); });
    moreStories.addEventListener('click', function() { storyLimit += 16; renderOverview(); });
    if (location.hash === '#overview') queueMicrotask(function() { showView(true); });
  }

  // Initial pass
  applyFilters();

})();
