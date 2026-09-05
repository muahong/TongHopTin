"""Browser regression for the source-traceable editorial tree, local or live."""
import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright

URL=os.environ.get('NEWS_MAP_URL','http://127.0.0.1:8766/docs/index.html')
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(URL.split('#')[0])
    assert page.locator('#overview-view').is_visible()
    assert page.locator('#news-view').is_hidden()
    assert page.locator('#tab-overview').get_attribute('aria-pressed')=='true'
    source_ids=page.evaluate('Object.keys(JSON.parse(document.getElementById("articles-data").textContent)).sort()')
    represented=page.locator('.edition-story').evaluate_all('(nodes)=>nodes.flatMap(n=>JSON.parse(n.dataset.articles)).sort()')
    assert represented==source_ids
    count=page.locator('.edition-story').count()
    assert count<len(source_ids), 'Expected a genuinely edited, grouped edition'
    assert page.evaluate('Object.keys(JSON.parse(document.getElementById("overview-data").textContent).editorial).length>0')
    assert page.locator('.topic-directory a').count()==11
    assert page.locator('.cluster-paging').count()==0
    page.screenshot(path='.audit/tree-desktop.png')
    first=page.locator('.edition-title').first
    first.scroll_into_view_if_needed()
    before=page.evaluate('scrollY')
    first.click()
    assert page.locator('.editorial-disclosure').is_visible()
    assert page.locator('.paragraph-sources button').count()>0
    assert page.locator('.edition-sources button').count()>0
    title=page.locator('#modal-title-text').inner_text() if page.locator('#modal-title-text').count() else page.locator('.modal-title-text').inner_text()
    page.wait_for_timeout(300)
    page.screenshot(path='.audit/tree-reader.png')
    page.locator('.edition-sources button').first.click()
    page.wait_for_function('document.getElementById("modal-body").textContent.length>100 && !document.querySelector(".modal-loading")')
    page.locator('.edition-return').click()
    assert page.locator('.editorial-disclosure').is_visible()
    page.keyboard.press('Escape');page.wait_for_timeout(300)
    assert page.locator('#article-modal').is_hidden()
    assert abs(page.evaluate('scrollY')-before)<2
    assert first.evaluate('(n)=>n===document.activeElement')
    first.click();page.locator('#modal-close').click();page.wait_for_timeout(300)
    assert abs(page.evaluate('scrollY')-before)<2
    page.locator('#overview-density').click()
    assert page.locator('#topic-tree').evaluate('(n)=>n.classList.contains("compact")')
    assert page.locator('.edition-story').count()==count
    page.locator('#overview-density').click()
    page.locator('#overview-search').fill('zzzz-no-such-story-999')
    assert page.locator('.edition-story').count()==0
    page.locator('#overview-search').fill('')
    assert page.locator('.edition-story').count()==count
    page.locator('.topic-directory a[href="#branch-economy"]').click()
    assert page.locator('#branch-economy h3').evaluate('(n)=>n===document.activeElement')
    page.locator('#tab-news').click();assert page.locator('#news-view').is_visible()
    page.locator('#tab-overview').click();assert page.locator('.edition-story').count()==count
    phone=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    phone.on('pageerror',lambda e:errors.append(str(e)));phone.goto(URL.split('#')[0])
    assert phone.locator('#overview-view').is_visible()
    assert phone.evaluate('document.documentElement.scrollWidth<=innerWidth')
    phone.screenshot(path='.audit/tree-mobile.png')
    first=phone.locator('.edition-title').first;first.scroll_into_view_if_needed();before=phone.evaluate('scrollY');first.click()
    phone.locator('#modal-close-fixed').click();phone.wait_for_timeout(300)
    assert phone.locator('#article-modal').is_hidden()
    assert abs(phone.evaluate('scrollY')-before)<2
    # Explicit source deep link still opens the original reader.
    page.goto(URL.split('#')[0]+'#news');assert page.locator('#news-view').is_visible()
    assert not errors,errors
    result={'url':URL,'source_articles':len(source_ids),'editorial_stories':count,'all_sources_represented_once':True,'overview_default':True,'source_deep_link':True,'source_traceback':True,'esc_and_exit_restore_position':True,'mobile_exit':True,'search':True,'compact_keeps_all_stories':True,'mobile_no_overflow':True,'js_errors':errors}
    Path('.audit/tree-browser-result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result));browser.close()
