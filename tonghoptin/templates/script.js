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
    modalExternalLink.hidden = !!m.editorial;

    modalTags.innerHTML = (m.topics || []).map(function(t) {
      return '<span class="tag">' + escapeHtml(t) + '</span>';
    }).join('');

    modalFooter.innerHTML = m.author ? 'Tác giả: ' + escapeHtml(m.author) : '';
    if (m.editionParent && !m.editorial) modalFooter.innerHTML += '<p><button class="edition-return" data-open="' + escapeHtml(m.editionParent) + '">← Trở lại bản tổng hợp</button></p>';

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
        navigator.share({ title: m.title, url: new URL(m.url, location.href).href }).catch(function() {});
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(new URL(m.url, location.href).href).then(function() {
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

  // Editorial tree: one source-traceable story per event/thread, all on one page.
  var overviewEl = document.getElementById('overview-data');
  if (overviewEl) {
    var overview = JSON.parse(overviewEl.textContent);
    var datePicker = document.getElementById('overview-date');
    var tree = document.getElementById('topic-tree'), directory = document.getElementById('map-categories');
    var search = document.getElementById('overview-search');
    var initialized = false, editionOrder = [], overviewScroll = 0, sourceScroll = 0;
    Object.keys(overview.days).forEach(function(day) {
      var option = document.createElement('option'); option.value = day; option.textContent = day; datePicker.appendChild(option);
    });
    function registerStory(story, category) {
      if (!story.paragraphs) return story.articles[0];
      var id = story.id;
      meta[id] = {title:story.title,source:'Tổng hợp từ ' + story.articles.length + ' bài gốc',category:category.name,date:escapeHtml(datePicker.value),rt:Math.max(1,Math.ceil(story.paragraphs.map(function(p){return p.text;}).join(' ').length/1000)),topics:[],img:'',url:'#overview',editorial:true};
      var html = '<p class="editorial-disclosure">Bản tin được biên tập tự động từ các nguồn bên dưới. Bạn có thể mở từng bài để đối chiếu.</p>';
      story.paragraphs.forEach(function(p) {
        html += '<p>' + escapeHtml(p.text) + '</p><div class="paragraph-sources">';
        p.sources.forEach(function(sourceId) { html += '<button data-open="' + escapeHtml(sourceId) + '">' + escapeHtml((meta[sourceId] || {}).source || 'Nguồn') + ' [' + (story.articles.indexOf(sourceId)+1) + ']</button>'; });
        html += '</div>';
      });
      html += '<h3>Bài gốc để đối chiếu</h3><ol class="edition-sources">';
      story.articles.forEach(function(sourceId) {
        var source = meta[sourceId]; if (!source) return;
        source.editionParent = id;
        html += '<li><button data-open="' + escapeHtml(sourceId) + '">' + escapeHtml(source.title) + '</button><small>' + escapeHtml(source.source) + ' · ' + escapeHtml(source.date) + '</small></li>';
      });
      contentCache[id] = html + '</ol>';
      return id;
    }
    function renderTree() {
      var groups = overview.days[datePicker.value] || {}, query = search.value.trim().toLocaleLowerCase('vi');
      var edited = (overview.editorial || {})[datePicker.value];
      var total = 0, storyCount = 0, matched = 0; editionOrder = [];
      tree.replaceChildren(); directory.replaceChildren();
      overview.categories.forEach(function(category,index) {
        var all = groups[category.id] || []; total += all.reduce(function(n,s){return n+s.articles.length;},0); storyCount += all.length;
        var stories = all.filter(function(s){return (s.title+' '+s.brief+' '+s.articles.map(function(id){return (meta[id] || {}).source || '';}).join(' ')).toLocaleLowerCase('vi').includes(query);});
        var link = document.createElement('a'); link.href = '#branch-' + category.id; link.style.setProperty('--branch-hue',index*31);
        var name = document.createElement('strong'); name.textContent = category.name;
        var count = document.createElement('span'); count.textContent = stories.length + ' câu chuyện';
        var categoryBrief = edited && (edited.category_briefs || []).find(function(b){return b.category===category.id;});
        var description = document.createElement('small'); description.textContent = categoryBrief ? categoryBrief.text : category.description;
        link.append(name,count,description); directory.appendChild(link);
        link.addEventListener('click',function(e){e.preventDefault();var branch=document.getElementById('branch-'+category.id);if(branch){branch.scrollIntoView({behavior:'instant',block:'start'});branch.querySelector('h3').focus({preventScroll:true});}});
        if (!stories.length) return;
        var branch = document.createElement('section'); branch.className = 'topic-branch'; branch.id = 'branch-' + category.id; branch.dataset.category = category.id; branch.style.setProperty('--branch-hue',index*31);
        var heading = document.createElement('h3'); heading.tabIndex=-1; heading.textContent = category.name;
        var subtitle = document.createElement('p'); subtitle.className='branch-description'; subtitle.textContent=category.description+' · '+stories.length+' câu chuyện';
        branch.append(heading,subtitle);
        var list = document.createElement('div');list.className='branch-stories';
        stories.forEach(function(story){
          var id = registerStory(story,category);editionOrder.push(id);matched++;
          var card = document.createElement('article');card.className='edition-story';card.dataset.storyId=id;card.dataset.articles=JSON.stringify(story.articles);
          var title = document.createElement('button');title.className='edition-title';title.textContent=story.title;title.dataset.open=id;
          var brief = document.createElement('p');brief.className='edition-brief';brief.textContent=story.brief;
          var source = document.createElement('button');source.className='edition-attribution';source.dataset.open=id;
          var names=Array.from(new Set(story.articles.map(function(sid){return (meta[sid] || {}).source || 'Nguồn';})));
          source.textContent=(story.paragraphs?'Đọc bản tổng hợp':'Đọc bài')+' ↗ · '+story.articles.length+' bài · '+names.join(', ');
          card.append(title,brief,source);
          if(!story.paragraphs && story.articles.length>1){var refs=document.createElement('div');refs.className='paragraph-sources';story.articles.forEach(function(sid){var button=document.createElement('button');button.dataset.open=sid;button.textContent=(meta[sid] || {}).source || 'Nguồn';refs.appendChild(button);});card.appendChild(refs);}
          list.appendChild(card);
        });
        branch.appendChild(list);tree.appendChild(branch);
      });
      document.getElementById('edition-note').textContent=edited?(edited.day_brief ? edited.day_brief.text : 'Tin cùng sự kiện được gộp lại, viết ngắn gọn và dẫn nguồn để bạn đối chiếu.'):'Ngày này chưa có bản biên tập; đang hiển thị trích đoạn từ các bài đã thu thập.';
      document.getElementById('edition-stats').textContent=total+' bài gốc → '+storyCount+' câu chuyện · '+overview.categories.length+' lĩnh vực';
      document.getElementById('map-result').textContent=matched+' câu chuyện'+(query?' phù hợp với từ khóa':' trên cùng một trang')+'. Chọn một câu chuyện để đọc và xem các nguồn liên quan.';
      currentOrder=editionOrder.slice();
    }
    function showView(isOverview) {
      var wasOverview=!document.getElementById('overview-view').hidden;
      if(initialized){if(wasOverview) overviewScroll=window.scrollY;else sourceScroll=window.scrollY;}
      document.getElementById('news-view').hidden=isOverview;document.getElementById('overview-view').hidden=!isOverview;
      ['news','overview'].forEach(function(name){var active=(name==='overview')===isOverview;var button=document.getElementById('tab-'+name);button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
      if(isOverview){if(!initialized){renderTree();initialized=true;}currentOrder=editionOrder.slice();}else applyFilters();
      window.scrollTo({top:isOverview?overviewScroll:sourceScroll,behavior:'instant'});
      try{history.replaceState(null,'',isOverview?'#overview':'#news');}catch(e){}
    }
    document.getElementById('tab-news').addEventListener('click',function(){showView(false);});
    document.getElementById('tab-overview').addEventListener('click',function(){showView(true);});
    datePicker.addEventListener('change',renderTree);search.addEventListener('input',renderTree);
    document.getElementById('overview-density').addEventListener('click',function(){var compact=tree.classList.toggle('compact');this.setAttribute('aria-pressed',String(compact));this.textContent=compact?'Hiện tóm tắt':'Chỉ tiêu đề';});
    document.getElementById('overview-top').addEventListener('click',function(){directory.scrollIntoView({behavior:'instant',block:'start'});});
    window.addEventListener('hashchange',function(){showView(location.hash!=='#news');});
    queueMicrotask(function(){showView(location.hash!=='#news');});
  }


  // Initial pass
  applyFilters();

})();
