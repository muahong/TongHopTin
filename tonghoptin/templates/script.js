// TongHopTin - Interactive digest controls

(function() {
  'use strict';

  var CARDS_PER_PAGE = 50;
  var visibleCount = CARDS_PER_PAGE;
  var activeSource = 'all';
  var activeTopic = 'all';
  var activeSort = 'score'; // 'score' or 'time'

  // Parse article data JSON once
  var articlesData = {};
  var dataEl = document.getElementById('articles-data');
  if (dataEl) {
    try { articlesData = JSON.parse(dataEl.textContent); } catch(e) {}
  }

  // ========== Theme Toggle ==========

  var themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) {
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    var saved = localStorage.getItem('tht-theme');
    if (saved) {
      document.documentElement.setAttribute('data-theme', saved);
    } else if (prefersDark) {
      document.documentElement.setAttribute('data-theme', 'dark');
    }

    themeBtn.addEventListener('click', function() {
      var current = document.documentElement.getAttribute('data-theme');
      var next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('tht-theme', next);
      themeBtn.textContent = next === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19';
    });
  }

  // ========== Search ==========

  var searchBox = document.getElementById('search-box');
  if (searchBox) {
    var debounceTimer;
    searchBox.addEventListener('input', function() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function() {
        visibleCount = CARDS_PER_PAGE;
        applyFilters();
      }, 300);
    });
  }

  // ========== Source Filter Pills ==========

  document.querySelectorAll('.filter-source').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var source = this.getAttribute('data-source');
      activeSource = source;
      document.querySelectorAll('.filter-source').forEach(function(b) { b.classList.remove('active'); });
      this.classList.add('active');
      visibleCount = CARDS_PER_PAGE;
      applyFilters();
    });
  });

  // ========== Topic Filter Pills ==========

  document.querySelectorAll('.filter-topic').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var topic = this.getAttribute('data-topic');
      activeTopic = topic;
      document.querySelectorAll('.filter-topic').forEach(function(b) { b.classList.remove('active'); });
      this.classList.add('active');
      visibleCount = CARDS_PER_PAGE;
      applyFilters();
    });
  });

  // ========== Sort Toggle ==========

  var cardGrid = document.getElementById('card-grid');

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
    if (!cardGrid) return;
    var cards = Array.from(cardGrid.querySelectorAll('.article-card'));
    cards.sort(function(a, b) {
      if (activeSort === 'score') {
        var sa = parseFloat(a.getAttribute('data-score') || '0');
        var sb = parseFloat(b.getAttribute('data-score') || '0');
        if (sb !== sa) return sb - sa;
        // Tie-break by time
        return (b.getAttribute('data-time') || '').localeCompare(a.getAttribute('data-time') || '');
      } else {
        // Sort by time descending
        return (b.getAttribute('data-time') || '').localeCompare(a.getAttribute('data-time') || '');
      }
    });
    cards.forEach(function(card) { cardGrid.appendChild(card); });
  }

  // ========== Reading Modal ==========

  var modal = document.getElementById('article-modal');
  var modalHero = document.getElementById('modal-hero');
  var modalMeta = document.getElementById('modal-meta');
  var modalTitleText = document.getElementById('modal-title-text');
  var modalExternalLink = document.getElementById('modal-external-link');
  var modalTags = document.getElementById('modal-tags');
  var modalBody = document.getElementById('modal-body');
  var modalFooter = document.getElementById('modal-footer');
  var modalCloseBtn = document.getElementById('modal-close');

  function openModal(articleId) {
    var data = articlesData[articleId];
    if (!data || !modal) return;

    if (data.hero_image_path) {
      modalHero.innerHTML = '<img src="' + data.hero_image_path + '" alt="">';
    } else {
      modalHero.innerHTML = '';
    }

    var metaParts = [data.source_category, data.published_date, data.reading_time + ' ph\u00FAt \u0111\u1ECDc'];
    modalMeta.innerHTML = metaParts.join(' <span class="meta-dot"></span> ');

    modalTitleText.textContent = data.title;
    modalExternalLink.href = data.url;

    modalTags.innerHTML = data.topics.map(function(t) {
      return '<span class="tag" data-topic="' + t + '">' + t + '</span>';
    }).join('');

    modalBody.innerHTML = data.content_html;

    if (data.author) {
      modalFooter.innerHTML = 'T\u00E1c gi\u1EA3: ' + data.author;
    } else {
      modalFooter.innerHTML = '';
    }

    modal.style.display = 'block';
    modal.offsetHeight;
    modal.classList.add('visible');
    document.body.classList.add('modal-open');
    modal.scrollTop = 0;
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.remove('visible');
    document.body.classList.remove('modal-open');
    setTimeout(function() {
      if (!modal.classList.contains('visible')) {
        modal.style.display = 'none';
      }
    }, 250);
  }

  // Open modal on card clickable areas
  document.addEventListener('click', function(e) {
    var clickable = e.target.closest('.card-clickable');
    if (clickable) {
      var articleId = clickable.getAttribute('data-article-id');
      if (articleId) {
        e.preventDefault();
        openModal(articleId);
      }
    }
  });

  if (modalCloseBtn) {
    modalCloseBtn.addEventListener('click', closeModal);
  }

  if (modal) {
    modal.addEventListener('click', function(e) {
      if (e.target === modal) closeModal();
    });
  }

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && modal && modal.classList.contains('visible')) {
      closeModal();
    }
  });

  // ========== Load More ==========

  var loadMoreBtn = document.getElementById('load-more');
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', function() {
      visibleCount += CARDS_PER_PAGE;
      applyFilters();
    });
  }

  // ========== Filter Application ==========

  function applyFilters() {
    var query = (searchBox ? searchBox.value : '').toLowerCase().trim();
    var cards = document.querySelectorAll('.article-card');
    var shown = 0;
    var totalMatched = 0;

    cards.forEach(function(card) {
      var source = card.getAttribute('data-source');
      var topics = card.getAttribute('data-topics') || '';
      var text = card.getAttribute('data-searchtext') || '';

      var match = true;

      // Source filter
      if (activeSource !== 'all' && source !== activeSource) match = false;

      // Topic filter
      if (activeTopic !== 'all' && topics.indexOf(activeTopic) === -1) match = false;

      // Search
      if (query && text.indexOf(query) === -1) match = false;

      if (match) {
        totalMatched++;
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
      loadMoreBtn.style.display = totalMatched > visibleCount ? '' : 'none';
      loadMoreBtn.textContent = 'Hi\u1EC3n th\u00EAm (' + (totalMatched - shown) + ' b\u00E0i c\u00F2n l\u1EA1i)';
    }
  }

  // Initial filter
  applyFilters();

  // ========== Back to Top ==========

  var backToTop = document.getElementById('back-to-top');
  if (backToTop) {
    window.addEventListener('scroll', function() {
      if (window.scrollY > 300) {
        backToTop.classList.add('visible');
      } else {
        backToTop.classList.remove('visible');
      }
    });

    backToTop.addEventListener('click', function() {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

})();
