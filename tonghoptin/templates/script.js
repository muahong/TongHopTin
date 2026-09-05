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
    if (returnFocus) returnFocus.focus({ preventScroll: true });
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

  // Radial news atlas: articles stay on the map; opening the reader never rebuilds it.
  var overviewEl = document.getElementById('overview-data');
  if (overviewEl) {
    var overview = JSON.parse(overviewEl.textContent);
    var datePicker = document.getElementById('overview-date');
    var map = document.getElementById('topic-map'), stage = document.getElementById('map-stage');
    var clusters = document.getElementById('map-clusters'), categoryNav = document.getElementById('map-categories');
    var search = document.getElementById('overview-search');
    var camera = { x: 0, y: 0, zoom: 1 }, initialized = false, pages = {}, positions = {}, mapOrder = [];
    var pointers = new Map(), gesture = null, suppressClick = false;
    var WORLD = 3600, RADIUS = 1450, PAGE_SIZE = 2;
    Object.keys(overview.days).forEach(function(day) {
      var option = document.createElement('option'); option.value = day; option.textContent = day; datePicker.appendChild(option);
    });
    function paintCamera() {
      stage.style.transform = 'translate(' + camera.x + 'px,' + camera.y + 'px) scale(' + camera.zoom + ')';
      map.style.setProperty('--map-scale', camera.zoom);
      map.classList.toggle('map-distant', camera.zoom < 0.48);
      document.getElementById('map-zoom-level').textContent = Math.round(camera.zoom * 100) + '%';
      // DOM data makes camera restoration observable to browser regression checks.
      map.dataset.camera = JSON.stringify(camera);
    }
    function fitMap() {
      camera.zoom = Math.max(0.08, Math.min(map.clientWidth, map.clientHeight) / WORLD);
      camera.x = map.clientWidth / 2; camera.y = map.clientHeight / 2; paintCamera();
    }
    function zoomAt(factor, x, y) {
      var next = Math.max(0.08, Math.min(2.4, camera.zoom * factor));
      var ratio = next / camera.zoom;
      camera.x = x - (x - camera.x) * ratio; camera.y = y - (y - camera.y) * ratio;
      camera.zoom = next; paintCamera();
    }
    function focusCategory(id) {
      var position = positions[id]; if (!position) return;
      camera.zoom = Math.min(1, (map.clientWidth - 32) / 420, (map.clientHeight - 28) / 620);
      camera.x = map.clientWidth / 2 - position.x * camera.zoom;
      camera.y = map.clientHeight / 2 - position.y * camera.zoom; paintCamera();
      categoryNav.querySelectorAll('button').forEach(function(button) { button.setAttribute('aria-pressed', String(button.dataset.category === id)); });
      map.focus({ preventScroll: true });
    }
    function renderMap() {
      var groups = overview.days[datePicker.value] || {}, query = search.value.trim().toLocaleLowerCase('vi');
      var total = 0, matched = 0; currentOrder = [];
      clusters.replaceChildren(); categoryNav.replaceChildren();
      var connections = stage.querySelector('svg'); connections.replaceChildren();
      var ring = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      ring.setAttribute('r', RADIUS); ring.setAttribute('class', 'atlas-ring'); connections.appendChild(ring);
      overview.categories.forEach(function(category, index) {
        var all = groups[category.id] || [];
        total += all.reduce(function(n, story) { return n + story.articles.length; }, 0);
        var stories = all.filter(function(story) { return (story.title + ' ' + story.brief).toLocaleLowerCase('vi').includes(query); });
        matched += stories.length;
        stories.forEach(function(story) { currentOrder = currentOrder.concat(story.articles); });
        var angle = index * Math.PI * 2 / overview.categories.length - Math.PI / 2;
        var x = Math.cos(angle) * RADIUS, y = Math.sin(angle) * RADIUS; positions[category.id] = { x:x, y:y };
        var chip = document.createElement('button'); chip.textContent = category.name + ' · ' + stories.length; chip.dataset.category = category.id; chip.setAttribute('aria-pressed','false');
        chip.addEventListener('click', function() { focusCategory(category.id); }); categoryNav.appendChild(chip);
        var line = document.createElementNS('http://www.w3.org/2000/svg', 'line'); line.setAttribute('x1', Math.cos(angle)*180); line.setAttribute('y1', Math.sin(angle)*180); line.setAttribute('x2',x); line.setAttribute('y2',y); connections.appendChild(line);
        var cluster = document.createElement('section'); cluster.className = 'news-cluster'; cluster.dataset.category = category.id; cluster.style.left = x + 'px'; cluster.style.top = y + 'px'; cluster.style.setProperty('--cluster-hue', String(index * 31));
        var header = document.createElement('button'); header.className = 'cluster-heading'; header.textContent = category.name; header.setAttribute('aria-label','Đọc gần: ' + category.name); header.addEventListener('click',function() { focusCategory(category.id); }); cluster.appendChild(header);
        var count = document.createElement('p'); count.className = 'cluster-count'; count.textContent = stories.length + ' tin · ' + category.description; cluster.appendChild(count);
        var pageCount = Math.max(1, Math.ceil(stories.length / PAGE_SIZE));
        var page = Math.min(pages[category.id] || 0, pageCount - 1); pages[category.id] = page;
        var list = document.createElement('div'); list.className = 'cluster-stories';
        stories.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).forEach(function(story) {
          var article = document.createElement('article'); article.className = 'map-story';
          var title = document.createElement('button'); title.className = 'map-story-title'; title.textContent = story.title; title.dataset.open = story.articles[0];
          var brief = document.createElement('button'); brief.className = 'map-story-brief'; brief.textContent = story.brief; brief.dataset.open = story.articles[0]; brief.setAttribute('aria-label','Đọc bài: ' + story.title);
          var sources = document.createElement('div'); sources.className = 'map-story-sources';
          var time = document.createElement('time'); time.textContent = story.time; sources.appendChild(time);
          story.articles.forEach(function(id) { var button = document.createElement('button'); button.textContent = (meta[id] || {}).source || 'Đọc bài'; button.dataset.open = id; sources.appendChild(button); });
          article.append(title,brief,sources); list.appendChild(article);
        });
        if (!stories.length) { var empty=document.createElement('p'); empty.className='cluster-empty'; empty.textContent='Chưa có tin phù hợp.'; list.appendChild(empty); }
        cluster.appendChild(list);
        var paging = document.createElement('div'); paging.className = 'cluster-paging';
        var previous = document.createElement('button'); previous.textContent = '←'; previous.setAttribute('aria-label','Tin trước trong ' + category.name); previous.disabled = page === 0;
        var next = document.createElement('button'); next.textContent = '→'; next.setAttribute('aria-label','Tin tiếp trong ' + category.name); next.disabled = page + 1 >= pageCount;
        var label = document.createElement('span'); label.textContent = (page + 1) + ' / ' + pageCount;
        function changePage(delta) { pages[category.id] = page + delta; renderMap(); var replacement = clusters.querySelector('[data-category="'+category.id+'"] .cluster-paging button' + (delta > 0 ? ':last-child' : ':first-child')); if (replacement) replacement.focus({preventScroll:true}); }
        previous.addEventListener('click',function() { changePage(-1); }); next.addEventListener('click',function() { changePage(1); });
        paging.append(previous,label,next); cluster.appendChild(paging); clusters.appendChild(cluster);
      });
      document.getElementById('overview-total').textContent = total + ' bài'; document.getElementById('overview-day').textContent = datePicker.value || 'Chưa có dữ liệu';
      mapOrder = currentOrder.slice();
      document.getElementById('map-result').textContent = matched + ' tin theo chủ đề. Mỗi lĩnh vực hiển thị 2 tin mỗi trang; dùng ← → ngay trên bản đồ để đọc các tin còn lại.';
    }
    function showView(isOverview) {
      document.getElementById('news-view').hidden = isOverview; document.getElementById('overview-view').hidden = !isOverview;
      ['news','overview'].forEach(function(name) { var active = (name === 'overview') === isOverview; var button=document.getElementById('tab-'+name); button.classList.toggle('active',active); button.setAttribute('aria-pressed',String(active)); });
      if (isOverview && !initialized) { renderMap(); fitMap(); initialized = true; } else if (!isOverview) applyFilters();
      if (isOverview) currentOrder = mapOrder.slice();
      try { history.replaceState(null,'',isOverview ? '#overview' : '#news'); } catch(e) {}
    }
    document.getElementById('tab-news').addEventListener('click',function() { showView(false); });
    document.getElementById('tab-overview').addEventListener('click',function() { showView(true); });
    document.getElementById('map-zoom-in').addEventListener('click',function() { zoomAt(1.4,map.clientWidth/2,map.clientHeight/2); });
    document.getElementById('map-zoom-out').addEventListener('click',function() { zoomAt(1/1.4,map.clientWidth/2,map.clientHeight/2); });
    document.getElementById('map-fit').addEventListener('click',fitMap);
    datePicker.addEventListener('change',function() { pages={}; renderMap(); fitMap(); });
    search.addEventListener('input',function() { pages={}; renderMap(); });
    map.addEventListener('wheel',function(e) { e.preventDefault(); var rect=map.getBoundingClientRect(); zoomAt(Math.exp(-Math.max(-150,Math.min(150,e.deltaY))*0.003),e.clientX-rect.left,e.clientY-rect.top); },{passive:false});
    function points() { return Array.from(pointers.values()); }
    function beginGesture() { var p=points(); gesture={ camera:{x:camera.x,y:camera.y,zoom:camera.zoom}, points:p.map(function(v){return {x:v.x,y:v.y};}) }; }
    map.addEventListener('pointerdown',function(e) {
      if (e.button !== 0 && e.pointerType === 'mouse') return;
      pointers.set(e.pointerId,{x:e.clientX,y:e.clientY}); beginGesture();
    });
    map.addEventListener('pointermove',function(e) {
      if (!pointers.has(e.pointerId) || !gesture) return;
      pointers.set(e.pointerId,{x:e.clientX,y:e.clientY}); var p=points(), start=gesture.points;
      if (p.length===2 && start.length===2) {
        var distance=Math.hypot(p[1].x-p[0].x,p[1].y-p[0].y), initial=Math.hypot(start[1].x-start[0].x,start[1].y-start[0].y);
        if (initial<5) return;
        var rect=map.getBoundingClientRect(), sx=(start[0].x+start[1].x)/2-rect.left, sy=(start[0].y+start[1].y)/2-rect.top;
        camera.zoom=Math.max(.08,Math.min(2.4,gesture.camera.zoom*distance/initial)); var ratio=camera.zoom/gesture.camera.zoom;
        camera.x=(p[0].x+p[1].x)/2-rect.left-(sx-gesture.camera.x)*ratio; camera.y=(p[0].y+p[1].y)/2-rect.top-(sy-gesture.camera.y)*ratio;
      } else if (p.length===1 && start.length===1) {
        var dx=p[0].x-start[0].x, dy=p[0].y-start[0].y; if (!suppressClick && Math.hypot(dx,dy)<6) return;
        camera.x=gesture.camera.x+dx; camera.y=gesture.camera.y+dy;
      } else return;
      suppressClick=true; map.classList.add('dragging'); map.setPointerCapture(e.pointerId); paintCamera();
    });
    function endPointer(e) { pointers.delete(e.pointerId); if(map.hasPointerCapture(e.pointerId)) map.releasePointerCapture(e.pointerId); map.classList.remove('dragging'); if(pointers.size) beginGesture(); else { gesture=null; setTimeout(function(){suppressClick=false;},0); } }
    window.addEventListener('pointerup',endPointer); window.addEventListener('pointercancel',endPointer);
    map.addEventListener('click',function(e) { if(suppressClick) {e.preventDefault();e.stopImmediatePropagation();} },true);
    map.addEventListener('keydown',function(e) {
      if (e.target!==map || currentId) return;
      if (e.key==='+' || e.key==='=') zoomAt(1.4,map.clientWidth/2,map.clientHeight/2);
      else if(e.key==='-') zoomAt(1/1.4,map.clientWidth/2,map.clientHeight/2);
      else if(e.key==='0') fitMap();
      else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) {camera.x+=e.key==='ArrowLeft'?60:e.key==='ArrowRight'?-60:0;camera.y+=e.key==='ArrowUp'?60:e.key==='ArrowDown'?-60:0;paintCamera();}
      else return; e.preventDefault();
    });
    var previousSize=null;
    new ResizeObserver(function() { var width=map.clientWidth,height=map.clientHeight; if(!width || !height) return; if(previousSize && initialized) {camera.x+=(width-previousSize.width)/2;camera.y+=(height-previousSize.height)/2;paintCamera();} previousSize={width:width,height:height}; }).observe(map);
    if(location.hash==='#overview') queueMicrotask(function(){showView(true);});
  }


  // Initial pass
  applyFilters();

})();
